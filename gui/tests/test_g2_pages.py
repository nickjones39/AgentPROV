"""G2 pages offscreen: Runs (with the fake CLI), the job dialog, Logs, System, Licences, Package, dev runs."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


@pytest.fixture
def settings(tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings

    return Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def runs(qapp: Any, tmp_path: Path, settings: Any) -> Any:
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    page = RunsPage(manager, settings)
    page.show()
    yield page
    page.tick_timer.stop()
    page.list_timer.stop()
    page.deleteLater()


def test_runs_dashboard_follows_a_job(qapp: Any, runs: Any) -> None:
    job = runs.start(JobSpec("import", ("import", "--units", "6", "--sleep", "0.05"), "R1", "fake import"))
    assert job is not None and runs.selected is not None
    wait(qapp, lambda: runs.manager.jobs[job.job_id].state != "running", 30)
    runs.refresh()
    runs.select(job.job_id)
    assert "ok" in runs.title.text()
    counts = {runs.counts.item(r, 0).text(): runs.counts.item(r, 1).text() for r in range(runs.counts.rowCount())}
    assert counts and int(counts.get("sealed", "0")) == 6
    assert runs.resume_btn.isEnabled() and not runs.stop_btn.isEnabled()


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
def test_runs_stop_is_confirmed_and_ends_interrupted(qapp: Any, runs: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    job = runs.start(JobSpec("import", ("import", "--units", "200", "--sleep", "0.05"), "R1", "long"))
    time.sleep(0.3)
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    runs.stop()
    wait(qapp, lambda: runs.manager.refresh() and runs.manager.jobs[job.job_id].state != "running", 30)
    assert runs.manager.jobs[job.job_id].exit_code == 130


def test_refused_spawn_is_reported_not_raised(qapp: Any, runs: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    shown: list[str] = []

    class Box:
        def __init__(self, *a: Any, **k: Any) -> None:
            shown.append(str(k.get("informative", "")))

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(runs_mod, "safe_message_box", Box)
    target = "/tmp/never-written-corpus"
    runs.start(JobSpec("import", ("import", "--units", "100", "--sleep", "0.05"), "R1", "a", writes=(target,)))
    assert runs.start(JobSpec("import", ("import",), "R1", "b", writes=(target,))) is None
    assert shown and "one writer per corpus" in shown[0]  # the CLI's reason (D-704: the rule is agentprov jobs')
    for j in runs.manager.jobs.values():
        runs.manager.kill(j)


def test_job_dialog_preview_tier_and_conformance(qapp: Any) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["import"], program=("agentprov",), preset={"source": "agentdojo", "corpus": "/tmp/c"})
    assert "agentprov import --corpus /tmp/c" in dlg.preview.toPlainText()
    assert dlg.tier.text().startswith("R1")
    assert not dlg.conformance.isEnabled() and dlg.conformance.isChecked()  # the CLI has no option yet (G2c-5)
    dlg.inputs["fetch"].setChecked(True)
    dlg.inputs["allow_network"].setChecked(True)
    assert dlg.tier.text().startswith("R2")
    dlg.extra.setText("--show-content")
    assert not dlg.ok.isEnabled() and "not allowed" in dlg.error.text()


def test_conformance_warning_flow(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.jobdialog as jd

    dlg = jd.JobDialog(FORMS["derive"], program=("agentprov",), preset={"corpus": "/a", "out": "/b"},
                       conformance_option="--skip-prov-conformance")
    monkeypatch.setattr(jd, "choose", lambda *a, **k: False)  # the user keeps the check
    dlg.conformance.click()
    assert dlg.conformance.isChecked() and "--skip-prov-conformance" not in dlg.preview.toPlainText()
    monkeypatch.setattr(jd, "choose", lambda *a, **k: True)  # the user skips it, after the warning
    dlg.conformance.click()
    assert not dlg.conformance.isChecked() and "--skip-prov-conformance" in dlg.preview.toPlainText()
    assert "Not advisable" in jd.CONFORMANCE_WARNING


def test_logs_page_reads_the_job_log(qapp: Any, runs: Any) -> None:
    from agentprov_gui.ui.logs import LogsPage

    job = runs.start(JobSpec("import", ("import", "--units", "5"), "R1", "logged"))
    wait(qapp, lambda: runs.manager.refresh() and runs.manager.jobs[job.job_id].state != "running", 30)
    page = LogsPage(runs.manager)
    page.show()
    page.show_job(job.job_id)
    page._tick()
    assert page.model.rowCount() >= 6
    page.ex.setText("ex_2")
    assert page.model.rowCount() == 1
    page.source.setCurrentIndex(1)  # stderr.txt (empty)
    page._tick()


def test_system_sampler_once(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.system import SystemPage

    page = SystemPage(tmp_path)
    page.follow_job(os.getpid(), None)
    page.sampler.active = True
    got = [page.sampler.sample()]
    assert got and got[0]["cpu"] and any(pid == os.getpid() for pid, *_ in got[0]["procs"])
    page._show(got[0])
    assert "memory" in page.summary.text()
    page.shutdown()


def test_licences_page(qapp: Any) -> None:
    from agentprov.adapters.registry import REGISTRY

    from agentprov_gui.about import default_checkout
    from agentprov_gui.ui.licences import LicencesPage, flags_of

    page = LicencesPage(default_checkout())
    assert page.included.rowCount() == len(REGISTRY)
    assert page.excluded.rowCount() > 0
    copyleft = [s for s in REGISTRY if any(f == "copyleft" for f, _ in flags_of(s))]
    assert all(s.licence.spdx and "GPL" in s.licence.spdx.upper() for s in copyleft)


def test_package_page_states_nothing_is_uploaded(qapp: Any, mini_corpus: Path) -> None:
    from agentprov_gui.ui.package import FINISH_TEXT, PackagePage

    page = PackagePage(lambda spec: None, None)
    page.corpus.setText(str(mini_corpus))
    page._show(0)
    assert "partial:" in page.texts[0].toPlainText()
    page._show(8)
    assert "Nothing has been uploaded" in page.texts[8].toPlainText() and "Nothing has been uploaded" in FINISH_TEXT
    page.timer.stop()


def test_viewer_only_without_a_cli(qapp: Any, tmp_path: Path, settings: Any) -> None:
    from agentprov_gui.ui.mainwindow import MainWindow

    settings.checkout = tmp_path / "no-checkout"
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    assert not w.runs.new_btn.isEnabled()
    w.close()


# ----------------------------------------------------------------------------------------------- dev runs


def test_conformance_rules_per_command() -> None:
    from agentprov_gui.jobs.commands import FormError, build_spec

    assert not FORMS["validate"].prov_generating  # validate is the check: no skip flag
    opt = "--skip-prov-conformance"
    with pytest.raises(FormError):
        build_spec(FORMS["import"], {"source": "s", "corpus": "/c", "release": True}, conformance=False,
                   conformance_option=opt)
    with pytest.raises(FormError):
        build_spec(FORMS["recompute"], {"corpus": "/c"}, conformance=False, conformance_option=opt)
    ok = build_spec(FORMS["recompute"], {"corpus": "/c", "dry_run": False, "out": "/n"}, conformance=False,
                    conformance_option=opt)
    assert opt in ok.argv
    assert not FORMS["package_seal"].prov_generating and not FORMS["package_deposit"].prov_generating


def test_package_seal_disabled_for_a_marked_corpus(qapp: Any, corpus_copy: Path) -> None:
    from agentprov_gui.ui.package import MARKED_TEXT, PackagePage

    manifest = corpus_copy.with_name("mini.partial") / "corpus.json"
    doc = json.loads(manifest.read_text())
    doc.setdefault("validation", {})["prov_conformance"] = "skipped"
    manifest.write_text(json.dumps(doc))
    started: list[Any] = []
    page = PackagePage(started.append, None)
    page.corpus.setText(str(corpus_copy))
    page._show(4)
    assert page.buttons[4] is not None and not page.buttons[4].isEnabled()
    page.seal()
    assert not started and page.texts[4].toPlainText() == MARKED_TEXT
    page.timer.stop()


def test_ci_local_form_is_a_tool_job(qapp: Any, runs: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.about import default_checkout
    from agentprov_gui.jobs.commands import build_spec

    form = FORMS["ci_local"]
    assert form.tool == "tools/ci_local.py"
    spec = build_spec(form, {"only": "core", "json": True})
    assert spec.argv == ("--only", "core", "--json") and spec.tier == "R1"
    assert build_spec(form, {"allow_network": True}).tier == "R2"
    runs.manager.cli = CliLocator(default_checkout(), runs.manager.cli.program, (sys.executable,))
    program = runs.tool_program(form.tool)
    assert program is not None and program[1].endswith("tools/ci_local.py") and program[2] == "-C"
    started: list[JobSpec] = []
    monkeypatch.setattr(runs, "start", lambda s, **k: started.append(s))

    class Dialog:
        def __init__(self, *a: Any, **k: Any) -> None:
            self.spec = spec

        def exec(self) -> int:
            return 1

    import agentprov_gui.ui.runs as runs_mod

    monkeypatch.setattr(runs_mod, "JobDialog", Dialog)
    runs.new_job("ci_local")
    assert started and started[0].argv == spec.argv and started[0].extra["tool"] == "tools/ci_local.py"
    from agentprov_gui.jobs.manager import job_start_argv

    argv = job_start_argv(started[0])  # D-704: `jobs start --tool` (resolved inside tools/ by the CLI)
    assert argv[argv.index("--tool") + 1] == "tools/ci_local.py" and "--queue-cpu" not in argv
    assert argv[argv.index("--") + 1:] == ["--only", "core", "--json"]


def test_revalidate_is_a_full_recompute_into_a_new_corpus(qapp: Any, runs: Any, monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:
    """User decision 2026-10-15: only recompute --out NEW --stages sem,prov,validation clears the mark; never in place."""
    seen: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(runs, "new_job", lambda key, preset=None: seen.append((key, dict(preset or {}))))
    corpus = tmp_path / "corpora" / "c"
    corpus.with_name("c-revalidated.partial").mkdir(parents=True)  # a previous attempt exists
    runs.revalidate(str(corpus.with_name("c.partial")))
    ((key, preset),) = seen
    assert key == "recompute" and preset["corpus"] == str(corpus) and preset["dry_run"] is False
    assert preset["out"] == str(tmp_path / "corpora" / "c-revalidated-2") and preset["stages"] == "sem,prov,validation"
    from agentprov_gui.jobs.commands import build_spec

    spec = build_spec(FORMS["recompute"], preset)
    assert "--dry-run" not in spec.argv and "--skip-prov-conformance" not in spec.argv
    assert spec.writes == (preset["out"],) and str(corpus) not in spec.writes


def test_marked_corpus_offers_revalidate_in_package_and_viewer(qapp: Any, corpus_copy: Path, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.package import PackagePage
    from agentprov_gui.ui.viewer import ViewerPage

    manifest = corpus_copy.with_name("mini.partial") / "corpus.json"
    doc = json.loads(manifest.read_text())
    doc.setdefault("validation", {})["prov_conformance"] = "skipped"
    manifest.write_text(json.dumps(doc))
    asked: list[str] = []
    page = PackagePage(lambda spec: None, None, revalidate=asked.append)
    page.corpus.setText(str(corpus_copy))
    page._show(4)
    button = page.buttons[4]
    assert button is not None and button.isEnabled() and button.text().startswith("Revalidate")
    page.seal()
    assert asked == [str(corpus_copy)]
    page.timer.stop()
    del Settings, QSettings
    viewer = ViewerPage([corpus_copy.parent], tmp_path / "layout")
    viewer.show()
    try:
        from agentprov_gui.readmodel.corpus import summarise

        viewer.summary = summarise(corpus_copy)
        viewer._show_banner(viewer.summary)
        assert viewer.revalidate_btn.isVisible() and "full recompute" in viewer.banner_text.text()
        got: list[str] = []
        viewer.revalidate_requested.connect(got.append)
        viewer.revalidate_btn.click()
        assert got == [str(corpus_copy)]
    finally:  # GR-69: a shown top-level page left open can catch later tests' offscreen mouse events
        viewer.close()
        viewer.deleteLater()
        page.deleteLater()


def test_ended_jobs_release_their_progress_handles(qapp: Any, runs: Any) -> None:
    """GR-27: a follower closes its progress reader after the final fold, and is never re-folded after that."""
    import psutil

    home = os.path.realpath(runs.manager.jobs_dir)

    def open_progress() -> list[str]:
        return [f.path for f in psutil.Process().open_files()
                if os.path.realpath(f.path).startswith(home) and f.path.endswith("progress.jsonl")]

    ids = []
    for i in range(5):
        job = runs.start(JobSpec("import", ("import", "--units", "3", "--sleep", "0.01"), "R1", f"fd {i}"))
        assert job is not None
        wait(qapp, lambda j=job: runs.manager.refresh() and runs.manager.jobs[j.job_id].state != "running", 30)
        runs.refresh()
        ids.append(job.job_id)
    for job_id in ids:
        runs.select(job_id)
    assert open_progress() == []
    first = {job_id: runs.followers[job_id] for job_id in ids}
    runs.refresh()
    for job_id in ids:
        runs.select(job_id)
        runs.select(job_id)
        f = runs.followers[job_id]
        assert f is first[job_id] and f.state.done == 3  # the same follower, folded once
    assert open_progress() == []


def test_selecting_a_large_ended_job_folds_in_bounded_steps(qapp: Any, runs: Any, settings: Any) -> None:
    """GR-44: the final fold of an ended job reads one tick's byte budget per call, never the whole file at once."""
    from agentprov.jobs.follow import READ_CAP

    from agentprov_gui.ui.runs import RunsPage

    job = runs.start(JobSpec("import", ("import", "--units", "1", "--sleep", "0.01"), "R1", "big"))
    assert job is not None
    wait(qapp, lambda: runs.manager.refresh() and runs.manager.jobs[job.job_id].state != "running", 30)
    v = "agentprov-progress/0.1"
    units = 12_000
    lines = [json.dumps({"v": v, "ts": "t0", "level": "summary", "event": "start", "total": units})]
    for i in range(units):
        lines.append(json.dumps({"v": v, "ts": "t", "level": "status", "event": "unit_start", "unit": f"u{i}"}))
        lines.append(json.dumps({"v": v, "ts": "t", "level": "status", "event": "unit_done", "unit": f"u{i}",
                                 "status": "sealed", "codes": [], "pad": "x" * 64}))
    data = ("\n".join(lines) + "\n").encode()
    assert len(data) > 2 * READ_CAP
    job.file("progress.jsonl").write_bytes(data)
    page = RunsPage(JobManager(runs.manager.home, CliLocator(None, (sys.executable, str(FAKE)))), settings)
    try:
        page.list_timer.stop()
        page.tick_timer.stop()
        row = next(i for i, j in enumerate(page.model.jobs) if j.job_id == job.job_id)
        page.view.selectRow(row)
        f = page.followers[job.job_id]
        assert f.reader.offset <= READ_CAP and not f.finished  # one tick's budget, not the whole file
        for _ in range(4 * len(data) // READ_CAP + 4):
            if f.finished:
                break
            before = f.reader.offset
            page._tick()
            assert f.reader.offset - before <= READ_CAP
        assert f.finished and f.reader._fh is None and f.state.done == units
        page.refresh()
        page._tick()
        assert f.state.done == units and page.followers[job.job_id] is f  # folded once, never twice
    finally:
        page.deleteLater()
