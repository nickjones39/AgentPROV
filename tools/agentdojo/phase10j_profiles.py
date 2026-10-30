"""Phase-10j profile census: map every selected log of a part with its profile, offline (D.6.10 item 3; D.6.12).

    uv run python -I tools/agentdojo/phase10j_profiles.py census --profile ID --part P [--workers N] [--out REPORT.json]
    uv run python -I tools/agentdojo/phase10j_profiles.py fixtures --profile ID --part P --out-dir DIR [--max-bytes N]

The phase-10j sources are deposit archives (Zenodo 23138310 and 22011266, Figshare 32657856) or git pins (Kavach,
EnvironmentOptim, drift-1). The phase-10c staging copies are read in place, extraction-free; nothing is downloaded.

* **Archive pins.** The staged file is checked against the pin (size, md5, sha256) and opened with the product's G.3.5
  gate (:func:`agentprov.ingest.archives.open_archive`, release mode). A member that matches an ``[[import.nested]]``
  pattern is opened as the next level (D-382, D-57); every other member is selected by the profile's ``include`` and
  ``exclude`` globs, matched against its own label as the importer does (D-380). Each selected member is mapped with a
  ``member`` origin (container digest, label, method, CRC-32, size): the origin the import gives it (D-200, D-204).
* **Git pins.** ``git ls-tree``/``cat-file --batch`` over the phase-10c bare partial clone with ``GIT_NO_LAZY_FETCH=1``;
  each blob is checked against its id and mapped with a ``git`` origin (the profile's canonical repository, the pinned
  commit, the path and the blob id), as ``profile_census.py`` does.

Each mapping is sealed by the core writer (release-mode validation) and summed into the per-file census counts of
:mod:`agentprov.adapters.agentdojo.census`, then compared with the profile's ``observed`` table. The report holds counts,
codes, variants and labels only; never source text. ``fixtures`` writes the smallest selected log per criterion
(variant, issue code, quirk, nested level, identity row) byte-identically with a ``SOURCE.json`` (D-109, D-258).
"""

from __future__ import annotations

import argparse
import collections
import fnmatch
import hashlib
import io
import itertools
import json
import os
import subprocess
import sys
import time
import zlib
from collections.abc import Iterator, Mapping
from multiprocessing import Pool
from pathlib import Path
from typing import Any

HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
STAGING = HOME / "staging" / "10c"
#: The staged file of each archive pin, by its SHA-256 (phase-10c acquisitions).
ARCHIVES: dict[str, str] = {
    "1dce0380c98598926dac4ff16ed1123c9a2b26bb39bb9eb055ed51babd3c05bf": "zenodo-23138310/agent-authority-caps-v2.0.0.zip",
    "c2370724960a3fa17772518ef99623a1dab5f99547c457ecbcf9276a4faa5226": "zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip",
    "ed500ca30d4420ed268d0798d4296296d6acfb0a2f82411c5a2f0ec5cbe40ce3":
        "figshare-32657856/DCA_AgentDojo_artifact_v1_20260612.zip",
}
#: The phase-10c bare partial clone of each git source, by canonical repository.
BARES: dict[str, str] = {
    "https://github.com/Ishani018/Kavach": "kavach/Kavach.git",
    "https://github.com/omseeth/EnvironmentOptim": "environmentoptim/EnvironmentOptim.git",
    "https://github.com/CGboom-git/drift-1": "drift-1/drift-1.git",
}
_ENV = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
_PROFILE: dict[str, str] = {}


def _init(profile_id: str, part: str) -> None:
    _PROFILE["id"], _PROFILE["part"] = profile_id, part


def _match(label: str, glob: str) -> bool:
    from agentprov.adapters.runner.importer import _match as match

    return bool(match(label, glob))


def _pin(profile: Any, part: str) -> dict[str, Any]:
    pins = [dict(p) for p in profile.data["source"]["pins"]]
    own = [p for p in pins if p.get("part") == part]
    return own[0] if own else next(p for p in pins if p.get("primary") is True)


# ---------------------------------------------------------------------------------------------------------------------
# Candidates: (label, data, origin json, extra) with extra = {"level", "chain", "excluded"?}
# ---------------------------------------------------------------------------------------------------------------------


def _verify(path: Path, pin: dict[str, Any]) -> None:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    if (size, md5.hexdigest(), sha.hexdigest()) != (pin["size"], pin["md5"], pin["sha256"]):
        raise SystemExit(f"{path.name}: size, md5 or sha256 differs from the profile pin")


