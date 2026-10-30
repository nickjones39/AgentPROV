"""Phase 10q (memo-ozdincer/agentdojo, D-470..D-479): census of the results containers through the results-container build.

    uv run python tools/agentdojo/phase10q_trial.py census [--workers 10] [--cache DIR] [--out REPORT.json]
    uv run python tools/agentdojo/phase10q_trial.py scan --corpus DIR [--cache DIR]
    uv run python tools/agentdojo/phase10q_trial.py import --corpus DIR [--jobs 4] [--cache DIR] [--out REPORT.json]

``import`` is the part-C scratch trial (the registry part is ``planned``, so the CLI refuses it): the full pinned snapshot
through :func:`agentprov.adapters.runner.importer.import_source` in release mode up to validation, into a scratch corpus
(never under ``~/.agentprov/corpora``), as ``tools/agentdojo/phase10d_trial.py import`` does.

``scan`` checks a scratch corpus (part C, D-476): every file under it is searched for the account path forms of the
pinned containers' model strings (plain prefix, JSON-Pointer-escaped prefix, the whole string). Raw objects and the
raw-level descriptors may hold them (D-186 (c), D-510); derived files (AER, SEM, PROV, views, index) must not. Counts
only.

Reads every selected container of the profile's git pin from the bare, extraction-free fetch cache (``git ls-tree`` /
``git cat-file --batch``, each blob checked against its id; no checkout, no network), maps it one execution per row
(:func:`agentprov.adapters.runner.map_artefact_units`, D-320), seals each row with the core writer and counts: rows,
variants, units, degenerate rows, issue codes (rows), quirks the build detected but the profile does not declare
(``agentdojo.undeclared_quirk`` details, rows), judgement origins, redactions, the system prompts by SHA-256, and, as a
check of D-476, how many sealed AERs still hold a workstation account segment of their container's model string in any
form (expected 0). The report holds counts, codes, digests and paths only; never source text, never an account name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path
from typing import Any

PROFILE = "memo-ozdincer-agentdojo"
#: the account path prefix of a cluster checkpoint (the D-476 rules' structure; never printed). A bare account segment
#: is no test: it may occur inside ordinary words (rule ids, issue codes).
_ACCOUNT = re.compile(r"^/(?:scratch|mfs1/u)/[^/]+/")


def _work(job: tuple[str, str, str, str, bytes]) -> dict[str, Any]:
    repo, commit, path, blob, raw = job
    from agentprov.adapters.runner import NoExecution, aer_bytes, map_artefact_units
    from agentprov.adapters.types import Origin
    from agentprov.errors import MalformedArtefact
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    out: dict[str, Any] = {"path": path, "rows": 0, "variants": Counter(), "units": Counter(), "issues": Counter(),
                           "undeclared": Counter(), "origins": Counter(), "degenerate": 0, "redacted_rows": 0,
                           "account_leaks": 0, "system_prompts": Counter(), "sealed": 0,
                           "features": Counter(), "rows_with": Counter()}
    try:
        container = strict_json_loads(raw, IngestLimits())
        model = container.get("model") if isinstance(container, dict) else None
        prefix = _ACCOUNT.match(model) if isinstance(model, str) else None
        # the account path in every form a record could hold it: plain, JSON-Pointer-escaped, and the whole model string
        needles = ([prefix.group(0).encode(), prefix.group(0).replace("~", "~0").replace("/", "~1").encode(),
                    str(model).encode()] if prefix is not None else [])
        for row in container.get("results", ()) if isinstance(container, dict) else ():
            for m in row.get("messages", ()) if isinstance(row, dict) else ():
                if isinstance(m, dict) and m.get("role") == "system" and isinstance(m.get("content"), str):
                    out["system_prompts"][hashlib.sha256(m["content"].encode("utf-8", "surrogatepass")).hexdigest()] += 1
        pairs = map_artefact_units(raw, Origin.git(repo, commit, path, blob), profile_id=PROFILE, part="head")
    except NoExecution:
        out["status"] = "no_execution"
        return out
    except MalformedArtefact:
        out["status"] = "not_dialect"
        return out
    except Exception as exc:  # noqa: BLE001 - a crash is a finding; the label is the pinned path, never content
        out.update(status="crash", code=getattr(exc, "code", type(exc).__name__))
        return out
    out["status"] = "mapped"
    for outcome, unit in pairs:
        out["rows"] += 1
        out["variants"][unit.primary.variant] += 1
        out["degenerate"] += int(outcome.degenerate)
        data, info = aer_bytes(outcome)
        out["sealed"] += 1
        records = [json.loads(line) for line in data.splitlines()][:-1]
        out["units"][str(records[0].get("unit"))] += 1
        codes = {str(i["code"]) for i in info.issues}
        out["issues"].update(codes)
        out["undeclared"].update({str(i.get("detail")) for i in info.issues if i["code"] == "agentdojo.undeclared_quirk"})
        out["redacted_rows"] += int("rescont.value_redacted" in codes)
        seen: set[str] = set()
        for r in records:
            k = r.get("k")
            if k == "judgement":
                out["origins"][f"{r['name']}:{r['origin']}"] += 1
                if r["origin"] == "harness_default":
                    seen.add("exception_row" if any("exception_imposes" in x for x in r.get("rule", ())) else "benign_security")
            elif k == "decision" and r.get("verdict") == "terminate":
                out["features"]["melon_block"] += 1
                seen.add("melon_block")
            elif k == "message":
                ext = (r.get("ext") or {}).get("rescont") or {}
                if "copy_of" in ext:
                    out["features"]["repeat_copy"] += 1
                    seen.add("repeat_copy")
                if "content_state" in ext:
                    out["features"]["spotlighted_output"] += 1
                    seen.add("spotlighted_output")
                if (r.get("unk") or {}).get("/parts/0/text") == "ambiguous":
                    out["features"]["empty_assistant_text"] += 1
                    seen.add("empty_assistant_text")
                calls = sum(1 for p in r.get("parts", ()) if p.get("t") == "tool_call")
                if calls:
                    out["features"]["tool_calls"] += calls
                    seen.add("tool_calls")
            elif k == "tool_execution" and ("returned" in r or "raw_output" in ((r.get("ext") or {}).get("rescont") or {})):
                out["features"]["raw_output"] += 1
                seen.add("raw_output")
        if "unexecuted_tool_call" in codes:
            seen.add("unexecuted_trailing_calls")
        out["rows_with"].update(seen)
        if any(n in data for n in needles):
            out["account_leaks"] += 1
    return out


def _blobs(fetcher: Any, recipe: Any, include: tuple[str, ...], exclude: tuple[str, ...]) -> Iterator[tuple[str, str, str, str, bytes]]:
    from agentprov.adapters.runner.importer import _match

    entries, _skipped = fetcher.git_tree(recipe)
    chosen = [e for e in entries if e.is_blob and any(_match(e.path, g) for g in include)
              and not any(_match(e.path, g) for g in exclude)]
    seen: set[str] = set()
    for blob in fetcher.iter_git_blobs(recipe, chosen):
        if blob.entry.oid in seen:  # a byte-identical copy at another path collapses by source key (H.7.2)
            continue
        seen.add(blob.entry.oid)
        yield recipe.repo, recipe.commit, blob.entry.path, blob.entry.oid, blob.data


def census(*, cache: str | None = None, workers: int = 10) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(PROFILE)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    fetcher = Fetcher(resolve_cache_dir(cache))
    imp = profile.data["import"]
    include = tuple(imp.get("include", ()))
    exclude = tuple(e["glob"] for e in imp.get("exclude", ()))
    started = time.perf_counter()
    totals: dict[str, Counter[str]] = {k: Counter() for k in ("variants", "units", "issues", "undeclared", "origins",
                                                               "system_prompts", "features", "rows_with")}
    status: Counter[str] = Counter()
    sums: Counter[str] = Counter()
    crashes: list[dict[str, Any]] = []
    with Pool(workers) as pool:
        for row in pool.imap(_work, _blobs(fetcher, recipe, include, exclude), chunksize=2):
            status[row["status"]] += 1
            if row["status"] == "crash":
                crashes.append({"path": row["path"], "code": row.get("code")})
            for key in totals:
                totals[key].update(row[key])
            for key in ("rows", "sealed", "degenerate", "redacted_rows", "account_leaks"):
                sums[key] += row[key]
    return {
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
        "pin": recipe.commit, "containers": dict(sorted(status.items())), **dict(sorted(sums.items())),
        **{k: dict(sorted(v.items())) for k, v in totals.items()}, "crashes": crashes[:50],
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


def _needles(cache: str | None) -> list[bytes]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(PROFILE)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    imp = profile.data["import"]
    out: set[bytes] = set()
    for _repo, _commit, _path, _oid, raw in _blobs(Fetcher(resolve_cache_dir(cache)), recipe, tuple(imp["include"]),
                                                  tuple(e["glob"] for e in imp["exclude"])):
        model = strict_json_loads(raw, IngestLimits()).get("model")
        prefix = _ACCOUNT.match(model) if isinstance(model, str) else None
        if prefix is not None:
            out |= {prefix.group(0).encode(), prefix.group(0).replace("~", "~0").replace("/", "~1").encode(), model.encode()}
    return sorted(out)


def run_import(corpus: Path, *, cache: str | None = None, jobs: int = 4) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import GitPinTree, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(PROFILE)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    tree = GitPinTree(Fetcher(resolve_cache_dir(cache)), recipe)
    limits = IngestLimits()
    part = profile.parts[0]
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release", part=part,
                               snapshot_id=part, corpus_id=profile.source_id, until="validation", workers=jobs,
                               limits=limits, pin=pin)
    return {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "pin": recipe.commit,
            "jobs": jobs, "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"], "path": f["subject"].get("path")} for f in report.failures[:50]],
            "notices": list(report.notices)[:20], "elapsed_s": round(time.perf_counter() - started, 1)}


#: corpus files that describe raw objects and may repeat their origin data (D-186 (c), D-510)
_RAW_LEVEL = ("raw/", "register", "WITHHELD.json")


def scan(corpus: Path, *, cache: str | None = None) -> dict[str, Any]:
    needles = _needles(cache)
    raw_hits: Counter[str] = Counter()
    derived_hits: Counter[str] = Counter()
    files = 0
    for path in sorted(p for p in corpus.rglob("*") if p.is_file()):
        files += 1
        rel = path.relative_to(corpus).as_posix()
        data = path.read_bytes()
        if any(n in data for n in needles):
            (raw_hits if rel.startswith(_RAW_LEVEL) or "/register" in rel else derived_hits)[rel.split("/", 1)[0]] += 1
    return {"files": files, "needles": len(needles), "raw_level_files_with_paths": dict(raw_hits),
            "derived_files_with_paths": dict(derived_hits)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("--cache", default=None)
    c.add_argument("--workers", type=int, default=10)
    c.add_argument("--out", type=Path, default=None)
    s = sub.add_parser("scan")
    s.add_argument("--corpus", type=Path, required=True)
    s.add_argument("--cache", default=None)
    i = sub.add_parser("import")
    i.add_argument("--corpus", type=Path, required=True)
    i.add_argument("--cache", default=None)
    i.add_argument("--jobs", type=int, default=4)
    i.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        report = scan(args.corpus, cache=args.cache)
    elif args.cmd == "import":
        report = run_import(args.corpus, cache=args.cache, jobs=args.jobs)
    else:
        report = census(cache=args.cache, workers=args.workers)
    text = json.dumps(report, indent=1, sort_keys=False)
    if getattr(args, "out", None) is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
