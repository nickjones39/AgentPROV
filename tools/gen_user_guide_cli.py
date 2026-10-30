"""The user guide's CLI reference (``docs/user-guide/11-cli-reference.md``), generated from the CLI's own ``--help``.

Usage::

    uv run python tools/gen_user_guide_cli.py --check     # exit 1 if the generated block is out of date
    uv run python tools/gen_user_guide_cli.py --write     # rewrite the block between the markers

The block between ``BEGIN`` and ``END`` is generated; the rest of the file is hand-written. Every command and every
subcommand (recursively; aliases are listed with the command they name, never repeated) gets its ``--help`` text,
exactly as ``agentprov <command> ... --help`` prints it. A conflict in the block is resolved by running ``--write``,
never by hand.

The help texts are produced by one child process, ``uv run --frozen --offline python -c ...``, which builds the CLI's
parser and calls ``agentprov.cli.main.main([..., "--help"])`` for each command path, so the text is what the console
script prints. The child gets ``COLUMNS=100`` (argparse wraps to it) so the output does not depend on the terminal.
The user's home directory is shown as ``~``.

Standard library only; reads no corpus; no network (``--offline``).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs" / "user-guide" / "11-cli-reference.md"
BEGIN = "<!-- BEGIN generated: cli (tools/gen_user_guide_cli.py --write) -->"
END = "<!-- END generated: cli -->"
COLUMNS = "100"

# Runs in the project environment. It prints one JSON document: [{"path": [...], "aliases": [...], "help": "..."}].
_CHILD = r'''
import argparse, contextlib, io, json, sys
from agentprov.cli.main import build_parser, main

def subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            seen = {}
            for name, child in action.choices.items():
                seen.setdefault(id(child), (child, []))[1].append(name)
            for child, names in seen.values():
                yield names[0], names[1:], child

def walk(parser, path, aliases):
    yield path, aliases
    for name, child_aliases, child in subparsers(parser):
        yield from walk(child, path + [name], child_aliases)

out = []
for path, aliases in walk(build_parser(), [], []):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([*path, "--help"])
    if code != 0:
        raise SystemExit(f"agentprov {' '.join(path)} --help exited {code}")
    out.append({"path": path, "aliases": aliases, "help": buffer.getvalue()})
sys.stdout.write(json.dumps(out))
'''


def collect() -> list[dict]:
    """Every command path with its aliases and its ``--help`` text (home shown as ``~``)."""
    env = dict(os.environ, COLUMNS=COLUMNS, LINES="50", NO_COLOR="1")
    env.pop("AGENTPROV_PROGRESS", None)
    proc = subprocess.run(
        ["uv", "run", "--frozen", "--offline", "python", "-c", _CHILD],
        cwd=REPO, env=env, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"gen_user_guide_cli: the help child exited {proc.returncode}")
    home = str(Path.home())
    entries = json.loads(proc.stdout)
    for entry in entries:
        entry["help"] = entry["help"].replace(home, "~").rstrip() + "\n"
    return entries


def _anchor_title(path: list[str]) -> str:
    return " ".join(["agentprov", *path])


def render(entries: list[dict]) -> str:
    lines = [BEGIN, "", "Commands in this reference (subcommands indented):", ""]
    for entry in entries:
        path = entry["path"]
        title = _anchor_title(path)
        anchor = title.replace(" ", "-")
        indent = "  " * max(0, len(path) - 1)
        alias = f" (alias {', '.join(entry['aliases'])})" if entry["aliases"] else ""
        lines.append(f"{indent}- [`{title}`](#{anchor}){alias}")
    lines.append("")
    for entry in entries:
        title = _anchor_title(entry["path"])
        level = "#" * min(4, 2 + max(0, len(entry["path"]) - 1))
        lines += [f"{level} {title}", ""]
        if entry["aliases"]:
            lines += [f"Alias: {', '.join('`' + a + '`' for a in entry['aliases'])}.", ""]
        lines += ["```text", entry["help"].rstrip("\n"), "```", ""]
    lines.append(END)
    return "\n".join(lines) + "\n"


def splice(text: str, block: str) -> str:
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < start:
        raise SystemExit(f"gen_user_guide_cli: the markers are missing from {GUIDE.relative_to(REPO)}")
    return text[:start] + block + text[end + len(END) + 1:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="exit 1 if the generated block is out of date")
    mode.add_argument("--write", action="store_true", help="rewrite the generated block")
    args = parser.parse_args(argv)
    current = GUIDE.read_text(encoding="utf-8")
    wanted = splice(current, render(collect()))
    if args.write:
        if wanted != current:
            GUIDE.write_text(wanted, encoding="utf-8")
            print(f"wrote {GUIDE.relative_to(REPO)}")
        return 0
    if wanted != current:
        print(f"{GUIDE.relative_to(REPO)} is out of date: run uv run python tools/gen_user_guide_cli.py --write",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
