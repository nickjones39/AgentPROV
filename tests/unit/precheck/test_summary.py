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
