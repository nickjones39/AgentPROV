"""Build the pre-check summary (docs/reports/precheck/summary.json and summary.md) from committed per-corpus files.

    uv run python tools/precheck/summary.py [--check]

Inputs, all committed: ``data/_rows/wave<n>.json`` (the dossier writers' rows), ``data/<corpus>/findings.json``
(format ``agentprov-precheck-findings/0.1``, cross-cutting.md CC-06: class and severity counts are recomputed from it,
so a harmonised class wins over the row's), ``data/<corpus>/l1-09-<part>.json`` (L1-09), ``manifest.json`` (the 50
listed parts, so a part not yet examined shows as ``pending``) and ``stats-notes.json`` (statistics and manuscript notes).
``--check`` exits 1 when the committed summary files differ from a fresh build. The post-check compares its own summary
with this one row by row.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO: Final = Path(__file__).resolve().parents[2]
PRE: Final = REPO / "docs" / "reports" / "precheck"
FORMAT: Final = "agentprov-precheck-summary/0.1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def findings_counts(corpus: str) -> dict[str, Any] | None:
    path = PRE / "data" / corpus / "findings.json"
    if not path.is_file():
        return None
    doc = _load(path)
    found = [f for f in doc.get("findings", []) if f.get("verdict", "confirmed") not in ("refuted",)]
    corpus_findings = [f for f in found if f.get("cls") != "analysis-artefact"]
    return {
        "by_class": dict(sorted(Counter(str(f.get("cls")) for f in found).items())),
        "by_severity": dict(sorted(Counter(str(f.get("severity")) for f in corpus_findings).items())),
        "refuted": len(doc.get("refuted", [])),
        "security": sorted(str(f.get("id")) for f in found if f.get("security")),
        "format": doc.get("format"),
    }


def l1_09(corpus: str) -> dict[str, Any]:
    out = {}
    for path in sorted((PRE / "data" / corpus).glob("l1-09-*.json")):
        d = _load(path)
        out[str(d["part"])] = {k: d[k] for k in ("members_walked", "metadata_members", "metadata_include_match")}
    return out


def code_idents(corpus: str) -> dict[str, Any]:
    """Per part: the commit and the stage code digests of the Level-2 import (``code-<part>.json``, code_ident.py)."""
    out = {}
    for path in sorted((PRE / "data" / corpus).glob("code-*.json")):
        d = _load(path)
        out[str(d["part"])] = {"commit": d.get("commit"), "tracked_changes": d.get("tracked_changes"),
                               "stages": {str(st.get("stage")): st.get("engine_code_sha256") for st in d.get("stages", [])},
                               "adapters": {str(a.get("id")): a.get("code_sha256") for a in d.get("adapters", [])}}  # fmt: skip
    return out


def build() -> dict[str, Any]:
    manifest = _load(PRE / "manifest.json")
    listed = [p for p in manifest["parts"] if p.get("in_listing")]
    rows: dict[str, Mapping[str, Any]] = {}
    for path in sorted((PRE / "data" / "_rows").glob("wave*.json")):
        for row in _load(path).get("rows", []):
            rows[str(row["corpus_id"])] = row
    corpora: dict[str, list[Mapping[str, Any]]] = {}
    for p in listed:
        corpora.setdefault(str(p["corpus_id"]), []).append(p)
    out_rows = []
    for corpus in sorted(corpora):
        row = rows.get(corpus)
        counts = findings_counts(corpus)
        entry: dict[str, Any] = {
            "corpus_id": corpus,
            "listed_parts": sorted(f"{p['source']}:{p['part']}" for p in corpora[corpus]),
            "status": row.get("status") if row else "pending",
            "wave": row.get("wave") if row else None,
            "parts": row.get("parts", []) if row else [],
            "readiness": row.get("readiness") if row else None,
            "readiness_why": row.get("readiness_why") if row else None,
            "outcome_gap_flags": row.get("outcome_gap_flags", []) if row else [],
            "security_flags": row.get("security_flags", []) if row else [],
            "artefact_proposals": row.get("artefact_proposals") if row else None,
            "agents_md_12": row.get("agents_md_12", []) if row else [],
            "dossier": f"docs/reports/precheck/{corpus}.md" if (PRE / f"{corpus}.md").is_file() else None,
            "findings": counts,
            "l1_09": l1_09(corpus),
            "code": code_idents(corpus),
        }
        out_rows.append(entry)
    readiness = Counter(str(r["readiness"]) for r in out_rows if r["readiness"])
    notes_path = PRE / "stats-notes.json"
    notes = _load(notes_path).get("notes", []) if notes_path.is_file() else []
    return {
        "format": FORMAT,
        "population": {"corpora": len(corpora), "listed_parts": len(listed)},
        "examined": sum(1 for r in out_rows if r["status"] != "pending"),
        "readiness": dict(sorted(readiness.items())),
        "rows": out_rows,
        "stats_notes": notes,
    }


def render(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Corpus pre-check: summary",
        "",
        "Generated by `tools/precheck/summary.py` from the committed per-corpus files; do not edit by hand. Method:",
        "[`README.md`](README.md); canonical classes: [`cross-cutting.md`](cross-cutting.md). The post-check compares its",
        "own `summary.json` with [`summary.json`](summary.json) row by row.",
        "",
        f"Population: {summary['population']['corpora']} corpora, {summary['population']['listed_parts']} listed parts. "
        f"Examined: {summary['examined']}. Readiness: "
        + (", ".join(f"{k} {v}" for k, v in summary["readiness"].items()) or "none yet") + ".",
        "",
        "| Corpus | Wave | Status | Parts (L1 units / sample) | Findings by class (excl. refuted) | Corpus findings by severity | Refuted | Outcome-gap flags | L1-09 metadata in include | Readiness |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for r in summary["rows"]:
        parts = "; ".join(f"{p.get('source')}:{p.get('part')} {str(p.get('l1_units', '')).split(' ')[0]} / "
                          f"{str(p.get('sample_n', '')).split(' ')[0]}" for p in r["parts"]) or ", ".join(r["listed_parts"])  # fmt: skip
        f = r["findings"] or {}
        cls = ", ".join(f"{k} {v}" for k, v in (f.get("by_class") or {}).items()) or "—"
        sev = ", ".join(f"{k} {v}" for k, v in (f.get("by_severity") or {}).items()) or "—"
        meta = ", ".join(f"{k} {v['metadata_include_match']}" for k, v in r["l1_09"].items()) or "—"
        dossier = f"[`{r['corpus_id']}`]({r['corpus_id']}.md)" if r["dossier"] else f"`{r['corpus_id']}`"
        lines.append(f"| {dossier} | {r['wave'] or '—'} | {r['status']} | {parts} | {cls} | {sev} | {f.get('refuted', '—')} | "
                     f"{len(r['outcome_gap_flags'])} | {meta} | {r['readiness'] or 'pending'} |")  # fmt: skip
    lines += ["", "## Code identity per part (Level 2)", "",
              "The commit each part's scratch import ran at, and the stage code digests (``code-<part>.json``). Parts with",
              "equal stage digests ran the same mapping, SEM, PROV and validation code even where the commit differs (docs",
              "or tool commits only).", "", "| Corpus | Part | Commit | aer | sem | prov | validation |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in summary["rows"]:
        for part, c in r["code"].items():
            st = c["stages"]
            lines.append(f"| {r['corpus_id']} | {part} | `{str(c['commit'])[:8]}` | " + " | ".join(
                f"`{str(st.get(k) or '-').removeprefix('sha256:')[:12]}`" for k in ("aer", "sem", "prov", "validation")) + " |")
    lines += ["", "## Readiness notes", ""]
    for r in summary["rows"]:
        if r["readiness_why"]:
            lines.append(f"- **{r['corpus_id']}** ({r['readiness']}): {r['readiness_why']}")
    lines += ["", "## Statistics and manuscript notes", "",
              "Conventions the statistics owner must state wherever the numbers are used (routed via the orchestrator).", ""]  # fmt: skip
    for n in summary["stats_notes"]:
        lines.append(f"- **{n['id']}** ({n['corpora']}): {n['text']} Source: {n['source']}.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed files differ from a fresh build")
    a = ap.parse_args(argv)
    summary = build()
    text_json = json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    text_md = render(summary)
    targets = {PRE / "summary.json": text_json, PRE / "summary.md": text_md}
    if a.check:
        stale = [str(p) for p, t in targets.items() if not p.is_file() or p.read_text(encoding="utf-8") != t]
        for s in stale:
            print(f"stale: {s}", file=sys.stderr)
        return 1 if stale else 0
    for path, text in targets.items():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from l2_common import guard_output

        guard_output(path).write_text(text, encoding="utf-8")
    print(json.dumps({"examined": summary["examined"], "readiness": summary["readiness"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
