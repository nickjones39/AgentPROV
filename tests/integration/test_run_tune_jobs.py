"""``agentprov run --tune-jobs`` against the fake backend environment (N.2.1a(4); D-820..D-823): a scripted sweep
(``test_only``), its warm-up, one working corpus per arm, the report, resume, and the preset live-run rules.

No benchmark package, model or network: :mod:`live_fake` provides the environment, ``--llm-script`` the transport.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import make_fake_env, repo_root  # noqa: E402


@pytest.fixture(autouse=True)
def _mac_studio_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``m5ultra`` preset's memory terms are calibrated for the Mac Studio's 256 GiB, and the plan is sized from the
    host probe's memory (N.2.1a(5)). The probe here reports that memory, so the plans do not depend on the machine the
    tests run on (a 7 to 16 GB CI runner fits no model; D-1011); everything else the probe reports is the real host's."""
    import dataclasses

    from agentprov import host

    real = host.detect_host
    monkeypatch.setattr(host, "detect_host", lambda **kw: dataclasses.replace(
        real(**kw), memory_bytes=256 * 2**30, memory_how="synthetic (the Mac Studio's 256 GiB, for the m5ultra preset)"))

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")

FACTS = ("--model-size-gb", "10", "--active-params-b", "3")


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    make_fake_env(path, "ok")
    return path


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    from agentprov.cli.main import main

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


@pytest.fixture
def script(tmp_path: Path) -> str:
    path = tmp_path / "script.json"
    path.write_text("[]")
    return str(path)


def _sweep(cli: Callable[..., Run], out: Path, script: str, *extra: str) -> Run:
    return cli("run", "agentdojo", "--m5ultra", "--tune-jobs", "1,2", "--tune-out", str(out), "--llm-script", script,
               *FACTS, "--progress", "off", *extra)


def test_a_scripted_sweep_writes_one_corpus_per_arm_and_a_report(cli: Callable[..., Run], home: Path, tmp_path: Path,
                                                                 script: str) -> None:
    out = tmp_path / "sweep"
    run = _sweep(cli, out, script)
    assert run.code == 0, run.err
    doc = json.loads((out / "tune-jobs.json").read_text())
    assert doc["format"] == "agentprov-tune-jobs/0.1" and doc["test_only"] is True and doc["warm_up"] is True
    assert [a["jobs"] for a in doc["arms"]] == [1, 2] and {a["status"] for a in doc["arms"]} == {"ran"}
    assert doc["recommendation"]["jobs"] in (1, 2) and doc["recommendation"]["rule"]["rate_share"] == 0.9
    assert doc["sample"]["default"] is True and doc["preset"] == {
        "name": "m5ultra", "version": doc["preset"]["version"], "data_sha256": doc["preset"]["data_sha256"],
        "calibrated": True}
    assert doc["run"]["llm_element"] == "gateway_compat" and doc["run"]["request_timeout_s"] == 900
    assert (out / "tune-jobs.md").read_text().startswith("# Concurrency sweep")
    for n in (1, 2):
        manifest = json.loads((out / f"jobs-{n}.partial" / "corpus.json").read_text())
        assert manifest["live"]["jobs"] == n and manifest["live"]["test_only"] is True
        assert manifest["live"]["llm_element"] == "gateway_compat"
        preset = manifest["producer"]["preset"]
        assert preset["name"] == "m5ultra" and preset["resolved"]["concurrency"]["jobs"] == n
        assert preset["resolved"]["start_stagger_s"] == {"value": n, "source": "preset"}  # 1 s per worker
        assert preset["resolved"]["gpu_budget_fraction"] == "0.75"
        assert (out / "arms" / f"jobs-{n}.json").is_file()
    assert any(p.name.startswith("warmup-") for p in out.iterdir())
    assert "recommended jobs" in run.out + run.err


def test_a_rerun_reuses_finished_arms_and_reruns_an_unfinished_one(cli: Callable[..., Run], home: Path,
                                                                   tmp_path: Path, script: str) -> None:
    out = tmp_path / "sweep"
    assert _sweep(cli, out, script).code == 0
    (out / "arms" / "jobs-2.json").unlink()  # as if the run stopped during arm 2
    again = _sweep(cli, out, script)
    assert again.code == 0, again.err
    assert any(p.name.startswith("jobs-2.partial.interrupted-") for p in out.iterdir())
    doc = json.loads((out / "tune-jobs.json").read_text())
    assert [a["status"] for a in doc["arms"]] == ["ran", "ran"] and doc["reused_arms"] == [1]
    assert doc["warm_up"] is True  # arm 2 ran again, after a fresh warm-up


