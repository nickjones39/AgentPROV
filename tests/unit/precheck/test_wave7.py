"""The wave-7 extensions of the pre-check tools (phase-10j corpora): the ``url`` download pin as an L1 archive input
(DCA), nested-member chain labels in the AgentDojo hook (authority-caps, ipi-defenses), the proposed stratum keys, the
plan file, and the sample frame's ``--exclude-profile-code`` (EnvironmentOptim's D-255 logs). Synthetic data only, under
``tmp_path`` (never ``tests/fixtures`` nor ``~/.agentprov``)."""

from __future__ import annotations

import io
import json
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "precheck"
WAVE7_PROFILES = ("authority-caps-agentdojo", "ipi-defenses-agentdojo", "dca-agentdojo", "kavach-agentdojo",
                  "environmentoptim-agentdojo", "drift1-agentdojo")  # fmt: skip


@pytest.fixture(scope="module")
def tools() -> Any:
    sys.path.insert(0, str(TOOLS))
    try:
        import l1_families
        import l1_scan
        import l2_sample

        yield l1_scan, l1_families, l2_sample
    finally:
        sys.path.remove(str(TOOLS))


def _log(suite: str, task: str, attack: str | None, injection: str | None, pipeline: str) -> bytes:
    return json.dumps({
        "suite_name": suite, "pipeline_name": pipeline, "user_task_id": task, "injection_task_id": injection,
        "attack_type": attack, "injections": {}, "messages": [{"role": "user", "content": "do it"},
                                                               {"role": "assistant", "content": "done"}],
        "error": None, "utility": True, "security": False, "duration": 1.0, "benchmark_version": None,
        "evaluation_timestamp": "2026-08-01T00:00:00", "agentdojo_package_version": "0.1.35"}).encode()


def test_url_pin_is_an_l1_download_pin(tools: Any) -> None:
    from agentprov.adapters.profiles import load_profile

    l1, _fam, _ls = tools
    profile = load_profile("dca-agentdojo")
    for part in ("v1", "drift"):  # one url pin serves both parts (variant_labels split them)
        pins = l1.download_pins(profile, part)
        assert [(p["kind"], p["file"]) for p in pins] == [("url", "DCA_AgentDojo_artifact_v1_20260612.zip")]
    assert l1.download_pins(load_profile("kavach-agentdojo"), "main") == []  # git pins stay git


def test_a_part_with_several_primary_pins_scans_all_of_them(tools: Any) -> None:
    """D-932: RedCode-OpenHands' six trajectory zips are primary pins of part head, each with its own role; L1 scans all six
    (only the first, before the fix, so every other zip failed verify_download against the first pin's name)."""
    from agentprov.adapters.profiles import load_profile

    l1, _fam, _ls = tools
    pins = l1.download_pins(load_profile("redcode-exec-openhands"), "head")
    assert [p["role"] for p in pins] == ["oh-sonnet-s1", "oh-sonnet-s2", "oh-sonnet-s3", "oh-qwen3coder-s1",
                                         "oh-qwen3coder-s2", "oh-qwen3coder-s3"]
    assert all(p["primary"] is True and p["part"] == "head" for p in pins)  # the supp context pin is not an input


def test_nested_chain_label_reads_the_member_layout(tools: Any) -> None:
    _l1, fam, _ls = tools
    layout = "{model_dir?}/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json"
    ctx = fam.Ctx(profile_id="authority-caps-agentdojo", part="head", layout=layout)
    own = "runs/gpt-4o-mini-2024-07-18-capA3/banking/user_task_0/important_instructions/injection_task_1.json"
    value = json.loads(_log("banking", "user_task_0", "important_instructions", "injection_task_1",
                            "gpt-4o-mini-2024-07-18-capA3"))
    flat = fam.agentdojo_unit(value, own, ctx)
    nested = fam.agentdojo_unit(value, "original-study/experiments/reexecuted_caps/runs_exp4.tar.gz!/" + own, ctx)
    assert nested.facets.pop("container") == "original-study/experiments/reexecuted_caps/runs_exp4.tar.gz"
    assert nested.facets == flat.facets and nested.flags == flat.flags == []
    assert flat.facets["model_dir"] == "runs" and flat.facets["pipeline_dir"] == "gpt-4o-mini-2024-07-18-capA3"
    assert "container" not in flat.facets


def test_wave7_strata_keys(tools: Any) -> None:
    _l1, fam, _ls = tools
    for pid in WAVE7_PROFILES:
        keys = fam.strata_keys(pid, "agentdojo.tracelogger")
        assert keys and all(isinstance(k, str) for k in keys)
    assert fam.strata_keys("environmentoptim-agentdojo", "agentdojo.tracelogger") == (
        fam.HOOKS["agentdojo.tracelogger"].default_strata)
    assert fam.strata_keys("authority-caps-agentdojo", "agentdojo.tracelogger")[0] == "container"


