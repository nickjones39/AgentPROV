"""``aer/0.2`` records annotate, derive and pass tiers 3 and 4 (D-211): a withheld part member is absent and declared, so the PROV engine
states no content for it and every tier-4 check passes. ``agentprov-prov/0.1`` is unchanged; ``apv:aerVersion`` names
the record's format version.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402

import pytest  # noqa: E402

from agentprov.adapters.runner.provjob import PROFILES  # noqa: E402
from agentprov.prov.engine import derive  # noqa: E402
from agentprov.sem.engine import annotate  # noqa: E402
from agentprov.sem.validate import validate_sem_document  # noqa: E402
from agentprov.validate.prov import validate_prov  # noqa: E402


def test_withheld_part_members_derive_and_pass_tier4(tmp_path: Path) -> None:
    records = ps.generic_records()
    records[0]["aer"] = "0.2"
    m0 = next(r for r in records if r["id"] == "m0")
    del m0["parts"][0]["text"]
    m0["unk"] = {"/parts/0/text": "withheld"}
    m1 = next(r for r in records if r["id"] == "m1")
    del m1["parts"][1]["args"]
    m1["unk"] = {**m1.get("unk", {}), "/parts/1/args": "withheld"}
    doc = ps.write_aer(records, tmp_path / "w.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(doc, registry) == []
    result = derive(doc, registry=registry)
    report = validate_prov(result.prov_json, doc, registry=registry)
    failures = [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status == "fail"]
    assert failures == [] and report.passed
    body = result.prov_json.decode("utf-8")
    assert '"apv:aerVersion"' in body and "aer/0.2" in body
    entities = {k: v for bundle in json.loads(body).get("bundle", {}).values() for k, v in bundle.get("entity", {}).items()}
    part = entities["x:m0-0"]
    assert "apv:contentSha256" not in part and "apv:text" not in part
    assert "Withheld" in json.dumps(part["apv:contentStatus"])  # the declared status, never an empty content


VECTORS = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "examples" / "C"
#: D-211: the part members ``aer/0.2`` lets a record withhold (a ``tool_result`` keeps its ``text`` or ``value``).
WITHHOLDABLE: dict[str, str] = {"text": "text", "reasoning": "text", "refusal": "text", "tool_call": "args", "other": "value"}


def _findings(tmp: Path, records: list[dict[str, Any]]) -> dict[str, list[tuple[str, str | None]]]:
    doc = ps.write_aer(records, tmp / "x.aer.jsonl")
    return {ref: [(f.code, f.pointer) for f in validate_sem_document(annotate(doc, profile), doc, mode="release",
                                                                     profile=profile).findings]
            for ref, profile in PROFILES.items()}


@pytest.mark.parametrize("name", ["agentdojo_2024_pi_detector", "adprov_v1_llama_injecagent", "rope_denial_qwen_autodojo",
                                  "stac_case_223"])
def test_withholding_every_part_member_adds_no_sem_finding_under_any_shipped_profile(tmp_path: Path, name: str) -> None:
    """Every shipped profile annotates a record whose part contents are all withheld, and validates it exactly as it
    validates the record with its contents (a profile run on another family's vector may have findings of its own)."""
    records = [json.loads(line) for line in (VECTORS / f"{name}.aer.jsonl").read_bytes().splitlines()][:-1]
    records[0]["aer"] = "0.2"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    full = _findings(tmp_path / "a", copy.deepcopy(records))
    withheld = 0
    for record in records:
        for k, part in enumerate(record.get("parts") or []):
            member = WITHHOLDABLE.get(str(part.get("t")))  # D-211: only these members may be absent
            pointer = f"/parts/{k}/{member}"
            if member is not None and member in part and pointer not in record.get("unk", {}):
                del part[member]
                record["unk"] = {**record.get("unk", {}), pointer: "withheld"}
                withheld += 1
    assert withheld
    codes = ps.check_valid(ps.write_aer(records, tmp_path / "check.aer.jsonl"), ps.registry())
    assert "aer.schema.required" not in codes  # every absence is one aer/0.2 allows (the vectors' catalogues aside)
    assert _findings(tmp_path / "b", records) == full
