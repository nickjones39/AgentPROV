"""Count the fail-closed SEM annotations of a working corpus (numbers only; docs/architecture C.14.3, D.6.14).

    uv run python tools/agentdojo/sem_unknown_tools.py --corpus DIR.partial [--out REPORT.json]

The semantics profile ``agentdojo.suites`` annotates a tool it has no table for as ``unknown`` (integrity ``unknown``, role
``["unknown"]``, no channel; rule ``agentdojo.unknown_tool@1``). AgentDyn's new suites (``shopping``, ``github``,
``dailylife``; benchmark label ``agentdyn``) have no table, so every tool execution and tool call of those logs is unknown by
design. This tool reads only the ``sem/**/*.sem.jsonl`` files of the corpus and prints, per annotation type, how many
annotations cite the unknown-tool rule, in how many logs, and how many annotations there are in all. It never prints text of
the sources.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

UNKNOWN_TOOL = "agentdojo.unknown_tool@1"


def scan(corpus: Path) -> dict[str, object]:
    files = sorted(corpus.glob("sem/*/*/*.sem.jsonl"))
    annotations: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    unknown_files = 0
    executions = 0
    calls = 0
    for path in files:
        seen = False
        for line in path.read_bytes().splitlines():
            record = json.loads(line)
            if record.get("k") != "ann":
                continue
            annotations[str(record["type"])] += 1
            if UNKNOWN_TOOL in record.get("rule", ()):
                seen = True
                unknown[str(record["type"])] += 1
                target = str(record["target"])
                if record["type"] == "role" and "#" not in target:
                    executions += 1
                elif record["type"] == "role":
                    calls += 1
        unknown_files += seen
    return {
        "sem_files": len(files),
        "annotations": sum(annotations.values()),
        "annotations_by_type": dict(sorted(annotations.items())),
        "unknown_tool_annotations_by_type": dict(sorted(unknown.items())),
        "unknown_tool_annotations": sum(unknown.values()),
        "files_with_unknown_tool_annotations": unknown_files,
        "unknown_tool_executions": executions,
        "unknown_tool_call_parts": calls,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = scan(args.corpus)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
