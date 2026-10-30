"""D-664: the T0 egress proxy (CONNECT-only, exact allowlist, counts only) and its endpoint parsing."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading

import pytest

from agentprov.cli.live.egress import EgressProxy, allow_pair, endpoint_target


@pytest.fixture
def echo_server():
    """A loopback TCP server that echoes what it receives (the stand-in for an endpoint)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    stop = threading.Event()

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                continue
            with conn:
                while data := conn.recv(65536):
                    conn.sendall(data)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield srv.getsockname()[1]
    stop.set()
    srv.close()


def _request(port: int, head: bytes) -> tuple[socket.socket, bytes]:
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    sock.sendall(head)
    reply = b""
    while b"\r\n\r\n" not in reply:
        chunk = sock.recv(4096)
        if not chunk:
            break
        reply += chunk
    return sock, reply


def test_connect_to_an_allowed_pair_tunnels_bytes_both_ways(echo_server):
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        sock, reply = _request(proxy.port, f"CONNECT 127.0.0.1:{echo_server} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        with sock:
            assert reply.startswith(b"HTTP/1.1 200 ")
            sock.sendall(b"\x16\x03\x01opaque-bytes")
            assert sock.recv(64) == b"\x16\x03\x01opaque-bytes"
        summary = proxy.summary()
    assert summary["kind"] == "connect_proxy"
    assert summary["allow"] == [f"127.0.0.1:{echo_server}"]
    assert summary["tunnels"] == {f"127.0.0.1:{echo_server}": 1}
    assert summary["refused"] == {} and summary["refused_targets_distinct"] == 0


@pytest.mark.parametrize(("head", "status", "kind", "distinct"), [
    (b"CONNECT evil.example:443 HTTP/1.1\r\n\r\n", b"403", "not_allowed", 1),
    (b"GET http://evil.example/ HTTP/1.1\r\n\r\n", b"405", "method", 0),
    (b"CONNECT nonsense\r\n\r\n", b"400", "malformed", 0),
])
def test_everything_else_is_refused_and_counted(echo_server, head, status, kind, distinct):
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        sock, reply = _request(proxy.port, head)
        sock.close()
        summary = proxy.summary()
    assert reply.split(b" ")[1] == status
    assert summary["refused"] == {kind: 1} and summary["tunnels"] == {}
    assert summary["refused_targets_distinct"] == distinct


def test_another_port_of_an_allowed_host_is_refused(echo_server):
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        sock, reply = _request(proxy.port, f"CONNECT 127.0.0.1:{echo_server + 1 if echo_server < 65535 else 1} HTTP/1.1\r\n\r\n".encode())
        sock.close()
    assert reply.startswith(b"HTTP/1.1 403 ")
    assert proxy.summary()["refused"] == {"allowed_host_other_port": 1}


def test_refused_targets_are_counted_never_recorded(echo_server):
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        for i in range(5):
            for _ in range(2):  # the same target twice counts once in the distinct count
                sock, _reply = _request(proxy.port, f"CONNECT h{i}.example:443 HTTP/1.1\r\n\r\n".encode())
                sock.close()
        summary = proxy.summary()
    assert summary["refused"] == {"not_allowed": 10} and summary["refused_targets_distinct"] == 5
    assert not summary["refused_targets_capped"] and "h0.example" not in json.dumps(summary)


def test_a_worker_cannot_smuggle_a_value_through_a_connect_target(echo_server):
    """R1-7 (rebuild-window review): a contained T2 chooses the CONNECT target; a planted key-shaped value must not
    reach the summary (which goes into corpus.json's live block without T0's secret scan). Synthetic key."""
    planted = "sk-proj-" + "A1b2C3d4E5f6G7h8" * 3
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        for target in (f"{planted}:443", f"{planted}.example:443", f"127.0.0.1:{echo_server}{planted}"):
            sock, _reply = _request(proxy.port, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
            sock.close()
        summary = proxy.summary()
    text = json.dumps(summary)
    assert planted not in text and "A1b2C3d4" not in text and "sk-proj" not in text
    assert sum(summary["refused"].values()) == 3


def test_an_oversized_head_is_refused(echo_server):
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        sock, reply = _request(proxy.port, b"CONNECT 127.0.0.1:1 HTTP/1.1\r\nX: " + b"a" * 9000 + b"\r\n\r\n")
        sock.close()
        summary = proxy.summary()
    assert reply.split(b" ")[1] == b"431"
    assert summary["refused"] == {"oversize": 1}


def test_allowlist_and_endpoint_parsing():
    assert allow_pair("API.OpenAI.com.", 443) == ("api.openai.com", 443)
    for host, port in (("a b", 443), ("x.example", 0), ("x.example", 70000), ("", 443)):
        with pytest.raises(ValueError):
            allow_pair(host, port)
    with pytest.raises(ValueError):
        EgressProxy([])
    assert endpoint_target("https://openrouter.ai/api/v1") == ("openrouter.ai", 443, False)
    assert endpoint_target("https://api.example:8443/v1") == ("api.example", 8443, False)
    assert endpoint_target("http://localhost:11434/v1") == ("localhost", 11434, True)
    assert endpoint_target("http://127.0.0.1/v1") == ("127.0.0.1", 80, True)
    for bad in ("http://api.example/v1", "ftp://x.example", "https:///v1"):
        with pytest.raises(ValueError):
            endpoint_target(bad)


@pytest.mark.skipif(sys.platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"), reason="macOS sandbox-exec")
def test_under_the_profile_the_endpoint_is_reachable_only_through_the_proxy(echo_server, tmp_path):
    """The composition D-664 relies on: a T2 child under the real profile reaches the endpoint through a CONNECT tunnel,
    and a direct connection to the same endpoint is denied by the kernel."""
    from agentprov.cli.live.sandbox import wrap_argv

    child = (
        "import socket, sys, json\n"
        "proxy, target = int(sys.argv[1]), int(sys.argv[2])\n"
        "out = {}\n"
        "s = socket.create_connection(('127.0.0.1', proxy), timeout=10)\n"
        "s.sendall(f'CONNECT 127.0.0.1:{target} HTTP/1.1\\r\\n\\r\\n'.encode())\n"
        "head = b''\n"
        "while b'\\r\\n\\r\\n' not in head:\n"
        "    head += s.recv(4096)\n"
        "s.sendall(b'ping'); out['tunnel'] = s.recv(16).decode(); s.close()\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', target), timeout=5).close(); out['direct'] = 'allowed'\n"
        "except PermissionError:\n"
        "    out['direct'] = 'denied'\n"
        "print(json.dumps(out))\n"
    )
    dirs = {n: tmp_path / n for n in ("staging", "t2home", "repo", "home")}
    for d in dirs.values():
        d.mkdir()
    with EgressProxy([("127.0.0.1", echo_server)]) as proxy:
        argv = wrap_argv([sys.executable, "-I", "-B", "-c", child, str(proxy.port), str(echo_server)],
                         staging_root=dirs["staging"], t2home_root=dirs["t2home"], repo=dirs["repo"],
                         home=dirs["home"], egress_port=proxy.port)
        proc = subprocess.run(argv, capture_output=True, timeout=60, check=False, cwd=dirs["staging"],
                              env={"PATH": "/usr/bin:/bin", "HOME": str(dirs["t2home"]), "LANG": "C.UTF-8"})
        summary = proxy.summary()
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")[-2000:]
    assert json.loads(proc.stdout) == {"tunnel": "ping", "direct": "denied"}
    assert summary["tunnels"] == {f"127.0.0.1:{echo_server}": 1}


# ------------------------------------------------------------------------------------------------ LAN forward mode (D-698)
@pytest.fixture
def http_server():
    """A loopback HTTP stand-in for a LAN model server: records each request it receives, answers 200, closes."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    stop = threading.Event()
    seen: list[bytes] = []

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                continue
            with conn:
                conn.settimeout(5)
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                head, _, body = data.partition(b"\r\n\r\n")
                length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                               if line.lower().startswith(b"content-length:")), 0)
                while len(body) < length:
                    body += conn.recv(65536)
                seen.append(head + b"\r\n\r\n" + body)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield srv.getsockname()[1], seen
    stop.set()
    srv.close()


def _exchange(port: int, data: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(data)
        out = b""
        while chunk := sock.recv(65536):
            out += chunk
    return out


def test_the_forward_mode_passes_one_request_to_the_exact_pair(http_server):
    port, seen = http_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (f"POST http://127.0.0.1:{port}/v1/chat/completions?x=1 HTTP/1.1\r\n"
                                       f"Host: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: 7\r\n"
                                       "Proxy-Authorization: Basic c2VjcmV0\r\nConnection: keep-alive\r\n"
                                       "Proxy-Connection: keep-alive\r\n\r\n{\"a\":1}").encode())
        summary = proxy.summary()
    assert reply.startswith(b"HTTP/1.1 200 OK") and reply.endswith(b"ok")
    (got,) = seen
    head, _, body = got.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    assert lines[0] == b"POST /v1/chat/completions?x=1 HTTP/1.1" and body == b'{"a":1}'
    names = [line.split(b":", 1)[0].lower() for line in lines[1:]]
    assert b"proxy-authorization" not in names and b"proxy-connection" not in names
    assert names.count(b"connection") == 1 and b"Connection: close" in lines and b"Content-Type: application/json" in lines
    assert summary["forwards"] == {f"127.0.0.1:{port}": 1} and summary["tunnels"] == {} and summary["refused"] == {}


@pytest.mark.parametrize(("first", "status", "kind"), [
    ("GET http://127.0.0.2:{port}/ HTTP/1.1", b"403", "not_allowed"),
    ("GET http://127.0.0.1:1/ HTTP/1.1", b"403", "allowed_host_other_port"),
    ("GET http://u:p@127.0.0.1:{port}/ HTTP/1.1", b"400", "malformed"),
    ("PUT http://127.0.0.1:{port}/ HTTP/1.1", b"405", "method"),
    ("GET /relative HTTP/1.1", b"405", "method"),
])
def test_the_forward_mode_refuses_everything_else(http_server, first, status, kind):
    port, seen = http_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (first.format(port=port) + "\r\nHost: x\r\n\r\n").encode())
        summary = proxy.summary()
    assert reply.split(b" ")[1] == status and seen == []
    assert summary["refused"] == {kind: 1} and summary["forwards"] == {}


def test_without_a_forward_pair_plain_http_is_refused(http_server):
    port, seen = http_server
    with EgressProxy([("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    assert reply.split(b" ")[1] == b"405" and seen == []
    with pytest.raises(ValueError):
        EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port + 1 if port < 65535 else 1)])


def test_endpoint_target_accepts_a_lan_literal_only_when_allowed():
    assert endpoint_target("http://10.0.0.5:1234/v1", allow_lan=True) == ("10.0.0.5", 1234, False)
    assert endpoint_target("http://192.168.1.20/v1", allow_lan=True) == ("192.168.1.20", 80, False)
    assert endpoint_target("http://[fd00::5]:8080/v1", allow_lan=True) == ("fd00::5", 8080, False)
    assert endpoint_target("https://10.0.0.5/v1", allow_lan=True) == ("10.0.0.5", 443, False)
    for bad in ("http://10.0.0.5:1234/v1", "http://8.8.8.8/v1", "http://lan.local/v1"):
        with pytest.raises(ValueError):
            endpoint_target(bad, allow_lan=bad != "http://10.0.0.5:1234/v1")
    with pytest.raises(ValueError):
        endpoint_target("http://10.0.0.5:1234/v1")  # without --allow-lan-endpoint
    assert allow_pair("[FD00::0005]", 1) == ("fd00::5", 1)


@pytest.mark.skipif(sys.platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"), reason="macOS sandbox-exec")
def test_under_the_profile_a_lan_server_is_reachable_only_through_the_forward_mode(http_server, tmp_path):
    """D-698 with D-664: a T2 child under the real profile reaches the (stand-in) LAN server with an absolute-form
    request through the proxy; its direct connection is denied by the kernel."""
    from agentprov.cli.live.sandbox import wrap_argv

    port, seen = http_server
    child = (
        "import socket, sys, json\n"
        "proxy, target = int(sys.argv[1]), int(sys.argv[2])\n"
        "out = {}\n"
        "s = socket.create_connection(('127.0.0.1', proxy), timeout=10)\n"
        "s.sendall(f'GET http://127.0.0.1:{target}/v1/models HTTP/1.1\\r\\nHost: 127.0.0.1\\r\\n\\r\\n'.encode())\n"
        "data = b''\n"
        "while chunk := s.recv(4096):\n"
        "    data += chunk\n"
        "out['forward'] = data.split(b'\\r\\n', 1)[0].decode(); s.close()\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', target), timeout=5).close(); out['direct'] = 'allowed'\n"
        "except PermissionError:\n"
        "    out['direct'] = 'denied'\n"
        "print(json.dumps(out))\n"
    )
    dirs = {n: tmp_path / n for n in ("staging", "t2home", "repo", "home")}
    for d in dirs.values():
        d.mkdir()
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        argv = wrap_argv([sys.executable, "-I", "-B", "-c", child, str(proxy.port), str(port)],
                         staging_root=dirs["staging"], t2home_root=dirs["t2home"], repo=dirs["repo"],
                         home=dirs["home"], egress_port=proxy.port)
        proc = subprocess.run(argv, capture_output=True, timeout=60, check=False, cwd=dirs["staging"],
                              env={"PATH": "/usr/bin:/bin", "HOME": str(dirs["t2home"]), "LANG": "C.UTF-8"})
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")[-2000:]
    assert json.loads(proc.stdout) == {"forward": "HTTP/1.1 200 OK", "direct": "denied"}
    assert seen and seen[0].startswith(b"GET /v1/models HTTP/1.1")


# ------------------------------------------------------------------------------------------------ allowlist hosts (rebuild-window final re-check nits)
def test_brackets_enclose_an_ipv6_literal_only(echo_server):
    assert allow_pair("[::1]", 443) == ("::1", 443)
    for host in ("[localhost]", "[127.0.0.1]", "[api.example]", "[fd00::5%en0]", "fd00::5%en0"):
        with pytest.raises(ValueError):
            allow_pair(host, 443)
    with EgressProxy([("localhost", echo_server)]) as proxy:  # CONNECT [localhost]:P is not the pair localhost:P
        sock, reply = _request(proxy.port, f"CONNECT [localhost]:{echo_server} HTTP/1.1\r\n\r\n".encode())
        sock.close()
        summary = proxy.summary()
    assert reply.startswith(b"HTTP/1.1 403 ") and summary["refused"] == {"not_allowed": 1} and summary["tunnels"] == {}


def test_ip_literals_are_for_the_lan_path_only():
    """D-698 admits IP literals for a private LAN address with --allow-lan-endpoint; a remote https endpoint is named
    (an IPv4 literal passed the old name pattern by accident, an IPv6 one never did)."""
    for url in ("https://8.8.8.8/v1", "https://[2001:db8::1]/v1", "https://10.0.0.5/v1"):
        with pytest.raises(ValueError):
            endpoint_target(url)
    assert endpoint_target("https://10.0.0.5/v1", allow_lan=True) == ("10.0.0.5", 443, False)
    with pytest.raises(ValueError):
        endpoint_target("https://8.8.8.8/v1", allow_lan=True)
    with pytest.raises(ValueError):  # a zone id fails the LAN check
        endpoint_target("http://[fd00::5%25en0]:8080/v1", allow_lan=True)


# ------------------------------------------------------------------------------------------------ LF-1: one request per head
@pytest.mark.parametrize("head", [
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nX-A: 1\nGET /smuggled HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nX-A: 1\rGET /smuggled HTTP/1.1\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nX-A: a\x00b\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nX A: 1\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nX-A : 1\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\n folded: 1\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nno-colon\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1\x7f HTTP/1.1\r\nHost: x\r\n\r\n",
    b"POST http://127.0.0.1:{port}/v1\nGET HTTP/1.1\r\nHost: x\r\n\r\n",
    b"PO(ST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\n\r\n",
    b"CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: x\nX: y\r\n\r\n",
])
def test_a_head_that_could_carry_a_second_request_is_refused(http_server, head):
    """LF-1 (rebuild-window final re-check): a bare LF in a header line made a lenient server see a second request."""
    port, seen = http_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, head.replace(b"{port}", str(port).encode()))
        summary = proxy.summary()
    assert reply.split(b" ")[1] == b"400" and seen == []
    assert summary["refused"] == {"malformed": 1} and summary["forwards"] == {} and summary["tunnels"] == {}


# ------------------------------------------------------------------------------------------------ LF-2: the forward rules are a boundary
@pytest.fixture
def raw_server():
    """A loopback server that records every byte it receives until the sender is idle for 0.5 s, then answers 200."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    stop = threading.Event()
    seen: list[bytes] = []

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                continue
            with conn:
                conn.settimeout(0.5)
                data = b""
                try:
                    while chunk := conn.recv(65536):
                        data += chunk
                except TimeoutError:
                    pass
                seen.append(data)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield srv.getsockname()[1], seen
    stop.set()
    srv.close()


def test_connect_to_a_forward_pair_is_refused(echo_server):
    with EgressProxy([("127.0.0.1", echo_server)], forward=[("127.0.0.1", echo_server)]) as proxy:
        sock, reply = _request(proxy.port, f"CONNECT 127.0.0.1:{echo_server} HTTP/1.1\r\n\r\n".encode())
        sock.close()
        summary = proxy.summary()
    assert reply.startswith(b"HTTP/1.1 405 ") and summary["refused"] == {"method": 1} and summary["tunnels"] == {}


def test_nothing_after_the_body_is_passed(raw_server):
    port, seen = raw_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (f"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nContent-Length: 7\r\n\r\n"
                                       '{"a":1}GET /second HTTP/1.1\r\nHost: x\r\n\r\n').encode())
        summary = proxy.summary()
    assert reply.startswith(b"HTTP/1.1 200 OK")
    (got,) = seen
    head, _, body = got.partition(b"\r\n\r\n")
    assert body == b'{"a":1}' and b"/second" not in got and head.startswith(b"POST /v1 HTTP/1.1")
    assert summary["forwards"] == {f"127.0.0.1:{port}": 1}


def test_a_get_without_a_length_passes_no_body(raw_server):
    port, seen = raw_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        _exchange(proxy.port, f"GET http://127.0.0.1:{port}/v1/models HTTP/1.1\r\nHost: x\r\n\r\nGET /second HTTP/1.1\r\n\r\n".encode())
    (got,) = seen
    assert got.endswith(b"Connection: close\r\n\r\n") and b"/second" not in got


@pytest.mark.parametrize("framing", [
    "Transfer-Encoding: chunked\r\n", "Content-Length: 7\r\nContent-Length: 7\r\n", "Content-Length: -1\r\n",
    "Content-Length: 7, 7\r\n", "Content-Length: 1234567890123\r\n",
])
def test_a_body_framed_otherwise_is_refused(raw_server, framing):
    port, seen = raw_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (f"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\n{framing}\r\n"
                                       '{"a":1}').encode())
        summary = proxy.summary()
    assert reply.split(b" ")[1] == b"400" and seen == [] and summary["refused"] == {"malformed": 1}


def test_an_oversized_body_is_refused(raw_server, monkeypatch):
    from agentprov.cli.live import egress

    monkeypatch.setattr(egress, "MAX_FORWARD_BODY", 4)
    port, seen = raw_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (f"POST http://127.0.0.1:{port}/v1 HTTP/1.1\r\nHost: x\r\nContent-Length: 7\r\n\r\n"
                                       '{"a":1}').encode())
        summary = proxy.summary()
    assert reply.split(b" ")[1] == b"413" and seen == [] and summary["refused"] == {"oversize": 1}


