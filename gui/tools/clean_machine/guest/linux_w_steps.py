"""The G5 §3 level-W steps (4-9) inside a Linux guest (D-862, D-865), after ``linux_steps.py`` has run steps 1-3.
Runs as the guest's own user with the guest's ``python3`` (stdlib only); it is the harness, not part of what is tested.

    python3 linux_w_steps.py --uv uv.tar.gz --checkout checkout.tar.gz --out DIR

Each step appends one JSON line to ``DIR/steps.jsonl`` and keeps its command output under ``DIR/w/``. Downloads (the
user's yes, design §6 row 4): uv's CPython 3.14 and 3.12, the locked core, GUI and AgentDojo backend dependencies.
No key is read: step 5 stores a dummy value, in this throwaway guest's own test keyring only, and deletes it.

Two harness additions, both recorded in the step lines: ``tools/g5_sleeper.py`` (the jobs tests' sleeper) is written into
the guest's copy of the checkout for step 6, and step 5's Secret Service variant unlocks a gnome-keyring collection with
a fixed test password inside ``dbus-run-session``.
"""

# ruff: noqa: S603 - the harness runs uv, agentprov and fixed guest tools (dbus-run-session) from the guest PATH

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

from linux_steps import Steps, _tail

SLEEPER = '''import signal, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))
print("started", flush=True)
time.sleep(float(sys.argv[-1]))
'''
#: step 8: the benign_banking_single_pass scenario of the live tests (one tool call, one answer)
SCRIPT = [
    {"reply": "tool_calls", "calls": [{"name": "get_most_recent_transactions", "args": {"n": 100}, "id": "call_1"}]},
    {"reply": "text", "content": "You spent 1050 in March 2022."},
]
DUMMY = "g5-dummy-value-not-a-key"
#: step 5's Secret Service variant: unlock a test collection, then status, set, list, delete, list (one JSON doc each)
UNLOCK = """set -u
printf '%s' g5-test-collection | gnome-keyring-daemon --unlock --components=secrets >/dev/null
agentprov() { uv run --no-sync agentprov "$@"; }
"""
#: the key variable names (``keys list`` needs a keychain, so it runs in its own unlocked session)
NAMES = UNLOCK + "agentprov keys list --format json\n"
KEYRING = UNLOCK + """echo "== status"; agentprov keys status --format json; echo "== exit $?"
echo "== set"; printf '%s\\n' "$G5_DUMMY" | agentprov keys set "$G5_NAME" --stdin; echo "== exit $?"
echo "== list"; agentprov keys list --format json; echo "== exit $?"
echo "== delete"; agentprov keys delete "$G5_NAME" --yes; echo "== exit $?"
echo "== list"; agentprov keys list --format json; echo "== exit $?"
"""


