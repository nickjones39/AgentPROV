"""The phase-10h AgentHarm Inspect profiles (D-180..D-185; phase-10e cards §3.3, §3.4; docs/architecture D.9.8).

No real log of either source is committed: every finished log, and both unfinished ones, records a workstation account
path somewhere (dataset location, checkpoint model ids, memory-bank parameters, tracebacks), and raw bytes are never
edited (user decision 2026-10-12, docs/reports/phase10h/README.md §4). The tests therefore use synthetic logs built in
code (``inspect_support``; synthetic text only, a made-up account name) and, when the pinned commits are in the fetch
cache (``agentprov fetch``; ``$AGENTPROV_UPSTREAM_CACHE`` or ``$AGENTPROV_HOME/cache``), the real pinned logs, read in
memory. AgentHarm holds harmful requests by design and the real logs hold account names: nothing here prints or quotes
their content (R-42); assertions compare counts, codes and digests.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.rules import load_catalogue

PROFILES = {
    "kexin-xu-01-agentharm": ("859c34f411fdf8d6a01670da2d2460d21e739e7e", "logs", 68, 36467328, ["0.3.263"]),
    "fragfuse-agentharm": ("24cc8aea1b9906bee20fb585007410a5d885933a", None, 3847, 318827530,
                           ["0.3.154.dev37+g1289c1ad", "0.3.158", "0.3.159.dev20+g3ddd7997"]),
}
NONE_NONE = {
    "logs_archive/2025-12-30T22-06-25+00-00_agentharm-benign_KGn46FpufqVFoqh8omxcQa.eval",
    "logs_archive/2025-12-30T22-06-25+00-00_agentharm_cXghW9ubBnVHXWDUAUbjEb.eval",
    "logs_archive/2025-12-30T22-07-17+00-00_agentharm-benign_KGn46FpufqVFoqh8omxcQa.eval",
    "logs_archive/2025-12-30T22-07-17+00-00_agentharm_cXghW9ubBnVHXWDUAUbjEb.eval",
}
#: A made-up account name for the synthetic redaction cases (never a real one).
FAKE_ACCOUNT = "synthetic-account-7q"


def _toml(profile_id: str) -> dict[str, Any]:
    path = support.REPO / "src/agentprov/adapters/inspect/profiles" / f"{profile_id}.profile.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _trial_tool() -> Any:
    spec = importlib.util.spec_from_file_location("phase10h_trial", support.REPO / "tools/inspect/phase10h_trial.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _header(producer: str, model: str = "openai/gpt-4o-2024-08-06") -> dict[str, Any]:
    header = support.synthetic_header(producer)
    header["eval"]["model"] = model
    return header


# ------------------------------------------------------------------------------------------------ profiles and registry
@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_profile_pin_licence_and_band(profile_id: str) -> None:
    commit, tree, files, size, band = PROFILES[profile_id]
    profile, data = load_profile(profile_id), _toml(profile_id)
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["kind"] == "git" and pin["commit"] == commit and pin.get("tree") == tree
    assert (pin["expected_files"], pin["expected_bytes"]) == (files, size)
    licence = data["licence"]
    assert licence["spdx"] == "MIT" and licence["policy"] == "include"
    assert any("additional clause" in r for r in licence["restrictions"]), "AgentHarm use clause (LIC 3)"
    family = data["family"]["inspect"]
    assert family["benchmark"] == "agentharm" and family["producer_band"]["inspect_ai"] == band
    assert family["span_roles"] == {"solver": "agent", "scorer": "judge"} and family["log_versions"] == [2]
    assert profile.version == 2 and profile.family == "inspect" and profile.parts == ("logs",)


@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_family_table_conforms_to_the_closed_schema(profile_id: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((support.REPO / "src/agentprov/adapters/inspect/family.schema.json").read_bytes())
    jsonschema.validate(_toml(profile_id)["family"]["inspect"], schema)


@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_quirk_rules_exist(profile_id: str) -> None:
    for quirk in _toml(profile_id)["family"]["inspect"].get("quirk", ()):
        for rule in quirk.get("rules", ()):
            entry = load_catalogue("inspect").get(rule)
            assert entry is not None and entry.citable, (quirk["id"], rule)


def test_attack_declaration_d184() -> None:
    """kexin is plain AgentHarm (no_attack, as the survey); fragfuse mixes plain runs and attack experiments, so it
    declares nothing and task.attack_id stays unrecorded (D-184)."""
    assert _toml("kexin-xu-01-agentharm")["family"]["inspect"]["no_attack"] is True
    assert "no_attack" not in _toml("fragfuse-agentharm")["family"]["inspect"]


@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_registry_part_is_supported_restricted_and_its_own_corpus(profile_id: str) -> None:
    registration = get_source(profile_id)
    (part,) = registration.capabilities
    assert part.part == "logs" and part.profile == profile_id and part.corpus_id == profile_id
    assert part.import_status == "supported" and part.target_import_status == "supported"
    assert part.semantics == ("inspect.agentharm@2",)  # D-31 option B: @1 on the inspect catalogue version 2
    assert registration.family == "inspect" and registration.licence.spdx == "MIT"
    assert registration.licence.restrictions and "additional clause" in registration.licence.restrictions[0]


def test_fragfuse_selection_excludes_exactly_the_none_none_logs_d183() -> None:
    from agentprov.adapters.runner.importer import _match

    imp = _toml("fragfuse-agentharm")["import"]
    excluded = [e for e in imp["exclude"] if e.get("note", "").startswith("model none/none")]
    assert {e["glob"] for e in excluded} == NONE_NONE
    assert {e["code"] for e in excluded} == {"select.not_execution_artefact"}

    def selected(label: str) -> bool:
        return any(_match(label, g) for g in imp["include"]) and not any(_match(label, e["glob"]) for e in imp["exclude"])

    assert not any(selected(p) for p in NONE_NONE)
    assert selected("logs_archive/2025-12-30T04-56-15+00-00_agentharm-benign_eNvdDKEU4JLRNbwg85dLup.eval")
    assert selected("logs_archive/agentharm_2025-12-30_run1/x.eval")
    assert selected("src/inspect_evals/agentharm/tasks10_outputs/retrieve_test_logs_memory/task_1-1/x.eval")
    assert not selected("src/inspect_evals/agentharm/agentharm.py")
    assert not selected("src/inspect_evals/other_task/logs/x.eval")


# ------------------------------------------------------------------------------------------------ synthetic logs
@pytest.mark.parametrize(("profile_id", "producer"), [("kexin-xu-01-agentharm", "0.3.263"), ("fragfuse-agentharm", "0.3.158")])
def test_a_band_log_maps_to_valid_aer(tmp_path: Path, profile_id: str, producer: str) -> None:
    data = support.build_eval(_header(producer), {"1-1_epoch_1.json": support.basic_sample("1-1")})
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile(profile_id))
    (unit,) = imp.units
    assert not imp.register and not unit.outcome.degenerate
    report = _validate(imp, unit, profile_id)
    assert report.ok, [f.code for f in report.findings if f.severity == "error"]
    task = unit.header["task"]
    assert task["benchmark"] == "agentharm" and task["task_id"] == "1-1"
    assert ("attack_id" in task) is (profile_id == "kexin-xu-01-agentharm")


def _validate(imp: support.Imported, unit: support.Unit, profile_id: str) -> Any:
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import AerValidator

    profile = load_profile(profile_id)
    validator = AerValidator(store=imp.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    return validator.finish()


@pytest.mark.parametrize("producer", ["0.3.247.dev69+g53c1fa98b", "0.3.130"])
def test_a_producer_outside_the_band_is_planned(tmp_path: Path, producer: str) -> None:
    data = support.build_eval(_header(producer), {"1-1_epoch_1.json": support.basic_sample("1-1")})
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile("kexin-xu-01-agentharm"))
    assert not imp.units and [r["code"] for r in imp.register] == ["select.dialect_planned"]


def test_an_unfinished_log_without_header_is_planned(tmp_path: Path) -> None:
    """kexin's two unfinished logs hold _journal/ members and samples but no header.json (quirk inspect.unfinished_log)."""
    import io
    import warnings
    import zipfile

    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for name, body in (("_journal/start.json", {"version": 2, "eval": _header("0.3.263")["eval"]}),
                               ("samples/1-1_epoch_1.json", support.basic_sample("1-1")),
                               ("_journal/summaries/1.json", [])):
                info = zipfile.ZipInfo(name, (2026, 9, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_ZSTANDARD
                z.writestr(info, json.dumps(body).encode())
    imp = support.import_log(buf.getvalue(), tmp_path, path="logs/x.eval", profile=load_profile("kexin-xu-01-agentharm"))
    assert not imp.units
    assert [(r["code"], r["detail"]) for r in imp.register] == [("select.dialect_planned", "inspect.eval: no header.json member")]


@pytest.mark.parametrize("model", [
    f"vllm//workspace/{FAKE_ACCOUNT}/outputs/job-1/run-train_1-0/merged",
    f"vllm/Qwen/Qwen3-14B:/workspace/{FAKE_ACCOUNT}/outputs/job-1/run-train_2-0/lora",
    f"vllm//Users/{FAKE_ACCOUNT}/models/ckpt",
])
def test_the_trial_tool_flags_local_path_model_ids(model: str) -> None:
    tool = _trial_tool()
    assert tool._local_path_model(support.build_eval(_header("0.3.263", model), {})) is True


@pytest.mark.parametrize("model", ["vllm/Qwen/Qwen3-14B", "openai/gpt-4o-2024-08-06", "anthropic/claude-sonnet-5"])
def test_the_trial_tool_keeps_hub_model_ids(model: str) -> None:
    assert _trial_tool()._local_path_model(support.build_eval(_header("0.3.263", model), {})) is False


def _account_pointers(unit: support.Unit) -> set[str]:
    found: set[str] = set()

    def walk(value: object, ptr: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{ptr}/{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{ptr}/{i}")
        elif isinstance(value, str) and FAKE_ACCOUNT in value:
            found.add(re.sub(r"/[0-9]+(?=/|$)", "/*", ptr))

    for record in unit.records:
        walk(record, f"{record['k']}:")
    return found


def _path_model_unit(tmp_path: Path) -> support.Unit:
    model = f"vllm//workspace/{FAKE_ACCOUNT}/outputs/job-1/run-train_1-0/merged"

    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "model" and e["model"].startswith("ollama/synthetic-agent"):
                e["model"] = model
                e["output"]["model"] = model.split("/", 1)[1]

    data = support.build_eval(_header("0.3.263", model), {"1-1_epoch_1.json": support.basic_sample("1-1", tune=tune)})
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile("kexin-xu-01-agentharm"))
    (unit,) = imp.units
    return unit


def test_the_redacted_model_id_is_a_salted_label_that_keeps_the_leaf(tmp_path: Path) -> None:
    """The gap D-182 closed (item 107): the id reached the agent actor and every model call verbatim; now both hold the
    profile's label, which keeps the checkpoint kind (merged) and a salted digest of the path, never the path."""
    unit = _path_model_unit(tmp_path)
    (agent,) = [a for a in unit.of_kind("actor") if a["id"] == "agent"]
    assert re.fullmatch(r"vllm/<local-checkpoint:[0-9a-f]{12}/merged>", agent["model"]["requested"])
    served = {m.get("served_model") for m in unit.of_kind("model_call") if m.get("served_model")}
    assert agent["model"]["requested"].split("/", 1)[1] in served and not any("/workspace/" in str(v) for v in served)


def test_a_redacted_model_id_leaves_no_account_in_the_aer(tmp_path: Path) -> None:
    """D-182, applied by regeneration-batch item 107: kexin-xu-01's local checkpoint path is redacted."""
    assert _account_pointers(_path_model_unit(tmp_path)) == set()


def test_a_traceback_account_path_does_not_reach_ext(tmp_path: Path) -> None:
    """D-182, applied by regeneration-batch item 107: fragfuse's /Users/<account>/ in copied harness text is redacted."""
    error = {"message": "synthetic failure", "traceback": f'File "/Users/{FAKE_ACCOUNT}/x.py", line 1',
             "traceback_ansi": f'File "/Users/{FAKE_ACCOUNT}/x.py", line 1'}
    data = support.build_eval(_header("0.3.158"), {"1-1_epoch_1.json": support.basic_sample("1-1", tune=lambda s, d: d.update(error=error))})
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile("fragfuse-agentharm"))
    (unit,) = imp.units
    assert _account_pointers(unit) == set()


# ------------------------------------------------------------------------------------------------ the pinned logs
def _pinned(profile_id: str) -> tuple[Any, Any]:
    from agentprov.adapters.runner.importer import GitPinTree
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(profile_id)
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=profile.data["source"]["canonical_repo"])
    fetcher = Fetcher(resolve_cache_dir(None))
    if not fetcher.plan(recipe).cached:
        pytest.skip(f"the pinned commit of {profile_id} is not in the fetch cache (agentprov fetch)")
    return GitPinTree(fetcher, recipe), profile


@pytest.mark.parametrize(("profile_id", "selected"), [("kexin-xu-01-agentharm", 68), ("fragfuse-agentharm", 164)])
def test_pinned_tree_selection(profile_id: str, selected: int) -> None:
    tree, profile = _pinned(profile_id)
    _, _, files, size, _ = PROFILES[profile_id]
    assert len(tree.entries) == files and sum(e.size or 0 for e in tree.entries.values()) == size
    assert len(_trial_tool()._selected(tree, profile)) == selected


@pytest.mark.slow
def test_pinned_kexin_local_path_model_logs() -> None:
    """18 of the 68 logs name a local checkpoint; 2 have no header (census, docs/reports/phase10h/)."""
    tree, profile = _pinned("kexin-xu-01-agentharm")
    tool = _trial_tool()
    logs = tool._selected(tree, profile)
    flags = [tool._local_path_model(b.data) for b in tree.fetcher.iter_git_blobs(tree.recipe, [tree.entries[p] for p in logs])]
    assert (flags.count(True), flags.count(None), flags.count(False)) == (18, 2, 48)


@pytest.mark.slow
@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_smallest_pinned_band_log_maps_to_valid_aer(tmp_path: Path, profile_id: str) -> None:
    """The smallest selected log whose header is in the band and whose model id has no path maps without findings."""
    tree, profile = _pinned(profile_id)
    tool = _trial_tool()
    logs = sorted(tool._selected(tree, profile), key=lambda p: tree.entries[p].size or 0)
    for path in logs:
        data = tree.open(path)
        if tool._local_path_model(data) is False:
            break
    else:  # pragma: no cover - the census says otherwise
        pytest.fail("no band log without a local-path model id")
    imp = support.import_log(data, tmp_path, path=path, profile=profile)
    assert imp.units and not imp.register
    for unit in imp.units:
        report = _validate(imp, unit, profile_id)
        assert report.ok and not unit.outcome.degenerate
