# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Examination 2, D01/D02: metamorphic determinism checks (read-only; nothing is written into a corpus).

D01 re-derives SEM and PROV from each sampled execution's corpus AER with the project's own functions (the body of the
import pipeline's ``prov`` job: ``annotate`` + ``dumps_sem`` + ``derive(check_aer=False)``) and compares the bytes with
the corpus SEM and PROV files, under an environment matrix (TZ, locale, PYTHONHASHSEED, PYTHONUTF8, worker count).
With ``--validate`` (baseline configuration only) it also re-runs tiers 3-4 and compares the check statuses with the
corpus validation row.

D02 re-maps the raw primary object of each sampled whole-file execution (``map_artefact_total`` + the import seal path
with the degenerate fallback) and compares the AER bytes with the corpus AER. Context artefacts are rebuilt from the raw
store's origins (paths matching the profile's ``context_artefacts``), in label order.

Modes:
  sample   --corpora DIR... --out SAMPLE.json [--per-corpus 150] [--remap-per-corpus 50] [--seed 20261011]
  child    --sample SAMPLE.json --part K --of N --out RESULT.jsonl [--validate] [--remap]
  run      --sample SAMPLE.json --outdir DIR (all configurations, sequentially; the 4-worker one in parallel)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

SEED = 20261011
_UBIQUITOUS = {"map.accounting_unverifiable", "map.earlier_attempts_unobservable"}


def build_sample(corpora: list[str], per_corpus: int, remap_per: int, seed: int) -> dict[str, Any]:
    out: dict[str, Any] = {"seed": seed, "derive": [], "remap": [], "strata": {}}
    for c in corpora:
        root = Path(c).expanduser()
        rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
        rows = sorted((r for r in rows if (r.get("stages") or {}).get("aer") == "ok"), key=lambda r: r["ex"])
        strata: dict[tuple, list] = defaultdict(list)
        for r in rows:
            other = sorted(set(r.get("issues") or ()) - _UBIQUITOUS)
            strata[(r.get("profile"), bool(other), r.get("completeness"), r.get("status"))].append(r)
        total = len(rows)
        rnd = random.Random(f"{seed}:{root.name}")
        chosen: list[dict] = []
        alloc = {}
        for key in sorted(strata, key=str):
            members = strata[key]
            k = max(min(10, len(members)), round(per_corpus * len(members) / total))
            k = min(k, len(members))
            alloc[str(key)] = [len(members), k]
            chosen += rnd.sample(members, k)
        out["strata"][root.name] = alloc
        for r in chosen:
            out["derive"].append({"corpus": str(root), "ex": r["ex"], "paths": r["paths"], "raw": r.get("raw"),
                                  "unit": r.get("unit"), "profile": r.get("profile")})
        prims = [r for r in rows if r.get("unit") == "agent_execution"]
        rnd2 = random.Random(f"{seed}:remap:{root.name}")
        for r in rnd2.sample(prims, min(remap_per, len(prims))):
            out["remap"].append({"corpus": str(root), "ex": r["ex"], "paths": r["paths"], "raw": r.get("raw"),
                                 "profile": r.get("profile")})
    return out


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def child(sample: dict[str, Any], part: int, of: int, out_path: str, validate: bool, remap: bool) -> None:
    from agentprov.adapters.runner.provjob import PROFILES, tier3_checks, tier4_row
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate, dumps_sem

    items = sample["remap" if remap else "derive"][part::of]
    with open(out_path, "w", encoding="utf-8") as fh:
        for it in items:
            root = Path(it["corpus"]).expanduser()
            res: dict[str, Any] = {"ex": it["ex"], "corpus": root.name}
            try:
                if remap and str(it.get("profile", "")).startswith("survey-agentharm"):
                    res["skipped"] = "container_dialect"  # Inspect .eval: units come from a container plan, not replayed here
                elif remap:
                    res.update(_remap(root, it))
                else:
                    aer = (root / it["paths"]["aer"]).read_bytes()
                    doc = load_aer_bytes(aer)
                    sems, profiles = [], {}
                    res["sem"] = {}
                    for ref, p in (it["paths"].get("sem") or {}).items():
                        prof = PROFILES[ref]
                        sem = annotate(doc, prof)
                        data = dumps_sem(sem)
                        res["sem"][ref] = {"equal": data == (root / p).read_bytes(), "sha": _sha(data)[:16]}
                        sems.append(sem)
                        profiles[(prof.id, prof.version)] = prof
                    for spec, forms in (it["paths"].get("prov") or {}).items():
                        r = derive(doc, sems, sem_profiles=profiles, check_aer=False)
                        data = r.prov_json
                        res["prov"] = {"equal": data == (root / forms["json"]).read_bytes(), "sha": _sha(data)[:16]}
                        if validate:
                            from agentprov.sem.validate import validate_sem_document
                            from agentprov.validate import validate_prov

                            rep = validate_prov(data, doc, sems=sems)
                            row = tier4_row(rep, strict=True)
                            checks = dict(row["checks"])
                            for ref, sem in zip((it["paths"].get("sem") or {}), sems, strict=True):
                                checks.update(tier3_checks(validate_sem_document(sem, doc, mode="release", profile=PROFILES[ref]), ref))
                            stored = _stored_validation(root, it["ex"])
                            diff = {k: [v, stored.get(k)] for k, v in checks.items() if stored.get(k) != v}
                            res["validation_equal"] = not diff
                            res["validation_diff"] = sorted(diff)[:10]
            except Exception as exc:  # noqa: BLE001 - recorded, never hidden
                res["error"] = f"{type(exc).__name__}"
            fh.write(json.dumps(res, sort_keys=True) + "\n")


