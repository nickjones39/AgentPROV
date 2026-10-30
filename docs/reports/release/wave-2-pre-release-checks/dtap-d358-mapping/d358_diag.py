"""DTap D-358 diagnosis (read only): the same `recompute --dry-run` as the stopped run, with two reporting patches in the
parent process. (1) Every non-identical change is listed (not only the first 20), and each `unexplained_change` is
written to OUT/changes.jsonl with its new index row's unit and raw refs. (2) The corpus-level comparison writes the
removed and added lines (after the same accounted-token filter) to OUT/corpus-diff.jsonl. Nothing else changes; the
workers are untouched and only OUT is written.
Usage: python d358_diag.py OUT <agentprov argv...>"""
import json
import sys
from collections import Counter
from pathlib import Path

import agentprov.cli.derive as cli_derive
from agentprov.cli.main import main
from agentprov.corpus.derive import Derivation

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
cli_derive._SHOWN_CHANGES = 10**6

_compare = Derivation.compare
_corpus = Derivation._compare_corpus_files


def compare(self, new, new_stages):
    report = _compare(self, new, new_stages)
    rows = {r.ex: r for r in new.index()}
    with open(OUT / "changes.jsonl", "w") as f:
        for ch in report.changes:
            r = rows.get(ch["ex"])
            rec = {**ch, "in_source": ch["ex"] in self.src_by_ex, "absent_ex": ch["ex"] in self.absent_ex,
                   "withheld_ex": ch["ex"] in self.withheld_ex}
            if r is not None and ch["class"] != "unverified":
                try:
                    rec.update(unit=r.unit, source_key=r.source_key, status=r.status, issues=list(r.issues),
                               raw=[{"sha256": ref.sha256, "role": getattr(ref, "role", None)} for ref in r.raw])
                except Exception as e:  # a reporting slip must not lose the run
                    rec["row_error"] = repr(e)
            if ch["class"] != "unverified" or not rec["in_source"]:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
    with open(OUT / "sets.json", "w") as f:
        json.dump({"absent": sorted(self.absent), "absent_ex": sorted(self.absent_ex),
                   "withheld_ex": sorted(self.withheld_ex), "absent_labels": sorted(self.absent_labels)}, f)
    return report


def compare_corpus_files(self, new, report, changed, renames=None):
    accounted = tuple(self.absent) + tuple(sorted(self.absent_ex | self.withheld_ex)) + tuple(sorted(self.absent_labels))
    with open(OUT / "corpus-diff.jsonl", "w") as f:
        for label in ("raw/origins.jsonl", "raw/members.jsonl", "register.jsonl"):
            old = self.src.read_bytes(label) if self.src.exists(label) else b""
            now = new.read_bytes(label) if new.exists(label) else b""
            if old == now:
                continue
            o = Counter(x for x in old.splitlines() if not any(t.encode() in x for t in accounted))
            n = Counter(x for x in now.splitlines() if not any(t.encode() in x for t in accounted))
            for side, lines in (("removed", o - n), ("added", n - o)):
                for line, k in lines.items():
                    f.write(json.dumps({"file": label, "side": side, "count": k, "line": line.decode("utf-8", "replace")}) + "\n")
    return _corpus(self, new, report, changed, renames)


Derivation.compare = compare
Derivation._compare_corpus_files = compare_corpus_files
sys.exit(main(sys.argv[2:]))
