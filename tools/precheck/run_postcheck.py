"""Run the post-check of the regenerated stored corpora inside ONE queued job (docs/reports/postcheck/README.md).

    uv run python tools/suite_queue.py --class import --cpu 4 --mem-gib 8 --label postcheck-round1 -- \\
        uv run python tools/precheck/run_postcheck.py [--only CORPUS[,CORPUS]] [--steps S[,S]] [--force] [--list]

Per corpus, in this order (README section 3): ``raw`` and ``ids`` (rg1 against p10), ``seal`` (seal forecast), ``l2_rg1``
and ``l2_p10`` (full population), ``sample_rg1`` and ``sample_p10`` (the frozen pre-check sample's executions, per
part), ``verify`` (``agentprov verify --level chain``), ``dryrun`` (``agentprov recompute --dry-run --jobs 4``; the round
ran ``--jobs 3``), ``validate`` (``agentprov validate --strict --tiers aer,sem,prov,linkage --jobs 4``, fresh at this
commit), ``scan`` (release-scan forecast with the pinned gitleaks, 4 threads), ``import`` (the frozen sample re-imported
into scratch, ``l2_import.py --jobs 2``, per part), ``tie`` (scratch against rg1) and ``check`` (``l2_check.py`` on the
scratch import, commands included). Every corpus input is read-only; outputs go to
``docs/reports/postcheck/data/<corpus>/`` (counts, digests, statuses) and logs to
``<precheck root>/postcheck/_batch/`` (scratch, never committed). A CLI step's ``--summary-json`` is kept in scratch and
reduced (exit code, outcome, counters, issue codes, failures, notices) into the data directory. A step whose output exists
is skipped (resumable); ``--force`` reruns. A failed step is recorded and the next step runs. ``--list`` prints the
commands (the protocol records them) and runs nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parents[2]
DATA: Final = REPO / "docs" / "reports" / "postcheck" / "data"
PRE: Final = REPO / "docs" / "reports" / "precheck" / "data"
STEPS: Final = ("raw", "ids", "seal", "l2_rg1", "l2_p10", "sample_rg1", "sample_p10", "verify", "dryrun", "validate", "scan",
                "import", "tie", "check", "dispatch")  # fmt: skip
TIMEOUT: Final = 8 * 3600
TIERS: Final = "aer,sem,prov,linkage"  # the round's tiers (D-354 addendum: no regression tier in validate --corpus)


@dataclass(frozen=True)
class Part:
    pre: str  # pre-check corpus id (docs/reports/precheck/data/<pre>/)
    source: str
    part: str


@dataclass(frozen=True)
class Corpus:
    id: str
    parts: tuple[Part, ...]
    new: str = "rg1"  # the tree checked: corpora/<id>-<new>.partial
    old: str = "p10.pre-regen"  # its predecessor
    data: str = ""  # data directory name (default: the id)

    @property
    def name(self) -> str:
        return self.data or self.id

    @property
    def new_tag(self) -> str:  # file-name tag of the checked tree ("rg1"); steps keep their role names (l2_rg1 = new)
        return self.new.split(".", 1)[0]

    @property
    def old_tag(self) -> str:  # file-name tag of the predecessor ("p10")
        return self.old.split(".", 1)[0]


CORPORA: Final = (
    Corpus("mandate-agentdojo-eval", (Part("mandate-agentdojo-eval", "mandate-agentdojo-eval", "head"),)),
    Corpus("ast-survey-agentharm", (Part("ast-survey-agentharm", "agent-security-tools-survey", "agentharm"),)),
    Corpus("ast-survey-agentdojo", (Part("ast-survey-agentdojo", "agent-security-tools-survey", "agentdojo-runs"),)),
    Corpus("adprov-v1-release", (Part("adprov-v1", "adprov-v1", "release"),)),
    Corpus("agentdojo-upstream-2024-06", (Part("agentdojo-upstream", "agentdojo", "2024-06"),)),
    Corpus("rope", (Part("rope", "rope", "head"), Part("rope", "autodojo", "rope-slice"))),
    Corpus("agentdojo-upstream-head", (Part("agentdojo-upstream", "agentdojo", "head"),)),
    Corpus("agentdyn-a", (Part("agentdyn", "agentdyn", "a"),)),
)


def precheck_root() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from l2_common import precheck_root as root

    return root()


def home() -> Path:
    return Path(os.environ.get("AGENTPROV_HOME") or (Path.home() / ".agentprov")).expanduser()


def _units(p: Part) -> Path:
    units_part = "head" if p.part == "rope-slice" else p.part  # the AutoDojo slice reads ROPE's L1 rows (pre-check plan)
    return precheck_root() / p.pre / f"l1-units-{units_part}.jsonl"


def commands(c: Corpus) -> list[tuple[str, list[str], Path, Path | None]]:
    """``(step, argv, output that marks it done, CLI summary to reduce or None)``, in order."""
    corpora = home() / "corpora"
    new, old = corpora / f"{c.id}-{c.new}.partial", corpora / f"{c.id}-{c.old}.partial"
    out = DATA / c.name
    batch = precheck_root() / "postcheck" / "_batch"
    py = ["uv", "run", "python"]
    pc = [*py, "tools/precheck/post_check.py"]
    q = ["-q", "--progress", "off"]
    rows: list[tuple[str, list[str], Path, Path | None]] = [
        ("raw", [*pc, "raw", "--old", str(old), "--new", str(new), "--out", str(out / "raw.json")], out / "raw.json", None),
        ("ids", [*pc, "ids", "--old", str(old), "--new", str(new), "--out", str(out / "ids.json")], out / "ids.json", None),
        ("seal", [*pc, "seal-forecast", "--corpus", str(new), "--spec", f"corpora/{c.id}/corpus-spec.toml", "--out",
                  str(out / "seal-forecast.json")], out / "seal-forecast.json", None),
        ("l2_rg1", [*pc, "l2", "--corpus", str(new), "--out", str(out / f"l2-full-{c.new_tag}.json")],
         out / f"l2-full-{c.new_tag}.json", None),
        ("l2_p10", [*pc, "l2", "--corpus", str(old), "--out", str(out / f"l2-full-{c.old_tag}.json")],
         out / f"l2-full-{c.old_tag}.json", None),
    ]
    for tag, tree in ((c.new_tag, new), (c.old_tag, old)):
        for p in c.parts:
            o = out / f"l2-sample-{p.part}-{tag}.json"
            rows.append(("sample_rg1" if tag == c.new_tag else "sample_p10", [*pc, "l2", "--corpus", str(tree), "--scope", "sample", "--sample",
                                           str(PRE / p.pre / f"l2-sample-{p.part}.json"), "--l1-units", str(_units(p)),
                                           "--out", str(o)], o, None))
    for step, argv in (("verify", ["verify", "--corpus", str(new), "--level", "chain"]),
                       ("dryrun", ["recompute", "--corpus", str(new), "--dry-run", "--jobs", "4"]),
                       ("validate", ["validate", "--corpus", str(new), "--strict", "--tiers", TIERS, "--jobs", "4"])):
        summary = batch / f"{c.name}.{step}.summary.json"
        rows.append((step, [*py, "-m", "agentprov", *argv, *q, "--summary-json", str(summary)], out / f"{step}.json", summary))
    rows.append(("scan", [*pc, "scan", "--corpus", str(new), "--gitleaks", shutil.which("gitleaks") or "gitleaks",
                          "--threads", "4", "--out", str(out / "scan.json")], out / "scan.json", None))
    for p in c.parts:
        scratch = precheck_root() / "postcheck" / c.id / f"post-{p.part}"
        rows.append(("import", [*py, "tools/precheck/l2_import.py", "--sample", str(PRE / p.pre / f"l2-sample-{p.part}.json"),
                                "--corpus", str(scratch), "--source", p.source, "--part", p.part, "--jobs", "2",
                                "--mode", "release",  # as the round imported (fn_digest and validation rows record it)
                                "--summary-json", str(batch / f"{c.id}.import-{p.part}.json")],
                     batch / f"{c.id}.import-{p.part}.json", None))
        rows.append(("tie", [*pc, "tie", "--scratch", f"{scratch}.partial", "--stored", str(new), "--out",
                             str(out / f"tie-{p.part}.json")], out / f"tie-{p.part}.json", None))
        rows.append(("check", [*py, "tools/precheck/l2_check.py", "--corpus", f"{scratch}.partial", "--out",
                               str(out / f"l2-scratch-{p.part}.json"), "--sample", str(PRE / p.pre / f"l2-sample-{p.part}.json"),
                               "--l1-units", str(_units(p)), "--jobs", "2", "--tiers", TIERS],
                     out / f"l2-scratch-{p.part}.json", None))
    for tag, tree in ((c.new_tag, new), (c.old_tag, old)):
        rows.append(("dispatch", [*pc, "dispatch", "--corpus", str(tree), "--out", str(out / f"dispatch-{tag}.json")],
                     out / f"dispatch-{tag}.json", None))
    return rows


def reduce_summary(summary: Path, out: Path, exit_code: int) -> None:
    """The CLI ``--summary-json`` reduced to counts and codes (no path, no value): ``l2_check._summary_view``."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from l2_check import _summary_view
    from l2_common import write_json

    doc = json.loads(summary.read_text(encoding="utf-8")) if summary.is_file() else None
    write_json(out, {"format": "agentprov-postcheck-cli/0.1", "exit_code": exit_code, **_summary_view(doc)})


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--only", help="corpus ids, comma-separated")
    ap.add_argument("--steps", help="steps, comma-separated (default all)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true", help="print the commands and run nothing")
    ap.add_argument("--variant", help="ID:NEW:OLD: check corpora/ID-NEW.partial against ID-OLD.partial (data dir ID-NEW); "
                                      "the sample re-import is the base corpus's (its scratch and marker are reused)")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    steps = set(a.steps.split(",")) if a.steps else set(STEPS)
    batch = precheck_root() / "postcheck" / "_batch"
    batch.mkdir(parents=True, exist_ok=True)
    status = batch / "status.jsonl"
    corpora: tuple[Corpus, ...] = CORPORA
    if a.variant:  # ID:NEW:OLD, e.g. adprov-v1-release:rg2:rg1 (a re-derived or re-imported tree against its predecessor)
        cid, new, old = a.variant.split(":")
        base = next(c for c in CORPORA if c.id == cid)
        corpora = (Corpus(cid, base.parts, new=new, old=old, data=f"{cid}-{new}"),)
    for c in corpora:
        if only is not None and c.id not in only:
            continue
        (DATA / c.name).mkdir(parents=True, exist_ok=True)
        for n, (step, cmd, done, summary) in enumerate(commands(c)):
            if step not in steps:
                continue
            if a.list:
                print(f"{c.id} {step}: " + " ".join(cmd).replace(str(Path.home()), "~"))
                continue
            if done.exists() and not a.force:
                continue
            log = batch / f"{c.name}.{step}.{n}.log"
            started = time.time()
            with log.open("wb") as handle:
                try:
                    rc = subprocess.run(cmd, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT, timeout=TIMEOUT,
                                        check=False).returncode
                except subprocess.TimeoutExpired:
                    rc = 124
            if summary is not None:
                reduce_summary(summary, done, rc)
            row = {"corpus": c.name, "step": step, "n": n, "rc": rc, "seconds": round(time.time() - started, 1),
                   "done": done.exists()}
            with status.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            print(json.dumps(row, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
