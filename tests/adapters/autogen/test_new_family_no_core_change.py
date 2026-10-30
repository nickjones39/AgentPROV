"""The new-family test for the AutoGen guard-placement deposit (docs/architecture D.19.12; the D.12.3 analogue).

The adding branch changes only the family's files, its tests and fixtures, the registry entry, the ATIA inspect profile
of the same phase, documentation, and one runner test that lists the families with per-unit inputs. Nothing under
aer/, prov/, validate/, corpus/, runner/ (code), raw/ or ingest/ (D-301: the row-unit capability is routed, R-10n-3).
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch
from pathlib import Path

import autogen_support as support
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from new_family_guard import changed_or_skip  # noqa: E402

ALLOWED = (
    "src/agentprov/adapters/autogen/*", "tests/adapters/autogen/*", "tests/fixtures/autogen/*", "tools/autogen/*",
    "src/agentprov/adapters/registry/__init__.py", "docs/*", "AGENTS.md",
    "tests/adapters/runner/test_per_unit_inputs.py",
    "tests/adapters/runner/test_job_failure_degenerate.py",
    # D-360: the fixture source budget exception of this family
    "tests/FIXTURES.json",
    # part B of the same phase (D-307): the ATIA inspect profile and its tests
    "src/agentprov/adapters/inspect/profiles/atia-benchmark.profile.toml", "tests/adapters/inspect/test_atia.py",
    # D-603: the D-31 pin of the archived profile version 1, the README row note and the regenerated README blocks
    "tests/unit/test_d31_bumps.py", "README.md", "tools/readme_corpora.toml",
)
PROTECTED = ("src/agentprov/aer/", "src/agentprov/prov/", "src/agentprov/validate/", "src/agentprov/corpus/",
             "src/agentprov/adapters/runner/", "src/agentprov/raw/", "src/agentprov/ingest/")




def test_the_branch_touches_only_the_family():
    changed = changed_or_skip(support.REPO)  # the merge base with origin/main or main, the newer
    if not any(p.startswith("src/agentprov/adapters/autogen/") for p in changed):
        pytest.skip("this branch does not change the autogen family")
    assert [p for p in changed if p.startswith(PROTECTED)] == []
    assert [p for p in sorted(changed) if not any(fnmatch(p, g) for g in ALLOWED)] == []
