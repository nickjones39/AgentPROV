"""Write ``docs/reports/phase10d/README.md``'s results table from the saved phase-10d reports (counts only).

    uv run python tools/agentdojo/phase10d_report.py

Reads, per profile, ``docs/reports/phase10d/<profile>.census.json`` (census over the full pinned snapshot),
``<profile>.reconcile.json`` (against the phase-10c census), and, where present, ``<profile>.trial.json`` (two trial
imports at different worker counts, their corpus summaries and the byte comparison). Prints the Markdown table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "reports" / "phase10d"


def row(profile: str) -> str:
    census = json.loads((ROOT / f"{profile}.census.json").read_text(encoding="utf-8"))
    reconcile = json.loads((ROOT / f"{profile}.reconcile.json").read_text(encoding="utf-8"))
    agree = sum(1 for v in reconcile.values() if v["agree"])
    explained = sum(1 for v in reconcile.values() if not v["agree"] and v.get("explanation"))
    unresolved = census["files_by_issue_code"].get("identity_unresolved", 0)
    trial_path = ROOT / f"{profile}.trial.json"
    if trial_path.is_file():
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        runs = trial["imports"]
        a = runs[0]["summary"]
        trial_cell = (f"{a['executions']} executions; stages {', '.join(sorted({k.split(':')[1] for k in a['stages']}))}; "
                      f"{len(a['validation_failed'])} failing checks; jobs {'/'.join(str(r['jobs']) for r in runs)}: "
                      f"{'byte-identical' if trial['compare']['n_differ'] == 0 and not trial['compare']['only_a'] and not trial['compare']['only_b'] else 'DIFFER'}")
    else:
        trial_cell = "pending"
    return (f"| `{profile}` | {census['files']} | {', '.join(f'{k} {v}' for k, v in sorted(census['variants'].items()))} | "
            f"{len(census['crashes'])} | {len(census['differences'])} | {agree} agree, {explained} explained | {unresolved} | {trial_cell} |")


def table() -> str:
    profiles = sorted(p.name.removesuffix(".census.json") for p in ROOT.glob("*.census.json"))
    lines = ["| Profile | Logs mapped | Variants | Crashes | Census differences (before fill) | Reconciled with 10c | "
             "Identity unresolved | Trial import |", "|---|---:|---|---:|---:|---|---:|---|"]
    return "\n".join(lines + [row(p) for p in profiles])


def main() -> int:
    """Print the table; with ``--write``, replace the README's results table (between its Results heading and the
    column notes) by it."""
    text = table()
    if "--write" in sys.argv[1:]:
        readme = ROOT / "README.md"
        doc = readme.read_text(encoding="utf-8")
        head, rest = doc.split("## Results\n\n", 1)
        _old, tail = rest.split("\n\nColumn notes:", 1)
        readme.write_text(f"{head}## Results\n\n{text}\n\nColumn notes:{tail}", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
