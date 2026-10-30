"""The new-family test for AgentOps-Bench (docs/architecture D.18.12; the D.12.3 analogue; K.6.4).

The adding branch changes only the family's files, its tests, fixtures, the registry entry and documentation, plus the one
core change the user approved under invariant 5: the register code select.out_of_scope in corpus/register.py and
adapters/profiles.py (D-191, 2026-10-12). Nothing else under aer/, prov/, validate/ or corpus/.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch
from pathlib import Path

import agentops_support as support
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from new_family_guard import changed_or_skip  # noqa: E402

ALLOWED = (
    "src/agentprov/adapters/agentops/*", "tests/adapters/agentops/*", "tests/fixtures/agentops/*",
    "tests/fixtures/LICENSES/AgentOps-Bench-*", "src/agentprov/adapters/registry/__init__.py", "docs/*", "AGENTS.md",
    # D-191 (user-approved 2026-10-12): the new register code and its tests
    "src/agentprov/adapters/profiles.py", "src/agentprov/corpus/register.py", "tests/unit/corpus/test_register.py",
    "tests/adapters/runner/test_profile_selection.py", "tests/adapters/runner/test_per_unit_inputs.py",
    "README.md",  # D-608: the generated source table carries the profile's [withhold] note
    "corpora/datasheet-statements.toml",  # D-608: the known-issues statement for agentops-bench
)
PROTECTED = ("src/agentprov/aer/", "src/agentprov/prov/", "src/agentprov/validate/", "src/agentprov/corpus/")
APPROVED_CORE = {"src/agentprov/corpus/register.py"}




def test_the_branch_touches_only_the_family_and_the_approved_core_code():
    changed = changed_or_skip(support.REPO)  # the merge base with origin/main or main, the newer
    if not any(p.startswith("src/agentprov/adapters/agentops/") for p in changed):
        pytest.skip("this branch does not change the agentops family")
    assert [p for p in changed if p.startswith(PROTECTED) and p not in APPROVED_CORE] == []
    assert [p for p in sorted(changed) if not any(fnmatch(p, g) for g in ALLOWED)] == []