def _archive(fh: Any, container: str, depth: int, imp: dict[str, Any], chain: str,
             tally: collections.Counter[str]) -> Iterator[tuple[str, bytes, dict[str, Any], dict[str, Any]]]:
    from agentprov.ingest.archives import iter_zip_members, open_archive
    from agentprov.raw.origins import Origin

    include = tuple(imp.get("include", ()))
    nested = tuple(str(n["pattern"]) for n in imp.get("nested", ()))
    excludes = [e for e in imp.get("exclude", ()) if isinstance(e, Mapping)]
    with open_archive(fh, release=True, depth=depth, max_depth=max((int(n.get("max_depth", 0)) for n in
                                                                     imp.get("nested", ())), default=None) or None) as arc:
        for member in iter_zip_members(arc, None):
            if member.disposition != "selected" or member.label is None:
                tally[f"d{depth}:{member.disposition}:{member.code}"] += 1
                continue
            label = member.label
            if any(_match(label, g) for g in nested):
                tally[f"d{depth}:nested"] += 1
                data = arc.read_member(member)
                sha = hashlib.sha256(data).hexdigest()
                yield from _archive(io.BytesIO(data), sha, depth + 1, imp, f"{chain}{label}!/", tally)
                continue
            if not any(_match(label, g) for g in include):
                tally[f"d{depth}:not_selected"] += 1
                continue
            entry = next((e for e in excludes if _match(label, str(e["glob"]))), None)
            if entry is not None:
                tally[f"excluded:{entry.get('code')}"] += 1
                continue
            tally[f"d{depth}:selected"] += 1
            data = arc.read_member(member)
            origin = Origin.member(container, label, member.method, member.crc32, member.file_size)
            yield label, data, origin.to_json(), {"level": depth, "chain": chain + label}


def archive_candidates(profile: Any, pin: dict[str, Any], tally: collections.Counter[str]
                       ) -> Iterator[tuple[str, bytes, dict[str, Any], dict[str, Any]]]:
    path = STAGING / ARCHIVES[pin["sha256"]]
    _verify(path, pin)
    with path.open("rb") as fh:
        yield from _archive(fh, pin["sha256"], 1, dict(profile.data["import"]), "", tally)