class Guest:
    def __init__(self, src: Path, home: Path, out: Path) -> None:
        self.src, self.home, self.out = src, home, out
        self.env = {**os.environ, "PATH": f"{Path.home() / 'uv'}:{os.environ['PATH']}", "AGENTPROV_HOME": str(home),
                    "LANG": "C.UTF-8"}
        self.env.pop("DBUS_SESSION_BUS_ADDRESS", None)  # no Secret Service unless a step starts one

    def run(self, name: str, argv: list[str], timeout: float = 600, stdin: str | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        try:
            done = subprocess.run(argv, cwd=self.src, env=env or self.env, input=stdin, capture_output=True, text=True,
                                  check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            done = subprocess.CompletedProcess(argv, -1, _tail(exc.stdout), _tail(exc.stderr) + "\n(timed out)")
        (self.out / "w" / f"{name}.out").write_text(f"$ {' '.join(argv)}\n--- exit {done.returncode}\n--- stdout\n"
                                                   f"{done.stdout}\n--- stderr\n{done.stderr}", encoding="utf-8")
        return done

    def agentprov(self, name: str, *args: str, timeout: float = 600) -> subprocess.CompletedProcess[str]:
        return self.run(name, ["uv", "run", "--no-sync", "agentprov", *args], timeout=timeout)


def _json(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _sections(text: str) -> list[tuple[str, str, str]]:
    """``== label`` / body / ``== exit N`` blocks of the keyring script's output."""
    found: list[tuple[str, str, str]] = []
    label: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("== exit "):
            if label is not None:
                found.append((label, "\n".join(body), line.removeprefix("== exit ")))
            label, body = None, []
        elif line.startswith("== "):
            label, body = line.removeprefix("== "), []
        elif label is not None:
            body.append(line)
    return found


def _wait_ended(job_dir: Path, timeout: float = 60) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ended = job_dir / "ended.json"
        if ended.is_file():
            return json.loads(ended.read_text(encoding="utf-8"))
        time.sleep(0.5)
    return None


def _wait_started(job_dir: Path, timeout: float = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any("started" in p.read_text(encoding="utf-8", errors="replace") for p in job_dir.glob("std*")):
            return True
        time.sleep(0.2)
    return False


def step4(steps: Steps, g: Guest) -> bool:
    t = time.monotonic()
    core = g.run("4-sync-core", ["uv", "sync", "--locked"], timeout=3600)
    gui = g.run("4-sync-gui", ["uv", "sync", "--locked", "--project", "gui"], timeout=3600)
    info = g.agentprov("4-info", "info")
    pythons = {p: g.run(f"4-python-{p}", ["uv", "run", "--no-sync", *(["--project", "gui"] if p == "gui" else []),
                                          "python", "-V"]).stdout.strip() for p in ("core", "gui")}
    ok = core.returncode == 0 and gui.returncode == 0 and info.returncode == 0
    steps.record(4, "W", ok, t, sync_core=core.returncode, sync_gui=gui.returncode, info_exit=info.returncode,
                 python=pythons, uv=g.run("4-uv", ["uv", "--version"]).stdout.strip(),
                 stderr_tail=_tail(core.stderr + gui.stderr + info.stderr) if not ok else "")
    return ok


def step5(steps: Steps, g: Guest) -> None:
    t = time.monotonic()
    names = _json(g.run("5-key-names", ["dbus-run-session", "--", "sh", "-c", NAMES], timeout=300).stdout)
    name = names["keys"][0]["name"] if isinstance(names, dict) and names.get("keys") else None
    # without a Secret Service: the P-1 message
    bare = g.agentprov("5a-status-no-secret-service", "keys", "status", "--format", "json")
    doc = _json(bare.stdout)
    refused = isinstance(doc, dict) and doc.get("allowed") is False and bool(doc.get("reason"))
    # with gnome-keyring in a private session bus: allowed; set, list, delete a dummy value
    variant = g.run("5b-secret-service", ["dbus-run-session", "--", "sh", "-c", KEYRING], timeout=300,
                    env={**g.env, "G5_NAME": name or "", "G5_DUMMY": DUMMY})
    sections = _sections(variant.stdout)  # [(label, body, exit)] for status, set, list, delete, list
    exits = [code for _label, _body, code in sections]
    status = _json(sections[0][1]) if sections else None
    lists = [_json(body) for label, body, _code in sections if label == "list"]
    stored = [next((k["stored"] for k in d["keys"] if k["name"] == name), None) if isinstance(d, dict) else None
              for d in lists]
    allowed = isinstance(status, dict) and status.get("allowed") is True
    ok = name is not None and refused and allowed and exits == ["0"] * 5 and stored == [True, False]
    steps.record(5, "W", ok, t, key_name=name, dummy_value="fixed test text, not a key",
                 no_secret_service={"exit": bare.returncode, "doc": doc},
                 secret_service={"status": status, "exits": exits, "stored_after_set_then_delete": stored,
                                 "harness": "gnome-keyring, dbus-run-session"},
                 stderr_tail=_tail(variant.stderr) if not ok else "")


def step6(steps: Steps, g: Guest) -> None:
    t = time.monotonic()
    (g.src / "tools" / "g5_sleeper.py").write_text(SLEEPER, encoding="utf-8")
    jobs = g.home / "jobs"
    results: dict[str, object] = {}

    def start(name: str, *argv: str) -> Path | None:
        doc = _json(g.agentprov(name, "jobs", "start", "--format", "json", *argv).stdout)
        return Path(doc["directory"]) if isinstance(doc, dict) and doc.get("directory") else None

    info = start("6-start-info", "--", "info")
    results["info"] = _wait_ended(info) if info else None
    sleeper = start("6-start-sleeper-stop", "--tool", "tools/g5_sleeper.py", "--", "60")
    if sleeper and _wait_started(sleeper):
        g.agentprov("6-stop", "jobs", "stop", sleeper.name)
        results["stop"] = _wait_ended(sleeper)
    victim = start("6-start-sleeper-kill", "--tool", "tools/g5_sleeper.py", "--", "60")
    if victim and _wait_started(victim):
        g.agentprov("6-kill", "jobs", "kill", "--yes", victim.name)
        results["kill"] = _wait_ended(victim)
    outcome = {k: (v.get("outcome"), v.get("how")) if isinstance(v, dict) else None for k, v in results.items()}
    killed = outcome.get("kill")
    ok = (outcome.get("info") == ("ok", "waited") and outcome.get("stop") == ("interrupted", "waited")
          and killed is not None and killed[0] == "killed")
    steps.record(6, "W", ok, t, ended=results, jobs_dir_exists=jobs.is_dir(),
                 note="Linux: stop is one SIGTERM (G5 note 2.4); the control-file stop is Windows' path (P-2)",
                 harness="tools/g5_sleeper.py written into the guest's checkout copy")


def step7(steps: Steps, g: Guest) -> Path | None:
    t = time.monotonic()
    done = g.agentprov("7-backends-build", "backends", "build", "agentdojo", "--allow-network", timeout=5400)
    markers = sorted((g.home / "envs").glob("agentdojo-*/AGENTPROV_ENV.json"))
    marker = json.loads(markers[0].read_text(encoding="utf-8")) if markers else {}
    ok = done.returncode == 0 and marker.get("status") == "complete" and marker.get("sandbox_status") == "not_applicable"
    steps.record(7, "W", ok, t, exit=done.returncode, env=markers[0].parent.name if markers else None,
                 marker_status=marker.get("status"), sandbox_status=marker.get("sandbox_status"),
                 stderr_tail=_tail(done.stderr) if not ok else "")
    return markers[0].parent if ok else None


def step8(steps: Steps, g: Guest) -> None:
    t = time.monotonic()
    script = g.out / "w" / "script.json"
    script.write_text(json.dumps(SCRIPT), encoding="utf-8")
    corpus = g.home / "corpora" / "g5-dev"
    run = g.agentprov("8-run-scripted", "run", "agentdojo", "--corpus", str(corpus), "--campaign", "g5", "--suite",
                      "banking", "--user-tasks", "user_task_1", "--benign", "only", "--model-display-name",
                      "Scripted Model", "--llm-script", str(script), "--max-attempts", "1", "--json", "--progress",
                      "off", timeout=1800)
    summary = _json(run.stdout)
    partial = Path(str(corpus) + ".partial")
    validate = g.agentprov("8-validate", "validate", "--corpus", str(partial), timeout=900)
    counters = summary.get("counters") if isinstance(summary, dict) else None
    ok = run.returncode == 0 and validate.returncode == 0 and partial.is_dir()
    steps.record(8, "W", ok, t, run_exit=run.returncode, counters=counters, validate_exit=validate.returncode,
                 network="not enforced: the guest has network; the scripted transport makes no model call",
                 stderr_tail=_tail(run.stderr + validate.stderr) if not ok else "")


def step9(steps: Steps, g: Guest) -> None:
    """The containment Run Live offers on this OS (P-4), read from the GUI package of this checkout; nothing starts."""
    t = time.monotonic()
    probe = ("import json; from agentprov_gui.live.runspec import containment_choices, containment_line; "
             "print(json.dumps({c: containment_line(c) for c in containment_choices()}))")
    done = g.run("9-containment", ["uv", "run", "--no-sync", "--project", "gui", "python", "-c", probe])
    offered = _json(done.stdout)
    ok = isinstance(offered, dict) and set(offered) == {"dedicated-user", "vm"}
    steps.record(9, "W", ok, t, offered=offered, expected=["dedicated-user", "vm"],
                 note="read from runspec.containment_choices (P-4), not by driving the Run Live dialog",
                 stderr_tail=_tail(done.stderr) if not ok else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uv", type=Path, required=True)
    ap.add_argument("--checkout", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    (args.out / "w").mkdir(parents=True, exist_ok=True)
    uv_dir, src = Path.home() / "uv", Path.home() / "src"
    for archive, dest, strip in ((args.uv, uv_dir, True), (args.checkout, src, False)):
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            if strip:
                for m in members:
                    m.name = m.name.split("/", 1)[1] if "/" in m.name else m.name
                members = [m for m in members if m.name]
            tf.extractall(dest, members=members, filter="tar")  # the guest's own copy of files the host made
    g = Guest(src, Path.home() / "g5-home", args.out)
    steps = Steps(args.out)
    if not step4(steps, g):
        return 1  # steps 5-9 need the environment
    step5(steps, g)
    step6(steps, g)
    step7(steps, g)
    step8(steps, g)
    step9(steps, g)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
