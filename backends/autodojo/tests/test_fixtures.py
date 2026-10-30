"""The committed AutoDojo fixtures (``tests/fixtures/capture/autodojo/``, written by ``tools/make_capture_fixtures.py``)
are what the core mapping wave consumes: each verifies sealed with its expected terminal status, its ``SOURCE.json``
digests match, the replay cell carries the synthetic cache, and no file holds the producing machine's home path or
host name. The fixtures are read programmatically; nothing here prints their content."""

from __future__ import annotations

import hashlib
import json
import pwd
import os
import socket
from pathlib import Path

import pytest

from agentprov_backend.testing.scenarios import AUTODOJO_CACHE_LABEL, autodojo_cache_bytes

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "capture" / "autodojo"
EXPECTED = {
    "autodojo_banking_important_instructions": ("complete", "worker"),
    "autodojo_banking_cache_replay": ("complete", "worker"),
    "autodojo_error_skipped_json_decode": ("complete", "worker"),
    "autodojo_aborted_kill": ("aborted", "parent"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture_is_sealed_and_listed(name):
    from agentprov_capture.verify import verify_file

    root = FIXTURES / name
    if not root.is_dir():
        pytest.skip(f"fixture {name} is not present")
    (log,) = sorted((root / "session" / "raw" / "capture").glob("*.capture.jsonl"))
    report = verify_file(log)
    assert report.sealed and not report.issues
    assert (report.status, report.appended_by) == EXPECTED[name]
    listed = {e["sample_file"]: e["sha256"] for e in json.loads((root / "SOURCE.json").read_text())}
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
    assert listed == files
    home = pwd.getpwuid(os.getuid()).pw_dir.encode()
    host = socket.gethostname().encode()
    for p in root.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            assert home not in data and (len(host) < 4 or host not in data), p.relative_to(root).as_posix()
    run_cell = json.loads((root / "run_cell.json").read_text())
    if run_cell["cell"]["attack"] == "autodojo":
        assert (root / "session" / AUTODOJO_CACHE_LABEL).read_bytes() == autodojo_cache_bytes()
        assert run_cell["attack_env"]["AUTODOJO_CACHE_label"] == AUTODOJO_CACHE_LABEL