_VAL_CACHE: dict[str, dict[str, dict]] = {}


def _stored_validation(root: Path, ex: str) -> dict[str, str]:
    key = str(root)
    if key not in _VAL_CACHE:
        rows = {}
        for x in (root / "validation" / "results.jsonl").read_bytes().splitlines():
            if x:
                r = json.loads(x)
                rows[r["ex"]] = r.get("checks") or {}
        _VAL_CACHE[key] = rows
    return {k: v for k, v in _VAL_CACHE[key].get(ex, {}).items() if k != "aer.validator"}


_ORIGINS: dict[str, list[dict]] = {}


def _remap(root: Path, it: dict[str, Any]) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import aer_bytes, degenerate_unit, map_artefact_total
    from agentprov.aer.rules import RuleRegistry
    from agentprov.raw.origins import Origin

    aer = (root / it["paths"]["aer"]).read_bytes()
    header = json.loads(aer.split(b"\n", 1)[0])
    prim = next(a for a in header["artifacts"] if a.get("role") == "primary")
    sha = prim["sha256"]
    data = next(p for p in (root / "raw" / "objects" / sha[:2]).glob(f"{sha}.*") if p.is_file()).read_bytes()
    origin = Origin.from_json(prim["origin"])
    profile_id = str(it["profile"]).split("@")[0]
    profile = load_profile(profile_id)
    corpus = json.loads((root / "corpus.json").read_bytes())
    parts = next((s.get("parts") for s in corpus.get("sources", ()) if (s.get("profile") or {}).get("id") == profile_id), None)
    part = parts[0] if parts else None
    globs = tuple(profile.data.get("import", {}).get("context_artefacts", ()))
    context: list[dict] = []
    ctx_bytes: dict[str, bytes] = {}
    if globs:
        key = str(root)
        if key not in _ORIGINS:
            _ORIGINS[key] = [json.loads(x) for x in (root / "raw" / "origins.jsonl").read_bytes().splitlines() if x]
        seen = set()
        for row in _ORIGINS[key]:
            path = str(row["origin"].get("path") or "")
            if path and any(fnmatchcase(path, g) or path.endswith("/" + g) or path == g for g in globs) and path not in seen:
                h = row["sha256"].split(":", 1)[1]
                obj = next((p for p in (root / "raw" / "objects" / h[:2]).glob(f"{h}.*") if p.is_file()), None)
                if obj is None:
                    continue
                seen.add(path)
                b = obj.read_bytes()
                context.append({"label": path, "origin": row["origin"], "sha256": h, "size": len(b)})
                ctx_bytes[path] = b
        context.sort(key=lambda r: r["label"])
    registry = RuleRegistry.default()
    outcome, _unit = map_artefact_total(data, origin, profile_id=profile_id, part=part, context=context,
                                        context_bytes=ctx_bytes, registry=registry)
    from agentprov.adapters.runner import _family_classes  # noqa: PLC2701 - same factory as the importer

    imp = profile.data.get("import", {})
    _reader, mapper = _family_classes(str(imp.get("dialect")), str(imp.get("mapper")))
    fallback = degenerate_unit(sha, len(data), origin, profile=profile, mapper=mapper)
    got, _info = aer_bytes(outcome, registry=registry, unit=fallback, mapper=mapper, profile=profile)
    res: dict[str, Any] = {"aer_equal": got == aer, "context_rows": len(context)}
    if got != aer:
        a_lines, b_lines = got.split(b"\n"), aer.split(b"\n")
        res["lines"] = [len(a_lines), len(b_lines)]
        res["first_diff_line"] = next((i for i, (x, y) in enumerate(zip(a_lines, b_lines)) if x != y), None)
        if res["first_diff_line"] is not None:
            x = json.loads(a_lines[res["first_diff_line"]])
            y = json.loads(b_lines[res["first_diff_line"]])
            res["diff_keys"] = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))[:10]
            res["diff_record"] = f"{y.get('k')}:{y.get('id')}"
    return res


