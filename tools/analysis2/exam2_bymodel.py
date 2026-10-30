"""Examination 2: selected string-content hits per model (from ``exam2_scan.py`` rows; counts of executions).

Usage: ``python tools/analysis2/exam2_bymodel.py SCAN.jsonl [...]`` -> JSON on stdout.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

KEYS = {
    "args_wholly_escaped": ("WHOLLY_ESCAPED|aer|/message:assistant/parts/*/args/~",),
    "args_literal_escape": ("LIT_ESC|aer|/message:assistant/parts/*/args/~",),
    "args_repr_list_string": ("JSONSTR:yaml_ok:list|aer|/message:assistant/parts/*/args/~", "JSONSTR:python_repr:list|aer|/message:assistant/parts/*/args/~"),
    "assistant_text_variation_selector": ("VARIATION|aer|/message:assistant/parts/*/text",),
    "assistant_text_wholly_escaped": ("WHOLLY_ESCAPED|aer|/message:assistant/parts/*/text",),
    "tool_text_python_repr": ("JSONSTR:python_repr:dict|aer|/message:tool/parts/*/text", "JSONSTR:python_repr:list|aer|/message:tool/parts/*/text"),
}


def main() -> int:
    out = {}
    for path in sys.argv[1:]:
        per: dict[str, Counter] = defaultdict(Counter)
        for line in open(path, encoding="utf-8"):
            d = json.loads(line)
            m = d.get("model") or "<none>"
            per[m]["executions"] += 1
            h = d.get("hits", {})
            for name, keys in KEYS.items():
                if any(h.get(k) for k in keys):
                    per[m][name] += 1
        out[path.rsplit("/", 1)[-1]] = {m: dict(c) for m, c in sorted(per.items())}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
