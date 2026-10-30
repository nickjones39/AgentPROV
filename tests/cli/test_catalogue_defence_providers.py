"""F-15: the catalogue check (D-652) accepts every defence ``provider`` and ``aux_llm`` the live defence registry
(D-670..D-679, ``backends/shared/src/agentprov_backend/defences.toml``) uses, ``port`` included (D-674: MELON), and
takes them from the registry's data, not from a hand list."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.live.defences import REGISTRY_RELPATH, load_registry, registry_values
from agentprov.cli.run import checked_catalogue
from agentprov.errors import AgentProvError

ROOT = Path(__file__).resolve().parents[2]


def _catalogue(defences: list[dict[str, Any]]) -> dict[str, Any]:
    return {"format": "agentprov-backend-catalogue/0.1", "backend": "agentdojo", "benchmark_version": "v1.2.2",
            "benchmark_versions": ["v1.2.2"], "suites": [{"name": "banking", "user_tasks": [], "injection_tasks": []}],
            "attacks": [], "defences": defences}


def _defence(name: str, provider: str, aux: str) -> dict[str, Any]:
    return {"name": name, "title": "t", "provider": provider, "aux_llm": aux, "licence": "MIT", "refused": None,
            "needs": [], "suites": ["*"], "cost": {}}


def test_every_registry_entry_passes_the_catalogue_check() -> None:
    registry = load_registry(ROOT / REGISTRY_RELPATH)
    providers, aux = registry_values(ROOT)
    assert "port" in providers and {"builtin", "provisioned"} <= providers  # the kinds D-670..D-674 define
    doc = checked_catalogue(_catalogue([_defence(e.id, e.provider, e.aux_llm) for e in registry.values()]),
                            "agentdojo", ROOT)
    assert {(d["name"], d["provider"], d["aux_llm"]) for d in doc["defences"]} == \
        {(e.id, e.provider, e.aux_llm) for e in registry.values()}


@pytest.mark.parametrize("field", ["provider", "aux_llm"])
def test_a_value_the_registry_does_not_use_is_refused(field: str) -> None:
    d = _defence("melon", "port", "none")
    d[field] = "not_a_kind"
    with pytest.raises(AgentProvError, match=r"defence\.provider"):
        checked_catalogue(_catalogue([d]), "agentdojo", ROOT)


def test_the_accepted_values_come_from_the_registry_data(tmp_path: Path) -> None:
    registry = tmp_path / REGISTRY_RELPATH
    registry.parent.mkdir(parents=True)
    registry.write_text('format = "agentprov-defence-registry/0.1"\n\n[[defence]]\nid = "x"\nbackends = ["agentdojo"]\n'
                        'provider = "future_kind"\nsuites = ["*"]\naux_llm = "none"\n', encoding="utf-8")
    assert checked_catalogue(_catalogue([_defence("x", "future_kind", "none")]), "agentdojo", tmp_path)["defences"]
    with pytest.raises(AgentProvError, match=r"defence\.provider"):
        checked_catalogue(_catalogue([_defence("x", "port", "none")]), "agentdojo", tmp_path)


def test_a_catalogue_without_defences_reads_no_registry(tmp_path: Path) -> None:
    assert checked_catalogue(_catalogue([]), "agentdojo", tmp_path / "nowhere")["defences"] == []
    with pytest.raises(AgentProvError, match="registry cannot be read"):
        checked_catalogue(_catalogue([_defence("x", "port", "none")]), "agentdojo", tmp_path / "nowhere")


def test_run_help_lists_every_live_source_of_the_registry() -> None:
    """F-16: ``run --help`` names the live sources from the registry (agentharm included), never a hand list."""
    import io
    from contextlib import redirect_stdout

    from agentprov.adapters.registry import BACKENDS, REGISTRY
    from agentprov.cli.main import main
    from agentprov.cli.run import live_sources

    expected = sorted(r.source_id for r in REGISTRY
                      if any(c.live_status is not None and c.backend in BACKENDS for c in r.capabilities))
    assert live_sources() == expected and {"agentdojo", "autodojo", "agentdyn", "agentharm"} <= set(expected)
    out = io.StringIO()
    with redirect_stdout(out):
        assert main(["run", "--help"]) == 0
    flat = " ".join(out.getvalue().split())
    assert "live source: " + ", ".join(expected[:-1]) + " or " + expected[-1] in flat