def test_arms_above_the_memory_term_are_skipped(cli: Callable[..., Run], home: Path, tmp_path: Path,
                                                script: str) -> None:
    from agentprov.host import detect_host

    memory = detect_host(probe=False).memory_bytes
    if not memory:
        pytest.skip("the host's memory is unknown")
    gib = 2**30
    room = 0.75 * memory - 10e9 - 16 * gib  # M_budget - W - the fixed reserve (N.2.1a(5))
    kv_gb = (room / 1.5 - 0.5 * gib) / 1e9  # one trace (KV + 0.5 GiB) fits, two do not: J_memory = 1
    out = tmp_path / "sweep"
    run = cli("run", "agentdojo", "--m5ultra", "--tune-jobs", "1,2", "--tune-out", str(out), "--llm-script", script,
              "--model-size-gb", "10", "--active-params-b", "3", "--kv-gb-per-trace", f"{kv_gb:.3f}",
              "--progress", "off")
    doc = json.loads((out / "tune-jobs.json").read_text())
    assert [(a["jobs"], a["status"], a.get("reason")) for a in doc["arms"]] == [(1, "ran", None),
                                                                                (2, "skipped", "memory")], run.err


def test_dry_run_lists_the_arms(cli: Callable[..., Run], home: Path) -> None:
    run = cli("run", "agentdojo", "--m5ultra", "--dry-run", "--tune-jobs", "1,2,4", *FACTS)
    text = run.out + run.err
    assert run.code == 0, run.err
    assert "sweep: arms 1,2,4; 24 cells per arm;" in text and "arm jobs=4: runs" in text
    assert "time, if throughput scaled" in text


@pytest.mark.parametrize("extra, code, words", [
    (("--jobs", "2"), 2, "--tune-jobs sets --jobs itself"),
    (("--corpus", "x", "--campaign", "c"), 2, "--tune-jobs sets --corpus, --campaign itself"),
    (("--llm-element", "native"), 2, "stock OpenAILLM"),
])
def test_sweep_refusals(cli: Callable[..., Run], home: Path, tmp_path: Path, script: str,
                        extra: tuple[str, ...], code: int, words: str) -> None:
    run = _sweep(cli, tmp_path / "sweep", script, *extra)
    assert run.code == code and words in run.err, run.err


