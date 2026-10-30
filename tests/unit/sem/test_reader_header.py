"""The SEM reader checks the header members the SemDocument accessors read (ex, aer_digest, profile.id/version)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from sem_support import example_sem

from agentprov.aer.canon import dumps_line
from agentprov.cli.main import main
from agentprov.sem.engine import dumps_sem
from agentprov.sem.reader import SemFormatError, load_sem_bytes

DIGEST = "sha256:" + "0" * 64
PROFILE = {"id": "a.b", "version": 1}


def _sealed(header: dict[str, Any]) -> bytes:
    """A header-only SEM file with a correct seal: only the header's members can be at fault."""
    line = dumps_line(header)
    seal = {"k": "seal", "id": "seal", "n_records": 2, "records_sha256": hashlib.sha256(line).hexdigest()}
    return line + dumps_line(seal)


BAD_HEADERS = [
    pytest.param({"k": "sem", "ex": "e"}, id="no-profile-no-aer_digest"),
    pytest.param({"k": "sem", "profile": PROFILE, "aer_digest": DIGEST}, id="no-ex"),
    pytest.param({"k": "sem", "ex": 1, "profile": PROFILE, "aer_digest": DIGEST}, id="ex-not-str"),
    pytest.param({"k": "sem", "ex": "e", "profile": PROFILE}, id="no-aer_digest"),
    pytest.param({"k": "sem", "ex": "e", "profile": PROFILE, "aer_digest": 0}, id="aer_digest-not-str"),
    pytest.param({"k": "sem", "ex": "e", "profile": "x", "aer_digest": DIGEST}, id="profile-not-object"),
    pytest.param({"k": "sem", "ex": "e", "profile": {"version": 1}, "aer_digest": DIGEST}, id="profile-no-id"),
    pytest.param({"k": "sem", "ex": "e", "profile": {"id": "a.b", "version": "zz"}, "aer_digest": DIGEST},
                 id="profile-version-not-int"),
    pytest.param({"k": "sem", "ex": "e", "profile": {"id": "a.b", "version": True}, "aer_digest": DIGEST},
                 id="profile-version-bool"),
]


@pytest.mark.parametrize("header", BAD_HEADERS)
def test_reader_rejects_a_header_the_accessors_cannot_read(header: dict[str, Any]) -> None:
    with pytest.raises(SemFormatError):
        load_sem_bytes(_sealed(header), verify=True)


def test_engine_written_header_still_loads() -> None:
    doc = load_sem_bytes(dumps_sem(example_sem()))
    assert (doc.ex, doc.profile_id, doc.profile_version, doc.aer_digest) == (
        example_sem().ex, example_sem().profile_id, example_sem().profile_version, example_sem().aer_digest)


@pytest.mark.parametrize("view", [[], ["--view", "sem"]])
def test_inspect_reports_an_invalid_sem_document_not_an_internal_error(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], view: list[str]) -> None:
    path = tmp_path / "x.sem.jsonl"
    path.write_bytes(_sealed({"k": "sem", "ex": "e"}))
    code = main(["inspect", str(path), *view])
    err = capsys.readouterr().err
    assert code != 70, err
    assert "internal error" not in err
    assert "not a valid SEM document (sem.format)" in err
