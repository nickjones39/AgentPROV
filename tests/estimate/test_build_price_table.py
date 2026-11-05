"""``tools/estimate/build_price_table.py``: the direct-provider rows refuse any price that is given but not valid,
cache prices included (AU-TRG-7). Synthetic TOML in ``tmp_path``; the shipped table is never written."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "estimate" / "build_price_table.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_price_table", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _direct(tmp_path: Path, row: str) -> Path:
    path = tmp_path / "direct.toml"
    path.write_text(f'[[openai]]\nsource = "s"\nas_of = "2026-10-21"\nrows = [\n  {{ model = "m", {row} }},\n]\n',
                    encoding="utf-8")
    return path


def test_valid_cache_prices_are_kept(tmp_path: Path) -> None:
    g = _tool()
    out = tmp_path / "prices.json"
    direct = _direct(tmp_path, 'input = "2.00", output = "10.00", cached_input = "0.10", cache_write = "2.50"')
    assert g.main(["--direct", str(direct), "--out", str(out)]) == 0
    (row,) = json.loads(out.read_text(encoding="utf-8"))["rows"]
    assert row["cached_input"] is not None and row["cache_write"] is not None


@pytest.mark.parametrize("prices", [
    'input = "2.00", output = "10.00", cached_input = "0,25"',      # malformed
    'input = "2.00", output = "10.00", cache_write = "-1"',          # negative
    'input = "2.00", output = "10.00", cached_input = "1e12"',       # implausible
    'input = "2.00", output = "-10.00"',
])
def test_an_invalid_price_is_refused(tmp_path: Path, prices: str) -> None:
    g = _tool()
    out = tmp_path / "prices.json"
    with pytest.raises(SystemExit, match="not a valid decimal"):
        g.main(["--direct", str(_direct(tmp_path, prices)), "--out", str(out)])
    assert not out.exists()
