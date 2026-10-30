"""Examination 2: Markdown tables from the merged per-corpus scan summaries (``scan-<corpus>.json``).

Usage: ``python tools/analysis2/exam2_tables.py DATA_DIR`` -> Markdown on stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ORDER = ["rope-p10", "agentdyn-a-p10", "agentdojo-upstream-head-p10", "mandate-agentdojo-eval-p10", "ast-survey-agentdojo-p10",
         "agentdojo-upstream-2024-06-p10", "adprov-v1-release-p10", "ast-survey-agentharm-p10"]
SHORT = {"rope-p10": "rope", "agentdyn-a-p10": "agentdyn", "agentdojo-upstream-head-p10": "head", "mandate-agentdojo-eval-p10": "mandate",
         "ast-survey-agentdojo-p10": "survey", "agentdojo-upstream-2024-06-p10": "2024-06", "adprov-v1-release-p10": "adprov-v1",
         "ast-survey-agentharm-p10": "agentharm"}


def fmt(n: object) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def main() -> int:
    d = Path(sys.argv[1])
    S = {c: json.loads((d / f"scan-{c}.json").read_text(encoding="utf-8")) for c in ORDER}

    def row(label: str, fn) -> str:
        return "| " + label + " | " + " | ".join(fmt(fn(S[c])) for c in ORDER) + " |"

    def csum(s: dict, prefix: str) -> int:
        return sum(v for k, v in s["counters"].items() if k.startswith(prefix))

    def hsum(s: dict, prefix: str) -> int:
        return sum(v for k, v in s["hits"].items() if k.startswith(prefix))

    print("| Check | " + " | ".join(SHORT[c] for c in ORDER) + " |")
    print("|---|" + "---:|" * len(ORDER))
    rows = [
        ("executions", lambda s: s["executions"]),
        ("analysis errors", lambda s: s["analysis_error_count"]),
        ("AER records / SEM records / PROV docs", lambda s: f"{csum(s, 'records|aer'):,} / {csum(s, 'records|sem'):,} / {csum(s, 'files|prov'):,}"),
        ("bytes AER+SEM+PROV (GB)", lambda s: round(csum(s, 'bytes_total|') / 1e9, 2)),
        ("X01 strict-parse failures (all classes)", lambda s: csum(s, "strict|")),
        ("X01 integers beyond I-JSON / -0 tokens", lambda s: f"{csum(s, 'strictflag|') }"),
        ("X02 second-JCS mismatches / errors", lambda s: f"{csum(s, 'jcs|')}"),
        ("X05 framing (no final LF, CR, blank line)", lambda s: csum(s, "framing|")),
        ("X05 raw U+2028/2029/U+0085 in lines", lambda s: csum(s, "bytes|aer|SPLITLINES") + csum(s, "bytes|sem|SPLITLINES") + csum(s, "bytes|prov|SPLITLINES")),
        ("non-canonical escapes (bytes)", lambda s: csum(s, "bytes|aer|NONCANON") + csum(s, "bytes|sem|NONCANON") + csum(s, "bytes|prov|NONCANON") + csum(s, "bytes|aer|UPPER") + csum(s, "bytes|prov|UPPER")),
        ("X03 floats in trees / integral floats in trees", lambda s: f"{csum(s, 'num|') - csum(s, 'num|aer|float_integral') - csum(s, 'num|prov|float_integral') - csum(s, 'num|sem|float_integral'):,} / {csum(s, 'num|aer|float_integral') + csum(s, 'num|prov|float_integral') + csum(s, 'num|sem|float_integral')}"),
        ("X03 objects whose UTF-16 and code-point key order differ", lambda s: csum(s, "num|aer|objects_utf16") + csum(s, "num|prov|objects_utf16") + csum(s, "num|sem|objects_utf16")),
        ("X03 ext.lex flt pointers / ord objects", lambda s: f"{csum(s, 'x03|lex_flt'):,} / {csum(s, 'x03|lex_ord'):,}"),
        ("U01 $utf16 / $lit / $int / $float wrappers", lambda s: f"{csum(s, 'bytes|aer|UTF16')} / {csum(s, 'bytes|aer|LIT_WRAP')} / {csum(s, 'bytes|aer|INT_WRAP')} / {csum(s, 'bytes|aer|FLOAT_WRAP')}"),
        ("U02 escaped surrogates (bytes) / decoded surrogates", lambda s: f"{csum(s, 'bytes|aer|ESC_SURR') + csum(s, 'bytes|sem|ESC_SURR') + csum(s, 'bytes|prov|ESC_SURR')} / {hsum(s, 'SURROGATE|')}"),
        ("U03 U+2028/2029/0085 strings", lambda s: hsum(s, "SEPARATORS|")),
        ("U04 C0/C1 strings / NUL / CR / ESC sequences", lambda s: f"{hsum(s, 'C0_C1|')} / {hsum(s, 'NUL|')} / {hsum(s, 'CR|')} / {hsum(s, 'ESC_SEQ|')}"),
        ("U05 bidi / zero-width / tags / variation sel. / PUA / U+FFFD / mojibake", lambda s: " / ".join(str(hsum(s, p + "|")) for p in ("BIDI", "ZERO_WIDTH", "TAGS", "VARIATION", "PUA_NONCH", "FFFD", "MOJIBAKE"))),
        ("U06 literal escapes / double / wholly escaped / escaped surrogate text / YAML-only", lambda s: " / ".join(str(hsum(s, p + "|")) for p in ("LIT_ESC", "LIT_ESC_2X", "WHOLLY_ESCAPED", "LIT_U_SURR", "YAML_DQ_ESC"))),
        ("U06 ESC as text", lambda s: hsum(s, "ESC_TEXT|")),
        ("U07 damaged / intact Windows paths", lambda s: f"{hsum(s, 'WINPATH_CTRL|')} / {hsum(s, 'WINPATH_OK|')}"),
        ("U08 JSON-like strings: json / repr / yaml / unparsed", lambda s: " / ".join(str(hsum(s, f"JSONSTR:{p}")) for p in ("json_ok", "python_repr", "yaml_ok", "unparsed"))),
        ("U09 repr heads / object reprs / constructor calls / bytes literals", lambda s: " / ".join(str(hsum(s, p + "|")) for p in ("PY_REPR_HEAD", "PY_OBJ", "PY_CALLS", "PY_BYTES"))),
        ("U10 <U+XXXX> / entities / render markup (all strings)", lambda s: " / ".join(str(hsum(s, p + "|")) for p in ("ANGLE_U", "ENTITY", "RENDER"))),
        ("U10 same, PROV strings only", lambda s: " / ".join(str(hsum(s, p + "|prov")) for p in ("ANGLE_U", "ENTITY", "RENDER"))),
        ("U11 id-like strings ending in LF", lambda s: hsum(s, "ID_TRAIL_NL|")),
        ("U11 PROV keys with unusual chars / DOT keywords", lambda s: f"{csum(s, 'u11|prov_key')} / {csum(s, 'u11|prov_local_dot')}"),
        ("U12 pointer tokens: non-ASCII digit / leading zero / non-ASCII", lambda s: f"{csum(s, 'ptr|') and sum(v for k, v in s['counters'].items() if k.startswith('ptr|') and k.endswith('nonascii_digit'))} / {sum(v for k, v in s['counters'].items() if k.startswith('ptr|') and k.endswith('leading_zero'))} / {sum(v for k, v in s['counters'].items() if k.startswith('ptr|') and k.endswith('nonascii_token'))}"),
        ("U12 pointer strings checked", lambda s: sum(v for k, v in s["counters"].items() if k.startswith("ptr|") and k.endswith("checked"))),
        ("U13 names: non-ASCII / not NFC / mixed script / ws-or-control", lambda s: " / ".join(str(sum(v for k, v in s["counters"].items() if k.startswith("names|") and k.endswith(x))) for x in ("non_ascii", "not_nfc", "mixed_script", "ws_or_control"))),
        ("U14 absolute-path-like strings / secret-shaped strings", lambda s: f"{hsum(s, 'ABS_PATH|')} / {hsum(s, 'SECRET_SHAPE|')}"),
    ]
    for label, fn in rows:
        print(row(label, fn))
    print()
    print("| PROV check | " + " | ".join(SHORT[c] for c in ORDER) + " |")
    print("|---|" + "---:|" * len(ORDER))
    prow = [
        ("P01 views checked", lambda s: csum(s, "p01|views|")),
        ("P01 strict-order cycles (C42)", lambda s: csum(s, "p01|strict")),
        ("P01 non-strict event cycles (simultaneity)", lambda s: csum(s, "p01|nonstrict")),
        ("P02 dependency / informed / derivation / specialization cycles", lambda s: " / ".join(str(csum(s, f"p02|{x}")) for x in ("dependency", "informed", "derivation", "specialization"))),
        ("P03 wasDerivedFrom / C51 violations", lambda s: f"{csum(s, 'p03|wasDerivedFrom'):,} / {csum(s, 'p03|c51')}"),
        ("P04 C26 duplicate starts / C24 duplicate generations", lambda s: f"{csum(s, 'p04|c26')} / {csum(s, 'p04|c24')}"),
        ("P05 multi-generator entities explicit / after Inf. 9-11 expansion", lambda s: f"{csum(s, 'p05|entities_multi_generator_explicit')} / {csum(s, 'p05|entities_multi_generator_expanded')}"),
        ("P05 trigger generator = starter / implied only / differs", lambda s: f"{csum(s, 'p05|trigger_generator_is_starter'):,} / {csum(s, 'p05|trigger_generator_implied_only')} / {csum(s, 'p05|trigger_generator_differs')}"),
        ("P05 attribution supported / generator implied only / generator not associated", lambda s: f"{csum(s, 'p05|attribution_supported'):,} / {csum(s, 'p05|attribution_generator_implied_only'):,} / {csum(s, 'p05|attribution_generator_not_associated')}"),
        ("P05 delegation: delegate explicit & responsible implied / both explicit / no activity", lambda s: f"{csum(s, 'p05|delegation_assoc|delegate=explicit|responsible=implied'):,} / {csum(s, 'p05|delegation_assoc|delegate=explicit|responsible=explicit')} / {csum(s, 'p05|delegation_without_activity'):,}"),
        ("P06 unresolved in container+core+top: resolved elsewhere / nowhere", lambda s: f"{csum(s, 'p06|unresolved_elsewhere'):,} / {csum(s, 'p06|unresolved_nowhere')}"),
        ("P06 generation/usage ids unresolved", lambda s: csum(s, "p06|relid")),
        ("P08 mentionOf (assess / inf)", lambda s: f"{csum(s, 'p08|mentionOf|assess'):,} / {csum(s, 'p08|mentionOf|inf'):,}"),
        ("P08 general not in named bundle / specific undeclared / bundle missing", lambda s: f"{csum(s, 'p08|general')} / {csum(s, 'p08|specific')} / {csum(s, 'p08|mention_bundle')}"),
        ("P10 trailing '.' (keys / QName values) / prefix IRI not '#'|'/'", lambda s: f"{csum(s, 'p10|local_trailing')} / {csum(s, 'p10|qname_value_trailing')} / {csum(s, 'p10|prefix_iri')}"),
        ("P11 multi-valued statement keys", lambda s: csum(s, "p11|")),
        ("P09 components core p50 / max", lambda s: f"{s['components']['core']['p50']} / {s['components']['core']['max']}"),
        ("P09 components core+inf p50 / max", lambda s: f"{s['components']['core+inf']['p50']} / {s['components']['core+inf']['max']}"),
        ("P09 components core+inf+attr p50 / min-max", lambda s: f"{s['components']['core+inf+attr']['p50']} / {s['components']['core+inf+attr']['min']}-{s['components']['core+inf+attr']['max']}"),
        ("P09 apv:Gap share of core+inf entities", lambda s: f"{csum(s, 'p09|gap_entities') / max(1, csum(s, 'p09|entities_core_inf')):.3f}"),
        ("P09 core activities with startTime", lambda s: f"{csum(s, 'p09|activities_with_startTime|core'):,} / {csum(s, 'p09|activities|core'):,}"),
        ("P09 inference activities with startTime", lambda s: f"{csum(s, 'p09|activities_with_startTime|inf'):,} / {csum(s, 'p09|activities|inf'):,}"),
        ("P09 relations with prov:time", lambda s: csum(s, "p09|relations_with_time")),
        ("P09 shared top-level keys / with variants (within corpus)", lambda s: f"{s['shared_statements']['keys']:,} / {s['shared_statements']['keys_with_variants']}"),
    ]
    for label, fn in prow:
        print(row(label, fn))
    print()
    # orphan classes
    orphan: dict[str, dict[str, int]] = {}
    for c in ORDER:
        for k, v in S[c]["counters"].items():
            if k.startswith("p09|orphan|"):
                orphan.setdefault(k.split("|", 2)[2], {})[c] = v
    print("| Orphan class in core ∪ inference (zero relation degree) | " + " | ".join(SHORT[c] for c in ORDER) + " |")
    print("|---|" + "---:|" * len(ORDER))
    for cls in sorted(orphan, key=lambda x: -sum(orphan[x].values())):
        nodes = {c: S[c]["counters"].get(f"p09|nodes|{cls}", 0) for c in ORDER}
        print(f"| {cls} | " + " | ".join(f"{orphan[cls].get(c, 0):,}/{nodes[c]:,}" if nodes[c] else "–" for c in ORDER) + " |")
    print()
    # degree by selected classes
    print("| Degree in core ∪ inference, p50 / p95 / max | " + " | ".join(SHORT[c] for c in ORDER) + " |")
    print("|---|" + "---|" * len(ORDER))
    for cls in ("apv:ModelInvocation", "apv:ToolExecution", "apv:Message", "apv:MessagePart", "apv:AgentSystem", "apv:ToolRuntime", "apv:Fixture", "apv:Outcome"):
        cells = []
        for c in ORDER:
            x = S[c]["degree_by_class"].get(cls)
            cells.append(f"{x['p50']} / {x['p95']} / {x['max']}" if x else "–")
        print(f"| {cls} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