def test_nested_archive_end_to_end(tools: Any, tmp_path: Path) -> None:
    """A zip with a declared nested tar.gz (ipi-defenses' layout): the nested members are scanned under their chain
    labels, with the member's layout facets and the container facet; nothing is extracted."""
    l1, _fam, _ls = tools
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode="w:gz") as tar:
        for i, attack in enumerate(("important_instructions", "none")):
            data = _log("banking", f"user_task_{i}", None if attack == "none" else attack,
                        None if attack == "none" else "injection_task_0", "gpt-5.4-mini-2026-03-17")
            name = (f"runs/run1/gpt-5.4-mini-2026-03-17/no_defense/banking/user_task_{i}/{attack}/"
                    f"{'none' if attack == 'none' else 'injection_task_0'}.json")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    raw = tmp_path / "raw"
    raw.mkdir()
    archive = raw / "AgentSecurity-IPIDefenses-v4.0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("AgentSecurity-IPIDefenses-v4.0/data/traces_run1_mini_pdef.tar.gz", inner.getvalue())
        zf.writestr("AgentSecurity-IPIDefenses-v4.0/README.md", "readme")
    out = tmp_path / "summary.json"
    scratch = tmp_path / "scratch"
    argv = ["--source", "ipi-defenses-agentdojo", "--part", "head", "--input", str(archive), "--no-verify-pin",
            "--summary-out", str(out), "--scratch", str(scratch), "--jobs", "1"]
    l1.run(l1.parser().parse_args(argv))
    rows = [json.loads(line) for line in (scratch / "l1-units-head.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    for row in rows:
        container, _sep, own = row["label"].rpartition("!/")
        assert container == "AgentSecurity-IPIDefenses-v4.0/data/traces_run1_mini_pdef.tar.gz"
        assert own.startswith("runs/run1/gpt-5.4-mini-2026-03-17/no_defense/banking/")
        assert row["facets"]["container"] == container
        assert row["facets"]["model_dir"] == "run1/gpt-5.4-mini-2026-03-17/no_defense"
        assert "layout_mismatch" not in row["flags"] and not [f for f in row["flags"] if f.startswith("path_disagrees")]
        assert row["stratum"].startswith(f"container={container}|model_dir=run1/gpt-5.4-mini-2026-03-17/no_defense|")


@pytest.mark.usefixtures("environmentoptim_registered")  # excluded (D-901): registered for the test only
def test_exclude_profile_code_frame(tools: Any) -> None:
    _l1, _fam, ls = tools
    # environmentoptim-agentdojo v2 (regeneration-batch item 106) has no select.redaction_pending excludes any more; the
    # frame is checked on its select.owned_elsewhere excludes instead (the same mechanism)
    with pytest.raises(SystemExit):
        ls.profile_exclude_globs("environmentoptim-agentdojo", "head", ["select.redaction_pending"])
    globs = ls.profile_exclude_globs("environmentoptim-agentdojo", "head", ["select.owned_elsewhere"])
    assert len(globs["select.owned_elsewhere"]) == 9
    with pytest.raises(SystemExit):
        ls.profile_exclude_globs("environmentoptim-agentdojo", "head", ["select.no_such_code"])
    kept = [{"label": f"runs/gpt-5.4-2026-03-05/workspace/user_task_{i}/none/none.json", "stratum": "s"} for i in range(40)]
    held = [{"label": "runs/dojo_gpt-4o-2024-05-13/workspace/user_task_0/none/none.json", "stratum": "s"},
            {"label": "runs/gpt-4o-mini-2024-07-18-drift/workspace/user_task_0/none/none.json", "stratum": "s"}]
    doc = ls.select([*kept, *held], source="environmentoptim-agentdojo", part="head", corpus_id="c", exclude_globs=globs)
    assert doc["population"]["units"] == 40 and doc["population"]["dropped_profile_code"] == {"select.owned_elsewhere": 2}
    assert doc["rule"]["exclude_profile_codes"] == globs and not set(doc["labels"]) & {h["label"] for h in held}
    plain = ls.select(kept, source="environmentoptim-agentdojo", part="head", corpus_id="c")
    assert "exclude_profile_codes" not in plain["rule"] and "dropped_profile_code" not in plain["population"]
    assert plain["labels"] == ls.select(kept, source="environmentoptim-agentdojo", part="head", corpus_id="c",
                                        exclude_globs=globs)["labels"]


@pytest.mark.usefixtures("environmentoptim_registered")  # excluded (D-901); the plan records wave 7 as it ran
def test_wave7_plan(tools: Any) -> None:
    from agentprov.adapters.registry import get_source

    plan = tomllib.loads((TOOLS / "plans" / "wave7.toml").read_text(encoding="utf-8"))
    parts = {(p["source"], p["part"]): p for p in plan["part"]}
    expected = {(s, c.part) for s in WAVE7_PROFILES for c in get_source(s).capabilities}
    assert set(parts) == expected and len(expected) == 9
    blocked = {k for k, p in parts.items() if p.get("l2_blocked")}
    assert blocked == {("dca-agentdojo", "v1"), ("dca-agentdojo", "drift")}
    assert parts[("environmentoptim-agentdojo", "head")]["sample"] == ["--exclude-profile-code", "select.redaction_pending"]
    for (source, _part), p in parts.items():
        assert p["corpus_id"] == source and p["l1"][0] in ("--input", "--git")
        assert p["l1"][1].startswith("~/.agentprov/staging/10c/")
