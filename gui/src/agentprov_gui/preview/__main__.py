"""The live preview helper process (design §9; D-398): ``python -I -m agentprov_gui.preview AGENTPROV_HOME``.

* Below-normal priority (``os.nice(10)``; ``BELOW_NORMAL_PRIORITY_CLASS`` on Windows), so the run's timing is not
  affected beyond noise.
* stdin: JSON lines ``{"watch": "<session id>"}`` from the GUI (sessions named by the job's ``session`` progress
  events). EOF (the GUI went away) ends the helper; the run is unaffected.
* stdout: JSON lines, one per delta, ``{"session", "op", "id", "kind", "label", "src", "dst"}`` (metadata only;
  ``model.PreviewGraph``). A broken pipe ends the helper.
* Every 250 ms each watched log is polled (at most 1 MiB per poll). It writes nothing to disk.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from agentprov_gui.preview.model import CaptureTail, PreviewGraph, capture_log

POLL_S = 0.25
MAX_SESSIONS = 256


def _lower_priority() -> None:
    try:
        if os.name == "nt":
            import psutil

            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except (OSError, AttributeError, ImportError):
        pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: python -I -m agentprov_gui.preview AGENTPROV_HOME\n")
        return 2
    home = Path(args[0])
    _lower_priority()
    pending: list[str] = []
    lock = threading.Lock()
    closed = threading.Event()

    def read_stdin() -> None:
        for raw in sys.stdin.buffer:
            if len(raw) > 4096:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            session = msg.get("watch") if isinstance(msg, dict) else None
            if isinstance(session, str):
                with lock:
                    pending.append(session)
        closed.set()

    threading.Thread(target=read_stdin, name="preview-stdin", daemon=True).start()
    tails: dict[str, tuple[CaptureTail, PreviewGraph]] = {}
    out = sys.stdout
    while not closed.is_set():
        with lock:
            new, pending[:] = list(pending), []
        for session in new:
            path = capture_log(home, session)
            if path is not None and session not in tails and len(tails) < MAX_SESSIONS:
                tails[session] = (CaptureTail(path), PreviewGraph(session))
        lines = []
        for session, (tail, graph) in tails.items():
            was = tail.stopped
            for event in tail.poll():
                lines += [json.dumps({"session": session, **d.to_json()}, separators=(",", ":"))
                          for d in graph.apply(event)]
            if tail.stopped and not was:
                lines.append(json.dumps({"session": session, "op": "stopped", "label": tail.stopped}))
        if lines:
            try:
                out.write("\n".join(lines) + "\n")
                out.flush()
            except (BrokenPipeError, OSError):
                return 0
        time.sleep(POLL_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