# ------------------------------------------------------------------------------------------------ LF-3: malformed absolute forms
@pytest.mark.parametrize("target", ["http://[::1/v1", "http://[fd00::5%en0]/v1", "http://127.0.0.1:99999/v1",
                                    "http://127.0.0.1:port/v1", "http://[127.0.0.1]/v1"])
def test_a_malformed_absolute_form_is_refused_not_raised(http_server, target, capsys):
    port, seen = http_server
    planted = "sk-proj-" + "Q9w8E7r6T5y4U3i2" * 3
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, f"GET {target}?k={planted} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        summary = proxy.summary()
    assert reply.split(b" ")[1] in (b"400", b"403") and seen == []
    assert sum(summary["refused"].values()) == 1 and set(summary["refused"]) <= {"malformed", "not_allowed"}
    captured = capsys.readouterr()
    assert planted not in captured.err and planted not in captured.out and planted not in json.dumps(summary)


def test_an_unexpected_error_is_counted_and_not_logged(http_server, monkeypatch, capsys):
    port, _seen = http_server

    async def boom(*_a, **_k):
        raise RuntimeError("worker-chosen text sk-proj-ZZZZ")

    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        monkeypatch.setattr(proxy, "_forward", boom)
        reply = _exchange(proxy.port, f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        summary = proxy.summary()
    assert reply == b"" and summary["refused"] == {"malformed": 1}
    assert "sk-proj-ZZZZ" not in capsys.readouterr().err


# ------------------------------------------------------------------------------------------------ LF-4: stop() is bounded
@pytest.fixture
def silent_server():
    """A loopback server that accepts and then never sends or closes (an upstream that stays silent)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    held: list[socket.socket] = []
    stop = threading.Event()

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                continue
            held.append(conn)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield srv.getsockname()[1]
    stop.set()
    for conn in held:
        conn.close()
    srv.close()


@pytest.mark.parametrize("mode", ["tunnel", "forward"])
def test_stop_returns_promptly_and_closes_a_silent_exchange(silent_server, mode):
    import time

    port = silent_server
    proxy = EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)] if mode == "forward" else [])
    proxy.start()
    if mode == "tunnel":
        sock, reply = _request(proxy.port, f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode())
        assert reply.startswith(b"HTTP/1.1 200 ")
    else:
        sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        sock.sendall(f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        deadline = time.monotonic() + 5
        while not proxy.summary()["forwards"] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proxy.summary()["forwards"] == {f"127.0.0.1:{port}": 1}
    with sock:
        started = time.monotonic()
        proxy.stop()
        elapsed = time.monotonic() - started
        sock.settimeout(5)
        assert sock.recv(64) == b""  # the worker's side is closed, not left piping
    assert elapsed < 8, elapsed


# ------------------------------------------------------------------------------------------------ forward-mode nits
def test_the_scheme_ignores_case_and_host_is_regenerated(raw_server):
    port, seen = raw_server
    with EgressProxy([("127.0.0.1", port)], forward=[("127.0.0.1", port)]) as proxy:
        reply = _exchange(proxy.port, (f"GET HTTP://127.0.0.1:{port}/v1/models HTTP/1.1\r\nHost: evil.example\r\n"
                                       "HOST: other.example\r\nAccept: */*\r\n\r\n").encode())
        summary = proxy.summary()
    assert reply.startswith(b"HTTP/1.1 200 OK") and summary["forwards"] == {f"127.0.0.1:{port}": 1}
    (got,) = seen
    lines = got.partition(b"\r\n\r\n")[0].split(b"\r\n")
    assert lines[0] == b"GET /v1/models HTTP/1.1" and lines[1] == f"Host: 127.0.0.1:{port}".encode()
    assert [line for line in lines if line.lower().startswith(b"host:")] == [lines[1]]
    assert b"evil.example" not in got and b"other.example" not in got and b"Accept: */*" in lines


def test_the_run_forwards_only_an_http_lan_endpoint_in_any_case():
    from agentprov.cli.live.egress import forward_pairs

    for url in ("http://10.0.0.5:1234/v1", "HTTP://10.0.0.5:1234/v1", "Http://10.0.0.5:1234/v1"):
        host, port, _loopback = endpoint_target(url, allow_lan=True)
        assert forward_pairs(url, host, port, allow_lan=True) == [("10.0.0.5", 1234)]
    host, port, _loopback = endpoint_target("https://10.0.0.5/v1", allow_lan=True)
    assert forward_pairs("https://10.0.0.5/v1", host, port, allow_lan=True) == []  # tunnelled through CONNECT
    host, port, _loopback = endpoint_target("https://api.example/v1")
    assert forward_pairs("https://api.example/v1", host, port, allow_lan=False) == []
