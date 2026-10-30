"""The README's adapter-family and source tables, generated from the source registry.

Usage::

    uv run python tools/gen_readme_sources.py --check     # test: exit 1 if README.md's tables differ from the registry
    uv run python tools/gen_readme_sources.py --write     # rewrite the block between the markers in README.md

The block between ``BEGIN`` and ``END`` below is generated; everything else in README.md is hand-written. A branch that
adds a source, part or family runs ``--write``; a conflict in the block is resolved by running ``--write``, never by
hand. The tables show only registry values (family, readers, source, part, profile, gated status, the sealed corpus, SPDX
id and whether the licence carries use restrictions), so they cannot drift from ``agentprov info``.

The README lists only the parts this release has: those imported into a sealed corpus, and the live parts whose status
is ``partial`` (:func:`shown`). Registered parts that were not imported (planned, owned elsewhere, the compat oracle, the
toy format) stay in ``agentprov info`` and the user guide's corpus listing. A ``partial`` live part is labelled
``live (tested subset)`` here only (:data:`LIVE_LABEL`); the registry value stays ``partial``.

Standard library plus ``agentprov.adapters.registry``; reads no corpus; no network.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from agentprov.adapters.registry import READERS, REGISTRY

README = Path(__file__).resolve().parents[1] / "README.md"
BEGIN = "<!-- BEGIN generated: sources (tools/gen_readme_sources.py --write) -->"
END = "<!-- END generated: sources -->"
_STATUSES = ("supported", "partial")
#: README-only label of a ``partial`` live part: the scripted live gate passes, and real-model runs are admitted only for
#: the subset its caveat declares (D-720)
LIVE_LABEL = "live (tested subset)"


def shown(cap) -> bool:
    """A part the README lists: imported into a sealed corpus, or a live part whose status is ``partial``."""
    return cap.role == "source" and (bool(cap.sealed) or cap.live_status == "partial")


def _family_of_reader(factory: str) -> str:
    # "agentprov.adapters.<family>.<module>:<Class>"
    return factory.split(":", 1)[0].split(".")[2]


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _status(cap) -> str:
    parts = []
    if cap.sealed and cap.import_status:
        parts.append(f"import {cap.import_status}")
    if cap.live_status == "partial":
        parts.append(LIVE_LABEL)
    return ", ".join(parts) + "".join(f"; sealed as `{s.tag}`" for s in cap.sealed)


def _licence(src) -> str:
    lic = src.licence
    text = lic.spdx or lic.licence_ref or "unassessed"
    if lic.restrictions:
        text += " (restricted)"
    if lic.policy != "include":
        text += f", policy {lic.policy}"
    return text


def render() -> str:
    families: dict[str, list] = {}
    for src in REGISTRY:
        if any(shown(cap) for cap in src.capabilities):
            families.setdefault(src.family or "none", []).append(src)
    readers: dict[str, list[str]] = {}
    for key, factory in READERS.items():
        readers.setdefault(_family_of_reader(factory), []).append(key)

    out = [BEGIN, "", "| Family | Readers (dialects) | Sources | Parts by status | Sealed corpora |", "|---|---|---|---|---|"]
    for fam, sources in families.items():
        counts: Counter[str] = Counter()
        for src in sources:
            for cap in src.capabilities:
                if not shown(cap):
                    continue
                counts[cap.import_status if cap.sealed else LIVE_LABEL] += 1  # import status first
        order = [s for s in _STATUSES if counts[s]] + sorted(k for k in counts if k not in _STATUSES)
        summary = ", ".join(f"{counts[k]} {k}" for k in order)
        dialects = ", ".join(f"`{r}`" for r in sorted(readers.get(fam, [])))
        sealed = {s.corpus_id for src in sources for cap in src.capabilities for s in cap.sealed}
        out.append(f"| `{fam}` | {dialects} | {len(sources)} | {summary} | {len(sealed)} |")
    n_sources = sum(len(v) for v in families.values())
    n_parts = sum(shown(c) for v in families.values() for s in v for c in s.capabilities)
    out += ["", "<details>", f"<summary>The {n_sources} sources and their {n_parts} parts with a sealed corpus or a tested "
            "live backend</summary>", "",
            "| Family | Source | Part (profile) | Status | Licence |", "|---|---|---|---|---|"]
    for fam, sources in families.items():
        for src in sources:
            for cap in (c for c in src.capabilities if shown(c)):
                part = f"`{cap.part}`" + (f" (`{cap.profile}`)" if cap.profile else "")
                out.append(f"| `{fam}` | `{src.source_id}` | {part} | {_cell(_status(cap))} | {_cell(_licence(src))} |")
    out += ["", "</details>", "", END]
    return "\n".join(out)


def splice(text: str, block: str) -> str:
    try:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
    except ValueError:
        raise SystemExit(f"{README.name}: the generated-block markers are missing") from None
    return head + block + tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    current = README.read_text(encoding="utf-8")
    wanted = splice(current, render())
    if args.write:
        if wanted != current:
            README.write_text(wanted, encoding="utf-8")
        return 0
    if wanted != current:
        print("README.md: the source tables differ from the registry; run tools/gen_readme_sources.py --write",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
