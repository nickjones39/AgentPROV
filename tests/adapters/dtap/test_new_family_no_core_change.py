"""The new-family test for DTap (docs/architecture D.16.14 test 13; the D.12.3 analogue; K.6.4).

1. The adding branch changes only the family's files, its tests, fixtures and tools, the registry entry, the runner
   items R1-R3 and documentation: nothing under ``aer/``, ``prov/``, ``validate/`` or ``corpus/`` (invariant 5).
2. PROV derived from F07 (a tool-description suffix visible in the logged tool list) and F04 (a configured-only tool
   payload) holds the named statements and the named, disclosed gaps.
"""

from __future__ import annotations

import json
import sys
from fnmatch import fnmatch
from pathlib import Path

import dtap_support as support
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from new_family_guard import changed_or_skip  # noqa: E402

ALLOWED = (
    "src/agentprov/adapters/dtap/*", "tests/adapters/dtap/*", "tests/fixtures/dtap/*", "tests/fixtures/LICENSES/DTap-Bench-*",
    "tools/dtap/*", "src/agentprov/adapters/registry/__init__.py", "src/agentprov/adapters/runner/__init__.py",
    "src/agentprov/adapters/runner/importer.py", "tests/adapters/runner/*", "docs/*", "AGENTS.md",
    # the analysis tools read DTap's role `agent` through one grouping (sample-check fix b4, user-approved 2026-10-12)
    "tools/analysis/*", "tools/analysis2/*",
    # D-607: the D-31 pins of the dtap-bench@1 / dtap@1 archives, and the regenerated README source and corpus blocks
    "tests/unit/test_d31_bumps.py", "README.md", "tools/readme_corpora.toml",
    # D-607 (user decision 2026-10-21): the datasheet disclosure of the raw host accounts and its row test
    "corpora/datasheet-statements.toml", "tests/unit/corpus/test_datasheet.py",
)
PROTECTED = ("src/agentprov/aer/", "src/agentprov/prov/", "src/agentprov/validate/", "src/agentprov/corpus/")




def test_the_branch_touches_only_the_family_and_the_listed_runner_items():
    changed = changed_or_skip(support.REPO)  # the merge base with origin/main or main, the newer
    if not any(p.startswith("src/agentprov/adapters/dtap/") for p in changed):
        # the guard is about the branch that adds or changes the family; another branch's core change (e.g. D-81) is
        # recorded under invariant 5 by its own decision
        pytest.skip("this branch does not change the dtap family")
    assert not [p for p in changed if p.startswith(PROTECTED)]
    assert [p for p in sorted(changed) if not any(fnmatch(p, g) for g in ALLOWED)] == []


def _bundles(m):
    return json.loads(m.prov.prov_json)["bundle"]


def _statements(bundles, section):
    for name, content in bundles.items():
        for key, body in content.get(section, {}).items():
            yield name, key, body


def _cls(body):
    return body.get("apv:evidenceClass", {}).get("$")


def test_named_statements_and_gaps_f07(mapped):
    m = mapped["F07"]
    bundles = _bundles(m)
    used = [(b, s) for b, _k, s in _statements(bundles, "used") if s["prov:activity"].startswith("x:te")]
    assert used and all(".inf." in b and _cls(s) == "apv:Inferred" and s["apv:rule"] == "aprov.use_request@1" for b, s in used)
    exposures = [(b, s) for b, _k, s in _statements(bundles, "entity") if "dtap.exposure" in json.dumps(s)]
    (bundle, observed), = exposures
    assert ".assess." in bundle and _cls(observed) == "apv:Derived"
    assert json.loads(observed["apv:annotationValue"])["class"] == "observed_description_log"
    payload = next(f["id"] for f in m.of("fixture") if f["kind"] == "injection_payload")
    holders = [b for b, k, _s in _statements(bundles, "entity") if k == f"x:{payload}"]
    assert holders and all(".inf." in b for b in holders)  # the payload fixture is an inference-bundle entity


def test_named_gaps_configured_only_f04(mapped):
    m = mapped["F04"]
    bundles = _bundles(m)
    configured = [s for _b, _k, s in _statements(bundles, "entity")
                  if "configured_only" in str(s.get("apv:annotationValue", ""))]
    assert configured and all(_cls(s) == "apv:Inferred" for s in configured)
    prov = m.prov.prov_json
    assert b"prov:endedAtTime" not in prov and b"prov:endTime" not in prov and b"prov:startTime" not in prov
    informed = [s for _b, _k, s in _statements(bundles, "wasInformedBy")]
    assert informed and {s["apv:rule"] for s in informed} == {"aprov.comm@1"}  # closure only: never from array order
    config_sha = next(a["sha256"] for a in m.header["artifacts"] if a["origin"]["path"].endswith("config.yaml"))
    assert not [s for _b, _k, s in _statements(bundles, "used") if s["prov:entity"] == f"raw:sha256-{config_sha}"]
    core = {k: v for k, v in bundles.items() if ".core." in k}
    for fixture in (f["id"] for f in m.of("fixture") if f["kind"] == "injection_payload"):
        assert f'"x:{fixture}"' not in json.dumps(core)


def test_aer_and_prov_validate_with_no_core_change(mapped):
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records
    from agentprov.validate import validate_prov

    for fid in ("F07", "F04"):
        m = mapped[fid]
        assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []
        report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="dev")
        assert report.ok, fid
