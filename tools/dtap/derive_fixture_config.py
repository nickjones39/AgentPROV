"""Derive a DTap task-configuration fixture without its sandbox ``env_vars`` (docs/architecture D.16.14; K.4.1 item 6).

    uv run python -I tools/dtap/derive_fixture_config.py SOURCE.yaml OUT.yaml

The transformation ``drop_env_vars`` deletes every ``env_vars:`` mapping (the key line and its more-indented block) from
the YAML text and changes nothing else, so the derived file differs from the pinned blob only by those lines. It then
checks, through :func:`agentprov.ingest.yamlsafe.safe_load`, that the derived document equals the source document with
every ``env_vars`` member removed, and refuses otherwise. Values are never printed or written anywhere but OUT (which
holds none of them): the tool prints the number of removed blocks and the two sha256 digests only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_KEY = re.compile(r"^(?P<indent>[ -]*)env_vars\s*:")


def _without(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without(v) for k, v in value.items() if k != "env_vars"}
    if isinstance(value, list):
        return [_without(v) for v in value]
    return value


def drop_env_vars(text: str) -> tuple[str, int]:
    """``text`` without its ``env_vars`` blocks, and how many were removed."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        match = _KEY.match(lines[i])
        if match is None:
            out.append(lines[i])
            i += 1
            continue
        removed += 1
        prefix = match.group("indent")
        column = len(prefix)
        if prefix.rstrip(" ").endswith("-"):  # "- env_vars:" opens a list item: keep the dash on its own line
            out.append(prefix.rstrip() + "\n")
        i += 1
        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip(" ")
            if stripped.strip() and len(line) - len(stripped) <= column:
                break
            i += 1
    return "".join(out), removed


def main(argv: list[str] | None = None) -> int:
    from agentprov.ingest import yamlsafe

    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print(__doc__.splitlines()[2].strip(), file=sys.stderr)
        return 2
    source, target = Path(args[0]), Path(args[1])
    raw = source.read_bytes()
    derived, removed = drop_env_vars(raw.decode("utf-8"))
    data = derived.encode("utf-8")
    if _without(yamlsafe.safe_load(raw)) != yamlsafe.safe_load(data):
        print("refused: the derived document is not the source document minus env_vars", file=sys.stderr)
        return 1
    target.write_bytes(data)
    print(json.dumps({"removed_blocks": removed, "source_sha256": hashlib.sha256(raw).hexdigest(),
                      "derived_sha256": hashlib.sha256(data).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
