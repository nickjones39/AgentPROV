"""L1-10 (pre-check, wave-2 critic 2026-10-15): secret shapes and account paths in the raw files an import copies into the
raw store but L1-06 does not scan (context artefacts, blob artefacts, non-JSON auxiliaries: READMEs, scripts, configs,
manifests).

    uv run python tools/precheck/l1_context.py --source S --part P [--corpus-id C] <the l1_scan.py input args>
        [--out docs/reports/precheck/data/C/l1-10-<part>.json]

Enumeration and dispositions are ``l1_scan.py``'s (``build_source``, ``entries``, ``classify``). Every entry whose
disposition is ``context``, ``blob`` or ``auxiliary`` and whose name is not ``.json``/``.jsonl`` (those are L1-06's) is
read (git: by blob id with lazy fetch off; local: through ``agentprov.ingest.paths``; archive: streamed members), decoded
as UTF-8 with replacement, and screened with ``l1_scan.ACCOUNT_PATTERNS`` (named vs generic account, as L1-06 counts
them), ``l1_scan.SECRET_PATTERNS`` and the operator's own home path. Output: counts per pattern, files with a hit, distinct
accounts as truncated SHA-256 digests (never the name), operator-home hits. No value and no member name is written.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_scan  # noqa: E402

SCANNED_BY_L106: Final = (".json", ".jsonl")
DISPOSITIONS: Final = ("context", "blob", "auxiliary")


def screen(text: str, operator: str | None) -> dict[str, Any]:
    """Counts of one decoded file: account matches by pattern and kind, account digests, secret shapes, operator hits."""
    hits: Counter[str] = Counter()
    digests: dict[str, set[str]] = defaultdict(set)
    operator_hits = 0
    for name, rx in l1_scan.ACCOUNT_PATTERNS.items():
        for m in rx.finditer(text):
            account = m.group(1) if m.groups() else m.group(0)
            kind = "generic" if account.lower() in l1_scan.GENERIC_ACCOUNTS else "named"
            hits[f"account:{name}:{kind}"] += 1
            if kind == "named":
                digests[name].add(hashlib.sha256(account.encode("utf-8")).hexdigest()[:12])
            if operator and account == operator:
                operator_hits += 1
    for name, rx in l1_scan.SECRET_PATTERNS.items():
        n = len(rx.findall(text))
        if n:
            hits[f"secret:{name}"] += n
    return {"hits": hits, "digests": digests, "operator": operator_hits}


def candidates(entries: Iterable[Any], disposition: Mapping[str, str]) -> list[Any]:
    out = []
    for e in entries:
        d = disposition.get(e.label, e.disposition).split(":", 1)[0]
        if d in DISPOSITIONS and not e.own.lower().endswith(SCANNED_BY_L106):
            out.append(e)
    return out


def read_all(source: Any, wanted: Sequence[Any]) -> Iterable[tuple[Any, bytes | None]]:
    """(entry, bytes or None when absent/unreadable) for every wanted entry, through the source's own reader."""
    from agentprov.ingest.limits import IngestLimits

    by_label = {e.label: e for e in wanted}
    if isinstance(source, l1_scan.ArchiveSource):
        seen = set()
        for label, _size, data in source.stream(set(by_label)):
            seen.add(label)
            yield by_label[label], (data if isinstance(data, bytes) else None)
        for label in set(by_label) - seen:
            yield by_label[label], None
        return
    spec = source.spec()
    reader = l1_scan.GitBlobReader(spec["bare"]) if spec["kind"] == "git" else None
    limits = IngestLimits()
    for e in wanted:
        try:
            if reader is not None:
                yield e, (reader.read(e.sha1) if e.sha1 and e.disposition != "absent_blob" else None)
            else:
                from agentprov.ingest.paths import open_evidence

                with open_evidence(spec["root"], e.label, limits) as handle:
                    yield e, handle.read()
        except Exception:  # noqa: BLE001 - an unreadable file is counted, never fatal
            yield e, None


def scan(source: Any, entries: Sequence[Any], disposition: Mapping[str, str], operator: str | None) -> dict[str, Any]:
    wanted = candidates(entries, disposition)
    hits: Counter[str] = Counter()
    files_with: Counter[str] = Counter()
    digests: dict[str, set[str]] = defaultdict(set)
    by_disp: Counter[str] = Counter()
    unreadable = operator_hits = files_hit = 0
    for e, data in read_all(source, wanted):
        by_disp[disposition.get(e.label, e.disposition).split(":", 1)[0]] += 1
        if data is None:
            unreadable += 1
            continue
        res = screen(data.decode("utf-8", "replace"), operator)
        hits.update(res["hits"])
        for k in res["hits"]:
            files_with[k] += 1
        for k, v in res["digests"].items():
            digests[k] |= v
        operator_hits += res["operator"]
        files_hit += bool(res["hits"])
    return {"files_screened": len(wanted), "by_disposition": dict(sorted(by_disp.items())), "unreadable": unreadable,
            "files_with_a_hit": files_hit, "matches": dict(sorted(hits.items())),
            "files_with": dict(sorted(files_with.items())),
            "distinct_named_accounts": {k: len(v) for k, v in sorted(digests.items())},
            "account_digests": {k: sorted(v) for k, v in sorted(digests.items())},
            "operator_home_hits": operator_hits}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    p = l1_scan.parser()
    p.description = __doc__.split("\n", 1)[0]
    p.add_argument("--out", help="output JSON (default docs/reports/precheck/data/<corpus_id>/l1-10-<part>.json)")
    args = p.parse_args(argv)
    profile, cap = l1_scan.resolve(args.source, args.part, args.profile)
    corpus_id = args.corpus_id or (cap.corpus_id if cap is not None and cap.corpus_id else args.source)
    source, info = l1_scan.build_source(args, profile, args.part, l1_scan.IngestLimits())
    entries = source.entries()
    disposition = l1_scan.classify(entries, profile)
    result = {"check": "L1-10", "source": args.source, "part": args.part, "corpus_id": corpus_id, "profile": profile.id,
              "input_mode": info.get("input", {}).get("mode"), **scan(source, entries, disposition, Path.home().name)}  # fmt: skip
    out = Path(args.out) if args.out else l1_scan.REPO / "docs" / "reports" / "precheck" / "data" / corpus_id / f"l1-10-{args.part}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    l1_scan.guard_output(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("source", "part", "files_screened", "files_with_a_hit", "operator_home_hits")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
