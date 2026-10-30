"""L1-09 (pre-check, orchestrator request 2026-10-15): macOS AppleDouble and OS-metadata members of a part's raw input.

    uv run python tools/precheck/l1_appledouble.py --source S --part P [--corpus-id C] <the l1_scan.py input args>
        [--out docs/reports/precheck/data/C/l1-09-P.json]

Counts, per class, the walked members (archive members, nested members, files of a local or git tree) whose path is OS
metadata: ``appledouble`` (a ``._*`` basename), ``macosx_dir`` (any segment ``__MACOSX``), ``ds_store`` (``.DS_Store``),
``other_os`` (``Thumbs.db``, ``desktop.ini``, ``.Spotlight-V100``, ``.Trashes``, ``.fseventsd``). A member counts in every
class it belongs to. For each class: ``walked`` (seen), ``include_match`` (matched the profile's expand/include selection,
so an import decompresses and stores it although no reader maps it: the exposure the orchestrator asked for),
``not_selected`` (skipped by the selection, never read), ``rejected`` (by an ingest limit or link check), and the final
importer disposition (``stray``, ``selected``, ``auxiliary``, ...) from ``l1_scan.classify``. Counts and dispositions
only: no member name or content is written. The enumeration is ``l1_scan.py``'s own (``build_source`` and
``entries``), so labels and selection equal the importer's; nothing is decompressed beyond what the walk does to list a
nested archive.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_scan  # noqa: E402

OTHER_OS: Final = frozenset({"thumbs.db", "desktop.ini", ".spotlight-v100", ".trashes", ".fseventsd"})


def classes_of(label: str) -> list[str]:
    """The metadata classes of a member label (``!/`` separates nested archive levels)."""
    segments = [s for s in label.replace("!/", "/").split("/") if s]
    if not segments:
        return []
    base = segments[-1]
    out: list[str] = []
    if base.startswith("._"):
        out.append("appledouble")
    if "__MACOSX" in segments:
        out.append("macosx_dir")
    if base == ".DS_Store":
        out.append("ds_store")
    if any(s.lower() in OTHER_OS for s in segments):
        out.append("other_os")
    return out


def count(entries: Sequence[Any], disposition: dict[str, str]) -> dict[str, Any]:
    by: dict[str, Counter[str]] = defaultdict(Counter)
    final: dict[str, Counter[str]] = defaultdict(Counter)
    total = 0
    for e in entries:
        total += 1
        for cls in classes_of(e.label):
            c = by[cls]
            c["walked"] += 1
            if e.disposition in ("listed", "nested"):
                c["include_match"] += 1
                c["include_match_bytes"] += int(e.size or 0)
            elif e.disposition == "not_selected":
                c["not_selected"] += 1
            elif e.disposition.startswith("rejected:"):
                c["rejected"] += 1
            final[cls][disposition.get(e.label, e.disposition).split(":", 1)[0]] += 1
    any_cls = sum(1 for e in entries if classes_of(e.label))
    any_inc = sum(1 for e in entries if classes_of(e.label) and e.disposition in ("listed", "nested"))
    return {"members_walked": total, "metadata_members": any_cls, "metadata_include_match": any_inc,
            "by_class": {k: dict(sorted(v.items())) for k, v in sorted(by.items())},
            "final_disposition": {k: dict(sorted(v.items())) for k, v in sorted(final.items())}}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    p = l1_scan.parser()
    p.description = __doc__.split("\n", 1)[0]
    p.add_argument("--out", help="output JSON (default docs/reports/precheck/data/<corpus_id>/l1-09-<part>.json)")
    args = p.parse_args(argv)
    profile, cap = l1_scan.resolve(args.source, args.part, args.profile)
    corpus_id = args.corpus_id or (cap.corpus_id if cap is not None and cap.corpus_id else args.source)
    source, info = l1_scan.build_source(args, profile, args.part, l1_scan.IngestLimits())
    entries = source.entries()
    disposition = l1_scan.classify(entries, profile)
    imp = profile.data.get("import", {})
    result = {"check": "L1-09", "source": args.source, "part": args.part, "corpus_id": corpus_id,
              "profile": profile.id, "input_mode": info.get("input", {}).get("mode"),
              "include_globs": [str(g) for g in imp.get("include", ())], **count(entries, disposition)}  # fmt: skip
    out = Path(args.out) if args.out else l1_scan.REPO / "docs" / "reports" / "precheck" / "data" / corpus_id / f"l1-09-{args.part}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    l1_scan.guard_output(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("source", "part", "members_walked", "metadata_members", "metadata_include_match")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
