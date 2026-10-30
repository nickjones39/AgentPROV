"""Follow-ups after the GUI security review: D-529 sampling rules and the spread fallback in dev runs, end to end through
a batch's driver job (D-704). The skipped steps after a failed import and GR-70 checkout pinning are the core batch's
rules now (``tests/jobs/test_batch.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

from agentprov_gui.jobs.manager import CliLocator, JobManager

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
def _part():
    from agentprov.devrun.plan import DevPart

    return DevPart("agentdojo", "2024-06", 3, "supported", None)


def test_first_n_argv_and_unsupported_detection() -> None:
    """D-529's rules are the core's now (``agentprov.jobs.batch``; the batch driver applies them)."""
    from agentprov.jobs.batch import first_n_argv, sample_unsupported

    argv = ("import", "--corpus", "/c", "--sample", "3", "--sample-mode", "random", "--seed", "4", "agentdojo")
    assert first_n_argv(argv) == ("import", "--corpus", "/c", "--sample", "3", "--sample-mode", "first", "agentdojo")
    note = "error import.sample.unsupported: spread needs a stratum hook"
    assert sample_unsupported(5, {"notices": [note]})
    assert sample_unsupported(5, {"refusal": {"code": "import.sample.unsupported"}})
    assert not sample_unsupported(2, {"notices": [note]})
    assert not sample_unsupported(5, {"notices": ["other"]})


def test_spread_unsupported_inserts_a_first_n_import(tmp_path: Path) -> None:
    """End to end through the batch's driver job: the fake CLI refuses a spread sample (exit 5,
    import.sample.unsupported); the driver inserts a first-N import of the part and runs it, then the rest."""
    import time

    from agentprov.jobs.batch import FALLBACK_NOTE

    from agentprov_gui.jobs import batch as batch_client
    from agentprov_gui.jobs.batch import Batch

    home = tmp_path / "home"
    m = JobManager(home, CliLocator(None, (sys.executable, str(FAKE))))
    from agentprov.cli.devrun import run_steps
    from agentprov.devrun.plan import DevSettings

    from agentprov_gui.jobs.commands import JobSpec

    steps = run_steps(_part(), tmp_path / "run", DevSettings(mode="spread"), queue=False)  # D-705's own steps
    specs = [JobSpec(r.command, r.argv, r.tier, r.label, writes=r.writes, reads=r.reads, extra=dict(r.extra))
             for r in (st.request for st in steps)]
    bid = batch_client.create(m, "dev", specs, continue_on_failure=True)
    batch_client.start(m, bid, confirm_r2=True)
    end = time.monotonic() + 90
    while time.monotonic() < end:
        batch = next(b for b in Batch.load_all(home) if b.batch_id == bid)
        if batch.finished:
            break
        time.sleep(0.1)
    states = [(s.spec.command, s.state, s.note) for s in batch.steps]
    assert states[0][:2] == ("import", "failed") and batch.steps[0].exit_code == 5
    assert states[1][:2] == ("import", "done") and states[1][2] == FALLBACK_NOTE
    assert batch.steps[1].spec.argv[batch.steps[1].spec.argv.index("--sample-mode") + 1] == "first"
    assert [s[1] for s in states[2:]] == ["done", "done"]