def git_candidates(profile: Any, pin: dict[str, Any], tally: collections.Counter[str]
                   ) -> Iterator[tuple[str, bytes, dict[str, Any], dict[str, Any]]]:
    from agentprov.raw.origins import Origin

    repo = str(profile.data["source"]["canonical_repo"])
    bare = STAGING / BARES[repo]
    imp = dict(profile.data["import"])
    include = tuple(imp.get("include", ()))
    excludes = [e for e in imp.get("exclude", ()) if isinstance(e, Mapping)]
    out = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "-z", pin["commit"]], env=_ENV, check=True,
                         capture_output=True).stdout
    chosen: list[tuple[str, str]] = []
    for row in out.split(b"\0"):
        if not row:
            continue
        meta, _, raw_path = row.partition(b"\t")
        path, oid = raw_path.decode("utf-8", "surrogateescape"), meta.split()[2].decode()
        if not any(_match(path, g) for g in include):
            continue
        entry = next((e for e in excludes if _match(path, str(e["glob"]))), None)
        if entry is not None:
            tally[f"excluded:{entry.get('code')}"] += 1
            continue
        chosen.append((path, oid))
    proc = subprocess.Popen(["git", "-C", str(bare), "cat-file", "--batch"], env=_ENV, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for path, oid in chosen:
            proc.stdin.write(oid.encode() + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3:
                tally["git:absent_blob"] += 1
                continue
            data = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)
            if hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != oid:
                raise SystemExit(f"blob {oid} does not hash to its id")
            tally["git:selected"] += 1
            yield path, data, Origin.git(repo, pin["commit"], path, oid).to_json(), {"level": 0, "chain": path}
    finally:
        proc.stdin.close()
        proc.wait()


def candidates(profile: Any, part: str, tally: collections.Counter[str]
               ) -> Iterator[tuple[str, bytes, dict[str, Any], dict[str, Any]]]:
    pin = _pin(profile, part)
    if pin["kind"] == "git":
        return git_candidates(profile, pin, tally)
    return archive_candidates(profile, pin, tally)


# ---------------------------------------------------------------------------------------------------------------------
# Mapping (worker)
# ---------------------------------------------------------------------------------------------------------------------


def _work(job: tuple[str, bytes, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    label, raw, origin_json, extra = job
    from agentprov.adapters.agentdojo.census import census_file
    from agentprov.adapters.agentdojo.quirks import CensusFile
    from agentprov.adapters.runner import NotSelected, aer_bytes, map_artefact_total
    from agentprov.errors import MalformedArtefact
    from agentprov.raw.origins import Origin

    row: dict[str, Any] = {"path": extra["chain"], "label": label, "level": extra["level"], "size": len(raw),
                           "sha256": hashlib.sha256(raw).hexdigest(), "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"}
    try:
        origin = Origin(origin_json["kind"], {k: v for k, v in origin_json.items() if k != "kind"})
        outcome, unit = map_artefact_total(raw, origin, profile_id=_PROFILE["id"], part=_PROFILE["part"])
    except NotSelected:
        row["status"] = "not_selected"
        return row
    except MalformedArtefact:
        row["status"] = "not_dialect"
        return row
    except Exception as exc:  # a crash is a finding; the label is a pinned name, never content
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__))
        return row
    try:
        data, info = aer_bytes(outcome)
    except Exception as exc:  # noqa: BLE001
        row.update(status="seal_failed", code=getattr(exc, "code", type(exc).__name__), detail=str(exc)[:200])
        return row
    records = [json.loads(line) for line in data.splitlines()][:-1]
    actors = [r for r in records if r.get("k") == "actor"]
    agent = next((a for a in actors if a.get("id") == "agent"), None)
    defences = sorted(str(a.get("name")) for a in actors if a.get("kind") == "defense")
    row.update(status="degenerate" if outcome.degenerate else "sealed", variant=unit.primary.variant,
               unit=records[0].get("unit"), issues=sorted({str(i["code"]) for i in info.issues}),
               accounting=info.accounting.to_json()["status"], aer_sha256=hashlib.sha256(data).hexdigest(),
               model=(agent or {}).get("model", {}).get("requested"), defences=defences,
               census=census_file(CensusFile(records, info.issues)))
    return row


def census(profile_id: str, part: str, workers: int, rows_out: Path | None = None, limit: int | None = None,
           only: list[str] | None = None) -> dict[str, Any]:
    from agentprov.adapters.agentdojo.census import add, compare, declared
    from agentprov.adapters.agentdojo.profile import family_table
    from agentprov.adapters.profiles import load_profile

    profile = load_profile(profile_id)
    tally: collections.Counter[str] = collections.Counter()
    started = time.perf_counter()
    totals: dict[str, dict[str, int]] = {}
    count = collections.Counter
    status, variants, issues, accounting, units, models = count(), count(), count(), count(), count(), count()
    crashes: list[dict[str, Any]] = []
    samples: dict[str, list[str]] = {}
    digests: dict[str, str] = {}
    out = rows_out.open("w") if rows_out is not None else None
    try:
        with Pool(workers, initializer=_init, initargs=(profile_id, part)) as pool:
            jobs = candidates(profile, part, tally)
            if only:
                jobs = (j for j in jobs if any(fnmatch.fnmatchcase(j[3]["chain"], g) for g in only))
            if limit is not None:
                jobs = itertools.islice(jobs, limit)
            for row in pool.imap(_work, jobs, chunksize=8):
                status[row["status"]] += 1
                if out is not None:
                    out.write(json.dumps({k: v for k, v in row.items() if k != "census"}, sort_keys=True) + "\n")
                if row["status"] in ("crash", "seal_failed"):
                    crashes.append({k: row.get(k) for k in ("path", "code", "detail")})
                    continue
                if row["status"] in ("not_dialect", "not_selected"):
                    continue
                digests[row["path"]] = row["aer_sha256"]
                variants[str(row["variant"])] += 1
                units[str(row["unit"])] += 1
                accounting[str(row["accounting"])] += 1
                models[f"{row['model']} | {'+'.join(row['defences']) or 'none'}"] += 1
                issues.update(row["issues"])
                for code in row["issues"]:
                    if len(samples.setdefault(code, [])) < 3:
                        samples[code].append(row["path"])
                add(totals, row["census"])
    finally:
        if out is not None:
            out.close()
    table = family_table(profile)
    return {
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "part": part,
        "selection": dict(sorted(tally.items())), "files": sum(status.values()), "status": dict(sorted(status.items())),
        "variants": dict(sorted(variants.items())), "units": dict(sorted(units.items())),
        "accounting": dict(sorted(accounting.items())), "agent_model_defences": dict(sorted(models.items())),
        "files_by_issue_code": dict(sorted(issues.items())), "issue_samples": dict(sorted(samples.items())),
        "crashes": crashes[:50],
        "measured": {q: dict(sorted(k.items())) for q, k in sorted(totals.items())},
        "declared": declared(table, part), "differences": compare(table, part, totals),
        "aer_digest_of_digests": hashlib.sha256("".join(f"{k}\t{v}\n" for k, v in sorted(digests.items()))
                                                .encode()).hexdigest(),
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


# ---------------------------------------------------------------------------------------------------------------------
# Fixtures (D-109, D-258): the smallest selected log per criterion, byte-identical, with SOURCE.json
# ---------------------------------------------------------------------------------------------------------------------


def fixtures(profile_id: str, part: str, rows: Path, out_dir: Path, max_bytes: int, only: list[str] | None,
             forbid: list[str]) -> dict[str, Any]:
    """Pick from a census ``--rows`` file: per criterion the smallest sealed log, until ``max_bytes`` is reached."""
    from agentprov.adapters.profiles import load_profile

    profile = load_profile(profile_id)
    picked: dict[str, dict[str, Any]] = {}
    with rows.open() as fh:
        rs = [json.loads(line) for line in fh]
    rs = [r for r in rs if r["status"] in ("sealed", "degenerate")]
    rs = [r for r in rs if not any(fnmatch.fnmatchcase(r["path"], g) for g in forbid)]
    if only:
        rs = [r for r in rs if any(fnmatch.fnmatchcase(r["path"], g) for g in only)]
    rs.sort(key=lambda r: (r["size"], r["path"]))
    criteria: dict[str, Any] = collections.OrderedDict()
    for r in rs:
        keys = [f"variant:{r['variant']}", f"level:{r['level']}", f"model:{r.get('model')}|{r.get('defences')}"]
        keys += [f"issue:{c}" for c in r["issues"]]
        keys += [f"dir:{'/'.join(r['label'].split('/')[:-4])}"]
        for key in keys:
            criteria.setdefault(key, r)
    total = 0
    for key, r in criteria.items():
        if r["path"] in picked:
            picked[r["path"]]["criteria"].append(key)
            continue
        if total + r["size"] > max_bytes:
            continue
        picked[r["path"]] = {"row": r, "criteria": [key]}
        total += r["size"]
    wanted = {p: v for p, v in picked.items()}
    tally: collections.Counter[str] = collections.Counter()
    entries = []
    for label, data, origin_json, extra in candidates(profile, part, tally):
        hit = wanted.get(extra["chain"])
        if hit is None or hashlib.sha256(data).hexdigest() != hit["row"]["sha256"]:
            continue
        name = hit["row"]["sha256"][:16] + ".json"
        (out_dir / name).write_bytes(data)
        entries.append({"path": name, "part": part, "label": label, "chain": extra["chain"], "origin": origin_json,
                        "licence_class": "permissive", "synthetic": False,
                        "level": extra["level"], "sha256": hit["row"]["sha256"], "size": len(data),
                        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "variant": hit["row"]["variant"],
                        "criteria": sorted(hit["criteria"])})
    entries.sort(key=lambda e: e["chain"])
    return {"entries": entries, "bytes": sum(e["size"] for e in entries)}

# ---------------------------------------------------------------------------------------------------------------------
# observed: write the measured counts of census reports into the profile's quirk blocks
# ---------------------------------------------------------------------------------------------------------------------

#: The ``observed`` keys written per quirk (the keys earlier profiles declare); a quirk not listed keeps every measured key.
OBSERVED_KEYS: dict[str, tuple[str, ...]] = {
    "agentdojo.benign_security_constant": ("files", "origin_rule_applied"),
    "agentdojo.injection_task_as_user_task_prepass": ("files",),
    "agentdojo.silent_rerun_last_pass_only": ("null_final_logs",),
    "agentdojo.unexecuted_trailing_calls": ("calls", "logs"),
    "agentdojo.args_mutated_in_place": ("files",),
    "agentdojo.package_version_not_code_identity": ("files_without_package_version",),
    "agentdojo.placeholder_args_never_injection_evidence": ("present", "present_and_null"),
    "agentdojo.incomplete_run": ("files", "null_outcome_files"),
    "agentdojo.provider_call_id_anomalies": ("null_ids", "logs_with_null_ids", "logs_with_repeated_ids",
                                             "logs_with_duplicate_ids"),
    "agentdojo.pi_detector_redaction": ("logs", "redactions"),
    "agentdojo.tool_filter_aux_llm": ("logs", "logs_with_filter_messages"),
    "agentdojo.repeat_user_prompt_reinsertion": ("logs", "logs_with_copies"),
    "agentdojo.spotlighting_delimiters": ("logs", "logs_with_tool_results"),
    "agentdojo.run_error_imposes_outcome": ("files",),
    "agentdojo.empty_messages_without_outcome": ("files",),
    "agentdojo.empty_messages_with_outcome": ("files",),
    "agentdojo.dos_security_not_utility": ("files",),
}


def write_observed(profile_path: Path, reports: dict[str, Path]) -> list[str]:
    """Rewrite each ``[[family.agentdojo.quirk]]`` block's ``observed`` line from the reports' measured counts."""
    measured = {part: json.loads(path.read_text())["measured"] for part, path in reports.items()}
    lines = profile_path.read_text().split("\n")
    out: list[str] = []
    changed: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.strip() == "[[family.agentdojo.quirk]]":
            block = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith("["):
                block.append(lines[j])
                j += 1
            qid = next(b.split("=", 1)[1].strip().strip('"') for b in block if b.startswith("id = "))
            body = [b for b in block[1:] if not b.startswith("observed = ")]
            parts = []
            for part in sorted(measured):
                counts = measured[part].get(qid, {})
                keys = OBSERVED_KEYS.get(qid, tuple(sorted(counts)))
                inner = ", ".join(f"{k} = {counts.get(k, 0)}" for k in keys if k in counts)
                key = part if part.replace("_", "").replace("-", "").isalnum() and not part[0].isdigit() else f'"{part}"'
                parts.append(f"{key} = {{ {inner} }}")
            out[-1:] = [line, *body, f"observed = {{ {', '.join(parts)} }}"]
            changed.append(qid)
            i = j
            continue
        i += 1
    profile_path.write_text("\n".join(out))
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("--profile", required=True)
    c.add_argument("--part", required=True)
    c.add_argument("--workers", type=int, default=6)
    c.add_argument("--out", type=Path)
    c.add_argument("--rows", type=Path, help="write one JSON row per mapped log (counts and labels only)")
    c.add_argument("--limit", type=int, help="map only the first N selected logs (a quick check; counts then differ)")
    c.add_argument("--only", action="append", help="map only the logs whose chain label matches this glob (a quick check)")
    f = sub.add_parser("fixtures")
    f.add_argument("--profile", required=True)
    f.add_argument("--part", required=True)
    f.add_argument("--rows", type=Path, required=True)
    f.add_argument("--out-dir", type=Path, required=True)
    f.add_argument("--max-bytes", type=int, default=480 * 1024)
    f.add_argument("--only", action="append", help="glob over chain labels to draw from")
    f.add_argument("--forbid", action="append", default=[], help="glob over chain labels never to draw from")
    o = sub.add_parser("observed")
    o.add_argument("--profile-file", type=Path, required=True)
    o.add_argument("--report", action="append", required=True, help="PART=census report JSON")
    args = parser.parse_args(argv)
    if args.cmd == "observed":
        reports = dict(r.split("=", 1) for r in args.report)
        print(json.dumps(write_observed(args.profile_file, {k: Path(v) for k, v in reports.items()})))
        return 0
    if args.cmd == "census":
        report = census(args.profile, args.part, args.workers, args.rows, args.limit, args.only)
        text = json.dumps(report, indent=1, sort_keys=True) + "\n"
        if args.out is not None:
            args.out.write_text(text)
        print(json.dumps({k: report[k] for k in ("files", "status", "variants", "agent_model_defences", "files_by_issue_code",
                                                 "differences", "crashes", "selection", "elapsed_s")}, indent=1))
        return 0 if not report["differences"] and not report["crashes"] else 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    result = fixtures(args.profile, args.part, args.rows, args.out_dir, args.max_bytes, args.only, args.forbid)
    source = args.out_dir / "SOURCE.json"
    kept = [e for e in json.loads(source.read_text())] if source.is_file() else []
    kept = [e for e in kept if e["part"] != args.part] + result["entries"]
    kept.sort(key=lambda e: (e["part"], e["chain"]))
    source.write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"files": len(result["entries"]), "bytes": result["bytes"], "source_total": sum(e["size"] for e in kept)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
