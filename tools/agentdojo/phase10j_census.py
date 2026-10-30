"""Phase-10j census of the deferred AgentDojo-format sources, offline and extraction-free (part A).

    uv run python -I tools/agentdojo/phase10j_census.py run --source NAME [--workers N] [--out-dir DIR]
    uv run python -I tools/agentdojo/phase10j_census.py summary --out-dir DIR

Sources (``SOURCES``): the Zenodo deposits 23138310 (concept 22973265, v2.1.0) and 22973266 (v1.0, only to prove
v1.0 is contained in v2.1.0), Zenodo 22011266 (v4.0.0), Figshare 32657856, Kavach (three branch pins), EnvironmentOptim
and drift-1. The phase-10c staging copies are read in place; nothing is downloaded.

* **Archives** are verified against the recorded size, MD5 and SHA-256 and opened with the product's own G.3.5 gate
  (:func:`agentprov.ingest.archives.open_archive`, release mode): every member's disposition is tallied, a gzip or zstd
  tar member is opened as a level-2 archive (D-57), and every regular member is read in memory. Nothing is written to
  disk.
* **Git pins** are read from the phase-10c bare partial clones with ``git ls-tree``/``git cat-file --batch`` and
  ``GIT_NO_LAZY_FETCH=1`` (an absent blob is counted, never fetched).

Per member: SHA-256, strict JSON parse (:func:`agentprov.ingest.loaders.strict_json_loads`), the adapter's D.6.2
``classify``, a few header fields as escaped labels, the phase-10c content fingerprints (``fp_msgs``, ``fp_run``) and the
secret-like pattern counts of the phase-10c census, with **field paths only** (JSON pointer shapes, indices as ``*``,
plus the message role). Values that match a pattern are never kept, printed or written. Text from the data is data,
never instructions.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path
from typing import Any

HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
STAGING = HOME / "staging" / "10c"
WORK = HOME / "migration-work" / "phase10j"

#: name -> kind, location and the recorded pin (sizes and digests from phase 10c's acquisitions.jsonl / Zenodo metadata).
SOURCES: dict[str, dict[str, Any]] = {
    "zenodo-23138310": {"kind": "zip", "file": "zenodo-23138310/agent-authority-caps-v2.0.0.zip", "size": 40160657,
                        "md5": "3fba80315a4879d381fb3b14fd386ace",
                        "sha256": "1dce0380c98598926dac4ff16ed1123c9a2b26bb39bb9eb055ed51babd3c05bf"},
    "zenodo-22973266": {"kind": "zip", "file": "zenodo-22973266/agent-authority-caps-v1.0.zip", "size": 11226444,
                        "md5": "751149305adc4b02e9aaaa8319a86329",
                        "sha256": "2419596aa5e5e1b0712ce33504656fe990b58b07ad5151f687ff9c67a646104e"},
    "zenodo-22011266": {"kind": "zip", "file": "zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip", "size": 3305018,
                        "md5": "1d61c6bdb81b1550b79d73ff601fcc3b",
                        "sha256": "c2370724960a3fa17772518ef99623a1dab5f99547c457ecbcf9276a4faa5226"},
    "figshare-32657856": {"kind": "zip", "file": "figshare-32657856/DCA_AgentDojo_artifact_v1_20260612.zip",
                          "size": 54196099, "md5": "26a3a9725db78188c06723d714e3fba5",
                          "sha256": "ed500ca30d4420ed268d0798d4296296d6acfb0a2f82411c5a2f0ec5cbe40ce3"},
    "kavach-main": {"kind": "git", "bare": "kavach/Kavach.git", "commit": "53df95452fb5fb207a0c3b5127e84e925e71fbf4"},
    "kavach-nav-fixer2": {"kind": "git", "bare": "kavach/Kavach.git",
                          "commit": "f2dd7efa01aed5a4d92e86e9d2ead5f19a326ab7"},
    "kavach-rearch-forcedformat-fix": {"kind": "git", "bare": "kavach/Kavach.git",
                                       "commit": "6b31a5546b152c93435772bb4f3521dd78ee3446"},
    "environmentoptim": {"kind": "git", "bare": "environmentoptim/EnvironmentOptim.git",
                         "commit": "febf82d8d1d8344d6c19e9fd172b51e52d68416a"},
    "drift-1": {"kind": "git", "bare": "drift-1/drift-1.git", "commit": "0e28729b4d9a6f466ba4803ccdc18a842c50cd20"},
}

SECRET_PATTERNS = {  # the phase-10c census set (c00_common.py), so counts compare with phase 10c and RT-10
    "openai_sk": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "anthropic_sk": re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    "aws_akid": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_pat": re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{40,}"),
    "google_api": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "hf_token": re.compile(rb"\bhf_[A-Za-z0-9]{30,}\b"),
    "slack_token": re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "bearer": re.compile(rb"[Bb]earer [A-Za-z0-9._~+/-]{20,}"),
}
_STR_PATTERNS = {k: re.compile(p.pattern.decode()) for k, p in SECRET_PATTERNS.items()}
_HEADER = ("suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type", "benchmark_version",
           "agentdojo_package_version")


def _lab(value: Any, n: int = 120) -> Any:
    from agentprov.ingest.quote import escape_untrusted

    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return escape_untrusted(value[:n])
    return f"<{type(value).__name__}>"


def _cj(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _secret_paths(obj: Any) -> dict[str, list[str]]:
    """Pattern -> sorted JSON pointer shapes (indices as ``*``; the message role in brackets) of matching strings."""
    found: dict[str, set[str]] = collections.defaultdict(set)

    def walk(v: Any, path: str, role: str | None) -> None:
        if isinstance(v, dict):
            r = v.get("role") if isinstance(v.get("role"), str) and path.count("/") <= 2 else role
            for k, x in v.items():
                walk(x, f"{path}/{_lab(str(k), 40)}", r)
        elif isinstance(v, list):
            for x in v:
                walk(x, f"{path}/*", role)
        elif isinstance(v, str):
            for name, pat in _STR_PATTERNS.items():
                if pat.search(v):
                    found[name].add(f"{path}" + (f" [{role}]" if role else ""))

    walk(obj, "", None)
    return {k: sorted(v) for k, v in sorted(found.items())}


def analyse(job: tuple[str, str, bytes]) -> dict[str, Any]:
    """One member: digests, parse, classification, header labels, fingerprints, secret counts and field paths."""
    from agentprov.adapters.agentdojo.dialect import classify
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    container, label, data = job
    rec: dict[str, Any] = {"container": container, "label": label, "size": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()}
    sec = {k: n for k, p in SECRET_PATTERNS.items() if (n := len(p.findall(data)))}
    if sec:
        rec["secrets"] = sec
    if not label.endswith(".json"):
        return rec
    try:
        obj = strict_json_loads(data, IngestLimits())
    except IngestError as exc:
        rec["parse"] = exc.code
        return rec
    except Exception as exc:  # noqa: BLE001 - the census is total; the label is a pinned name, never content
        rec["parse"] = f"exception:{type(exc).__name__}"
        return rec
    rec["parse"] = "ok"
    if sec:
        rec["secret_paths"] = _secret_paths(obj)
    sniff = classify(obj)
    if not sniff.match:
        rec["tracelogger"] = False
        return rec
    rec["tracelogger"] = True
    rec["variant"] = sniff.variant
    rec["flags"] = sorted(sniff.flags or ())
    for key in _HEADER:
        rec[key] = _lab(obj.get(key)) if key in obj else "<absent>"
    ts = obj.get("evaluation_timestamp")
    rec["ts_month"] = ts[:7] if isinstance(ts, str) else ("<absent>" if "evaluation_timestamp" not in obj else None)
    for key in ("utility", "security"):
        v = obj.get(key, "<absent>")
        rec[key] = v if isinstance(v, bool) or v is None or v == "<absent>" else f"<{type(v).__name__}>"
    err = obj.get("error", "<absent>")
    rec["error"] = "absent" if err == "<absent>" else "null" if err is None else "str" if isinstance(err, str) else "other"
    msgs = obj.get("messages", obj.get("conversations"))
    run = {k: obj.get(k) for k in ("suite_name", "user_task_id", "injection_task_id", "attack_type", "injections")}
    run["messages"] = msgs
    rec["fp_msgs"] = hashlib.sha256(_cj(msgs)).hexdigest()
    rec["fp_run"] = hashlib.sha256(_cj(run)).hexdigest()
    if isinstance(msgs, list):
        rec["n_messages"] = len(msgs)
        system = next((m for m in msgs if isinstance(m, dict) and m.get("role") == "system"), None)
        if system is not None:
            content = system.get("content")
            text = content if isinstance(content, str) else "".join(
                b.get("content") or "" for b in content or [] if isinstance(b, dict) and isinstance(b.get("content"), str))
            rec["system_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            rec["system_len"] = len(text)
        last = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "assistant"), None)
        rec["last_assistant_null"] = None if last is None else last.get("content") is None
    return rec


# ---------------------------------------------------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------------------------------------------------


def verify_file(path: Path, pin: dict[str, Any]) -> None:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    if (size, md5.hexdigest(), sha.hexdigest()) != (pin["size"], pin["md5"], pin["sha256"]):
        raise SystemExit(f"{path.name}: size, md5 or sha256 differs from the recorded pin")


def _archive_members(fh: io.BufferedIOBase | io.BytesIO, container: str, depth: int,
                     gate: collections.Counter[str]) -> Iterator[tuple[str, str, bytes]]:
    from agentprov.errors import IngestError
    from agentprov.ingest.archives import iter_zip_members, open_archive

    with open_archive(fh, release=True, depth=depth) as archive:
        for member in iter_zip_members(archive, None):
            key = f"d{depth}:{member.disposition}" + (f":{member.code}" if member.code else "")
            gate[key] += 1
            if member.disposition != "selected" or member.label is None:
                continue
            data = archive.read_member(member)
            if member.label.endswith((".tar.gz", ".tgz", ".tar.zst", ".zip")):
                gate[f"d{depth}:nested_container"] += 1
                try:
                    yield from _archive_members(io.BytesIO(data), f"{container}!{member.label}", depth + 1, gate)
                except IngestError as exc:
                    gate[f"d{depth + 1}:container_refused:{exc.code}"] += 1
                    yield container, member.label, data
                continue
            yield container, member.label, data


def archive_jobs(name: str, gate: collections.Counter[str]) -> Iterator[tuple[str, str, bytes]]:
    pin = SOURCES[name]
    path = STAGING / pin["file"]
    verify_file(path, pin)
    with path.open("rb") as fh:
        yield from _archive_members(fh, pin["file"].split("/", 1)[1], 1, gate)


def git_jobs(name: str, gate: collections.Counter[str]) -> Iterator[tuple[str, str, bytes]]:
    pin = SOURCES[name]
    bare = STAGING / pin["bare"]
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
    listing = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "-l", "-z", pin["commit"]], env=env,
                             check=True, capture_output=True).stdout
    entries: list[tuple[str, str]] = []
    for row in listing.split(b"\0"):
        if not row:
            continue
        meta, _, path = row.partition(b"\t")
        mode, typ, oid, size = meta.split()
        if typ != b"blob":
            gate[f"git:{typ.decode()}"] += 1
            continue
        if size == b"-":
            gate["git:absent_blob"] += 1
            continue
        if mode == b"120000":
            gate["git:symlink"] += 1
            continue
        entries.append((path.decode("utf-8", "surrogateescape"), oid.decode()))
    proc = subprocess.Popen(["git", "-C", str(bare), "cat-file", "--batch"], env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for path, oid in entries:
            proc.stdin.write(oid.encode() + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                gate["git:missing"] += 1
                continue
            data = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)
            if hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != oid:
                raise SystemExit(f"{name}: blob {oid} does not hash to its id")
            gate["git:blob"] += 1
            yield f"{name}@{pin['commit'][:12]}", path, data
    finally:
        proc.stdin.close()
        proc.wait()


def run(name: str, workers: int, out_dir: Path) -> dict[str, Any]:
    gate: collections.Counter[str] = collections.Counter()
    jobs = archive_jobs(name, gate) if SOURCES[name]["kind"] == "zip" else git_jobs(name, gate)
    started = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with Pool(workers) as pool, (out_dir / f"{name}.files.jsonl").open("w") as out:
        for rec in pool.imap(analyse, jobs, chunksize=16):
            out.write(json.dumps(rec, sort_keys=True, ensure_ascii=True) + "\n")
            n += 1
    report = {"source": name, "pin": {k: v for k, v in SOURCES[name].items() if k != "file"}, "gate": dict(sorted(gate.items())),
              "members_read": n, "elapsed_s": round(time.perf_counter() - started, 1)}
    (out_dir / f"{name}.gate.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return report


# ---------------------------------------------------------------------------------------------------------------------
# Summary (counts and labels only; the input is the per-member JSONL written by ``run``)
# ---------------------------------------------------------------------------------------------------------------------

_TASK_DIR = re.compile(r"^(user|injection)_task_\d+$")
#: A cluster home path munged into a logged model name (EnvironmentOptim): the account segment is masked in reports.
_ACCOUNT = re.compile(r"(_ceph_ssd_students_)[^_/]+(_)")
_KAVACH = ("kavach-main", "kavach-nav-fixer2", "kavach-rearch-forcedformat-fix")


def _mask(label: str) -> str:
    return _ACCOUNT.sub(r"\1<account>\2", label)


def _run_dir(rec: dict[str, Any]) -> str:
    """``<nested container>!<path above the suite directory>``: the pipeline (arm) directory of a member."""
    comps = rec["label"].split("/")
    inner = rec["container"].split("!", 1)[1] + "!" if "!" in rec["container"] else ""
    for i, c in enumerate(comps):
        if _TASK_DIR.match(c) and i >= 2:
            return _mask(inner + "/".join(comps[: i - 1]))
    return _mask(inner + "<no layout>")


def _novel(path: Path | None) -> set[str] | None:
    """The phase-10c novelty set (byte-distinct and absent from every converted source and reference), if available."""
    if path is None or not path.is_file():
        return None
    with path.open() as fh:
        return {json.loads(line)["sha256"] for line in fh}


def summarise(name: str, out_dir: Path, novel: set[str] | None) -> dict[str, Any]:
    with (out_dir / f"{name}.files.jsonl").open() as fh:
        recs = [json.loads(line) for line in fh]
    gate = json.loads((out_dir / f"{name}.gate.json").read_text())["gate"]
    tl = [r for r in recs if r.get("tracelogger")]
    distinct = {r["sha256"]: r for r in tl}
    count = collections.Counter
    out: dict[str, Any] = {
        "gate": gate, "members": len(recs), "json": sum(1 for r in recs if r["label"].endswith(".json")),
        "parse": dict(count(r.get("parse") for r in recs if r["label"].endswith(".json"))),
        "tracelogger_members": len(tl), "byte_distinct": len(distinct),
        "content_distinct_fp_run": len({r["fp_run"] for r in tl}),
        "variants_byte_distinct": dict(count(r["variant"] for r in distinct.values())),
        "colon_labels": sum(1 for r in recs if ":" in r["label"]),
    }
    if novel is not None:
        out["novel_vs_phase10c_known"] = {
            "new": dict(count(r["variant"] for r in distinct.values() if r["sha256"] in novel)),
            "known_elsewhere": dict(count(r["variant"] for r in distinct.values() if r["sha256"] not in novel)),
        }
    for key in ("suite_name", "attack_type", "benchmark_version", "agentdojo_package_version", "ts_month", "error",
                "utility", "security", "last_assistant_null"):
        out[key] = dict(sorted(count(str(r.get(key)) for r in distinct.values()).items()))
    out["system_prompt_sha256_len"] = dict(count(f"{str(r.get('system_sha256'))[:12]}|{r.get('system_len')}"
                                                 for r in distinct.values()).most_common())
    dirs: collections.Counter[str] = collections.Counter()
    for r in distinct.values():
        tag = "" if novel is None else (" [new]" if r["sha256"] in novel else " [known]")
        dirs[f"{_run_dir(r)} :: {_mask(str(r.get('pipeline_name')))} :: {r['variant']}{tag}"] += 1
    out["run_dirs_byte_distinct"] = dict(sorted(dirs.items()))
    byte_copies: collections.Counter[str] = collections.Counter()
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in tl:
        groups[r["sha256"]].append(r)
    for rs in groups.values():
        if len(rs) > 1:
            byte_copies[" | ".join(sorted({_run_dir(r) for r in rs}))] += len(rs) - 1
    out["byte_identical_extra_copies"] = dict(byte_copies.most_common())
    content: dict[str, set[str]] = collections.defaultdict(set)
    for r in distinct.values():
        content[r["fp_run"]].add(r["sha256"])
    out["content_repeats"] = {"groups": sum(1 for v in content.values() if len(v) > 1),
                              "files_in_groups": sum(len(v) for v in content.values() if len(v) > 1)}
    files: collections.Counter[str] = collections.Counter()
    matches: collections.Counter[str] = collections.Counter()
    paths: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for r in recs:
        if not r.get("secrets"):
            continue
        cls = ("run_log_new" if novel is not None and r["sha256"] in novel else "run_log") if r.get("tracelogger") \
            else ("other_json" if r["label"].endswith(".json") else "other_file")
        for k, v in r["secrets"].items():
            files[f"{cls}:{k}"] += 1
            matches[f"{cls}:{k}"] += v
        for k, ps in (r.get("secret_paths") or {}).items():
            for p in ps:
                paths[f"{cls}:{k}"][p] += 1
    out["secret_like"] = {"files": dict(sorted(files.items())), "matches": dict(sorted(matches.items())),
                          "field_paths": {k: dict(v.most_common()) for k, v in sorted(paths.items())}}
    return out


def summary(out_dir: Path, novel_path: Path | None) -> dict[str, Any]:
    novel = _novel(novel_path)
    present = [n for n in SOURCES if (out_dir / f"{n}.files.jsonl").is_file()]
    report: dict[str, Any] = {"sources": {n: summarise(n, out_dir, novel) for n in present}}

    def shas(n: str) -> set[str]:
        with (out_dir / f"{n}.files.jsonl").open() as fh:
            return {r["sha256"] for r in map(json.loads, fh) if r.get("tracelogger")}

    cross: dict[str, Any] = {}
    if {"zenodo-22973266", "zenodo-23138310"} <= set(present):
        v1, v2 = shas("zenodo-22973266"), shas("zenodo-23138310")
        cross["zenodo_v1_0_in_v2_1"] = {"v1_0": len(v1), "also_in_v2_1": len(v1 & v2), "only_v1_0": len(v1 - v2)}
    if set(_KAVACH) <= set(present):
        pins: dict[str, set[str]] = collections.defaultdict(set)
        fps: dict[str, set[str]] = collections.defaultdict(set)
        for n in _KAVACH:
            with (out_dir / f"{n}.files.jsonl").open() as fh:
                for r in map(json.loads, fh):
                    if r.get("tracelogger"):
                        pins[r["sha256"]].add(n)
                        fps[r["fp_run"]].add(r["sha256"])
        cross["kavach_three_pins"] = {
            "byte_distinct": len(pins), "content_distinct": len(fps),
            "by_pin_set": {" + ".join(sorted(k)): v for k, v in
                           sorted(collections.Counter(tuple(sorted(s)) for s in pins.values()).items())},
            "content_groups_with_several_byte_forms": sum(1 for v in fps.values() if len(v) > 1),
            "files_in_those_groups": sum(len(v) for v in fps.values() if len(v) > 1)}
    report["cross"] = cross
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--source", choices=sorted(SOURCES), action="append", required=True)
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--out-dir", type=Path, default=WORK / "census")
    s = sub.add_parser("summary")
    s.add_argument("--out-dir", type=Path, default=WORK / "census")
    s.add_argument("--novel", type=Path, default=HOME / "migration-work" / "phase10c" / "census" / "novel_sha256.jsonl")
    s.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "run":
        for name in args.source:
            print(json.dumps(run(name, args.workers, args.out_dir), sort_keys=True))
        return 0
    text = json.dumps(summary(args.out_dir, args.novel), indent=1, sort_keys=True, ensure_ascii=False)
    if args.report:
        args.report.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
