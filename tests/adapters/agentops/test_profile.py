"""Profile, registry entry and family schema of the ``agentops`` family (docs/architecture D.18.10, D.3; D-190, D-191)."""

from __future__ import annotations

import json
import tomllib

import agentops_support as support

from agentprov.adapters.profiles import SELECT_CODES, load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "agentops"


def test_profile_pins_licence_import_and_family_schema():
    import jsonschema

    profile = load_profile(support.PROFILE)
    assert (profile.family, profile.source_id, profile.parts) == ("agentops", "agentops-bench", ("pilot-v1-seeded",))
    pins = {p["role"]: p for p in profile.data["source"]["pins"]}
    assert pins["runs"]["sha256"] == support.TAR_SHA256 and pins["runs"]["primary"] is True
    assert (pins["tasks"]["kind"], pins["tasks"]["repo"], pins["tasks"]["commit"]) == ("git", support.TASKS_REPO, support.TASKS_COMMIT)
    assert pins["tasks"]["primary"] is False and pins["tasks"]["tree"] == "tasks/"
    # the archival twin of the tasks pin: the Zenodo zip of the same tag, never imported (README §10)
    assert pins["tasks_archive"]["sha256"] == support.ZIP_SHA256 and pins["tasks_archive"]["primary"] is False
    assert {p["doi"] for p in pins.values() if p["kind"] == "zenodo"} == {"10.5281/zenodo.19875693"}
    assert imp_context(profile) == ["tasks:tasks/*/*.yaml"]
    assert profile.data["licence"]["spdx"] == "Apache-2.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "agentops.trace" and imp["variants"] == ("v1",)
    assert {e["code"] for e in imp["exclude"]} == {"select.out_of_scope", "select.not_execution_artefact"} <= SELECT_CODES
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / f"{support.PROFILE}.profile.toml").read_text(encoding="utf-8"))["family"]["agentops"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    assert family["semantics_profile"] == {"id": "agentops.tools", "version": 2}
    assert family["task_table"]["rows"] == 100


def imp_context(profile) -> list[str]:
    return list(profile.data["import"]["context_artefacts"])


def test_the_task_table_names_paths_of_the_git_tasks_pin():
    """D-194 with the git pin: every row is a ``tasks/<domain>/<file>.yaml`` path under the pin's tree, and the table
    records the pin's repository and commit and the archival twin it was first generated from."""
    from agentprov.adapters.agentops.dialect import task_files

    table = tomllib.loads((SRC / "tables" / "task_files.toml").read_text(encoding="utf-8"))
    assert (table["repo"], table["commit"]) == (support.TASKS_REPO, support.TASKS_COMMIT)
    assert table["archive_twin"]["sha256"] == support.ZIP_SHA256 and table["archive_twin"]["root"] == support.ZIP_ROOT
    rows = task_files()
    assert len(rows) == 100 and all(r.label.startswith("tasks/") and r.label.count("/") == 2 for r in rows.values())


def test_out_of_scope_globs_are_exactly_the_complement_of_the_scope():
    """Every exclude entry with select.out_of_scope names a clean or noisy condition and a non-safety domain, and every
    such (condition, domain) pair has one entry (D-143 as data: [family.agentops] in_scope)."""
    profile = load_profile(support.PROFILE)
    family = profile.family_table()
    scope = family["in_scope"]
    pairs = set()
    for entry in profile.data["import"]["exclude"]:
        if entry["code"] != "select.out_of_scope":
            continue
        _root, _agent, _model, cond, name = entry["glob"].split("/")
        dom = name.split("_*_run", 1)[0]
        assert cond not in scope["conditions"] and dom not in scope["domains"] and entry["note"].startswith("D-143")
        pairs.add((cond, dom))
    domains = {"code", "data_analysis", "research", "tool_use", "safety"} - set(scope["domains"])
    assert pairs == {(c, d) for c in set(family["conditions"]) - set(scope["conditions"]) for d in domains}


def test_appledouble_run_members_are_never_selected_for_expansion():
    """The deposit's AppleDouble ``._*_run*.json`` copies match no include glob, so the expand stage records them
    ``not_selected`` and never decompresses or stores them (R-40); the real run files stay selected."""
    from agentprov.raw import members

    # the matcher the expand stage compiles from the selection's include (``raw.members`` ``selected``)
    include = members._compile(members.Selection(include=tuple(load_profile(support.PROFILE).data["import"]["include"])).include)
    assert include is not None
    base = "pilot_v1_seeded/agent/model"
    for condition, name in (("adversarial", "code_001_run1.json"), ("clean", "safety_001_run2.json"),
                            ("noisy", "safety_010_run3.json")):  # fmt: skip
        assert include.match(f"{base}/{condition}/{name}") is not None
        assert include.match(f"{base}/{condition}/._{name}") is None


def test_registry_entry_is_supported_and_apache_without_restriction():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source("agentops-bench")
    (part,) = reg.capabilities
    assert part.part == "pilot-v1-seeded" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == support.PROFILE and part.semantics == ("agentops.tools@2",) and part.corpus_id == "agentops-bench"
    assert reg.licence.spdx == "Apache-2.0" and reg.licence.restrictions == () and reg.licence.policy == "include"
    assert resolve_factory(READERS["agentops.trace"]).__name__ == "AgentOpsTraceReader"
    assert resolve_factory(MAPPERS["agentops.trace"]).__name__ == "AgentOpsMapper"
