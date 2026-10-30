"""SEC-17 (T-13, T-20): what an artefact says about itself (embedded PROV, a claimed digest, claimed producer versions)
yields no core PROV statement and no identity; it is kept only as ``O`` data ``by: source``. ``hadPrimarySource`` is
stated only for ``prov_primary`` in {native, byte_derived}.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import agentdojo_support as ad
import pytest
from aer_support import example_records
from import_harness import Imported, run_import
from time_support import derive_records, relations

EMBEDDED_PROV = {
    "prefix": {"ex": "https://attacker.invalid/"},
    "wasDerivedFrom": {"_:d": {"prov:generatedEntity": "ex:answer", "prov:usedEntity": "ex:secret"}},
    "hadPrimarySource": {"_:p": {"prov:generatedEntity": "ex:answer", "prov:usedEntity": "ex:oracle"}},
}


def _k14(**claims: Any) -> dict[str, Any]:
    base = dict(benchmark_version="v1.2", evaluation_timestamp="2025-07-01 10:00:00", agentdojo_package_version="0.1.35")
    base.update(claims)
    return ad.base_log(**base)


def _import(tmp: Path, name: str, doc: dict[str, Any], part: str = "head") -> Imported:
    return run_import(tmp, {ad.path_of(doc): ad.log_bytes(doc)}, name=name, part=part)


def _prov(imported: Imported) -> dict[str, Any]:
    (row,) = imported.rows("executions.jsonl")
    (paths,) = row["paths"]["prov"].values()
    return json.loads((imported.partial / paths["json"]).read_bytes())


def _records(imported: Imported) -> list[dict[str, Any]]:
    (aer,) = imported.aers().values()
    return [json.loads(line) for line in aer.splitlines()]


def test_sec17_claimed_producer_versions_change_no_relation_and_give_no_code_identity(tmp_path: Path) -> None:
    control = _import(tmp_path, "control", _k14())
    claimed = _import(tmp_path, "claimed", _k14(agentdojo_package_version="9.9.9+claimed", benchmark_version="v9/../x"))
    # core, inference and conversion provenance are untouched by the claim
    assert relations(_prov(claimed), assessment=False) == relations(_prov(control), assessment=False)
    # the version label selects the SEM tool table (D.6.12 version_label_semantics), so an unrecognised claimed label
    # can only make the assessment bundle *less* trusting: its tools fail closed (agentdojo.unknown_tool@1)
    assessed = json.dumps([v for k, v in relations(_prov(claimed)).items() if k.startswith("xd:bundle.assess.")])
    assert "agentdojo.unknown_tool@1" in assessed
    bench = next(r for r in _records(claimed) if r["k"] == "actor" and r.get("kind") == "benchmark")
    assert bench["by"] == "source" and bench["evf"]["/code"] == "O" and bench["evf"]["/version"] == "O"
    assert bench["code"]["dist_version"] == "9.9.9+claimed" and bench["version"] == "v9/../x"  # kept verbatim, as data
    assert bench["unk"]["/code/commit"] == "not_recorded"  # a claimed version never becomes a code identity


@pytest.mark.parametrize("part", ["head", "2024-06"])
def test_sec17_embedded_prov_and_a_claimed_digest_are_kept_as_data_never_as_provenance(tmp_path: Path, part: str) -> None:
    claims = {"provenance": EMBEDDED_PROV, "sha256": "0" * 64}
    make = _k14 if part == "head" else ad.base_log
    kept = _import(tmp_path, "kept", make(**claims), part=part)
    control = _import(tmp_path, "control", make(), part=part)
    assert "map.agentdojo.unknown_top_level_key" in {r["code"] for r in kept.rows("register.jsonl")}
    assert relations(_prov(kept)) == relations(_prov(control))
    text = json.dumps(_prov(kept))
    assert "attacker.invalid" not in text and "ex:secret" not in text and "ex:oracle" not in text
    assert "0" * 64 not in text  # the claimed digest identifies nothing
    (aer,) = kept.aers().values()
    assert b"attacker.invalid" in aer  # ...while the AER keeps it, as recorded source data


@pytest.mark.parametrize(("prov_primary", "expected"), [("native", True), ("byte_derived", True),
                                                        ("secondary", False), ("unknown", False)])
def test_sec17_had_primary_source_only_for_native_or_byte_derived(prov_primary: str, expected: bool) -> None:
    records = copy.deepcopy(example_records())
    records[0]["artifacts"][0]["prov_primary"] = prov_primary
    prov = derive_records(records)
    stated = any(v.get("prov:type", {}).get("$") == "prov:PrimarySource"  # hadPrimarySource, E.3.3
                 for v in prov.get("wasDerivedFrom", {}).values())
    assert stated is expected
    assert any(v.get("apv:provPrimary") == prov_primary for v in prov["entity"].values())  # recorded either way
