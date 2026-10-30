"""The user guide's page of known corpus artefacts, generated from ``agentprov stats --artefacts`` outputs.

Usage::

    uv run python tools/gen_corpus_artefacts.py STATS_DIR [STATS_DIR ...]   # writes docs/user-guide/15-corpus-artefacts.md
    uv run python tools/gen_corpus_artefacts.py STATS_DIR --out PATH --home HOME

The page covers every sealed corpus under ``HOME/corpora`` (default ``$AGENTPROV_HOME``, else ``~/.agentprov``): each
directory whose ``corpus.json`` says ``sealed: true``. Working trees (``.partial``), withheld sidecars (``.withheld``)
and unsealed corpora are never listed. The ``STATS_DIR`` arguments hold one ``<corpus tree>.json`` per sealed corpus,
each written by::

    agentprov stats --corpus <tree> --artefacts --format json --out STATS_DIR/<tree>.json

Only files whose ``format`` is ``agentprov-stats/...`` are read; other JSON files in the directories are ignored. The
tool stops, writing nothing, when a sealed corpus has no stats file, has two, or has one that does not describe the
sealed corpus on disk: its ``corpus.state`` must be ``sealed``, and its corpus id and root digest must match the
corpus's ``corpus.json`` and ``checksums.sha256``. Stats files that name no sealed corpus (a working tree not yet
sealed, say) are listed on stderr and never used. Each corpus's heading is its corpus id (the id of its tag
``corpus/<corpus_id>/v<version>``; tree names are local to one machine), so its anchor is the id; the manifest title
without parenthetical remarks (which name repositories and snapshots) follows in italics. A title in the heading would
put its words in the anchor, where one ("task configurations") matched the site's key-shape leak guard. Corpora are
listed by corpus id.

The stats outputs are not committed (they are read from corpora under ``AGENTPROV_HOME``), so the page has no
``--check`` mode: regenerate it after a corpus is sealed or when an artefact catalogue changes. Artefact titles come
from the adapter families' ``artefacts.toml`` catalogues in this repository.

The page holds class names, titles, handling classes and counts only: never artefact contents, account paths, e-mail
addresses or keys. Counts are per corpus and never pooled. Rows are coverage, not a partition: one execution can show
several artefacts, and a class's count is summed over the per-model rows of the stats output (each execution has one
model). Unclassified findings (``artefact.unclassified.*``) are counted per execution and class.

Standard library only; reads each corpus's ``corpus.json`` and ``checksums.sha256`` and nothing else of it; no network.
Ported from the AgentPROV manuscript's ``paper/make_artefacts.py``.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "src" / "agentprov" / "adapters"
DEFAULT_OUT = ROOT / "docs" / "user-guide" / "15-corpus-artefacts.md"

HANDLING = ("CR", "DR", "RJ", "FO", "NR")
HANDLING_TEXT = {"CR": "correct representation", "DR": "derived reconstruction", "RJ": "recomputed judgement",
                 "FO": "flag only", "NR": "not recoverable"}
UNCLASSIFIED = "artefact.unclassified."


def catalogue_titles() -> dict[str, str]:
    """Artefact id -> title, from every adapter family's ``artefacts.toml``."""
    titles: dict[str, str] = {}
    for path in sorted(ADAPTERS.glob("*/artefacts.toml")):
        with path.open("rb") as f:
            for entry in tomllib.load(f).get("artefact", []):
                if "id" in entry and "title" in entry:
                    titles[entry["id"]] = entry["title"]
    return titles


def default_home() -> Path:
    raw = os.environ.get("AGENTPROV_HOME")
    return Path(raw) if raw else Path.home() / ".agentprov"


def short_name(title: str) -> str:
    """A manifest title without its parenthetical remarks, which name repositories, snapshots and commits."""
    return re.sub(r"\s+", " ", re.sub(r"\s*\([^()]*\)", "", title)).strip(" ,;:")


def sealed_corpora(home: Path) -> list[tuple[str, str, str, str]]:
    """(tree, short name, corpus id, root digest) for every sealed corpus under ``home/corpora``, by corpus id."""
    out = []
    corpora = home / "corpora"
    for path in sorted(corpora.iterdir()) if corpora.is_dir() else ():
        manifest = path / "corpus.json"
        if path.name.endswith((".partial", ".withheld")) or not manifest.is_file():
            continue
        m = json.loads(manifest.read_text(encoding="utf-8"))
        if m.get("sealed") is not True:
            continue
        root = "sha256:" + hashlib.sha256((path / "checksums.sha256").read_bytes()).hexdigest()
        out.append((path.name, short_name(m["title"]) or m["corpus_id"], m["corpus_id"], root))
    ids = [c for _t, _s, c, _r in out]
    if len(ids) != len(set(ids)):
        sys.exit("gen_corpus_artefacts: two sealed corpora share a corpus id: "
                 + ", ".join(sorted({c for c in ids if ids.count(c) > 1})))
    return sorted(out, key=lambda row: row[2])


def is_stats(path: Path) -> bool:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(doc, dict) and str(doc.get("format", "")).startswith("agentprov-stats/")


def stats_files(stats_dirs: list[Path]) -> dict[str, Path]:
    """Tree name -> stats file, over every ``<tree>.json`` stats output in the given directories."""
    found: dict[str, Path] = {}
    for d in stats_dirs:
        if not d.is_dir():
            sys.exit(f"gen_corpus_artefacts: {d} is not a directory")
        for path in sorted(d.glob("*.json")):
            if not is_stats(path):
                continue
            if path.stem in found:
                sys.exit(f"gen_corpus_artefacts: {path.stem} has two stats files: {found[path.stem]} and {path}")
            found[path.stem] = path
    return found


