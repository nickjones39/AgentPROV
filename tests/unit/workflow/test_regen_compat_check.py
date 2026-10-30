"""``tools/regen/compat_derive_check.py``: a compat derive output is its source plus one oracle graph per execution.

Synthetic corpus trees in ``tmp_path`` (two executions); no real corpus is read.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[3] / "tools" / "regen" / "compat_derive_check.py"
_spec = importlib.util.spec_from_file_location("regen_compat_check", _PATH)
assert _spec and _spec.loader
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

CORE = "agentprov-prov/0.1"
EXS = ("ex_aa1", "ex_bb2")


def _row(ex: str) -> dict:
    core = f"prov/agentprov-prov-0.1/{ex[3:5]}/{ex}.prov.json"
    return {"ex": ex, "digests": {"aer": "sha256:0", "prov": {CORE: {"json": "sha256:1"}}},
            "paths": {"prov": {CORE: {"json": core}}}, "stages": {"aer": "ok", "prov": {CORE: "ok"}}}


def _write_rows(root: Path, rows: list[dict]) -> None:
    (root / "executions.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    old = tmp_path / "old"
    for ex in EXS:
        p = old / f"prov/agentprov-prov-0.1/{ex[3:5]}/{ex}.prov.json"
        p.parent.mkdir(parents=True)
        p.write_text("{}")
    (old / "derivation.json").write_text(json.dumps({"format": "d", "stages": [{"stage": "prov", "spec": CORE}]}))
    (old / "corpus.json").write_text(json.dumps({"counts": {"executions": 2}}))
    (old / "register.jsonl").write_text("")
    _write_rows(old, [_row(ex) for ex in EXS])
    new = tmp_path / "new"
    shutil.copytree(old, new)
    rows = []
    for ex in EXS:
        rel = f"prov/adprov-v2.3-compat/{ex[3:5]}/{ex}.prov.json"
        data = json.dumps({"oracle": ex}).encode()
        (new / rel).parent.mkdir(parents=True, exist_ok=True)
        (new / rel).write_bytes(data)
        row = _row(ex)
        row["digests"]["prov"][chk.COMPAT] = {"json": "sha256:" + hashlib.sha256(data).hexdigest()}
        row["paths"]["prov"][chk.COMPAT] = {"json": rel}
        row["stages"]["prov"][chk.COMPAT] = "ok"
        row["oracles"] = {chk.COMPAT: {"gate_report": None, "status": chk.ORACLE}}
        row["facets"] = {"n.judgements": 2}  # derive writes full H.3.1 rows
        rows.append(row)
    _write_rows(new, rows)
    (new / "derivation.json").write_text(json.dumps({"format": "d", "stages": [
        {"stage": "prov", "spec": CORE}, {"stage": "compat", "spec": chk.COMPAT, "status": chk.ORACLE}]}))
    (new / "corpus.json").write_text(json.dumps({"counts": {"executions": 2}, "derived_from": "y",
                                                 "prov_specs": [CORE, chk.COMPAT]}))
    return old, new


def _run(old: Path, new: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, dict]:
    report = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["x", str(old), str(new), "--report", str(report)])
    rc = chk.main()
    return rc, json.loads(report.read_text())


def test_source_plus_one_oracle_per_execution_passes(trees, tmp_path, monkeypatch) -> None:
    rc, rep = _run(*trees, tmp_path, monkeypatch)
    assert rc == 0 and rep["pass"]
    assert rep["compat_files"] == 2 and rep["differ"] == ["corpus.json", "derivation.json", "executions.jsonl"]
    assert rep["derivation_stages"] == {"old": 1, "new": 2} and rep["row_fields_added"] == ["facets", "oracles"]
    assert rep["corpus_json_pointers"] == ["/derived_from", "/prov_specs"]


def test_a_changed_core_bundle_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    (new / "prov/agentprov-prov-0.1/aa/ex_aa1.prov.json").write_text('{"changed": 1}')
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1 and rep["unexpected_differ"] == ["prov/agentprov-prov-0.1/aa/ex_aa1.prov.json"]


def test_a_row_change_outside_the_compat_entries_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    rows = [json.loads(line) for line in (new / "executions.jsonl").read_text().splitlines()]
    rows[0]["stages"]["aer"] = "failed"
    _write_rows(new, rows)
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1 and rep["rows_bad"] == {"row_differs_outside_compat": 1}


def test_a_missing_oracle_or_a_wrong_digest_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    (new / "prov/adprov-v2.3-compat/bb/ex_bb2.prov.json").write_text("{}")  # digest no longer matches the row
    (new / "prov/adprov-v2.3-compat/aa/ex_aa1.prov.json").unlink()
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1
    assert rep["rows_bad"] == {"compat_path_mismatch": 1, "compat_digest_mismatch": 1}
    assert "compat files 1 != executions 2" in rep["problems"]


def test_an_unexpected_new_file_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    (new / "views").mkdir()
    (new / "views" / "x.json").write_text("{}")
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1 and rep["unexpected_new"] == ["views/x.json"]


def test_a_row_without_the_oracle_status_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    rows = [json.loads(line) for line in (new / "executions.jsonl").read_text().splitlines()]
    del rows[1]["oracles"]
    _write_rows(new, rows)
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1 and rep["rows_bad"] == {"oracle_status_missing": 1}


def test_a_changed_source_stage_or_a_corpus_json_change_elsewhere_fails(trees, tmp_path, monkeypatch) -> None:
    old, new = trees
    d = json.loads((new / "derivation.json").read_text())
    d["stages"][0]["spec"] = "other"
    (new / "derivation.json").write_text(json.dumps(d))
    c = json.loads((new / "corpus.json").read_text())
    c["counts"]["executions"] = 3
    (new / "corpus.json").write_text(json.dumps(c))
    rc, rep = _run(old, new, tmp_path, monkeypatch)
    assert rc == 1
    assert "derivation.json: a source stage changed or moved" in rep["problems"]
    assert any(p.startswith("corpus.json changed outside") for p in rep["problems"])
