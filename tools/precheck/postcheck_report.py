"""Render the post-check report (docs/reports/postcheck/): one dossier per checked tree, ``findings.json`` per tree
(format CC-06), and ``summary.md`` / ``summary.json``, from the measured data (``data/<name>/exam.json`` and the files
beside it) and the verdict file ``data/_rows/postcheck.json`` (the examiner's readiness, attributions, pre-check
finding statuses and post-check findings). Every number in a dossier comes from the data files; the verdict file holds
the judgements only.

    uv run python tools/precheck/postcheck_report.py [--check]

``--check`` exits 1 when a committed rendering differs from a fresh one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_postcheck import CORPORA, Corpus  # noqa: E402

REPO: Final = Path(__file__).resolve().parents[2]
POST: Final = REPO / "docs" / "reports" / "postcheck"
DATA: Final = POST / "data"
PRE: Final = REPO / "docs" / "reports" / "precheck" / "data"
SUMMARY_FORMAT: Final = "agentprov-postcheck-summary/0.1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def trees(rows: Mapping[str, Any]) -> list[Corpus]:
    """The checked trees in report order: the base corpora, then each variant named in the verdict file."""
    out = list(CORPORA)
    for name, row in rows.items():
        v = row.get("variant")
        if v:
            cid, new, old = str(v).split(":")
            base = next(c for c in CORPORA if c.id == cid)
            out.append(Corpus(cid, base.parts, new=new, old=old, data=name))
    return out


def _n(x: Any) -> str:
    return f"{x:,}" if isinstance(x, int) else ("—" if x is None else str(x))


def _cli(x: Mapping[str, Any] | None, keys: Sequence[str]) -> str:
    if not x:
        return "not run"
    counters = x.get("counters") or {}
    shown = ", ".join(f"{k} {_n(counters.get(k))}" for k in keys if counters.get(k) is not None)
    issues = ", ".join(f"`{k}` {v}" for k, v in (x.get("issues_by_code") or {}).items()) or "none"
    return f"exit {x.get('exit_code')}, {x.get('outcome')}; {shown}; issues: {issues}"


def checks_table(c: Corpus, e: Mapping[str, Any], d: Path) -> list[str]:
    r, p = e.get("PC1_raw") or {}, e.get("PC2_ids") or {}
    f = e.get("PC6_full") or {}
    o = e.get("PC8_outcomes") or {}
    s = e.get("PC11_seal") or {}
    sc = e.get("PC10_scan") or {}
    rows = [
        "| Check | Result |", "|---|---|",
        f"| PC1 raw (8.3.1) | objects {_n(r.get('objects'))}, equal {r.get('objects_equal')}; origins rows equal "
        f"{r.get('origins_rows_equal')} (object-origin pairs {r.get('origin_pairs_equal')}); member rows equal "
        f"{r.get('members_rows_equal')} |",
        f"| PC2 population | ids {_n((p.get('executions') or {}).get('common'))} common, only old "
        f"{(p.get('executions') or {}).get('only_old')}, only new {(p.get('executions') or {}).get('only_new')}; completeness "
        f"= round {p.get('completeness_equals_round')}; issue codes net {p.get('issues_net') or '{}'} (= round "
        f"{p.get('issues_net_equals_round')}); stage digests changed {p.get('stage_digests_changed')} |",
        f"| PC3 verify chain | {_cli(e.get('PC3_verify'), ('executions_checked', 'raw_rehashed', 'failed'))} |",
        f"| PC4 recompute --dry-run --jobs 4 | {_cli(e.get('PC4_dryrun'), ('identical', 'changed_explained', 'unexplained_change', 'failed', 'unverified'))} |",
        f"| PC5 validate --strict (aer,sem,prov,linkage) | {_cli(e.get('PC5_validate'), ('passed', 'failed', 'checks_skipped', 'results_differ', 'linkage_resolved'))} |",
        f"| PC6 full population | executions {_n((f.get('executions') or {}).get('old'))} → {_n((f.get('executions') or {}).get('new'))}; "
        f"degenerate {f.get('degenerate')}, adapter_defect {f.get('adapter_defect')}; SEM net = round "
        f"{f.get('sem_net_equals_round')}; {((f.get('diff') or {}).get('n_changed'))} changed census leaves |",
        f"| PC8 outcomes | {o.get('arm_measures')} arm × measure judgement counts, {o.get('moved')} moved |",
        f"| PC10 release-scan forecast | native {_n((sc.get('native') or {}).get('findings'))}, gitleaks "
        f"{_n((sc.get('gitleaks') or {}).get('findings'))} (section 4) |",
        f"| PC11 seal forecast | {s.get('refused')} refusal(s); {len(s.get('steps') or [])} checks; "
        f"{len(s.get('statements') or [])} datasheet statements apply; withholding policy {s.get('withholding_policy')} |",
    ]  # fmt: skip
    for part, x in (e.get("PC7_sample") or {}).items():
        tie = x.get("tie") or {}
        ex = tie.get("executions") or {}
        j = x.get("sample_join_rg1") or {}
        rows.append(f"| PC7 sample `{part}` | {j.get('labels_with_executions')}/{j.get('labels_sampled')} sampled labels "
                    f"found; pre-check scratch → {c.new_tag}: {(x.get('precheck_vs_rg1') or {}).get('n_changed')} leaves |")
        rows.append(f"| PC7b tie `{part}` | {_n(ex.get('all_digests_equal'))}/{_n(ex.get('scratch'))} executions with every "
                    f"digest equal; differ by stage {ex.get('differ_by_stage') or '{}'}; stage code equal "
                    f"{tie.get('stage_code_equal')} |")
    disp = _load(d / f"dispatch-{c.new_tag}.json")
    if disp:
        rows.append(f"| Dispatch census | {disp['executions_with_unexecuted_issue']} executions, {disp['unexecuted_parts']} "
                    f"unexecuted parts; {disp['dispatch_status_by_bundle_kind_value'] or '{}'} |")
    ora = _load(d / "oracle.json")
    if ora:
        rows.append(f"| Oracle vs release graphs | {ora['result']} (release pairs {ora['release_tree']['pairs']}) |")
    return rows


def movement(c: Corpus, e: Mapping[str, Any]) -> list[str]:
    f = e.get("PC6_full") or {}
    out = [f"SEM annotations, {c.old_tag} → {c.new_tag} (net, by type and evidence class; the round's `compare.json` for the "
           "base corpus beside it):", "", "| Type, class | Post-check | Round |", "|---|---|---|"]
    mine, rnd = (f.get("sem_net") or {}).get("by_type_class") or {}, f.get("round_sem_net") or {}
    for k in sorted(set(mine) | set(rnd)):
        out.append(f"| {k} | {_n(mine.get(k))} | {_n(rnd.get(k))} |")
    if not mine and not rnd:
        out.append("| (none) | 0 | 0 |")
    var = {k: v for k, v in ((f.get("sem_net") or {}).get("by_type_class_variant") or {}).items() if k.startswith("outcome")}
    if var:
        out += ["", "Outcome annotations by log variant: " + ", ".join(f"{k} {_n(v)}" for k, v in sorted(var.items())) + "."]
    diff = f.get("diff") or {}
    out += ["", f"Level-2 census leaves that changed, {c.old_tag} → {c.new_tag} ({diff.get('n_changed')}; by section "
                f"{diff.get('by_section')}):", "", "| Leaf | Old | New |", "|---|---|---|"]
    for x in (diff.get("changed") or [])[:40]:
        out.append(f"| `{x['leaf']}` | {_n(x['old'])} | {_n(x['new'])} |")
    for part, x in (e.get("PC7_sample") or {}).items():
        ch = [y for y in ((x.get("precheck_vs_rg1") or {}).get("changed") or [])
              if not y["leaf"].startswith(("executions.register_codes", "redaction.files_scanned"))]
        out += ["", f"Sample `{part}`: pre-check scratch (code `{str(x.get('precheck_code'))[:8]}`) → {c.new_tag}, per-execution "
                    f"leaves ({len(ch)}; the corpus-wide register codes and the file count differ by scope, R5):"]
        out += [f"- `{y['leaf']}` {_n(y['old'])} → {_n(y['new'])}" for y in ch] or ["- none"]
    return out


def release(d: Path, e: Mapping[str, Any]) -> list[str]:
    sc = e.get("PC10_scan") or {}
    nat, gl = sc.get("native") or {}, sc.get("gitleaks") or {}
    out = ["| Scanner | Area : rule | Findings | Files |", "|---|---|---|---|"]
    for k, v in sorted((nat.get("by_area_rule") or {}).items()):
        out.append(f"| native path scan | {k} | {_n(v)} | {_n((nat.get('files_by_area_rule') or {}).get(k))} |")
    for k, v in sorted((gl.get("by_area_rule") or {}).items()):
        out.append(f"| gitleaks {gl.get('version')} | {k} | {_n(v)} | |")
    if len(out) == 2:
        out.append("| both | — | 0 | 0 |")
    tri = _load(d / "triage.json") or _load(d / "triage-context.json")
    accts = (tri or {}).get("accounts") or nat.get("accounts") or {}
    out += ["", f"Distinct account names (ordinals, never names): {accts.get('distinct', 0)}."]
    ctx = {o["ordinal"]: o for o in ((_load(d / "triage-context.json") or {}).get("accounts") or {}).get("ordinals", ())}
    if tri or ctx:
        rows = (tri or {}).get("accounts", {}).get("ordinals") or list(ctx.values())
        out += ["", "Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON "
                    "member a match sits under and what follows the account segment (toolchain directory, user folder or "
                    "other) are counts, never values:", "",
                "| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |",
                "|---|---|---|---|---|---|---|"]
        for o in rows:
            c = ctx.get(o["ordinal"], {})
            out.append(f"| {o['ordinal']} | {o['length']} | {o['areas']} | {o['path_in_suite_data']} | "
                       f"{o['name_in_suite_data']} | {c.get('json_keys', '—')} | {c.get('path_tail', '—')} |")
        if (tri or {}).get("other_rules"):
            out += ["", "Other rules, by whether the finding's line shares a 16+ character token (or a private-key header) "
                        "with the suite data: " + ", ".join(f"{k} {_n(v)}" for k, v in tri["other_rules"].items()) + "."]
    return out


def dossier(c: Corpus, row: Mapping[str, Any]) -> str:
    d = DATA / c.name
    e = _load(d / "exam.json") or {}
    seal = _load(d / "seal-forecast.json") or {}
    commits = sorted({str((_load(p) or {}).get("code", {}).get("commit", ""))[:8] for p in d.glob("*.json")
                      if isinstance((_load(p) or {}).get("code"), Mapping)} - {""})
    lines = [f"# Post-check dossier: `{c.name}`", "", "## 1. Header", "", "| | |", "|---|---|",
             f"| Tree | `~/.agentprov/corpora/{c.id}-{c.new}.partial` (working tree, read only) |",
             f"| Predecessor | `{c.id}-{c.old}.partial` |",
             f"| Built at | {row.get('built_at', '—')} |",
             "| Pre-check corpus · parts | " + "; ".join(f"`{p.pre}` · `{p.part}`" for p in c.parts) + " |",
             f"| Post-check code | {', '.join(f'`{x}`' for x in commits)} (stage code: PC0) |",
             f"| Data | [`data/{c.name}/`](data/{c.name}/) |", "",
             "## 2. Checks", "", *checks_table(c, e, d), "",
             "## 3. Movement and attribution", "", *movement(c, e), "",
             "Attribution:", "", *([f"- {x}" for x in row.get("attribution", [])] or ["- (none recorded)"]), "",
             "## 4. Release-scan forecast", "", *release(d, e), "",
             *([f"- {x}" for x in row.get("release_notes", [])]), "",
             "## 5. Seal forecast", "",
             "| Check | Result |", "|---|---|",
             *[f"| {s['check']} | {s['result']}{(' — `' + s['code'] + '`: ' + s['message']) if s.get('code') else ''} |"
               for s in seal.get("steps", ())], "",
             "Datasheet statements that apply: " + (", ".join(f"`{x}`" for x in seal.get("statements", ())) or "none") + ".", "",
             "## 6. Pre-check findings", "", "| Finding | Status after the round |", "|---|---|",
             *[f"| {k} | {v} |" for k, v in row.get("precheck_status", {}).items()], "",
             "## 7. Post-check findings", "",
             "| Id | Class | Severity | Security | Title | Verdict |", "|---|---|---|---|---|---|",
             *[f"| {f['id']} | {f['cls']} | {f['severity']} | {f['security']} | {f['title']} | {f.get('verdict', '')} |"
               for f in row.get("findings", [])], "",
             *[f"- **{f['id']}**: {f.get('evidence', '')} Recommendation: {f.get('recommendation', '')}" for f in row.get("findings", [])],
             "", "## 8. Readiness for sealing", "", f"**{row.get('readiness', 'pending')}**: {row.get('why', '')}", "",
             "## 9. Reproduction", "", "```bash",
             "uv run python tools/precheck/run_postcheck.py --list" + (f" --variant {row['variant']}" if row.get("variant") else f" --only {c.id}"),
             "uv run python tools/precheck/postcheck_compare.py --corpus " + c.name + (f" --variant {row['variant']}" if row.get("variant") else ""),
             "```", ""]  # fmt: skip
    return "\n".join(lines)


def findings_doc(c: Corpus, row: Mapping[str, Any]) -> dict[str, Any]:
    return {"format": "agentprov-precheck-findings/0.1", "corpus_id": c.name, "check": "post-check",
            "findings": list(row.get("findings", [])), "refuted": list(row.get("refuted", []))}


def summary(rows: Mapping[str, Any], meta: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    entries = []
    for c in trees(rows):
        row = rows.get(c.name)
        if row is None:
            continue
        e = _load(DATA / c.name / "exam.json") or {}
        entries.append({"tree": c.name, "corpus_id": c.id, "new": c.new, "old": c.old, "readiness": row.get("readiness"),
                        "why": row.get("why"), "findings": [{k: f.get(k) for k in ("id", "cls", "severity", "security", "title")}
                                                            for f in row.get("findings", [])],
                        "executions": ((e.get("PC6_full") or {}).get("executions") or {}).get("new"),
                        "seal_refusals": (e.get("PC11_seal") or {}).get("refused"),
                        "outcomes_moved": (e.get("PC8_outcomes") or {}).get("moved"),
                        "superseded_by": row.get("superseded_by")})  # fmt: skip
    doc = {"format": SUMMARY_FORMAT, **{k: v for k, v in meta.items()}, "trees": entries}
    md = ["# Corpus post-check after the regeneration round: summary", "",
          "Generated by `tools/precheck/postcheck_report.py` from the data files and `data/_rows/postcheck.json`; do not",
          "edit by hand. Method and pre-registration: [`README.md`](README.md).", "",
          *[str(x) for x in meta.get("preamble", [])], "",
          "| Tree | Executions | Seal refusals | Outcome values moved | Findings | Readiness |", "|---|---|---|---|---|---|"]
    for t in entries:
        fs = ", ".join(f"{f['id']} ({f['cls']}, {f['severity']}{', security' if f['security'] else ''})" for f in t["findings"]) or "—"
        md.append(f"| [`{t['tree']}`]({t['tree']}.md) | {_n(t['executions'])} | {t['seal_refusals']} | {t['outcomes_moved']} | "
                  f"{fs} | **{t['readiness']}**{' (superseded by `' + t['superseded_by'] + '`)' if t['superseded_by'] else ''} |")
    md += ["", "## Readiness notes", ""] + [f"- **{t['tree']}** ({t['readiness']}): {t['why']}" for t in entries]
    md += ["", "## Decided items, numbers confirmed", ""] + [f"- {x}" for x in meta.get("decided", [])]
    md += ["", "## Notes for future checks", ""] + [f"- {x}" for x in meta.get("notes", [])]
    return doc, "\n".join(md) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    verdicts = _load(DATA / "_rows" / "postcheck.json") or {}
    rows, meta = verdicts.get("trees", {}), verdicts.get("meta", {})
    targets: dict[Path, str] = {}
    for c in trees(rows):
        row = rows.get(c.name)
        if row is None:
            continue
        targets[POST / f"{c.name}.md"] = dossier(c, row)
        targets[DATA / c.name / "findings.json"] = json.dumps(findings_doc(c, row), indent=1, sort_keys=True) + "\n"
    doc, md = summary(rows, meta)
    targets[POST / "summary.json"] = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    targets[POST / "summary.md"] = md
    if a.check:
        stale = [str(p.relative_to(REPO)) for p, t in targets.items() if not p.is_file() or p.read_text(encoding="utf-8") != t]
        for s in stale:
            print(f"stale: {s}", file=sys.stderr)
        return 1 if stale else 0
    from l2_common import guard_output

    for path, text in targets.items():
        guard_output(path).write_text(text, encoding="utf-8")
    print(json.dumps({"written": len(targets)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