CONFIGS = [
    ("c0_baseline", {"TZ": "UTC", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONUTF8": "1"}, 1),
    ("c1_auckland_seed1", {"TZ": "Pacific/Auckland", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "PYTHONHASHSEED": "1", "PYTHONUTF8": "1"}, 1),
    ("c2_stjohns_tr_random", {"TZ": "America/St_Johns", "LC_ALL": "tr_TR.UTF-8", "LANG": "tr_TR.UTF-8", "PYTHONHASHSEED": "random", "PYTHONUTF8": "0"}, 1),
    ("c3_kolkata_de_seed12345", {"TZ": "Asia/Kolkata", "LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8", "PYTHONHASHSEED": "12345", "PYTHONUTF8": "0"}, 1),
    ("c4_c_locale_utf8mode", {"TZ": "Europe/London", "LC_ALL": "C", "LANG": "C", "PYTHONHASHSEED": "random", "PYTHONUTF8": "1"}, 1),
    ("c5_four_workers", {"TZ": "Australia/Eucla", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "PYTHONHASHSEED": "random", "PYTHONUTF8": "1"}, 4),
]


def run_all(sample_path: str, outdir: str) -> None:
    Path(outdir).mkdir(parents=True, exist_ok=True)
    me = str(Path(__file__).resolve())
    py = sys.executable
    for name, env_over, workers in CONFIGS:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "AGENTPROV_HOME")}
        env.update(env_over)
        procs = []
        for k in range(workers):
            args = [py, me, "child", "--sample", sample_path, "--part", str(k), "--of", str(workers),
                    "--out", str(Path(outdir) / f"{name}.{k}.jsonl")]
            if name == "c5_four_workers":  # tiers 3-4 re-run once, in the parallel configuration
                args.append("--validate")
            procs.append(subprocess.Popen(args, env=env))
        for p in procs:
            p.wait()
        print(name, "done", file=sys.stderr, flush=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "AGENTPROV_HOME")}
    env.update(CONFIGS[0][1])
    subprocess.run([py, me, "child", "--sample", sample_path, "--part", "0", "--of", "1", "--remap",
                    "--out", str(Path(outdir) / "d02_remap.jsonl")], env=env, check=False)
    print("remap done", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sample", "child", "run"])
    ap.add_argument("--corpora", nargs="*")
    ap.add_argument("--sample")
    ap.add_argument("--out")
    ap.add_argument("--outdir")
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--per-corpus", type=int, default=150)
    ap.add_argument("--remap-per-corpus", type=int, default=50)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--remap", action="store_true")
    a = ap.parse_args()
    if a.mode == "sample":
        s = build_sample(a.corpora, a.per_corpus, a.remap_per_corpus, a.seed)
        Path(a.out).write_text(json.dumps(s, sort_keys=True) + "\n", encoding="utf-8")
        print(len(s["derive"]), "derive;", len(s["remap"]), "remap", file=sys.stderr)
    elif a.mode == "child":
        child(json.loads(Path(a.sample).read_text(encoding="utf-8")), a.part, a.of, a.out, a.validate, a.remap)
    else:
        run_all(a.sample, a.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
