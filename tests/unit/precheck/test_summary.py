"""tools/precheck/summary.py on a synthetic pre-check tree (tmp_path only)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "precheck" / "summary.py"


@pytest.fixture()
def summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    spec = importlib.util.spec_from_file_location("precheck_summary", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pre = tmp_path / "precheck"
    (pre / "data" / "_rows").mkdir(parents=True)
    (pre / "data" / "c1").mkdir()
    (pre / "manifest.json").write_text(json.dumps({"parts": [
        {"corpus_id": "c1", "source": "s1", "part": "p", "in_listing": True},
        {"corpus_id": "c2", "source": "s2", "part": "p", "in_listing": True},
        {"corpus_id": "c3", "source": "s3", "part": "p", "in_listing": False}]}))  # fmt: skip
    (pre / "data" / "_rows" / "wave1.json").write_text(json.dumps({"rows": [
        {"corpus_id": "c1", "wave": 1, "status": "examined", "parts": [], "readiness": "ready-with-caveats",
         "readiness_why": "x", "findings_by_class": {"source-defect": 9}}]}))  # fmt: skip
    (pre / "data" / "c1" / "findings.json").write_text(json.dumps({"format": "agentprov-precheck-findings/0.1",
        "findings": [{"id": "a", "cls": "documentation-mismatch", "severity": "S3", "verdict": "confirmed"},
                     {"id": "b", "cls": "analysis-artefact", "severity": "S3", "verdict": "confirmed"},
                     {"id": "c", "cls": "source-defect", "severity": "S2", "security": True, "verdict": "confirmed"}],
        "refuted": [{"id": "d"}]}))  # fmt: skip
    (pre / "data" / "c1" / "l1-09-p.json").write_text(json.dumps({"part": "p", "members_walked": 10,
                                                                    "metadata_members": 2, "metadata_include_match": 1}))  # fmt: skip
    monkeypatch.setattr(module, "PRE", pre)
    return module


def test_build_counts_from_findings_not_rows(summary: Any) -> None:
    out = summary.build()
    assert out["population"] == {"corpora": 2, "listed_parts": 2}
    c1, c2 = out["rows"]
    assert c1["findings"]["by_class"] == {"analysis-artefact": 1, "documentation-mismatch": 1, "source-defect": 1}
    assert c1["findings"]["by_severity"] == {"S2": 1, "S3": 1}  # analysis-artefacts are not corpus findings
    assert c1["findings"]["refuted"] == 1 and c1["findings"]["security"] == ["c"]
    assert c1["l1_09"] == {"p": {"members_walked": 10, "metadata_members": 2, "metadata_include_match": 1}}
    assert c2["status"] == "pending" and c2["readiness"] is None
    assert out["examined"] == 1 and out["readiness"] == {"ready-with-caveats": 1}


def test_check_detects_stale(summary: Any) -> None:
    assert summary.main([]) == 0
    assert summary.main(["--check"]) == 0
    (summary.PRE / "summary.md").write_text("edited\n")
    assert summary.main(["--check"]) == 1


def test_the_code_table_names_the_commit_of_the_check(summary: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-TRG-5: ``code-<part>.json`` takes its commit from the Level-2 check, which a re-run check (imports kept)
    records anew; the summary must not present it as the scratch import's commit."""
    spec = importlib.util.spec_from_file_location("precheck_code_ident", TOOL.parent / "code_ident.py")
    assert spec is not None and spec.loader is not None
    code_ident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(code_ident)
    data, scratch = summary.PRE / "data", tmp_path / "scratch"
    check, built = "c" * 40, "a" * 40  # the re-run check's commit; the commit the import was built at
    (data / "c1" / "l2-p.json").write_text(json.dumps({"code": {"commit": check, "tracked_changes": False}}))
    corpus = scratch / "c1" / "l2-p-j2.partial"
    corpus.mkdir(parents=True)
    (corpus / "derivation.json").write_text(json.dumps({"stages": [{"stage": "aer", "engine_code_sha256": "sha256:" + "e" * 64}]}))
    (corpus / "corpus.json").write_text(json.dumps({"producer": {"git_commit": built}}))
    monkeypatch.setattr(code_ident, "DATA", data)
    monkeypatch.setattr(code_ident, "scratch_root", lambda: scratch)
    record = code_ident.ident("c1", "p")
    assert record["commit"] == check
    (data / "c1" / "code-p.json").write_text(json.dumps(record))
    md = summary.render(summary.build())
    assert "| Corpus | Part | Check commit |" in md and f"| c1 | p | `{check[:8]}` |" in md
    assert "Level-2 check" in md and "scratch import ran at" not in md
