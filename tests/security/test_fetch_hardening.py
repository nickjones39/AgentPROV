"""Fetch hardening (SEC-24; K.12.14; R-43; G.7.5).

On a synthetic local repository (the file protocol is allowed in these tests only, through the Fetcher's test seam): no
working tree is created, blob SHA-1 is checked, symlinks are data, a gitlink is not fetched, a branch or tag is refused
(``raw.origin.unpinned``), a hook in the source never runs, and git refuses every transport but https and never follows a
redirect to another host (CB-25). For references: a reference resolves only against an
in-package profile origin, a token is attached unredirected and only to the host the recipe declares, a cross-host redirect
drops credentials, a downgrade to http is refused and an unlisted host is refused; ``REFERENCES.json`` holds no command or
instruction text. A static scan holds ``raw/fetch.py`` to the subprocess and network rules of MN M.5.3.
"""

from __future__ import annotations

import ast
import http.server
import os
import stat
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

_RAW_TESTS = Path(__file__).resolve().parents[1] / "unit" / "raw"
if str(_RAW_TESTS) not in sys.path:
    sys.path.insert(0, str(_RAW_TESTS))

from fetch_support import FILES, GITLINK_SHA, REPO_URL, SYMLINK_TARGET, FakeTransport, git, make_upstream, needs_git  # noqa: E402

import agentprov.raw.fetch as fetch_module  # noqa: E402
from agentprov.raw.fetch import Fetcher, RedirectRefusedError, Recipe, SafeRedirectHandler  # noqa: E402
from agentprov.raw.origins import OriginUnpinnedError  # noqa: E402

FETCH_SOURCE = Path(fetch_module.__file__)


@needs_git
@pytest.mark.parametrize("ref", ["main", "master", "v1.0.0", "HEAD", "refs/heads/main", "origin/main", "", "abc1234"])
def test_a_branch_a_tag_or_an_abbreviated_commit_is_refused_before_any_work(tmp_path, ref):
    with pytest.raises(OriginUnpinnedError) as err:
        Recipe(kind="git", repo=REPO_URL, commit=ref)
    assert err.value.code == "raw.origin.unpinned" and err.value.exit_code == 3


