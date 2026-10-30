"""Where do a corpus's e-mail addresses first appear in each execution's AER? (D-810; counts and digests only.)

Usage::

    uv run python tools/scan_origins.py --corpus DIR \\
        [--upstream GIT_DIR COMMIT REPO_URL ...] [--upstream-dir DIR REVISION REPO_URL ...] [--exclude PREFIX ...] \\
        [--file-names PERSONA_FILE ...] [--pin REPO_URL COMMIT --source-id ID --corpus-id ID --out FILE]

The corpus's distinct addresses are those of ``tools/release_scan.py --list-addresses`` (stored files and decoded archive
members). Reserved-domain addresses, addresses found in the benchmark's own upstream data (``tools/scan_personas.py``) and
the digests of the ``--file-names`` persona files (already cleared for this corpus) are set aside. Each of the rest is a
**not-found** address, and this tool classifies it by where it **first** appears in each execution's AER, by position in the
conversation (a message by its index; a tool call's arguments at its call message, its other fields and a state change
just after it; the header, actors and fixtures before the conversation):

* ``benchmark-input``: the first appearance is in benchmark input in at least one execution: a message of the benchmark,
  the simulated user, the environment or tool runtime (a tool result), the attacker (an injection), a defence, or a
  fixture or header field;
* ``model-generated``: in every execution that holds it the first appearance is model output: a message of the agent or an
  LLM judge, or a tool call's arguments. Those at a public mail provider are their own class, ``withhold`` (reported as
  ``model-generated|public-freemail``): they may be a third party's real address, so sealing withholds their executions;
* ``withhold-object``: no AER record holds it, and every finding is in raw objects: one the import stores but does not
  map (such as a run of a part it does not import), or a cited object the mapper does not read it from (D-962). Sealing
  withholds those objects alone (path-scan 6, user decision 2026-10-28; D-961);
* ``not-in-aer``: any other address no AER string or object key holds (reported, never written; expected to be none).

(An address that is benchmark input in one execution and model output in another is ``benchmark-input``: the first
appearance in the benchmark's own input is the generous reading, and is counted in ``mixed``.)

Output, one JSON line of counts: per origin and domain class the distinct addresses and findings, the executions and raw
objects that withholding the ``model-generated`` public-freemail addresses would remove (the executions whose AER holds
one, with the objects of their primary or native records; shared ``supporting`` objects are not counted) and their split by
suite. **Never an address, local part or domain.**

With ``--out FILE`` it writes a persona file (``agentprov-personas/0.1``, :mod:`agentprov.corpus.personas`) with a
``benchmark-input``, a ``model-generated``, a ``withhold`` and a ``withhold-object`` group (each only when it has an
address): each address as its digest with the evidence of its first appearance (execution id, AER record id, JSON pointer
inside the record, actor kind), or for ``withhold-object`` the sha256 of the first raw object that holds it. ``--pin``, ``--source-id`` and
``--corpus-id`` name the corpus's pinned source for that evidence.

Exit codes: 0 ok; 1 an archive could not be read; 2 usage.
"""

from __future__ import annotations

import argparse
import collections
import json
import multiprocessing as mp
import os
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_scan as rs  # noqa: E402
import scan_personas as sp  # noqa: E402

from agentprov.corpus import personas as pe  # noqa: E402

#: Actor kinds (``actor.kind`` of the AER) whose messages are model output; every other kind is benchmark-supplied.
MODEL_ACTORS: Final = frozenset({"llm_agent", "judge"})
_BIG: Final = 1e9
_SKIP: Final = frozenset({"rule", "evf", "src", "id", "ns", "after", "k"})
_TARGETS: frozenset[str] = frozenset()
_RAW_OBJECT: Final = re.compile(r"raw/objects/[0-9a-f]{2}/([0-9a-f]{64})")


def _number(text: Any) -> int | None:
    match = re.match(r"^[a-z]*([0-9]+)", text if isinstance(text, str) else "")
    return int(match.group(1)) if match else None


def _segment(key: object) -> str:
    """A pointer segment for an object key; a key that holds an ``@`` (an address used as a member name) is written ``*``, so
    that an evidence pointer never carries an address."""
    text = str(key)
    return "*" if "@" in text else text.replace("~", "~0").replace("/", "~1")


