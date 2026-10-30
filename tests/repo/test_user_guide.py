"""The user guide (``docs/user-guide/``) stays correct: links resolve, commands exist, the CLI reference is current.

* Every relative link and image in the guide resolves to a file **inside** ``docs/user-guide/`` (the guide's website
  publishes only that folder, so a link to any other repository file must be an absolute GitHub URL), and every
  ``#anchor`` into a guide page names a heading of that page (GitHub's slug rules).
* Every ``agentprov <command> [<subcommand>] [--option ...]`` in a code block names a command of the CLI's parser,
  and every long option on it exists for that command (global options included). Commands are the lines of a
  ``bash`` block that start with ``agentprov`` or ``uv run agentprov``, and the ``$ agentprov …`` lines of any block.
* The generated CLI reference is current (``tools/gen_user_guide_cli.py --check``).
* Images are small (at most 300 KB each).
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "docs" / "user-guide"
PAGES = sorted(p for p in GUIDE.glob("*.md") if not p.name.startswith("_"))
GENERATED = {"11-cli-reference.md"}  # its code blocks are --help output, checked by --check instead
LINK = re.compile(r"!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^(\s*)```(\w*)\s*$")
MAX_IMAGE_BYTES = 300 * 1024


def _strip_code(text: str) -> str:
    """The page without fenced code blocks and inline code spans (links there are examples, not links)."""
    out, inside = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lower case, markup and punctuation dropped (except - and _), spaces to hyphens."""
    text = re.sub(r"`", "", heading.strip()).lower()
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(page: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for line in _strip_code_keep_headings(page.read_text(encoding="utf-8")):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m:
            continue
        slug = _slug(m.group(2))
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    return out


def _strip_code_keep_headings(text: str) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


def _links(page: Path) -> list[str]:
    return LINK.findall(_strip_code(page.read_text(encoding="utf-8")))


def test_the_guide_has_its_chapters() -> None:
    names = {p.name for p in PAGES}
    assert {"README.md", "01-install.md", "02-concepts.md", "11-cli-reference.md", "12-glossary.md",
            "13-namespace.md", "14-corpora.md"} <= names


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_relative_link_and_image_resolves_inside_the_guide(page: Path) -> None:
    problems = []
    for target in _links(page):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # https:, mailto:, …
            continue
        path_part, _, anchor = target.partition("#")
        dest = (page.parent / path_part).resolve() if path_part else page
        if not dest.is_relative_to(GUIDE.resolve()):
            problems.append(f"{target}: outside docs/user-guide (use an absolute GitHub URL)")
            continue
        if not dest.exists():
            problems.append(f"{target}: missing")
            continue
        if anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
            problems.append(f"{target}: no heading with anchor #{anchor}")
    assert not problems, problems


def _parser_tree() -> dict[tuple[str, ...], set[str]]:
    """Every command path of the CLI (aliases included) with the long options its parser accepts."""
    from agentprov.cli.main import build_parser

    tree: dict[tuple[str, ...], set[str]] = {}

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        options = {o for a in parser._actions for o in a.option_strings if o.startswith("--")}
        tree[path] = options
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, (*path, name))

    walk(build_parser(), ())
    return tree


def _command_lines(page: Path) -> list[str]:
    """The agentprov command lines of the page's code blocks (continuation lines joined)."""
    out: list[str] = []
    lang, inside, pending = "", False, ""
    for raw in page.read_text(encoding="utf-8").splitlines():
        m = FENCE.match(raw)
        if m:
            inside, lang, pending = (not inside), m.group(2), ""
            continue
        if not inside:
            continue
        line = pending + raw.strip()
        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue
        pending = ""
        if line.startswith("$ "):
            line = line[2:]
        elif lang not in ("bash", "sh", "shell", "console", ""):
            continue
        elif lang == "" or lang == "console":
            continue
        line = re.sub(r"^uv run (--\S+ )*", "", line)
        if re.match(r"^agentprov(\s|$)", line):
            out.append(line.split("#", 1)[0].strip() if " #" in line else line)
    return out


def _check_command(line: str, tree: dict[tuple[str, ...], set[str]]) -> list[str]:
    tokens = shlex.split(line)[1:]
    path: tuple[str, ...] = ()
    problems = []
    for i, token in enumerate(tokens):
        if token in ("|", "||", "&&", ";", ">", "2>&1"):
            break
        if token == "--":  # `jobs start … -- ARGV`: the job's own agentprov command
            problems += _check_command(shlex.join(["agentprov", *tokens[i + 1:]]), tree)
            break
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if name not in tree[path]:
                problems.append(f"{line}: {name} is not an option of 'agentprov {' '.join(path)}'")
            continue
        if token.startswith("-") or token.startswith("<"):
            continue
        child = (*path, token)
        if child in tree:
            path = child
        elif not path:
            problems.append(f"{line}: {token!r} is not an agentprov command")
            break
    return problems


@pytest.mark.parametrize("page", [p for p in PAGES if p.name not in GENERATED], ids=lambda p: p.name)
def test_every_command_and_option_in_a_code_block_exists(page: Path) -> None:
    tree = _parser_tree()
    problems = [problem for line in _command_lines(page) for problem in _check_command(line, tree)]
    assert not problems, problems


def test_the_command_checker_catches_unknown_commands_and_options() -> None:
    tree = _parser_tree()
    assert _check_command("agentprov verify --corpus c --level chain", tree) == []
    assert _check_command("agentprov --break-stale-lock import agentdojo --fetch --corpus c", tree) == []
    assert _check_command("agentprov backends build agentdojo --offline-check", tree) == []
    assert _check_command("agentprov verfy --corpus c", tree)
    assert _check_command("agentprov verify --no-such-option", tree)
    assert _check_command("agentprov backends build agentdojo --corpus c", tree)
    assert _check_command("agentprov jobs start --label x -- verify --corpus c", tree) == []
    assert _check_command("agentprov jobs start -- verify --no-such-option", tree)


def test_the_generated_cli_reference_is_current() -> None:
    proc = subprocess.run([sys.executable, str(REPO / "tools" / "gen_user_guide_cli.py"), "--check"], cwd=REPO,
                          capture_output=True, text=True, check=False, timeout=600)
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.parametrize("image", sorted((GUIDE / "images").rglob("*.*")), ids=lambda p: p.name)
def test_images_are_small(image: Path) -> None:
    assert image.stat().st_size <= MAX_IMAGE_BYTES, f"{image.name}: {image.stat().st_size} bytes"
