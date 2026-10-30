"""D-702 (D-655): the core keychain helper process, :mod:`agentprov.keys.helper`. No test touches a real keychain.

* It is the only core module that imports ``keyring`` (``tests/boundary/test_import_boundary.py``), and it builds an
  allowlisted back-end directly: never ``keyring.get_keyring``/``init_backend``/``keyring.core``.
* Its protocol: names are checked, no value ever appears in an error line, ``emit`` writes exactly one line (or nothing
  when a key is missing, exit 3).
"""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov.keys import helper

SRC = Path(helper.__file__)
SECRET = "sk-" + "test-" + "0123456789abcdef"  # built from fragments; never a real key


class FakeRing:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, name: str) -> str | None:
        return self.store.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.store[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.store.pop((service, name), None)


def call(monkeypatch: pytest.MonkeyPatch, ring: Any, request: object | bytes) -> tuple[int, str]:
    data = request if isinstance(request, bytes) else json.dumps(request).encode()
    monkeypatch.setattr(helper, "backend", lambda: ring)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    return helper.main(), out.getvalue()


def test_status_without_an_allowed_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = call(monkeypatch, None, {"op": "status"})
    assert code == 0 and json.loads(out) == {"ok": True, "backend": None, "allowed": False}
    code, out = call(monkeypatch, None, {"op": "has", "names": ["OPENAI_API_KEY"]})
    assert code == 4 and json.loads(out)["error"] == "keychain.unavailable"

def test_set_has_emit_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    ring = FakeRing()
    assert call(monkeypatch, ring, {"op": "set", "name": "OPENROUTER_API_KEY", "value": SECRET})[0] == 0
    assert ring.store == {("agentprov", "OPENROUTER_API_KEY"): SECRET}
    code, out = call(monkeypatch, ring, {"op": "has", "names": ["OPENROUTER_API_KEY", "OPENAI_API_KEY"]})
    assert code == 0 and json.loads(out)["present"] == {"OPENROUTER_API_KEY": True, "OPENAI_API_KEY": False}
    assert SECRET not in out
    code, out = call(monkeypatch, ring, {"op": "emit", "names": ["OPENROUTER_API_KEY"],
                                         "values": {"REASONING_EFFORT": "low"}})
    assert code == 0 and out.count("\n") == 1
    assert json.loads(out) == {"OPENROUTER_API_KEY": SECRET, "REASONING_EFFORT": "low"}
    assert call(monkeypatch, ring, {"op": "delete", "name": "OPENROUTER_API_KEY"})[0] == 0 and not ring.store

def test_a_missing_key_emits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = call(monkeypatch, FakeRing(), {"op": "emit", "names": ["OPENAI_API_KEY"], "values": {}})
    assert code == 3 and out == ""

@pytest.mark.parametrize("request_", [
    b"not json", b'{"op": "set", "op": "set"}', b'{"op": "status", "x": NaN}', {"op": "nope"},
    {"op": "set", "name": "lower_case", "value": SECRET}, {"op": "set", "name": "A", "value": SECRET + "\n"},
    {"op": "emit", "names": ["A"], "values": {"B": "x\ny"}}, {"op": "has", "names": ["../X"]},
])
def test_bad_requests_are_refused_without_echoing_values(monkeypatch: pytest.MonkeyPatch, request_: Any) -> None:
    ring = FakeRing()
    code, out = call(monkeypatch, ring, request_)
    assert code == 2 and json.loads(out)["ok"] is False and SECRET not in out and not ring.store

def test_an_oversized_request_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = call(monkeypatch, FakeRing(), b"{" + b" " * helper.MAX_REQUEST + b"}")
    assert code == 2 and json.loads(out)["error"] == "request.too_large"

def test_the_helper_imports_only_the_stdlib_and_keyring_backends() -> None:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    names = {(n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
             for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
             for a in (n.names if isinstance(n, ast.Import) else [n])}
    assert names <= {"__future__", "contextlib", "json", "re", "sys", "typing", "keyring"}, names
    code = "\n".join(line.split("#")[0] for line in SRC.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith(("#", "*", '"')))
    for forbidden in ("get_keyring", "init_backend", "keyring.core", "set_keyring", "load_config"):
        assert forbidden not in code, forbidden
