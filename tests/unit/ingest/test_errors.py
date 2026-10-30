"""IngestError, IngestFinding and the adapter hierarchy (G.3.9, D.2.7)."""

from __future__ import annotations

import pytest

from agentprov import errors
from agentprov.errors import (
    INGEST_CODES,
    AdapterDefect,
    AdapterError,
    AgentProvError,
    BackendUnavailable,
    IdentityMismatch,
    IngestError,
    IngestFinding,
    IngestSafetyError,
    Issue,
    MalformedArtefact,
    ProfileError,
    RuleNotDeclared,
    UnsupportedConfiguration,
    UnsupportedVariant,
)


def test_g39_registry_is_closed_and_namespaced():
    assert all(code.startswith("ingest.") and code.count(".") == 2 for code in INGEST_CODES)
    assert len(INGEST_CODES) == 48  # + ingest.name.colon (D-91), ingest.json.elements (D-242), ingest.archive.parts (D-243), ingest.path.duplicate (D-622)
    for must in ("ingest.json.depth", "ingest.archive.prefix", "ingest.path.special", "ingest.interpreter.unpatched"):
        assert must in INGEST_CODES


def test_ingest_error_carries_code_and_locator():
    err = IngestError("ingest.json.depth", "too deep", offset=7, limit=256)
    assert isinstance(err, AgentProvError)
    assert err.code == "ingest.json.depth"
    assert err.exit_code == 1
    assert err.to_json() == {"code": "ingest.json.depth", "offset": 7, "limit": 256}
    assert str(err).startswith("ingest.json.depth: ")


def test_unknown_code_is_a_programming_error():
    with pytest.raises(ValueError):
        IngestError("ingest.json.nonsense", "x")
    with pytest.raises(ValueError):
        IngestFinding("not.a.code")


def test_exit_codes_for_refusals():
    assert IngestError("ingest.archive.format", "tar").exit_code == 5  # G.3.5: tar refused, exit 5
    assert IngestError("ingest.interpreter.unpatched", "x").exit_code == 3  # G.3.8 / C-1
    assert IngestError("ingest.size.file", "x").exit_code == 1


def test_safety_error_is_an_ingest_error():
    err = IngestSafetyError("ingest.name.invalid", "x")
    assert isinstance(err, IngestError)
    with pytest.raises(IngestError):
        raise err


def test_finding_to_error_round_trip():
    finding = IngestFinding("ingest.jsonl.blank", "error", line=3, offset=40, detail="blank line")
    err = finding.to_error()
    assert (err.code, err.line, err.offset) == ("ingest.jsonl.blank", 3, 40)


def test_adapter_hierarchy_follows_d27():
    for cls in (ProfileError, MalformedArtefact, UnsupportedVariant, AdapterDefect, BackendUnavailable,
                IdentityMismatch, UnsupportedConfiguration):
        assert issubclass(cls, AdapterError)
    assert issubclass(RuleNotDeclared, ProfileError)
    assert not issubclass(AdapterError, IngestError)
    assert (ProfileError("x").exit_code, BackendUnavailable("x").exit_code) == (70, 3)
    assert (IdentityMismatch("x").exit_code, UnsupportedConfiguration("x").exit_code) == (3, 5)
    assert MalformedArtefact.seal_issue == "unparseable_artefact"
    assert UnsupportedVariant.seal_issue == "unsupported_variant"
    assert AdapterDefect.seal_issue == "adapter_defect"


def test_issue_is_frozen_with_d27_fields():
    issue = Issue("unparseable_artefact", ("m1",), "agentdojo.rule@1", "error", "detail")
    assert issue.ids == ("m1",) and issue.severity == "error"
    with pytest.raises(AttributeError):
        issue.code = "x"  # type: ignore[misc]
    assert Issue("x").severity == "warning"


def test_module_keeps_agentprov_error_base():
    base = errors.AgentProvError("m")
    assert (base.code, base.exit_code) == ("internal", 70)
