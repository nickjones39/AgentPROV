"""``agentprov run`` (MN N.2.1, N.2.1a; N.1.10(1); DECISIONS D-9, D-10): validation rules and the preset dry run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov.host import GIB

BASE = ("run", "agentdojo")
RUN_CONTEXT = ("--corpus", "C", "--campaign", "k", "--suite", "workspace", "--llm-script")


@pytest.fixture
def script(tmp_path: Path) -> str:
    path = tmp_path / "script.json"
    path.write_text("[]")
    return str(path)


# ---------------------------------------------------------------------------------------------- jobs (N.1.10(1))


def test_jobs_zero_is_a_usage_error_for_run(cli):
    run = cli(*BASE, "--jobs", "0")
    assert run.code == 2
    assert "--jobs must be >= 1" in run.err


def test_negative_jobs_is_a_usage_error(cli):
    assert cli(*BASE, "--jobs", "-3").code == 2


def test_jobs_above_the_host_maximum_is_refused_and_names_the_maximum(cli, host_with):
    host_with(8 * GIB)  # usable 6 GiB / 2 GiB per worker = 3
    run = cli(*BASE, "--jobs", "4")
    assert run.code == 2
    assert "maximum of 3" in run.err and "never clamped silently" in run.err


def test_jobs_at_the_host_maximum_is_not_a_usage_error(cli, host_with, script, tmp_path):
    host_with(8 * GIB)
    run = cli(*BASE, "--jobs", "3", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "workspace", "--llm-script", script)
    assert run.code == 3 and "backends build" in run.err  # passes validation; the fresh $AGENTPROV_HOME has no backend


def test_start_stagger_must_be_non_negative_and_finite(cli):
    assert cli(*BASE, "--start-stagger", "-1").code == 2
    assert cli(*BASE, "--start-stagger", "nan").code == 2
    assert cli(*BASE, "--start-stagger", "inf").code == 2


# ---------------------------------------------------------------------------------------------- model selection


def test_model_selectors_are_mutually_exclusive(cli, script):
    assert cli(*BASE, "--model", "deepseek", "--llm-script", script).code == 2
    assert cli(*BASE, "--model", "deepseek", "--endpoint", "openai", "--model-id", "m").code == 2


def test_endpoint_needs_a_model_id(cli):
    run = cli(*BASE, "--endpoint", "openai")
    assert run.code == 2 and "--model-id" in run.err


def test_unknown_model_shorthand_suggests_a_close_one(cli):
    run = cli(*BASE, "--model", "deepsek")
    assert run.code == 2 and "deepseek" in run.err


def test_known_shorthands_include_the_local_endpoints(cli, tmp_path):
    # D-720: the live part is partial, so a known shorthand passes the status gate and stops at the environment (exit 3)
    for name in ("ollama", "omlx", "deepseek"):
        run = cli(*BASE, "--model", name, "--corpus", str(tmp_path), "--campaign", "k", "--suite", "s")
        assert run.code == 3 and "agentprov backends build agentdojo" in run.err, (name, run.err)


def test_llm_script_must_exist(cli, tmp_path):
    assert cli(*BASE, "--llm-script", str(tmp_path / "missing.json")).code == 2


def test_model_aware_flags_need_a_preset(cli):
    run = cli(*BASE, "--model-size-gb", "60")
    assert run.code == 2 and "--preset" in run.err


def test_m5ultra_conflicts_with_another_preset(cli):
    assert cli(*BASE, "--m5ultra", "--preset", "other").code == 2


def test_unknown_preset_is_a_usage_error(cli, host_with):
    host_with(256 * GIB)
    run = cli(*BASE, "--preset", "nonesuch", "--dry-run", "--model-size-gb", "10")
    assert run.code == 2 and "unknown preset" in run.err


def test_numeric_flag_ranges(cli):
    for flags in (["--repeats", "0"], ["--max-attempts", "0"], ["--canary", "-1"], ["--context-tokens", "0"],
                  ["--model-size-gb", "0"], ["--active-params-b", "-1"], ["--server-max-concurrency", "0"]):  # fmt: skip
        assert cli(*BASE, *flags).code == 2, flags


def test_attack_autodojo_needs_the_cache_and_variant(cli, script, tmp_path):
    run = cli(*BASE, "--corpus", str(tmp_path), "--campaign", "k", "--suite", "s", "--attack", "autodojo", "--llm-script", script)
    assert run.code == 2 and "--autodojo-cache" in run.err


def test_a_real_run_needs_its_context(cli, script):
    assert cli(*BASE, "--llm-script", script).code == 2  # no --corpus


def test_plan_excludes_the_cell_options(cli, script, tmp_path):
    run = cli(*BASE, "--corpus", str(tmp_path), "--campaign", "k", "--plan", "p.toml", "--suite", "s", "--llm-script", script)
    assert run.code == 2 and "--plan excludes" in run.err


# ---------------------------------------------------------------------------------------------- live execution


def test_a_scripted_run_without_a_built_backend_exits_3_and_writes_nothing(cli, script, tmp_path, check_summary):
    run = cli(*BASE, "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "workspace", "--llm-script", script, "--json")
    assert run.code == 3
    document = run.json()
    check_summary(document)
    assert document["outcome"] == "environment"
    assert "agentprov backends build agentdojo" in run.err
    assert not (tmp_path / "c").exists() and not (tmp_path / "c.partial").exists()  # nothing written


def test_a_real_model_run_of_the_partial_live_part_passes_the_status_gate(cli, tmp_path, check_summary):
    """D-720: ``agentdojo`` · ``live`` is ``partial``, so a real-model run is not refused at the gate (exit 5); with no
    backend environment built it stops at the environment check (exit 3) and writes nothing."""
    run = cli(*BASE, "--model", "deepseek", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking", "--json")
    assert run.code == 3
    document = run.json()
    check_summary(document)
    assert document["outcome"] == "environment" and "planned" not in json.dumps(document.get("refusal"))
    assert not (tmp_path / "c").exists() and not (tmp_path / "c.partial").exists()


def test_dry_run_needs_the_run_context(cli):
    assert cli(*BASE, "--dry-run").code == 2


def test_preflight_only_needs_a_model_selection(cli):
    run = cli(*BASE, "--preflight-only")
    assert run.code == 2 and "--preflight-only needs" in run.err


def test_preflight_only_without_a_built_backend_exits_3(cli, script):
    assert cli(*BASE, "--preflight-only", "--llm-script", script).code == 3


def test_live_flags_with_typed_refusals(cli, script, tmp_path):
    ctx = ("--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking", "--llm-script", script)
    run = cli(*BASE, *ctx, "--defence", "drift")
    assert run.code == 5 and "replaces pipeline components" in run.err
    run = cli(*BASE, *ctx, "--defence", "tool_filter")  # allowed by agentdojo-live v3: the run reaches the environment
    assert run.code == 3 and "not built" in run.err
    run = cli("run", "autodojo", *ctx, "--defence", "tool_filter")  # the registry builds it on agentdojo only
    assert run.code == 5 and "builds it on: agentdojo" in run.err
    run = cli(*BASE, *ctx, "--defence", "no_such_defence")
    assert run.code == 5 and "not in the defence registry" in run.err
    assert cli(*BASE, *ctx, "--temperature-policy", "inject").code == 5
    assert cli(*BASE, *ctx, "--corpus-id", "Bad_Id").code == 2
    assert cli("run", "agentdojx", *ctx).code == 2
    assert cli("run", "rope", *ctx).code == 5


# ---------------------------------------------------------------------------------------------- preset dry run


def _plan(cli, *extra: str):
    return cli(*BASE, "--m5ultra", "--dry-run", "--json", *extra)


def test_dry_run_prints_the_resolved_plan(cli, host_with, check_summary):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    run = _plan(cli, "--model-size-gb", "60", "--active-params-b", "10", "--kv-gb-per-trace", "2")
    assert run.code == 0, run.err
    document = run.json()
    check_summary(document)
    assert document["dry_run"] is True
    counters = document["counters"]
    # cross-check against the pure function
    from agentprov.presets import ModelFacts, load_preset, local_concurrency

    host = host_with(256 * GIB, os_family="darwin", arch="arm64")
    facts = ModelFacts().with_flags(model_size_gb=60, active_params_b=10, kv_gb_per_trace=2)
    plan = local_concurrency(load_preset("m5ultra"), facts, host=host)
    assert counters == {"jobs": plan.jobs, "j_compute": plan.j_compute, "j_memory": plan.j_memory, "j_server": plan.j_server}
    assert plan.j_compute == 4 and plan.j_server == 8  # A <= 15 row (m5ultra v2, measured); the oMLX default limit
    err = run.err
    assert "preset m5ultra v2" in err and "binding term" in err
    assert f"J_compute = {plan.j_compute}" in err and f"J_memory = {plan.j_memory}" in err and f"J_server = {plan.j_server}" in err
    assert "source=flag" in err and "source=preset" in err
    assert any("binding term" in n for n in document["notices"])
    assert not any("a real run exits 5" in n for n in document["notices"])  # v2 is calibrated: it runs live


def test_dry_run_jobs_flag_overrides_and_is_reported(cli, host_with):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    run = _plan(cli, "--model-size-gb", "60", "--active-params-b", "10", "--kv-gb-per-trace", "2", "--jobs", "2")
    assert run.code == 0
    assert run.json()["counters"]["jobs"] == 2
    assert "jobs = 2 (flag)" in run.err


def test_dry_run_jobs_above_the_computed_term_warns_but_is_allowed_below_the_host_max(cli, host_with):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    run = _plan(cli, "--model-size-gb", "60", "--active-params-b", "10", "--kv-gb-per-trace", "2", "--jobs", "20")
    assert run.code == 0
    assert any("exceeds the computed" in n for n in run.json()["notices"])


def test_dry_run_jobs_above_the_host_max_is_a_usage_error(cli, host_with):
    host_with(256 * GIB, os_family="darwin", arch="arm64")  # max = 0.75 * 256 / 2 = 96
    run = _plan(cli, "--model-size-gb", "60", "--kv-gb-per-trace", "2", "--jobs", "97")
    assert run.code == 2 and "maximum of 96" in run.err


def test_dry_run_a_model_that_does_not_fit_is_a_usage_error(cli, host_with):
    host_with(32 * GIB, os_family="darwin", arch="arm64")
    run = _plan(cli, "--model-size-gb", "60")
    assert run.code == 2 and "does not fit" in run.err


def test_dry_run_without_model_facts_is_a_usage_error(cli, host_with):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    run = _plan(cli)
    assert run.code == 2 and "model weight size is unknown" in run.err


def test_dry_run_warns_and_records_a_host_mismatch_without_refusing(cli, host_with):
    host_with(256 * GIB, os_family="linux", arch="x86_64")
    run = _plan(cli, "--model-size-gb", "60", "--kv-gb-per-trace", "2")
    assert run.code == 0
    notices = run.json()["notices"]
    assert any("host mismatch" in n and "os_family" in n for n in notices)
    assert "recorded, not refused" in run.err


def test_dry_run_stagger_defaults_to_the_preset_value_and_flag_overrides(cli, host_with):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    base = ("--model-size-gb", "60", "--active-params-b", "10", "--kv-gb-per-trace", "2", "--jobs", "4")
    assert "start stagger 4 s (preset)" in _plan(cli, *base).err
    assert "start stagger 2.5 s (flag)" in _plan(cli, *base, "--start-stagger", "2.5").err


def test_dry_run_reads_the_model_directory_as_untrusted_input(cli, host_with, tmp_path):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text(
        json.dumps({"num_hidden_layers": 32, "num_key_value_heads": 8, "head_dim": 128, "num_attention_heads": 32,
                    "hidden_size": 4096}),  # fmt: skip
    )
    (model / "model-00001.safetensors").write_bytes(b"\0" * 4096)
    # weights are 4 KiB here: fits. The geometry comes from the directory, the rest from the preset.
    run = _plan(cli, "--model-dir", str(model), "--active-params-b", "7")
    assert run.code == 0, run.err
    assert "source=model_dir" in run.err
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    (hostile / "config.json").write_text('{"a": 1, "a": 2}')  # duplicate keys are refused by the strict loader
    bad = _plan(cli, "--model-dir", str(hostile))
    assert bad.code == 1  # a tier-1 violation of untrusted input
    assert "ingest.json.duplicate_key" in bad.err or "duplicate" in bad.err


def test_dry_run_writes_nothing(cli, host_with, tmp_path, monkeypatch):
    host_with(256 * GIB, os_family="darwin", arch="arm64")
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    run = _plan(cli, "--model-size-gb", "60", "--kv-gb-per-trace", "2", "--corpus", str(tmp_path / "c"))
    assert run.code == 0
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_autodojo_scripted_run_passes_the_status_gate(cli, script, tmp_path, check_summary):
    """`autodojo` · `live` is registered `partial` (D-720): a scripted run gets past the gate (as a test_only gate run); with
    no backend environment built it stops at the environment check (exit 3), not at the gate (exit 5)."""
    run = cli("run", "autodojo", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking", "--llm-script", script, "--json")
    assert run.code == 3
    check_summary(run.json())


def test_autodojo_real_run_passes_the_status_gate_as_partial(cli, tmp_path):
    # D-720: partial, so the run stops at the environment check (exit 3), not at the gate (exit 5)
    run = cli("run", "autodojo", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking", "--model", "gemini")
    assert run.code == 3 and "agentprov backends build autodojo" in run.err and "planned" not in run.err


def test_a_plan_s_defence_is_refused_before_spawn_with_exit_5(cli, script, tmp_path):
    # D-679: the plan's [plan] defence gets the flag's check (exit 5), not the worker's plan_refused (exit 2)
    plan = tmp_path / "plan.toml"
    plan.write_text('[plan]\nformat = "agentprov-run-plan/0.1"\nsuites = ["slack"]\ndefence = "mandate_intent"\n')
    run = cli(*BASE, "--corpus", str(tmp_path / "c"), "--campaign", "k", "--plan", str(plan), "--llm-script", script)
    assert run.code == 5 and "runs on banking only" in run.err
    assert not (tmp_path / "c.partial").exists()


# ---------------------------------------------------------------------------------------------- AutoDojo refusals (D.11.7 item 10; D.11.9)
def _autodojo(cli, tmp_path, script, *extra):
    return cli("run", "autodojo", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking",
               "--llm-script", script, *extra)


@pytest.mark.parametrize(("flags", "words"), [
    (("--llm-element", "gateway_compat"), "gateway_compat"),
    (("--attack", "ours"), "OURS_ATTACK_DIR"),
    (("--attack", "variant_generation"), "optimiser"),
    (("--defence", "drift"), "replaces pipeline components"),
    (("--defence", "camel_nopolicy"), "replaces pipeline components"),
])
def test_autodojo_refusals_exit_5_before_anything_starts(cli, script, tmp_path, flags, words):
    run = _autodojo(cli, tmp_path, script, *flags)
    assert run.code == 5 and words in run.err, run.err
    assert not (tmp_path / "c.partial").exists()


def test_the_autodojo_attack_runs_alone_and_only_on_the_fork(cli, script, tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{}")
    run = _autodojo(cli, tmp_path, script, "--attack", "autodojo,important_instructions", "--autodojo-cache", str(cache),
                    "--autodojo-variant", "0")
    assert run.code == 2 and "on its own" in run.err
    run = cli("run", "agentdojo", "--corpus", str(tmp_path / "c"), "--campaign", "k", "--suite", "banking", "--llm-script",
              script, "--attack", "autodojo", "--autodojo-cache", str(cache), "--autodojo-variant", "0")
    assert run.code == 2 and "only in the AutoDojo fork" in run.err
    run = _autodojo(cli, tmp_path, script, "--autodojo-cache", str(cache), "--autodojo-variant", "0")
    assert run.code == 2 and "belong to --attack autodojo" in run.err
