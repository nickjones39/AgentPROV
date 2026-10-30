"""The new-family test for OpenHands (docs/architecture D.17.12; the D.12.3 analogue; K.6.4; invariant 5).

The adding branch changes only the family's files, its tests, fixtures and tools, the registry entry, the runner test that
lists the registered families using per-unit inputs (D.16.14 R1; test code only) and documentation: nothing under ``aer/``, ``prov/``, ``validate/``, ``corpus/``, ``runner/``, ``raw/`` or ``ingest/``.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch
from pathlib import Path

import openhands_support as support
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from new_family_guard import changed_or_skip  # noqa: E402

ALLOWED = (
    "src/agentprov/adapters/openhands/*", "tests/adapters/openhands/*", "tests/fixtures/openhands/*",
    "tests/fixtures/LICENSES/OpenAgentSafety-*", "tests/fixtures/LICENSES/SOURCE.json", "tools/openhands/*",
    "src/agentprov/adapters/registry/__init__.py", "tests/adapters/runner/test_per_unit_inputs.py", "docs/*", "AGENTS.md",
    "tests/unit/test_d31_bumps.py", "README.md",  # D-606: the D-31 pins of catalogue openhands and openagentsafety v1
    "corpora/datasheet-statements.toml",  # D-606: the openagentsafety raw-account-paths disclosure (D-186 (c))
    # D-950: a catalogue-only pass across families (the wave-2 artefact scope) edits other families' artefact catalogues
    # and their catalogue tests; data, never a protected core folder
    "src/agentprov/adapters/*/artefacts.toml", "tests/adapters/*/test_artefacts.py", "tests/adapters/agentdojo/test_profile.py",
    "tests/adapters/*/test_new_family_no_core_change.py",
)
PROTECTED = ("src/agentprov/aer/", "src/agentprov/prov/", "src/agentprov/validate/", "src/agentprov/corpus/",
             "src/agentprov/adapters/runner/", "src/agentprov/raw/", "src/agentprov/ingest/", "src/agentprov/worker.py")




def test_the_branch_touches_only_the_family():
    changed = changed_or_skip(support.REPO)  # the merge base with origin/main or main, the newer
    if not any(p.startswith("src/agentprov/adapters/openhands/") for p in changed):
        pytest.skip("this branch does not change the openhands family")
    assert not [p for p in changed if p.startswith(PROTECTED)]
    assert [p for p in sorted(changed) if not any(fnmatch(p, g) for g in ALLOWED)] == []
