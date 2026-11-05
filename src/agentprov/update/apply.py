"""The Windows update helper (D-1065): ``python -I -m agentprov.update.apply PLAN``.

Started detached by ``agentprov update install --confirm`` (or ``rollback --yes``) on Windows, where the running app's
``.exe`` and folder cannot be renamed. It reads the plan that command wrote (``.AgentPROV-update/plan.json``, beside the
bundle), retries the swap of :mod:`agentprov.update.install` every :data:`RETRY_S` seconds until it succeeds (the app
has quit) or the plan's ``wait_s`` has passed, then writes the outcome to the plan's ``result`` file
(``$AGENTPROV_HOME/update/applied.json``) and removes the stage folder. It prints nothing and starts nothing; the user
reopens the app.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from agentprov.update.install import PLAN_FORMAT, STAGE_DIR, swap_back, swap_in
from agentprov.update.releases import utc_text

RETRY_S: Final = 2.0
_KEYS: Final = frozenset({"format", "op", "bundle", "previous", "new", "stage", "wait_s", "result", "record"})


def _plan(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        doc = json.loads(fh.read(1024 * 1024))
    if not isinstance(doc, dict) or set(doc) != _KEYS or doc["format"] != PLAN_FORMAT or doc["op"] not in (
            "install", "rollback"):
        raise ValueError("not an update plan")
    for key in ("bundle", "previous", "stage", "result") + (("new",) if doc["op"] == "install" else ()):
        if not isinstance(doc[key], str) or not os.path.isabs(doc[key]):
            raise ValueError("an update plan path is not absolute")
    stage = Path(doc["stage"])
    if stage.name != STAGE_DIR or stage != path.parent or Path(doc["bundle"]).parent != stage.parent:
        raise ValueError("the update plan is not beside its bundle")
    if not isinstance(doc["wait_s"], int) or not 0 <= doc["wait_s"] <= 24 * 3600:
        raise ValueError("the update plan's wait is out of range")
    return doc


def apply(plan_path: Path, *, sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Run the plan; the outcome written to its ``result`` file."""
    plan = _plan(plan_path)
    bundle, previous = Path(plan["bundle"]), Path(plan["previous"])
    deadline = clock() + plan["wait_s"]
    attempts, error = 0, None
    while True:
        attempts += 1
        try:
            if plan["op"] == "install":
                swap_in(bundle, Path(plan["new"]), previous)
            else:
                swap_back(bundle, previous)
            error = None
            break
        except OSError as exc:  # the app still runs (a sharing violation) or the folder is in use
            error = type(exc).__name__
            if clock() >= deadline:
                break
            sleep(RETRY_S)
    state = ("installed" if plan["op"] == "install" else "rolled-back") if error is None else "failed"
    outcome = {**plan["record"], "state": state, "attempts": attempts, "error": error,
               "applied_at": utc_text(dt.datetime.now(dt.UTC))}
    result = Path(plan["result"])
    result.parent.mkdir(parents=True, exist_ok=True)
    tmp = result.with_name(f".{result.name}.{os.getpid()}")
    tmp.write_bytes(json.dumps(outcome, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    os.replace(tmp, result)
    if error is None:
        shutil.rmtree(plan["stage"], ignore_errors=True)
    else:
        plan_path.unlink(missing_ok=True)  # the next install may start again; the new folder stays for inspection
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    try:
        outcome = apply(Path(args[0]))
    except (OSError, ValueError):
        return 1
    return 0 if outcome["state"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
