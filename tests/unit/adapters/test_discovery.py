"""Adapter families are discovered from package data (DoD Q.3): no core table names a family.

A new framework adds ``adapters/<family>/`` with ``profiles/`` and ``rules/<family>.rules.toml``; the profile loader and
the rule-catalogue loader find them by convention, without importing the family's modules, and the runner hands a
mapper the bytes of its unit's auxiliary artefacts.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from agentprov.adapters.profiles import load_profile, profile_families
from agentprov.adapters.runner import MapContext
from agentprov.aer import rules
from agentprov.errors import AgentProvError


def test_profile_families_are_the_adapter_packages_with_profiles() -> None:
    families = profile_families()
    assert "adprov" in families
    assert list(families) == sorted(families)
    assert all(not f.startswith(("_", ".")) for f in families)


def test_no_core_table_lists_adapter_families() -> None:
    assert not hasattr(sys.modules["agentprov.adapters.profiles"], "FAMILIES")
    # core namespaces (`aer`, `corpus`, and `cap`, shipped by the capture distribution, C.6.4) and the namespaces that
    # live in another family's package; no family is listed for being a family
    assert set(rules.CATALOGUE_HOMES) == {"aer", "corpus", "cap", "rope", "agentdyn", "drift", "mandate", "survey",
                                          "autodojo", "rescont", "defence", "anthropic_messages"}  # anthropic_messages: D-656


def test_a_family_namespace_resolves_by_convention() -> None:
    assert rules.load_catalogue("adprov").namespace == "adprov"
    with pytest.raises(rules.CatalogueUnavailableError):
        rules.load_catalogue("nosuchfamily")
    with pytest.raises(rules.CatalogueUnavailableError):
        rules.load_catalogue("../aer")


def test_discovery_imports_no_adapter_module() -> None:
    code = (
        "import sys; from agentprov.adapters.profiles import load_profile, profile_families; "
        "from agentprov.aer.rules import load_catalogue; profile_families(); load_profile('adprov-v1'); "
        "load_catalogue('adprov'); "
        "bad = sorted(m for m in sys.modules if m.startswith('agentprov.adapters.') and m.count('.') >= 2 "
        "and m.split('.')[2] not in {'profiles', 'types', 'protocols', 'registry'}); print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


def test_auxiliary_bytes_reach_the_mapper() -> None:
    profile = load_profile("adprov-v1")
    ctx = MapContext(profile, rules.RuleRegistry.default(), "m/p", "ex_x", {"handoff": b"{}"})
    assert ctx.open_auxiliary("handoff") == b"{}"
    with pytest.raises(AgentProvError) as info:
        ctx.open_auxiliary("other")
    assert info.value.code == "adapter.auxiliary_missing"
    with pytest.raises(AgentProvError):
        MapContext(profile, rules.RuleRegistry.default(), "m/p", "ex_x").open_auxiliary("handoff")
