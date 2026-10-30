"""Gate D complete on the golden set (J.3.5; PQ phase 7): ``semantics(AER, agentdojo.suites@1) → SEM``, then
``provenance(AER, SEM, agentprov-prov/0.1) → PROV``, validated in strict release mode.

Inputs: the 19 golden v1 pairs (10 released, 9 converted; adapter ``adprov.transcript_v1``) and the 9 native June-2024
logs of the converted pairs (``N-C01`` … ``N-C09``; adapter ``agentdojo.tracelogger``). For each AER:

- the SEM document is built twice with identical bytes and passes tier 3 (C.14.4) with the profile's declarations;
- PROV is derived twice from the AER and the SEM with identical bytes; it holds exactly one assessment bundle, of
  profile ``agentdojo.suites@1``;
- every tier-4 check passes in release mode (a skipped check is a failure, MP-3), including the E.7.2 allowed-forms
  check of the assessment bundle (PV-NE-10) and, for the v1-import AERs, the gate-D profile checks (``migration``);
- the SEM and PROV digests equal the committed pins in ``gate_d_digests.json`` (E.9). Regenerate them deliberately with
  ``AGENTPROV_REGEN_GATE_D_DIGESTS=1`` after a spec, catalogue or semantics-profile version bump.

The core-and-inference half of gate D (cross-counts, context membership only in inference bundles, times) is
``test_prov_derive.py``; the full scope (all 35,691 + 18,241) is phase 13.
"""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_v1_round_trip as v1  # noqa: E402

from agentprov.adapters.runner import aer_bytes, map_artefact  # noqa: E402
from agentprov.adapters.semantics_profiles import load_semantics_profile  # noqa: E402
from agentprov.adapters.types import Origin  # noqa: E402
from agentprov.aer.reader import AerDocument, load_aer_bytes  # noqa: E402
from agentprov.io.canonical import sha256_hex  # noqa: E402
from agentprov.prov.engine import derive  # noqa: E402
from agentprov.sem.engine import annotate, dumps_sem  # noqa: E402
from agentprov.sem.types import SemanticsProfile  # noqa: E402
from agentprov.sem.validate import validate_sem_document  # noqa: E402
from agentprov.testing import golden  # noqa: E402
from agentprov.validate import validate_prov  # noqa: E402

DIGESTS = Path(__file__).resolve().parent / "gate_d_digests.json"
REGEN = "AGENTPROV_REGEN_GATE_D_DIGESTS"
PROFILE = ("agentdojo.suites", 1)


@cache
def _profile() -> SemanticsProfile:
    return load_semantics_profile(*PROFILE)


def _inputs() -> list[tuple[str, str]]:
    """``(id, kind)`` for every golden input: ``v1`` pairs and ``native`` logs of the converted pairs."""
    if not golden.golden_available():
        return []
    out = [(e.id, "v1") for e in golden.v1_pairs()]
    out += [(f"N-{e.id}", "native") for e in golden.v1_pairs() if e.is_converted and golden.native_of(e) is not None]
    return out


@cache
def _aer(input_id: str, kind: str) -> AerDocument:
    if kind == "v1":
        pair = next(p for p in v1.PAIRS if p.id == input_id)
        outcome, _ = map_artefact(v1._source(pair), v1._origin(pair), profile_id="adprov-v1")
    else:
        entry = next(e for e in golden.v1_pairs() if e.id == input_id.removeprefix("N-"))
        native = golden.native_of(entry)
        assert native is not None and not golden.verify_entry_files(native), input_id
        o = native.origin
        outcome, _ = map_artefact(native.native_bytes(), Origin.git(o["repo"], o["commit"], o["path"], o["git_blob_sha1"]),
                                  profile_id="agentdojo-upstream")
    assert not outcome.degenerate, input_id
    data, _ = aer_bytes(outcome)
    return load_aer_bytes(data)


@cache
def _gate_d(input_id: str, kind: str) -> dict[str, Any]:
    doc = _aer(input_id, kind)
    profile = _profile()
    sem, sem_again = annotate(doc, profile), annotate(doc, profile)
    profiles = {PROFILE: profile}
    first = derive(doc, [sem], sem_profiles=profiles)
    second = derive(doc, [sem_again], sem_profiles=profiles)
    return {"doc": doc, "sem": sem, "sem_bytes": (dumps_sem(sem), dumps_sem(sem_again)), "prov": first,
            "prov_again": second.prov_json}


def _ids() -> list[Any]:
    return [pytest.param(i, k, id=i) for i, k in _inputs()] or [pytest.param(None, None, id="no-golden-fixtures")]


def _require(input_id: str | None) -> None:
    if input_id is None:
        pytest.skip(golden.golden_skip_reason() or "no golden fixtures")


def test_the_golden_scope_is_19_v1_aers_and_9_native_logs():
    if not golden.golden_available():
        pytest.skip(golden.golden_skip_reason() or "no golden fixtures")
    kinds = [k for _i, k in _inputs()]
    assert (kinds.count("v1"), kinds.count("native")) == (19, 9)


@pytest.mark.parametrize(("input_id", "kind"), _ids())
def test_sem_is_deterministic_and_passes_tier_3(input_id: str | None, kind: str | None) -> None:
    _require(input_id)
    assert kind is not None and input_id is not None
    run = _gate_d(input_id, kind)
    assert run["sem_bytes"][0] == run["sem_bytes"][1]
    report = validate_sem_document(run["sem"], run["doc"], mode="release", profile=_profile())
    assert report.ok and not report.errors and not report.skipped, [f.code for f in report.errors]


@pytest.mark.parametrize(("input_id", "kind"), _ids())
def test_prov_with_the_assessment_bundle_is_deterministic_and_passes_tier_4(input_id: str | None, kind: str | None) -> None:
    _require(input_id)
    assert kind is not None and input_id is not None
    run = _gate_d(input_id, kind)
    result = run["prov"]
    assert result.prov_json == run["prov_again"]
    assessment = [b for b in result.bundles if b.kind == "assessment"]
    assert len(assessment) == 1 and assessment[0].profile == "agentdojo.suites@1"
    report = validate_prov(result.prov_json, run["doc"], migration=kind == "v1", sems=[run["sem"]])
    failures = [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status != "pass"
                and o.status != "not_applicable"]
    assert report.passed and failures == [], failures


def test_the_sem_and_prov_digests_equal_the_pins():
    if not golden.golden_available():
        pytest.skip(golden.golden_skip_reason() or "no golden fixtures")
    observed = {
        i: {"prov": "sha256:" + sha256_hex(_gate_d(i, k)["prov"].prov_json), "sem": "sha256:" + _gate_d(i, k)["sem"].digest}
        for i, k in _inputs()
    }
    if os.environ.get(REGEN) == "1":
        DIGESTS.write_text(json.dumps(observed, indent=1, sort_keys=True) + "\n")
    pinned = json.loads(DIGESTS.read_text())
    changed = sorted(i for i in observed if pinned.get(i) != observed[i])
    assert changed == [] and set(pinned) == set(observed), f"gate-D digests changed without a version bump: {changed}"