def _strings(value: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    """``(JSON pointer, string)`` for every string value below ``value`` and for every object **key** (an address is often a
    map key: ``shared_with``, a permissions table). A key is reported at ``<its object's pointer>/*``."""
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, f"{pointer}/{i}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and "@" in key:
                yield f"{pointer}/*", key
            yield from _strings(item, f"{pointer}/{_segment(key)}")


def _init(targets: frozenset[str]) -> None:
    global _TARGETS
    _TARGETS = targets


def first_appearances(path: str | os.PathLike[str], targets: frozenset[str] | None = None) -> tuple[str, dict[str, tuple]]:
    """``(execution id, {digest: (position, origin, record id, pointer, actor kind)})`` for one AER file: the first
    appearance of each target address, in a string value or an object key. A tie in position goes to ``model``."""
    wanted = _TARGETS if targets is None else targets
    raw_lines = [line for line in Path(path).read_bytes().splitlines() if line.strip()]
    lines = [json.loads(line) for line in raw_lines]
    kinds = {rec["id"]: rec.get("kind") for rec in lines if rec["k"] == "actor"}
    call_pos = {rec["id"]: _number(str(rec.get("call", "")).split("#")[0]) for rec in lines if rec["k"] == "tool_execution"}
    best: dict[str, tuple] = {}

    def keep(digest: str, pointer: str, rec_id: str, pos: float, origin: str, actor_kind: str) -> None:
        cur = best.get(digest)
        if cur is None or pos < cur[0] or (pos == cur[0] and origin == "model" and cur[1] != "model"):
            best[digest] = (pos, origin, rec_id, pointer, actor_kind)

    def note(text: str, pointer: str, rec_id: str, pos: float, origin: str, actor_kind: str) -> None:
        if "@" not in text:
            return
        for _start, raw in pe.find_addresses(text.encode("utf-8", "replace") + b"\0"):
            digest = pe.address_digest(raw)
            if digest in wanted:
                seen_here.add(digest)
                keep(digest, pointer, rec_id, pos, origin, actor_kind)

    def note_bytes(line: bytes, rec_id: str, pos: float, origin: str, actor_kind: str) -> None:
        """D-962: the release scan reads the stored bytes, where a JSON escape can set an address boundary the decoded text
        does not have; such an address is the record's (pointer ``""``: the whole record), with the record's origin."""
        if b"@" not in line:
            return
        for _start, raw in pe.find_addresses(line + b"\0"):
            digest = pe.address_digest(raw)
            if digest in wanted and digest not in seen_here:
                keep(digest, "", rec_id, pos, origin, actor_kind)

    for seq, (rec, line) in enumerate(zip(lines, raw_lines, strict=True)):
        kind, rec_id = rec["k"], rec.get("id", "")
        body = {k: v for k, v in rec.items() if k not in _SKIP}
        seen_here: set[str] = set()
        if kind == "message":
            pos = _number(rec_id)
            actor_kind = kinds.get(rec.get("actor")) or "unknown"
            origin = "model" if actor_kind in MODEL_ACTORS else "bench"
            for pointer, text in _strings(body):
                note(text, pointer, rec_id, seq if pos is None else pos, origin, actor_kind)
            note_bytes(line, rec_id, seq if pos is None else pos, origin, actor_kind)
        elif kind == "tool_execution":
            called = call_pos.get(rec_id)
            at: float = _BIG if called is None else called
            for pointer, text in _strings({k: v for k, v in body.items() if k in ("args", "args_effective")}):
                note(text, pointer, rec_id, at, "model", "llm_agent")
            for pointer, text in _strings({k: v for k, v in body.items() if k not in ("args", "args_effective", "call")}):
                note(text, pointer, rec_id, at + 0.5, "bench", kinds.get(rec.get("actor")) or "unknown")
            note_bytes(line, rec_id, at, "model", "llm_agent")  # args or output: bytes cannot tell; model withholds more
        elif kind == "state_change":
            cause = rec.get("cause")
            caused = call_pos.get(cause if isinstance(cause, str) else None)
            for pointer, text in _strings(body):
                note(text, pointer, rec_id, _BIG if caused is None else caused + 0.6, "bench", "tool_runtime")
            note_bytes(line, rec_id, _BIG if caused is None else caused + 0.6, "bench", "tool_runtime")
        elif kind in ("execution", "actor", "fixture"):
            for pointer, text in _strings(body):
                note(text, pointer, rec_id, -1, "bench", "benchmark")
            note_bytes(line, rec_id, -1, "bench", "benchmark")
        elif kind in ("judgement", "scope", "activity", "decision", "model_call"):
            for pointer, text in _strings(body):
                note(text, pointer, rec_id, _BIG, "bench", kinds.get(rec.get("actor")) or "benchmark")
            note_bytes(line, rec_id, _BIG, "bench", kinds.get(rec.get("actor")) or "benchmark")
    return Path(path).name.removesuffix(".aer.jsonl"), best


def _task_of(path: str | os.PathLike[str]) -> tuple[str, str]:
    """``(suite, task id)`` of an execution from its AER header (``task``), for the withheld executions' split."""
    with open(path, encoding="utf-8") as handle:
        header = json.loads(handle.readline())
    task = header.get("task") if isinstance(header, dict) else None
    task = task if isinstance(task, dict) else {}
    return str(task.get("suite") or "unknown"), str(task.get("task_id") or "unknown")


def classify(per_execution: Mapping[str, Mapping[str, tuple]]) -> tuple[dict[str, str], dict[str, tuple[str, tuple]]]:
    """``(class per digest, evidence per digest)``: ``benchmark-input`` when any execution's first appearance is benchmark
    input, else ``model-generated``; the evidence is the first execution in id order whose first appearance has that
    origin: ``(execution id, (position, origin, record, pointer, actor kind))``."""
    seen: dict[str, dict[str, list[tuple[str, tuple]]]] = collections.defaultdict(lambda: {"bench": [], "model": []})
    for ex in sorted(per_execution):
        for digest, appearance in per_execution[ex].items():
            seen[digest][appearance[1]].append((ex, appearance))
    classes, evidence = {}, {}
    for digest, by_origin in seen.items():
        origin = "bench" if by_origin["bench"] else "model"
        classes[digest] = "benchmark-input" if origin == "bench" else "model-generated"
        evidence[digest] = by_origin[origin][0]
    return classes, evidence


def write_observed_file(out: Path, persona_id: str, source_id: str, corpus_id: str, pin: tuple[str, str],
                        classes: Mapping[str, str], evidence: Mapping[str, tuple[str, tuple]]) -> None:
    lines = [f'format = "{pe.PERSONA_FORMAT}"', f'id = "{persona_id}"']
    for klass in pe.CORPUS_CLASSES:
        digests = sorted(d for d, c in classes.items() if c == klass)
        if not digests:
            continue
        lines += ["", "[[group]]", f'class = "{klass}"', f'source_id = "{source_id}"', f'repo = "{pin[0]}"',
                  f'commit = "{pin[1]}"', f'corpus_id = "{corpus_id}"', "entries = ["]
        for digest in digests:
            if klass == "withhold-object":
                lines.append(f'  {{ address = "{digest}", object = "{evidence[digest][0]}" }},')
                continue
            ex, (_pos, _origin, record, pointer, actor) = evidence[digest]
            lines.append(f'  {{ address = "{digest}", ex = "{ex}", record = "{record}", pointer = {json.dumps(pointer)}, '
                         f'actor_kind = "{actor}" }},')
        lines.append("]")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyse(root: Path, upstream: Mapping[str, Any], cleared: frozenset[str], *, workers: int = 2) -> dict[str, Any]:
    """Everything this tool reports for the corpus tree at ``root`` (a dict of counts, plus ``_classes`` and ``_evidence``
    for the list writer, which the printed line leaves out)."""
    table: dict[str, rs.AddressStat] = {}
    unread = rs.collect_addresses(root, "c", table, workers=workers)
    not_found = {d for d, s in table.items() if s.klass != pe.CLASS_RESERVED and d not in upstream and d not in cleared}
    files = sorted((root / "aer").rglob("*.aer.jsonl")) if (root / "aer").is_dir() else []
    per_execution: dict[str, dict[str, tuple]] = {}
    targets = frozenset(not_found)
    if workers > 1 and len(files) > 64:
        with mp.Pool(workers, initializer=_init, initargs=(targets,)) as pool:
            for ex, found in pool.imap_unordered(first_appearances, files, chunksize=64):
                if found:
                    per_execution[ex] = found
    else:
        for path in files:
            ex, found = first_appearances(path, targets)
            if found:
                per_execution[ex] = found
    classes, evidence = classify(per_execution)
    # a model-only address at a public mail provider is withheld, not kept (G.9.5): its own class
    classes = {d: ("withhold" if c == "model-generated" and table[d].klass == pe.CLASS_FREEMAIL else c)
               for d, c in classes.items()}
    index_path = root / "executions.jsonl"
    cited: set[str] = set()  # every raw object an execution indexes, in any role
    if index_path.is_file():
        for line in open(index_path, encoding="utf-8"):
            cited.update(str(r.get("sha256", "")).removeprefix("sha256:") for r in json.loads(line).get("raw", []))
    evidence = dict(evidence)
    for digest in sorted(not_found - set(classes)):
        labels = [where for _c, where, _l in table[digest].findings]
        shas = {m.group(1) for where in labels if (m := _RAW_OBJECT.match(where))}
        # only in raw objects: withhold-object, whether an execution cites them or not (D-962); its object is withheld
        # alone (D-961), the executions stay. An uncited object is named as the evidence when there is one.
        if shas and all(_RAW_OBJECT.match(where) for where in labels):
            classes[digest] = "withhold-object"
            evidence[digest] = ("sha256:" + min(shas - cited or shas),)  # type: ignore[assignment]
    mixed = sum(1 for d in classes if len({a[1] for ex in per_execution.values() for dd, a in ex.items() if dd == d}) == 2)
    rows: dict[str, dict[str, int]] = {}
    for digest in not_found:
        origin = {"withhold": "model-generated", "withhold-object": "not-in-aer|raw-only"}.get(
            classes.get(digest, ""), classes.get(digest, "not-in-aer"))
        stat = table[digest]
        row = rows.setdefault(f"{origin}|{stat.klass}", {"addresses": 0, "findings": 0})
        row["addresses"] += 1
        row["findings"] += len(stat.findings)
    index: dict[str, list[str]] = {}
    if index_path.is_file():
        for line in open(index_path, encoding="utf-8"):
            row_ = json.loads(line)
            index[row_["ex"]] = [r["sha256"] for r in row_.get("raw", []) if r.get("included") and r.get("role") != "supporting"]
    freemail = [d for d in not_found if classes.get(d) == "withhold"]
    executions = {ex for ex, found in per_execution.items() if any(d in found for d in freemail)}
    objects = {sha for ex in executions for sha in index.get(ex, ())}
    closure = {ex for ex, objs in index.items() if objects & set(objs)}
    split: collections.Counter[str] = collections.Counter()
    tasks: set[tuple[str, str]] = set()
    layout_files = {p.name.removesuffix(".aer.jsonl"): p for p in files}
    for ex in executions:
        suite, task = _task_of(layout_files[ex])
        split[suite] += 1
        tasks.add((suite, task))
    held_objects = {d: {m.group(1) for _c, w, _l in table[d].findings if (m := _RAW_OBJECT.match(w))}
                    for d, c in classes.items() if c == "withhold-object"}
    return {"not_found": len(not_found), "executions_total": len(index), "mixed": mixed,
            "withhold_object": {"addresses": len(held_objects), "raw_objects": len(set().union(*held_objects.values()))},
            "not_in_aer_other": sum(1 for d in not_found if d not in classes),
            "by_origin_and_class": dict(sorted(rows.items())), "unread": unread,
            "withhold_model_generated_freemail": {
                "addresses": len(freemail), "executions": len(executions), "raw_objects": len(objects),
                "executions_via_shared_objects": len(closure), "by_suite": dict(sorted(split.items())),
                "distinct_tasks": len(tasks)},
            "_classes": classes, "_evidence": evidence}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan_origins.py", description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--upstream", action="append", nargs=3, default=[], metavar=("GIT_DIR", "COMMIT", "REPO_URL"))
    parser.add_argument("--upstream-dir", action="append", nargs=3, default=[], metavar=("DIR", "REVISION", "REPO_URL"))
    parser.add_argument("--exclude", action="append", default=[], metavar="PREFIX")
    parser.add_argument("--file-names", action="append", default=[], type=Path, metavar="PERSONA_FILE")
    parser.add_argument("--pin", nargs=2, metavar=("REPO_URL", "COMMIT"))
    parser.add_argument("--source-id")
    parser.add_argument("--corpus-id")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--id", dest="persona_id")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)
    if args.out and not (args.pin and args.source_id and args.corpus_id and args.persona_id):
        print("scan_origins: --out needs --pin, --source-id, --corpus-id and --id", file=sys.stderr)
        return 2
    upstream: dict[str, str] = {}
    try:
        for git_dir, commit, _repo in args.upstream:
            upstream.update({d: p for d, p in sp.upstream_addresses(Path(git_dir), commit, args.exclude)[0].items()
                             if d not in upstream})
        for directory, _rev, _repo in args.upstream_dir:
            upstream.update({d: p for d, p in sp.dir_addresses(Path(directory), args.exclude)[0].items() if d not in upstream})
    except (sp.UpstreamError, OSError, ValueError) as exc:
        print(f"scan_origins: cannot read an upstream ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 1
    cleared: set[str] = set()
    for path in args.file_names:
        cleared |= pe.parse_persona_file(path.read_bytes()).file_names
    result = analyse(Path(os.path.realpath(args.corpus)), upstream, frozenset(cleared), workers=args.workers)
    classes, evidence = result.pop("_classes"), result.pop("_evidence")
    result["corpus"] = args.corpus.name.removesuffix(".partial")
    print(json.dumps(result, sort_keys=True))
    if args.out and not classes:
        print("scan_origins: no address to list; no file written", file=sys.stderr)
    elif args.out:
        write_observed_file(args.out, args.persona_id, args.source_id, args.corpus_id, tuple(args.pin), classes, evidence)
        print(f"scan_origins: wrote {len(classes)} digest(s) to {args.out.name}", file=sys.stderr)
    return 1 if result["unread"] else 0


if __name__ == "__main__":
    sys.exit(main())
