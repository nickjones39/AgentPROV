"""Spec item labels: every "D.x.y item N" citation must name an item that exists (D-422, design §2.4).

Usage::

    uv run python tools/spec_labels.py --check          # exit 1 on an unresolved or ambiguous citation
    uv run python tools/spec_labels.py --check --json
    uv run python tools/spec_labels.py --write          # docs/architecture/item-labels.json (the label mapping)

The numbered items of ``docs/architecture/D_adapters.md`` are cited from docs, code and tests as "D.6.10 item 3",
"§D.2.9 items 8–12" or "D.12.3(2)". Their numbers are now **frozen labels**: an item is never renumbered, a withdrawn
item keeps its number, and a new item takes the next number from ``tools/reserve_id.py``. This tool reads the lists
(the parser of ``reserve_id.py``: column-0 items under each ``D.x.y`` heading; a list restarting at 1 under the same
heading is that section's next list, ``D.9.5b``) and resolves every citation in the tracked text files.

* ``unresolved``: the section has no such list, or the list has no such item;
* ``ambiguous``: the cited section has a second list (``D.9.5`` and ``D.9.5b``), so "D.9.5 item 2" could mean either;
  cite ``D.9.5b item 2`` for the second;
* ``duplicate``: one list holds the number twice; such a label cannot resolve until one item is renumbered.

``item-labels.json`` maps each label to its list, section, line and title. It is generated and committed (once the
spec migration lands; ``--check`` compares it then). Third-party fixture trees are not scanned.

Standard library only; no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import git_ok, safe_text  # noqa: E402
from reserve_id import SPEC, WORKTREE, parse_spec_items  # noqa: E402

LABELS = "docs/architecture/item-labels.json"
SCANNED_SUFFIXES = (".md", ".py", ".toml", ".txt", ".json", ".yaml", ".yml")
EXEMPT_PREFIXES = ("tests/fixtures/", "tests/golden/", "docs/reports/systematic-search/data/",
                   # the workflow tooling cites hypothetical items (D.2.9 item 14 as the collision example)
                   "docs/reports/workflow-tools/", "tests/unit/workflow/", "tools/reserve_id.py", "tools/spec_labels.py")
_NUM = r"\d+(?:\s*(?:–|-|to)\s*\d+)?"
CITATION = re.compile(
    r"§?\bD\.(?P<sec>\d+(?:\.\d+)*[a-z]?)(?:\s+(?:note\s+)?items?\s+(?P<items>" + _NUM + r"(?:\s*(?:,|and|or)\s*"
    + _NUM + r")*)|\((?P<paren>\d+)\))")


def lists_of(spec_text: str) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """list id -> item number -> the definitions (more than one is a duplicate)."""
    defs, _jumps = parse_spec_items(spec_text, WORKTREE, SPEC)
    out: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for d in defs:
        out[d.scope][d.number].append({"line": d.line, "title": d.fingerprint})
    return out


def expand(items: str) -> list[int]:
    numbers: list[int] = []
    for part in re.split(r"\s*(?:,|and|or)\s*", items.strip()):
        m = re.fullmatch(r"(\d+)(?:\s*(?:–|-|to)\s*(\d+))?", part.strip())
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo or hi - lo > 50:
            numbers.append(lo)
        else:
            numbers.extend(range(lo, hi + 1))
    return numbers


def resolve(lists: dict[str, dict[int, list[dict[str, Any]]]], section: str, number: int) -> str | None:
    """None if the citation resolves, else the problem."""
    if section not in lists:
        return "no numbered list in that section"
    if number not in lists[section]:
        return f"the list has no item {number}"
    if len(lists[section][number]) > 1:
        return "duplicate: the list holds this number twice"
    if f"{section}b" in lists and number in lists[f"{section}b"]:
        return f"ambiguous: {section}b also has an item {number}"
    return None


def scan(root: Path, lists: dict[str, dict[int, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    tracked = (git_ok(["ls-files", "-z"], root) or "").split("\0")
    problems = []
    for rel in tracked:
        if not rel.endswith(SCANNED_SUFFIXES) or rel.startswith(EXEMPT_PREFIXES) or rel == LABELS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in CITATION.finditer(line):
                section = "D." + m.group("sec")
                numbers = expand(m.group("items")) if m.group("items") else [int(m.group("paren"))]
                for n in numbers:
                    why = resolve(lists, section, n)
                    if why:
                        problems.append({"path": rel, "line": lineno, "citation": f"{section} item {n}",
                                         "problem": why})
    return problems


def mapping(lists: dict[str, dict[int, list[dict[str, Any]]]]) -> dict[str, Any]:
    return {f"{lst} item {n}": {"list": lst, "section": re.sub(r"[a-z]$", "", lst), "line": defs[0]["line"],
                                "title": defs[0]["title"]}
            for lst, items in sorted(lists.items()) for n, defs in sorted(items.items())}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd())
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    top = git_ok(["rev-parse", "--show-toplevel"], a.cwd)
    if top is None:
        print(f"spec-labels: {a.cwd} is not inside a git worktree", file=sys.stderr)
        return 2
    root = Path(top)
    lists = lists_of((root / SPEC).read_text(encoding="utf-8"))
    labels = json.dumps(mapping(lists), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if a.write:
        (root / LABELS).write_text(labels, encoding="utf-8")
        print(f"spec-labels: wrote {LABELS}")
        return 0
    problems = scan(root, lists)
    stale = (root / LABELS).is_file() and (root / LABELS).read_text(encoding="utf-8") != labels
    if a.json:
        print(json.dumps({"problems": problems, "labels_stale": stale}, indent=2, ensure_ascii=True))
    else:
        for x in problems:
            print(f"{x['path']}:{x['line']}: {safe_text(x['citation'])}: {x['problem']}")
        if stale:
            print(f"spec-labels: {LABELS} is stale; run tools/spec_labels.py --write")
        print(f"spec-labels: {len(problems)} problem(s)")
    return 1 if problems or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
