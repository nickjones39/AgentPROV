"""A fake ``agentprov`` for the job-manager tests (design §14): it writes progress 0.1, log and summary files like the
real CLI and honours SIGTERM (summary with exit 130). Behaviour comes from its own options: ``--units N``,
``--sleep S`` (per unit), ``--exit N``, ``--lock DIR`` (create DIR.partial/.agentprov.lock with this pid),
``--env-stdin`` (read one JSON object from stdin, as ``run`` does; only its names and byte length are recorded)."""

import json
import os
import signal
import sys
import time

argv = sys.argv[1:]

if argv[:1] in (["jobs"], ["batch"], ["devrun"], ["settings"]):
    # D-704, D-705, D-703: `jobs`, `batch`, `devrun` and `settings` are the core's own commands; only the program a job runs is this fake (patched in this
    # process, never through an option or a variable of the real CLI)
    from agentprov.cli.main import main as _core_main
    from agentprov.jobs import manager as _manager

    _manager.JobManager.program = lambda self: [sys.executable, os.path.abspath(__file__)]
    if argv[:1] in (["batch"], ["devrun"]):  # this fake's options are not agentprov's: batch steps are checked by the fake's rules
        from agentprov.cli import batch as _batch

        _fake_commands = ("import", "validate", "recompute", "derive", "run", "fetch", "info")
        _batch.validate_argv = lambda step_argv: None if step_argv and step_argv[0] in _fake_commands else (
            "not a fake command")
        _batch.checkout_pin = lambda: None  # tests edit nothing, but a developer may: the pin is tests/jobs' (GR-70)
    raise SystemExit(_core_main(argv))


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


if argv[:1] == ["import"] and opt("--sample-mode") == "spread":  # a reader that cannot draw a spread sample (D-529)
    summary_path = opt("--summary-json")
    if summary_path:
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump({"exit_code": 5, "outcome": "unsupported",
                       "refusal": {"code": "import.sample.unsupported", "mode": "spread"}}, fh)
    raise SystemExit(5)


progress, log, summary = opt("--progress-file"), opt("--log-file"), opt("--summary-json")
units, sleep, code = int(opt("--units", "3")), float(opt("--sleep", "0")), int(opt("--exit", "0"))
lock = opt("--lock")
command = argv[0]
stopped = False
stdin_names, stdin_bytes = None, None
if "--env-stdin" in argv:
    data = sys.stdin.buffer.read(65537)
    stdin_names, stdin_bytes = sorted(json.loads(data)), len(data)


def on_term(signum, frame):
    global stopped
    stopped = True


signal.signal(signal.SIGTERM, on_term)


def write(path, obj):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


if lock:
    os.makedirs(lock + ".partial", exist_ok=True)
    with open(os.path.join(lock + ".partial", ".agentprov.lock"), "w") as fh:
        json.dump({"pid": os.getpid(), "host": "x", "command": command}, fh)
write(log, {"level": "INFO", "logger": "agentprov.cli", "msg": f"start command={command}", "ts": "t0"})
write(progress, {"v": "agentprov-progress/0.1", "ts": "t0", "level": "summary", "event": "start", "total": units})
done = 0
for i in range(units):
    if stopped:
        break
    write(progress, {"v": "agentprov-progress/0.1", "ts": "t", "level": "status", "event": "unit_start", "unit": f"u{i}"})
    time.sleep(sleep)
    write(progress, {"v": "agentprov-progress/0.1", "ts": "t", "level": "status", "event": "unit_done", "unit": f"u{i}",
                     "status": "sealed" if i % 2 == 0 else "sealed_with_issues", "codes": ["map.x"] if i % 2 else []})
    write(log, {"level": "INFO", "logger": "agentprov.import", "msg": f"unit {i}", "ts": "t", "ex": f"ex_{i}"})
    done += 1
final = 130 if stopped else code
write(progress, {"v": "agentprov-progress/0.1", "ts": "t9", "level": "summary", "event": "end", "units_done": done,
                 "counts": {"sealed": done}, "issues": {}, "dropped": 0, "exit_code": final})
with open(summary, "w") as fh:
    json.dump({"format": "agentprov-cli-summary/0.1", "command": command, "exit_code": final,
               "outcome": {0: "ok", 1: "failures", 4: "refused", 70: "internal", 130: "interrupted"}.get(final, "internal"),
               "stdin_names": stdin_names, "stdin_bytes": stdin_bytes}, fh)
if lock and not stopped:
    os.unlink(os.path.join(lock + ".partial", ".agentprov.lock"))
sys.exit(final)