def load_corpus(path: Path, tree: str, corpus_id: str, root: str) -> dict:
    corpora = json.loads(path.read_text(encoding="utf-8"))["corpora"]
    if len(corpora) != 1:
        sys.exit(f"gen_corpus_artefacts: {path} holds {len(corpora)} corpora, expected one")
    corpus = corpora[0]
    meta = corpus.get("corpus", {})
    if meta.get("state") != "sealed" or meta.get("corpus_id") != corpus_id or meta.get("root_digest") != root:
        sys.exit(f"gen_corpus_artefacts: {path} does not describe the sealed corpus {tree} (state "
                 f"{meta.get('state')}, corpus id {meta.get('corpus_id')}, root digest {meta.get('root_digest')}; "
                 f"on disk: {corpus_id}, {root}); rerun `agentprov stats` on the sealed corpus")
    counts = corpus["tables"].get("counts", [])
    pop = corpus["population"]
    records = sum(r["records"] for r in counts) if counts else pop["rows"]
    outcome_only = sum(r["n_outcome_only"] for r in counts)
    if records != pop["rows"] or records - outcome_only != pop["n_executions"]:
        sys.exit(f"gen_corpus_artefacts: {tree}: records {records}, outcome-only {outcome_only} and "
                 f"n_executions {pop['n_executions']} do not add up")
    classes: dict[str, dict] = {}
    unclassified = 0
    for row in corpus["tables"].get("artefacts", []):
        if row["artefact_id"].startswith(UNCLASSIFIED):
            unclassified += row["executions"]
            continue
        c = classes.setdefault(row["artefact_id"], {"handling": row["handling"] or "", "executions": 0})
        c["executions"] += row["executions"]
    return {"records": records, "n_executions": pop["n_executions"], "outcome_only": outcome_only,
            "classes": classes, "unclassified": unclassified}


def fmt(n: int) -> str:
    return f"{n:,}"


def render(stats_dirs: list[Path], home: Path) -> str:
    titles = catalogue_titles()
    corpora = sealed_corpora(home)
    if not corpora:
        sys.exit(f"gen_corpus_artefacts: no sealed corpus under {home / 'corpora'}")
    files = stats_files(stats_dirs)
    missing = [t for t, _s, _c, _r in corpora if t not in files]
    if missing:
        sys.exit("gen_corpus_artefacts: sealed corpora without a stats file: " + ", ".join(missing))
    for tree in sorted(set(files) - {t for t, _s, _c, _r in corpora}):
        print(f"gen_corpus_artefacts: not used, names no sealed corpus: {files[tree]}", file=sys.stderr)
    md = [
        "<!-- Generated by tools/gen_corpus_artefacts.py from `agentprov stats --artefacts --format json`; do not edit."
        " Regenerate after a corpus is sealed or when a catalogue changes. -->",
        "",
        "# Known artefacts of the converted corpora",
        "",
        "Released logs contain artefacts of the harnesses that wrote them. Every corpus is scanned with the shared "
        "artefact layer (specification D.15), and each adapter family's catalogue names the artefacts it knows, with a "
        "detector and a handling class. The tables list, per corpus, each artefact class found, its handling class and "
        "how many records it affects. They hold class names, counts and handling only, never artefact contents. Rows "
        "are coverage, not a partition: one execution can show several artefacts. Findings that no catalogue entry "
        "claims appear as `artefact.unclassified.*` and are never filtered out.",
        "",
        "Handling classes: " + "; ".join(f"**{h}** {HANDLING_TEXT[h]}" for h in HANDLING) + ".",
        "",
        "Denominators: the `agentprov stats` population is the corpus's agent executions. Outcome-only records "
        "(AgentDojo logs with outcomes and an empty message list) are not agent executions; the scan still covers "
        "them, and the empty-message-list class counts them.",
        "",
        f"Corpora: the {len(corpora)} sealed corpora, listed by corpus id. Sealing withholds files and "
        "executions that hold personal data (decisions D-771, D-810 and D-811, and any later ones each corpus's "
        "`WITHHELD.json` records), so some execution counts are lower than in the working trees the corpora were "
        f"sealed from (generated {datetime.date.today()}).",
        "",
    ]
    for tree, short, corpus_id, root in corpora:
        d = load_corpus(files[tree], tree, corpus_id, root)
        line = f"{fmt(d['records'])} records in the corpus: {fmt(d['n_executions'])} agent executions"
        if d["outcome_only"]:
            line += f" and {fmt(d['outcome_only'])} outcome-only records"
        line += (f". {len(d['classes'])} artefact classes found; unclassified findings in {fmt(d['unclassified'])} "
                 "executions (counted per class).")
        md += [f"## `{corpus_id}`", "", f"*{short}*", "", line, "",
               "| Artefact class | Title | Handling | Records |", "|---|---|---|---|"]
        for aid, c in sorted(d["classes"].items(), key=lambda kv: (-kv[1]["executions"], kv[0])):
            title = titles.get(aid, "").replace("|", "\\|")
            md.append(f"| `{aid}` | {title} | {c['handling']} | {fmt(c['executions'])} |")
        md.append("")
    return "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stats_dir", type=Path, nargs="+",
                    help="directories of <corpus tree>.json files from `agentprov stats`, one file per sealed corpus")
    ap.add_argument("--home", type=Path, default=None,
                    help="the AgentPROV home whose corpora/ holds the sealed corpora (default: $AGENTPROV_HOME, "
                         "else ~/.agentprov)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the page to write (default: %(default)s)")
    args = ap.parse_args(argv)
    args.out.write_text(render(args.stats_dir, args.home or default_home()), encoding="utf-8")
    print(f"gen_corpus_artefacts: wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
