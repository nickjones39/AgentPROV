"""Units of ``agentprov_backend`` that need no benchmark package: JSON value encoding (C.11.3), the network guard,
protocol framing (D.11.3), response facts and UUIDv7."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import uuid

import pytest

from agentprov_backend._jsonval import encode_value, escape_text, to_jsonable
from agentprov_backend.gateway import decode_json_body, response_facts
from agentprov_backend.session import uuid7
from agentprov_backend.testing import netguard
from agentprov_backend.worker import MAX_LINE, PROTOCOL, ProtocolError, decode_message, encode_message


def test_encode_value_reserved_forms():
    assert encode_value({"a": 1, "b": [1.5, None, True]}) == {"a": 1, "b": [1.5, None, True]}
    assert encode_value(2**53) == {"$int": str(2**53)}
    assert encode_value(-(2**60)) == {"$int": str(-(2**60))}
    assert encode_value(float("nan")) == {"$float": "NaN"}
    assert encode_value(float("-inf")) == {"$float": "-Infinity"}
    assert encode_value(-0.0) == {"$float": "-0"}
    assert encode_value(1e20) == {"$int": "100000000000000000000"}
    assert encode_value("\ud800x") == {"$utf16": "2AAAeA=="}
    assert encode_value({"$blob": "x"}) == {"$lit": {"$blob": "x"}}
    assert encode_value((1, 2)) == [1, 2]
    with pytest.raises(TypeError):
        encode_value(object())


def test_to_jsonable_and_escape():
    import datetime

    assert to_jsonable({1: {2, 1}, "d": datetime.date(2022, 1, 1)}) == {"1": [1, 2], "d": "2022-01-01"}
    assert escape_text("a\x00b\u202ec\n") == "a\\u0000b\\u202ec\\u000a"
    assert escape_text("x" * 10, limit=3).startswith("xxx")


def _unescape_text(text: str) -> str:
    """The inverse of ``escape_text`` for an untruncated text: ``\\uXXXX`` and ``\\UXXXXXXXX`` are escapes, every other
    backslash is itself."""
    import re

    return re.sub(r"\\u([0-9a-f]{4})|\\U([0-9a-f]{8})", lambda m: chr(int(m.group(1) or m.group(2), 16)), text)


def test_escape_text_covers_bidi_isolates_word_joiners_and_tag_characters():
    hostile = [0x2060, 0x2062, 0x2064, 0x2066, 0x2067, 0x2068, 0x2069, 0x061C, 0x202E, 0x200B, 0xE0000, 0xE0041, 0xE007F, 0x1B]
    for cp in hostile:
        out = escape_text("a" + chr(cp) + "b")
        assert out.isascii() and chr(cp) not in out
        assert out == (f"a\\u{cp:04x}b" if cp <= 0xFFFF else f"a\\U{cp:08x}b")
    assert escape_text("\ud83d") == "\\ud83d"  # a lone surrogate
    assert escape_text("caf\u00e9 \U0001f600") == "caf\u00e9 \U0001f600"  # printable text, astral emoji included, is kept


def test_escape_text_is_unambiguous_for_literal_backslash_u_text():
    # A message that merely spells an escape must not read as the escape of a real code point.
    spelled = "\\u202e and \\U000e0041 and \\u005c and C:\\Users\\x \\"
    real = "\u202e and \U000e0041"
    assert escape_text(spelled) != escape_text(real)
    assert escape_text(real) == "\\u202e and \\U000e0041"
    assert _unescape_text(escape_text(spelled)) == spelled
    assert _unescape_text(escape_text(real)) == real
    assert escape_text("a\\b \\") == "a\\b \\"  # other backslashes are kept
    for text in ("\\", "\\u", "\\uu", "\\\\u2066", "x\\U\u2066", "\\u\u2066\\"):
        assert _unescape_text(escape_text(text)) == text


def test_netguard_blocks_and_restores():
    netguard.install()
    try:
        with pytest.raises(netguard.NetworkBlocked):
            socket.create_connection(("127.0.0.1", 9))
        with pytest.raises(netguard.NetworkBlocked):
            socket.getaddrinfo("example.invalid", 443)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(netguard.NetworkBlocked):
            s.connect(("127.0.0.1", 9))
        s.close()
        a, b = socket.socketpair()      # unix-domain pairs stay usable
        a.close(), b.close()
    finally:
        netguard.uninstall()
    assert not netguard.installed()
    assert netguard.install_from_env({"AGENTPROV_BLOCK_NETWORK": "0"}) is False
    assert netguard.install_from_env({"AGENTPROV_BLOCK_NETWORK": "1"}) is True
    netguard.uninstall()


def test_protocol_framing():
    line = encode_message("hello_ok", nonce="n", identity={"x": "é"})
    assert line.endswith(b"\n") and line.isascii()
    assert decode_message(line) == {"v": PROTOCOL, "op": "hello_ok", "nonce": "n", "identity": {"x": "é"}}
    for bad in (b'{"v": "agentprov-backend/0.1", "op": "x"}',                       # no LF
                b'[1]\n', b'{"op": "x"}\n', b'{"v": "agentprov-backend/0.1"}\n',
                b'{"v": "agentprov-backend/0.1", "op": "x", "op": "y"}\n',
                b'{"v": "agentprov-backend/0.1", "op": "x", "n": NaN}\n',
                b'\xff\n', b"x" * (MAX_LINE + 1) + b"\n"):
        with pytest.raises(ProtocolError):
            decode_message(bad)
    with pytest.raises(ValueError):
        encode_message("x", n=float("nan"))


def test_worker_without_a_benchmark_reports_fatal_and_exits(tmp_path):
    """In the shared project there is no agentdojo: hello fails and is reported as ``fatal`` (exit 2); shutdown
    and EOF exit 0; library output never reaches stdout."""
    def run(payload: bytes):
        return subprocess.run([sys.executable, "-I", "-B", "-m", "agentprov_backend.worker"], input=payload,
                              capture_output=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
                                                                     "AGENTPROV_BLOCK_NETWORK": "1"}, timeout=60)

    try:
        import agentdojo  # noqa: F401
        pytest.skip("agentdojo is installed in this environment")
    except ImportError:
        pass
    proc = run((json.dumps({"v": PROTOCOL, "op": "hello", "nonce": "n"}) + "\n").encode())
    assert proc.returncode == 2
    (msg,) = [json.loads(x) for x in proc.stdout.splitlines()]
    assert msg["op"] == "fatal" and msg["error"]["type"] in ("ModuleNotFoundError", "ImportError")
    assert run((json.dumps({"v": PROTOCOL, "op": "shutdown"}) + "\n").encode()).returncode == 0
    assert run(b"").returncode == 0


def test_netguard_counts_attempts_even_when_swallowed():
    netguard.install()
    try:
        start = len(netguard.attempts)
        try:
            socket.getaddrinfo("example.invalid", 443)
        except netguard.NetworkBlocked:
            pass  # a library may swallow it (nltk.download does); the attempt is still counted
        assert netguard.attempts[start:] == ["getaddrinfo"]
    finally:
        netguard.uninstall()


def test_stall_step_and_autodojo_scenario_data():
    import hashlib

    from agentprov_backend.testing import step_from_dict
    from agentprov_backend.testing.scenarios import AUTODOJO_SCENARIOS, autodojo_cache_bytes, autodojo_cache_sha256

    step = step_from_dict({"stall": 5})
    assert step.stall_s == 5.0 and step.raise_connect is not None
    for bad in ({"stall": 0}, {"stall": True}, {"stall": 4000}):
        with pytest.raises(ValueError):
            step_from_dict(bad)
    assert hashlib.sha256(autodojo_cache_bytes()).hexdigest() == autodojo_cache_sha256()
    replay = AUTODOJO_SCENARIOS["autodojo_banking_cache_replay"]
    assert replay.cell["attack_params"]["autodojo_cache_sha256"] == autodojo_cache_sha256()
    assert replay.attack_env == {"AUTODOJO_CACHE_label": "raw/attack/autodojo-cache.json", "AUTODOJO_VARIANT": 0}


def test_response_facts():
    body = {"id": "r1", "model": "served-x", "choices": [{"finish_reason": "stop", "message": {}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7,
                      "completion_tokens_details": {"reasoning_tokens": 2},
                      "prompt_tokens_details": {"cached_tokens": 1}}}
    assert response_facts(body) == {"response_id": "r1", "served_model": "served-x", "finish_reason": "stop",
                                    "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7,
                                              "reasoning_tokens": 2, "cache_read_tokens": 1}}
    assert response_facts({"choices": None, "usage": {"prompt_tokens": -1, "total_tokens": True}}) == {}
    assert decode_json_body(b'{"a": NaN}') is None and decode_json_body(b"\xff") is None


def test_uuid7():
    values = [uuid7() for _ in range(50)]
    for v in values:
        u = uuid.UUID(v)
        assert u.version == 7 and u.variant == uuid.RFC_4122 and str(u) == v
    assert len(set(values)) == 50
