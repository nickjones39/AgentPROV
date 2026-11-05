"""``tools/import_compare.py``: the determinism check between two working corpora of one source (K.13)."""

from __future__ import annotations

import json
from pathlib import Path

import import_compare as ic


def _tree(root: Path, prov: bytes, rows: int = 1) -> Path:
    (root / "aer").mkdir(parents=True)
    (root / "prov").mkdir()
    (root / "aer/x.aer.jsonl").write_bytes(b'{"aer": 1}\n')
    (root / "prov/x.prov.json").write_bytes(prov)
    row = {"ex": "ex_1", "paths": {"aer": "aer/x.aer.jsonl",
                                   "prov": {"agentprov-prov/0.1": {"json": "prov/x.prov.json"}}},
           "digests": {"prov": {"agentprov-prov/0.1": {"json": "sha256:same"}}}}
    (root / "executions.jsonl").write_text((json.dumps(row) + "\n") * rows, encoding="utf-8")
    return root


def test_identical_trees_are_all_equal(tmp_path: Path) -> None:
    a, b = _tree(tmp_path / "a", b'{"prov": 1}'), _tree(tmp_path / "b", b'{"prov": 1}')
    result = ic.compare(a, b, whole=True)
    assert result["all_equal"] and result["prov_equal"] == 1 and result["whole_tree"]["identical"]
    assert ic.main(["--a", str(a), "--b", str(b)]) == 0


def test_differing_prov_bytes_fail_the_check(tmp_path: Path) -> None:
    """AU-TWF-9: equal index rows (one PROV digest recorded) but different PROV-JSON bytes are not deterministic."""
    a, b = _tree(tmp_path / "a", b'{"prov": 1}'), _tree(tmp_path / "b", b'{"prov": 2}')
    result = ic.compare(a, b, whole=False)
    assert result["index_rows_equal"] == 1 and result["prov_equal"] == 0 and result["prov_files"] == 1
    assert result["all_equal"] is False
    assert ic.main(["--a", str(a), "--b", str(b)]) == 1


def test_a_duplicate_index_row_in_b_is_reported(tmp_path: Path) -> None:
    """AU-TWF-9: two index rows for one execution in --b are counted as a failure, not a ValueError traceback."""
    a, b = _tree(tmp_path / "a", b'{"prov": 1}'), _tree(tmp_path / "b", b'{"prov": 1}', rows=2)
    result = ic.compare(a, b, whole=False)
    assert result["duplicate_in_b"] == 1 and result["all_equal"] is False
    assert ic.main(["--a", str(a), "--b", str(b)]) == 1
