#!/usr/bin/env python3
"""Keep the published ontology copy ``docs/ns/apv-0.2.ttl`` identical to ``src/agentprov/vocab/apv-0.2.ttl``.

The package copy is the source of truth (docs/architecture EF E.4.6 item 1); the ``docs/ns`` copy is what is
published (the namespace is registered at w3id.org, U-02). Bytes are copied, never re-serialised. Earlier
releases stay published beside it as they are (``docs/ns/apv-0.1.ttl``, apv 0.1.0); this tool never touches them.

    uv run python tools/sync_ns.py            # copy vocab/apv-0.2.ttl to docs/ns/apv-0.2.ttl
    uv run python tools/sync_ns.py --check    # exit 1 if the two files differ (or the copy is missing)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "src" / "agentprov" / "vocab" / "apv-0.2.ttl"
TARGET = REPO / "docs" / "ns" / "apv-0.2.ttl"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the published copy differs")
    args = parser.parse_args(argv)

    source = SOURCE.read_bytes()
    if args.check:
        if not TARGET.is_file() or TARGET.read_bytes() != source:
            print(f"{_rel(TARGET)} differs from {_rel(SOURCE)}; run tools/sync_ns.py")
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(source)
    print(f"wrote {_rel(TARGET)} ({len(source)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