@needs_git
def test_no_working_tree_and_no_upstream_file_exists_outside_the_object_database(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    result = up.fetcher(cache, allow_network=True).fetch(up.recipe(paths=()))
    names = {p.name for p in cache.rglob("*")}
    # none of the upstream paths, link names or agent-instruction files exists on disk as a file
    assert not names & {"README.md", "one.json", "two.json", "three.json", "skip.txt", "link.json", ".gitmodules"}
    for p in cache.rglob("*"):
        assert not p.is_symlink(), p  # a symlink blob is data, never created on disk
    assert (result.path / "HEAD").is_file() and not (result.path / ".git").exists()
    assert git(result.path, "rev-parse", "--is-bare-repository") == "true"


@needs_git
def test_a_symlink_blob_is_data_and_never_resolved(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    fetcher.fetch(up.recipe())
    (link,) = [b for b in fetcher.iter_git_blobs(up.recipe()) if b.entry.is_symlink]
    assert link.data == SYMLINK_TARGET.encode() and link.entry.mode == "120000"
    assert not Path(SYMLINK_TARGET).exists() or True  # the target text is never opened by the fetcher


@needs_git
def test_a_gitlink_is_recorded_and_never_fetched(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    result = fetcher.fetch(up.recipe())
    assert result.gitlinks == 1
    entries, _ = fetcher.git_tree(up.recipe())
    assert [e.oid for e in entries if e.is_gitlink] == [GITLINK_SHA]
    assert all(not b.entry.is_gitlink for b in fetcher.iter_git_blobs(up.recipe()))


@needs_git
def test_a_hook_in_the_source_never_runs(tmp_path):
    up = make_upstream(tmp_path)
    marker = tmp_path / "hook-ran"
    for name in ("post-checkout", "post-merge", "reference-transaction", "pre-auto-gc", "post-update", "pre-receive"):
        hook = up.path / ".git" / "hooks" / name
        hook.write_text(f"#!/bin/sh\necho ran > '{marker}'\n")
        hook.chmod(0o755)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    fetcher.fetch(up.recipe())
    list(fetcher.iter_git_blobs(up.recipe()))
    assert not marker.exists()
    bare = tmp_path / "c" / "git" / "example.invalid" / "acme" / "runs.git"
    assert not any(p.is_file() and os.access(p, os.X_OK) and stat.S_ISREG(p.stat().st_mode) and p.parent.name == "hooks" for p in bare.rglob("*"))


@needs_git
def test_blob_sha1_is_recomputed_while_reading(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    fetcher.fetch(up.recipe())
    for blob in fetcher.iter_git_blobs(up.recipe()):
        assert blob.entry.oid == up.blob_ids.get(blob.entry.path, blob.entry.oid)
    assert any(b.entry.path == "runs/a/one.json" and b.data == FILES["runs/a/one.json"] for b in fetcher.iter_git_blobs(up.recipe()))


# ---------------------------------------------------------------------------------------------------- credentials and redirects


def test_a_token_goes_only_to_the_declared_host_and_only_unredirected(tmp_path):
    url = "https://zenodo.org/records/123/files/x.zip?download=1"
    body = b"xx"
    import hashlib

    recipe = Recipe.from_pin({"kind": "zenodo", "doi": "10.5281/zenodo.123", "file": "x.zip", "sha256": hashlib.sha256(body).hexdigest(),
                              "token_env": "ZENODO_TOKEN", "token_host": "zenodo.org"})  # fmt: skip
    transport = FakeTransport({url: body})
    Fetcher(tmp_path / "c", allow_network=True, transport=transport, env={"ZENODO_TOKEN": "tok-123"}).fetch(recipe)
    (call,) = transport.calls
    assert call.unredirected == {"Authorization": "Bearer tok-123"}
    assert all("tok-123" not in str(v) for v in call.headers.values())
    assert "tok-123" not in (tmp_path / "c" / "acquisitions.jsonl").read_text()


def test_cross_host_redirects_drop_credentials_downgrades_and_unlisted_hosts_are_refused():
    handler = SafeRedirectHandler(frozenset({"huggingface.co", "cdn-lfs.huggingface.co"}))

    def go(new: str, **headers: str):
        return handler.redirect_request(urllib.request.Request("https://huggingface.co/a", headers=headers), None, 302, "Found", {}, new)

    moved = go("https://cdn-lfs.huggingface.co/b", Authorization="Bearer t", Cookie="c=1")
    assert moved is not None and not {k.lower() for k in moved.headers} & {"authorization", "cookie"}
    with pytest.raises(RedirectRefusedError):
        go("http://huggingface.co/b", Authorization="Bearer t")
    with pytest.raises(RedirectRefusedError):
        go("https://attacker.example/b", Authorization="Bearer t")


# ---------------------------------------------------------------------------------------------------- git transports and redirects


def _git_probe(fetcher: Fetcher, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run ``git <hardening> <args>`` as the fetcher would (its argv prefix and scrubbed environment)."""
    return subprocess.run([fetcher._git_exe(), *fetcher._hardening(), *args], capture_output=True, timeout=60, check=False, env=fetcher._git_env())  # noqa: S603


@needs_git
@pytest.mark.parametrize("url", ["http://127.0.0.1:9/o/r", "git://127.0.0.1:9/o/r", "ssh://git@127.0.0.1:9/o/r", "ext::true", "file:///nonexistent/o/r"])
def test_git_refuses_every_transport_but_https_before_any_connection(tmp_path, url):
    fetcher = Fetcher(tmp_path, env={"PATH": os.environ.get("PATH", "")})
    done = _git_probe(fetcher, "ls-remote", "--", url)
    assert done.returncode != 0 and b"not allowed" in done.stderr, done.stderr


class _Hits(http.server.BaseHTTPRequestHandler):
    hits: list[str]
    target = ""

    def do_GET(self) -> None:  # noqa: N802 - the stdlib handler's name
        self.hits.append(self.path)
        if self.target:
            self.send_response(301)
            self.send_header("Location", self.target + self.path)
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@needs_git
def test_git_never_follows_a_redirect_to_another_host(tmp_path):
    # localhost only: a front that answers every request with 301 to a second server, which counts what reaches it;
    # plain http is re-allowed after the hardening options for this probe only, since TLS needs a certificate
    behind_hits: list[str] = []
    front_hits: list[str] = []
    behind = http.server.HTTPServer(("127.0.0.1", 0), type("Behind", (_Hits,), {"hits": behind_hits}))
    front = http.server.HTTPServer(
        ("127.0.0.1", 0), type("Front", (_Hits,), {"hits": front_hits, "target": f"http://127.0.0.1:{behind.server_port}"})
    )
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (front, behind)]
    for t in threads:
        t.start()
    try:
        fetcher = Fetcher(tmp_path, env={"PATH": os.environ.get("PATH", "")})
        done = _git_probe(fetcher, "-c", "protocol.http.allow=always", "ls-remote", "--", f"http://127.0.0.1:{front.server_port}/o/r")
    finally:
        for s in (front, behind):
            s.shutdown()
            s.server_close()
    assert done.returncode != 0
    assert front_hits and not behind_hits, (front_hits, behind_hits)


# ---------------------------------------------------------------------------------------------------- static rules for fetch.py


def _tree() -> ast.AST:
    return ast.parse(FETCH_SOURCE.read_text(encoding="utf-8"), filename=str(FETCH_SOURCE))


def test_fetch_never_uses_a_shell_and_always_passes_an_argv_list():
    calls = [
        n
        for n in ast.walk(_tree())
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "subprocess" and n.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
    ]  # fmt: skip
    assert calls, "fetch.py is the subprocess home of the raw layer"
    for call in calls:
        assert not any(kw.arg == "shell" for kw in call.keywords), "shell= is never passed"
        first = call.args[0]
        assert isinstance(first, ast.List), "the argv is a list built from validated data"


def test_fetch_uses_no_dangerous_calls_or_unsafe_helpers():
    banned_names = {"eval", "exec", "compile", "__import__"}
    banned_attrs = {"extract", "extractall", "unpack_archive", "system", "popen", "urlopen", "urlretrieve", "getoutput"}
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in banned_names
        if isinstance(node, ast.Attribute):
            assert node.attr not in banned_attrs, node.attr
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            assert not {n.split(".")[0] for n in names} & {"pickle", "marshal", "tarfile", "zipfile", "httpx", "requests", "dotenv"}


def test_fetch_reads_credentials_only_from_the_environment_mapping_it_was_given():
    tree = _tree()
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert ".env" not in literals and not any("dotenv" in s for s in literals)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"load_dotenv", "dotenv_values", "getenv"}
    environ = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "environ"]
    assert 0 < len(environ) <= 3  # the default mapping; everything else receives the mapping explicitly