def test_tune_jobs_needs_a_preset_and_uncalibrated_presets_do_not_run_live(cli: Callable[..., Run], home: Path,
                                                                           tmp_path: Path, script: str,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from agentprov import presets

    no_preset = cli("run", "agentdojo", "--tune-jobs", "1,2", "--llm-script", script)
    assert no_preset.code == 2 and "need --preset" in no_preset.err
    shipped = presets.load_preset
    monkeypatch.setattr(presets, "load_preset", lambda name: dataclasses.replace(shipped(name), calibrated=False))
    live = cli("run", "agentdojo", "--m5ultra", "--corpus", str(tmp_path / "c"), "--campaign", "t", "--suite",
               "banking", "--model", "omlx", "--model-id", "m", *FACTS)
    assert live.code == 5 and "uncalibrated preset m5ultra" in live.err, live.err


@pytest.fixture
def no_drain() -> Any:
    from agentprov import drain

    drain.reset()
    yield drain
    drain.reset()


@pytest.mark.parametrize("when", ["after_arm_1", "inside_arm_2"])
def test_a_drained_sweep_records_no_unrun_arm_and_a_rerun_measures_it(cli: Callable[..., Run], home: Path,
                                                                        tmp_path: Path, script: str, no_drain: Any,
                                                                        monkeypatch: pytest.MonkeyPatch,
                                                                        when: str) -> None:
    """AU-RN-1: a drain (the GUI's Drain, ``--control-file``) accepted during the sweep starts no further arm, writes no
    arm file for an arm it cut short or never started, and recommends nothing; a re-run measures those arms."""
    from agentprov.cli.live import campaign as cmod

    real_ingest, real_run = cmod.Campaign._ingest, cmod.Campaign.run
    armed = {"on": True}

    def ingest(self: Any, result: Any) -> Any:  # accepted just after arm 1's only attempt is ingested
        entry = real_ingest(self, result)
        if armed["on"] and when == "after_arm_1" and self.writer.final_dir.name == "jobs-1":
            no_drain.request()
        return entry

    def run(self: Any, cells: Any, **kw: Any) -> Any:  # accepted as arm 2 starts: none of its units is attempted
        if armed["on"] and when == "inside_arm_2" and self.writer.final_dir.name == "jobs-2":
            no_drain.request()
        return real_run(self, cells, **kw)

    monkeypatch.setattr(cmod.Campaign, "_ingest", ingest)
    monkeypatch.setattr(cmod.Campaign, "run", run)
    out = tmp_path / "sweep"
    first = _sweep(cli, out, script)
    assert first.code == 0, first.err
    doc = json.loads((out / "tune-jobs.json").read_text())
    assert [(a["jobs"], a["status"], a.get("reason")) for a in doc["arms"]] == [(1, "ran", None),
                                                                                (2, "skipped", "drained")]
    assert doc["recommendation"]["jobs"] is None and doc["recommendation"]["drained"] is True
    assert (out / "arms" / "jobs-1.json").is_file() and not (out / "arms" / "jobs-2.json").exists()
    assert (out / "jobs-2.partial").is_dir() is (when == "inside_arm_2")
    armed["on"] = False
    no_drain.reset()
    again = _sweep(cli, out, script)
    assert again.code == 0, again.err
    doc = json.loads((out / "tune-jobs.json").read_text())
    assert doc["reused_arms"] == [1] and [a["status"] for a in doc["arms"]] == ["ran", "ran"]
    assert doc["arms"][1]["cells"]["attempted"] == 1 and doc["recommendation"]["jobs"] in (1, 2)
    assert (out / "arms" / "jobs-2.json").is_file()


def test_each_corpus_of_a_capped_sweep_records_its_own_spend_and_the_sweep_keeps_to_the_caps(
        cli: Callable[..., Run], home: Path, tmp_path: Path, script: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-RN-2: the caps are per corpus (D-725), so the warm-up and each arm record only their own billed calls in
    live.caps; the sweep as a whole still starts a cell only while its total fits the caps."""
    from agentprov.cli.live import policy

    # the fake worker's capture logs carry no llm.response: each is billed 10 calls
    monkeypatch.setattr(policy, "log_billing", lambda log, limits=None: policy.LogBilling(billed_calls=10))
    out = tmp_path / "sweep"
    assert _sweep(cli, out, script, "--max-calls", "800").code == 0
    caps = {p.name.split(".")[0]: json.loads((p / "corpus.json").read_text())["live"]["caps"]
            for p in out.iterdir() if (p / "corpus.json").is_file()}
    assert sorted(caps) == ["jobs-1", "jobs-2", next(k for k in caps if k.startswith("warmup-"))]
    assert {k: c["billed_calls"] for k, c in caps.items()} == dict.fromkeys(caps, 10)
    assert all("probe_calls" not in c for c in caps.values())  # scripted: no probe
    # 400 calls: each corpus alone would admit a cell (384 at most), the sweep's third would not (20 + 384 > 400)
    tight = tmp_path / "tight"
    run = _sweep(cli, tight, script, "--max-calls", "400")
    doc = json.loads((tight / "tune-jobs.json").read_text())
    arm2 = doc["arms"][1]
    assert arm2["cells"]["attempted"] == 0 and "cap_reached: --max-calls 400" in arm2["stopped"][0], run.err
    assert json.loads((tight / "jobs-1.partial" / "corpus.json").read_text())["live"]["caps"]["billed_calls"] == 10


def test_a_sweep_never_moves_an_arm_corpus_a_live_writer_holds(cli: Callable[..., Run], home: Path, tmp_path: Path,
                                                               script: str) -> None:
    """AU-RN-4: an unfinished arm's corpus is renamed aside only when no live writer holds its lock (here another
    sweep's arm 1 on the same --tune-out): the sweep is refused and nothing is moved; once released, it runs."""
    from agentprov.corpus.writer import CorpusWriter

    out = tmp_path / "sweep"
    (out / "arms").mkdir(parents=True)
    held = CorpusWriter(out / "jobs-1", command="run").open()
    try:
        run = _sweep(cli, out, script)
        assert run.code == 4 and "held by another writer" in run.err, run.err
        assert held.layout.lock.is_file() and not any("interrupted" in p.name for p in out.iterdir())
    finally:
        held.close()
    again = _sweep(cli, out, script)
    assert again.code == 0, again.err
    assert any(p.name.startswith("jobs-1.partial.interrupted-") for p in out.iterdir())
