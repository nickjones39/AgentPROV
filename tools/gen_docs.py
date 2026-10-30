"""Generated shared docs: one file per entry, a committed index that is rebuilt from them (D-421, D-422).

Usage::

    uv run python tools/gen_docs.py --check [TARGET...]    # test + merge train: exit 1 if a generated file is stale
    uv run python tools/gen_docs.py --write [TARGET...]    # regenerate from the fragments
    uv run python tools/gen_docs.py --split TARGET          # one-time migration: fragments from today's file
    uv run python tools/gen_docs.py --adopt TARGET          # move direct edits of a generated file into fragments

Targets: ``decisions`` (``docs/architecture/DECISIONS.md``, an index of parts in ``docs/architecture/decision-log/``),
``regen-batch`` (``docs/reports/analysis/regen-batch.md``) and ``agents`` (``AGENTS.md``: the §0 session entries and the
§13 history entries; the rest stays as hand-edited parts).

**Why.** Several sessions appending to one file conflict on every merge, and ``merge=union`` corrupts entries
(``tests/unit/workflow/test_union_merge_hazards.py``). With one file per entry, two branches that add entries touch
different files. The generated file still conflicts, and is resolved by running ``--write``, never by hand.

**Rules.**

* Fragments are verbatim: the generated file is the plain concatenation of its parts, with no front matter.
* Order: ``_legacy-order-<list>.txt``, written once by ``--split`` and never appended, holds the order of the entries
  that existed at migration. Newer entries follow, sorted by number (decisions) or by file name. So no later branch
  edits a shared file to add an entry.
* ``--split`` refuses unless the parts concatenate back to the current file byte for byte, so the migration commit
  leaves the generated file unchanged (its ``git log`` and ``git blame`` continue).
* A target that has not been split yet is reported as ``not migrated`` and passes ``--check``, so this tool can land
  before the migration. A target with neither its file nor its directory in the tree is reported as ``absent`` and
  passes too: the public export leaves out ``AGENTS.md`` and ``docs/agents/`` (D-1004).
* **Parts** (D-1003): a fragment directory with a ``_parts.toml`` (``width``, ``directory``, ``title``, ``label``)
  generates its file as an index, with the list's entries in part files of ``width`` numbers each (by the entry's number;
  an entry without one stays with the entry before it). The index holds the fixed parts and, in the list's place, a
  generated table of the parts between ``PARTS_BEGIN`` and ``PARTS_END``. Each part keeps the global order of its entries.
  ``--check`` covers the index and every part, and reports a part file that is no longer generated; ``--write`` removes
  it. ``DECISIONS.md`` is split this way, so no generated file nears the repository's 1 MiB limit
  (``tests/repo/test_repository_hygiene.py``).
* ``--adopt`` re-splits the generated file as it stands (for example after a pre-migration branch merged ``main``) and
  writes every entry whose text differs from its fragment. It never deletes a fragment; an entry missing from the file
  is reported.
* ``--adopt`` is for branches started **before** the split only, and refuses a target whose fragment directory already
  existed where the branch (``--branch``, default ``HEAD``) left ``--base`` (default ``main``): the parent of the oldest
  first-parent commit of the branch that is not on the base, or the branch itself when the base reaches it. The merge
  train passes the merged branch's commit as ``--branch``. There, entries written by hand under their own file names (a session
  entry, ``D-701-addendum.md``) get a second fragment under the name the split derives, and every such entry appears
  twice (2026-10-23). After merging ``main`` into such a branch, take either side of a generated-file conflict and run
  ``--write``. Where ``--adopt`` runs, an entry whose exact text is already a fragment under another name is skipped
  and reported, never written twice.

Standard library only; no network.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import git_ok  # noqa: E402

Item = tuple[str, str]  # (fragment file name, verbatim text)


@dataclass(frozen=True)
class Fixed:
    name: str  # file name inside the target directory, e.g. "_preamble.md"


@dataclass(frozen=True)
class ListPart:
    name: str  # list name, used in "_legacy-order-<name>.txt"
    subdir: str  # "." for the target directory itself


Part = Fixed | ListPart
Segment = tuple[Part, str | list[Item]]


@dataclass(frozen=True)
class Target:
    name: str
    path: str  # the generated file, relative to the repository root
    directory: str  # the fragment directory
    layout: tuple[Part, ...]
    split: Callable[[str], list[Segment]]
    sort_key: Callable[[str], tuple]


# --------------------------------------------------------------------------------------------------- splitting

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str, words: int = 8, limit: int = 60) -> str:
    plain = re.sub(r"[`*_\[\]()]", " ", text).lower()
    s = _NON_SLUG.sub("-", " ".join(plain.split()[:words])).strip("-")
    return (s[:limit].rstrip("-") or "entry")


def stable_slug(title: str, words: int = 6) -> str:
    """A file name that survives status edits: the title up to its first parenthesis (``Item 20 (planned…`` and
    ``Item 20 (implemented…`` are both ``item-20``)."""
    m = re.match(r"\s*(Items?\s+[0-9](?:[0-9 ,and–-]*[0-9])?)", title)
    head = m.group(1) if m else title.split("(")[0]
    return slug(head, words)


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}-{seen[n]}")
    return out


def bullet_chunks(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    """Top-level ``- `` bullets from ``start`` with their indented and blank continuation lines.

    Stops at the first column-0 line that is not a bullet; returns the chunks and the index of that line.
    """
    chunks: list[list[str]] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.startswith("- "):
            chunks.append([line])
        elif chunks and (line == "\n" or line.startswith((" ", "\t")) or line == ""):
            chunks[-1].append(line)
        else:
            break
        i += 1
    return chunks, i


def _first(lines: list[str], pattern: str, start: int = 0) -> int:
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.match(lines[i]):
            return i
    raise ValueError(f"no line matching {pattern!r}")


#: ``D-N``, ``D-N addendum [k]``, ``D-N amendment [k]``, or a block bullet announcing ``D-a..D-b`` (also ``–``, ``—``,
#: ``to``), whose entries follow it: the block is named ``D-a-D-b.md``, so the real ``D-a`` keeps ``D-a.md``.
_DECISION = re.compile(r"^- \*\*D-(\d+)(?!\d)(?:\s*(?:\.\.|–|—|\bto\b)\s*D-(\d+)|\s+(addendum|amendment)(?:\s+(\d+))?)?")


def split_decisions(text: str) -> list[Segment]:
    lines = text.splitlines(keepends=True)
    start = _first(lines, r"^- \*\*D-\d+")
    chunks, end = bullet_chunks(lines, start)
    if end != len(lines):
        raise ValueError(f"DECISIONS.md: line {end + 1} is neither an entry nor inside one")
    names = []
    for chunk in chunks:
        m = _DECISION.match(chunk[0])
        if m:
            first, last, kind, k = m.groups()
            names.append(f"D-{first}-D-{last}.md" if last else
                         f"D-{first}-{kind}{f'-{k}' if k else ''}.md" if kind else f"D-{first}.md")
            continue
        # A note between entries (e.g. "- D-388–D-389 are reserved."): named after its first decision number.
        cited = re.search(r"\bD-(\d+)", chunk[0])
        names.append(f"D-{cited.group(1)}-note.md" if cited else f"note-{slug(chunk[0][2:], 4)}.md")
    items = list(zip(_unique_md(names), ("".join(c) for c in chunks), strict=True))
    return [(Fixed("_preamble.md"), "".join(lines[:start])), (ListPart("entries", "."), items)]


def _unique_md(names: list[str]) -> list[str]:
    return [n if n.endswith(".md") else n + ".md" for n in _unique([n.removesuffix(".md") for n in names])]


def decision_key(name: str) -> tuple:
    m = re.match(r"D-(\d+)(.*)\.md$", name)
    return (int(m.group(1)), m.group(2)) if m else (10**9, name)


def split_regen_batch(text: str) -> list[Segment]:
    lines = text.splitlines(keepends=True)
    header = _first(lines, r"^\|\s*#\s*\|\s*Item\b")
    if not lines[header + 1].startswith("|---"):
        raise ValueError("regen-batch.md: the item table has no separator row")
    rows_start = header + 2
    i = rows_start
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    rows = lines[rows_start:i]
    sec_start = _first(lines, r"^## ", i)
    notes = "".join(lines[i:sec_start])
    sections: list[list[str]] = []
    for line in lines[sec_start:]:
        if line.startswith("## "):
            sections.append([line])
        else:
            sections[-1].append(line)
    row_names = []
    for row in rows:
        cell = row.strip().strip("|").split("|")[0].strip()
        row_names.append(slug(cell) if cell not in ("—", "-", "–") else "dash")
    sec_names = [stable_slug(s[0][3:]) for s in sections]
    return [(Fixed("_preamble.md"), "".join(lines[:rows_start])),
            (ListPart("rows", "rows"), list(zip(_unique_md(row_names), rows, strict=True))),
            (Fixed("_notes.md"), notes),
            (ListPart("sections", "sections"), list(zip(_unique_md(sec_names), ("".join(s) for s in sections),
                                                        strict=True)))]


def regen_key(name: str) -> tuple:
    stem = name.removesuffix(".md")
    m = re.match(r"(?:items?-)?(\d+)", stem)
    return (0, int(m.group(1)), stem) if m else (1, 0, stem)


_BOLD = re.compile(r"^- \*\*(.+?)\*\*")


def split_agents(text: str) -> list[Segment]:
    lines = text.splitlines(keepends=True)
    par = _first(lines, r"^### Parallel sessions")
    s_start = _first(lines, r"^- ", par)
    sessions, s_end = bullet_chunks(lines, s_start)
    hist = _first(lines, r"^## 13\. History", s_end)
    h_start = _first(lines, r"^- ", hist)
    history, h_end = bullet_chunks(lines, h_start)

    def names(chunks: list[list[str]], dated: bool) -> list[str]:
        out = []
        for chunk in chunks:
            m = _BOLD.match(chunk[0])
            title = m.group(1) if m else chunk[0][2:]
            if dated:
                date = re.match(r"(\d{4}-\d{2}-\d{2})", title)
                rest = chunk[0][m.end():] if m else ""
                out.append(f"{date.group(1) if date else 'undated'}-{stable_slug(rest)}")
            else:
                out.append(stable_slug(title))
        return _unique_md(out)

    return [(Fixed("_head.md"), "".join(lines[:s_start])),
            (ListPart("sessions", "sessions"), list(zip(names(sessions, False), ("".join(c) for c in sessions),
                                                        strict=True))),
            (Fixed("_middle.md"), "".join(lines[s_end:h_start])),
            (ListPart("history", "history"), list(zip(names(history, True), ("".join(c) for c in history),
                                                      strict=True))),
            (Fixed("_tail.md"), "".join(lines[h_end:]))]


TARGETS: dict[str, Target] = {
    "decisions": Target("decisions", "docs/architecture/DECISIONS.md", "docs/architecture/decisions",
                        (Fixed("_preamble.md"), ListPart("entries", ".")), split_decisions, decision_key),
    "regen-batch": Target("regen-batch", "docs/reports/analysis/regen-batch.md", "docs/reports/analysis/regen-batch",
                          (Fixed("_preamble.md"), ListPart("rows", "rows"), Fixed("_notes.md"),
                           ListPart("sections", "sections")), split_regen_batch, regen_key),
    "agents": Target("agents", "AGENTS.md", "docs/agents",
                     (Fixed("_head.md"), ListPart("sessions", "sessions"), Fixed("_middle.md"),
                      ListPart("history", "history"), Fixed("_tail.md")), split_agents, lambda n: (n,)),
}


# --------------------------------------------------------------------------------------------------- generating

PARTS_FILE = "_parts.toml"
PARTS_BEGIN = "<!-- BEGIN generated parts (tools/gen_docs.py --write) -->"
PARTS_END = "<!-- END generated parts -->"
ENTRIES_MARK = "<!-- entries -->"


@dataclass(frozen=True)
class Parts:
    width: int  # numbers per part
    directory: str  # the parts' directory, relative to the generated file's directory
    title: str  # a part's heading, with ``{lo}`` and ``{hi}``
    label: str  # a part's range in the index table, with ``{lo}`` and ``{hi}``


def parts_config(root: Path, target: Target) -> Parts | None:
    """The target's ``_parts.toml``, or None when its file is generated whole."""
    path = root / target.directory / PARTS_FILE
    if not path.is_file():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    parts = Parts(int(data["width"]), str(data["directory"]), str(data["title"]), str(data["label"]))
    if parts.width < 1 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", parts.directory):
        raise ValueError(f"{path.relative_to(root)}: width must be positive and directory one plain lower-case name")
    return parts


def _order_file(directory: Path, part: ListPart) -> Path:
    return directory / f"_legacy-order-{part.name}.txt"


def _item_files(directory: Path, part: ListPart) -> list[Path]:
    folder = directory / part.subdir
    return sorted(p for p in folder.glob("*.md") if not p.name.startswith("_")) if folder.is_dir() else []


def ordered_items(directory: Path, part: ListPart, sort_key: Callable[[str], tuple]) -> list[Path]:
    """Legacy entries in their frozen order, then newer ones sorted by ``sort_key``."""
    folder = directory / part.subdir
    order_file = _order_file(directory, part)
    legacy = [n for n in order_file.read_text(encoding="utf-8").splitlines() if n] if order_file.is_file() else []
    missing = [n for n in legacy if not (folder / n).is_file()]
    if missing:
        raise ValueError(f"{part.name}: legacy fragment(s) missing: {', '.join(missing[:5])} (entries are never "
                         "deleted; a withdrawn entry keeps its file)")
    known = set(legacy)
    newer = sorted((p.name for p in _item_files(directory, part) if p.name not in known), key=sort_key)
    return [folder / n for n in [*legacy, *newer]]


def generate(root: Path, target: Target) -> str:
    directory = root / target.directory
    out = []
    for part in target.layout:
        if isinstance(part, Fixed):
            path = directory / part.name
            out.append(path.read_text(encoding="utf-8") if path.is_file() else "")
        else:
            out.extend(p.read_text(encoding="utf-8") for p in ordered_items(directory, part, target.sort_key))
    return "".join(out)


def _parts_dir(target: Target, parts: Parts) -> str:
    return f"{Path(target.path).parent.as_posix()}/{parts.directory}"


def generate_files(root: Path, target: Target) -> dict[str, str]:
    """Every generated file of ``target``, by repository path: the file itself, or its index and parts."""
    parts = parts_config(root, target)
    if parts is None:
        return {target.path: generate(root, target)}
    lists = [p for p in target.layout if isinstance(p, ListPart)]
    if len(lists) != 1:
        raise ValueError(f"{target.name}: parts need exactly one entry list in the layout")
    directory = root / target.directory
    buckets: dict[int, list[str]] = {}
    bucket = 0
    for path in ordered_items(directory, lists[0], target.sort_key):
        number = target.sort_key(path.name)[0]
        if isinstance(number, int) and number < 10**9:
            bucket = number // parts.width
        buckets.setdefault(bucket, []).append(path.read_text(encoding="utf-8"))
    stem, folder = Path(target.path).stem, _parts_dir(target, parts)
    out: dict[str, str] = {}
    rows = []
    for b in sorted(buckets):
        lo, hi = b * parts.width, b * parts.width + parts.width - 1
        name = f"{stem}-{lo:04d}-{hi:04d}.md"
        out[f"{folder}/{name}"] = (
            f"<!-- Generated by `uv run python tools/gen_docs.py --write {target.name}` from `{target.directory}/`: "
            "edit the entry's file there, never this file. -->\n"
            f"# {parts.title.format(lo=lo, hi=hi)}\n\n"
            f"Part of [{Path(target.path).name}](../{Path(target.path).name}), which lists every part. Entries keep "
            f"their order; this part holds the numbers {parts.label.format(lo=lo, hi=hi)}.\n\n"
            f"{ENTRIES_MARK}\n" + "".join(buckets[b]))
        rows.append(f"| [{name}]({parts.directory}/{name}) | {parts.label.format(lo=lo, hi=hi)} | {len(buckets[b])} |\n")
    table = (f"{PARTS_BEGIN}\n"
             f"The entries are kept in parts of {parts.width} numbers each, generated from `{target.directory}/`:\n\n"
             "| Part | Numbers | Entries |\n|---|---|---:|\n" + "".join(rows) + f"{PARTS_END}\n")
    index = []
    for part in target.layout:
        if isinstance(part, Fixed):
            path = directory / part.name
            index.append(path.read_text(encoding="utf-8") if path.is_file() else "")
        else:
            index.append(table)
    out[target.path] = "".join(index)
    return out


def stray_parts(root: Path, target: Target, files: dict[str, str]) -> list[str]:
    """Part files in the parts' directory that ``files`` does not generate (after a width change)."""
    parts = parts_config(root, target)
    if parts is None:
        return []
    folder = root / _parts_dir(target, parts)
    stem = Path(target.path).stem
    return sorted(p.relative_to(root).as_posix() for p in folder.glob(f"{stem}-*.md")
                  if p.relative_to(root).as_posix() not in files) if folder.is_dir() else []


def read_generated(root: Path, target: Target) -> str:
    """The generated text as one file, for ``--adopt``: an index's parts table is replaced by the parts' entries (in
    part order); a file without the table (generated whole, or from before the parts) is returned as it is."""
    text = (root / target.path).read_text(encoding="utf-8")
    parts = parts_config(root, target)
    if parts is None or PARTS_BEGIN not in text or PARTS_END not in text:
        return text
    head, rest = text.split(PARTS_BEGIN, 1)
    tail = rest.split(PARTS_END, 1)[1].removeprefix("\n")
    folder = root / _parts_dir(target, parts)
    entries = []
    for path in sorted(folder.glob(f"{Path(target.path).stem}-*.md")):
        body = path.read_text(encoding="utf-8")
        if ENTRIES_MARK + "\n" not in body:
            raise ValueError(f"{path.relative_to(root)}: no {ENTRIES_MARK} line")
        entries.append(body.split(ENTRIES_MARK + "\n", 1)[1])
    return head + "".join(entries) + tail


def migrated(root: Path, target: Target) -> bool:
    return (root / target.directory).is_dir()


def left_out(root: Path, target: Target) -> bool:
    """Neither the generated file nor its fragments are in this tree (the public export, D-1004)."""
    return not migrated(root, target) and not (root / target.path).is_file()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def split(root: Path, target: Target) -> int:
    """Write the fragments for ``target`` from its current generated file (one-time migration)."""
    directory = root / target.directory
    if directory.exists():
        raise ValueError(f"{target.directory} exists: {target.name} is already split")
    text = (root / target.path).read_text(encoding="utf-8")
    segments = target.split(text)
    rebuilt = "".join(body if isinstance(body, str) else "".join(t for _n, t in body) for _p, body in segments)
    if rebuilt != text:
        raise ValueError(f"{target.path}: the parts do not concatenate back to the file; nothing written")
    if [p for p, _b in segments] != list(target.layout):
        raise ValueError(f"{target.name}: split and layout disagree")
    count = 0
    for part, body in segments:
        if isinstance(part, Fixed):
            assert isinstance(body, str)
            _write(directory / part.name, body)
        else:
            assert isinstance(body, list)
            for name, item in body:
                _write(directory / part.subdir / name, item)
                count += 1
            _write(_order_file(directory, part), "".join(f"{n}\n" for n, _t in body))
    if generate(root, target) != text:
        raise ValueError(f"{target.name}: regenerated text differs after the split (fragments left for inspection)")
    return count


def fork_point(root: Path, branch: str, base: str) -> str | None:
    """Where ``branch`` left ``base``: the parent of the oldest first-parent commit of ``branch`` that ``base`` does
    not reach (a merge of ``base`` into the branch does not move it), or ``branch`` itself when ``base`` reaches it;
    None when either cannot be resolved or the branch shares no history with ``base``."""
    if any(git_ok(["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"], root) is None for rev in (branch, base)):
        return None
    own = git_ok(["rev-list", "--first-parent", branch, "--not", base, "--"], root)
    if own is None:
        return None
    commits = own.split()
    return git_ok(["rev-parse", "--verify", "-q", f"{commits[-1]}^1" if commits else f"{branch}^{{commit}}"], root)


def started_after_split(root: Path, target: Target, branch: str, base: str) -> str | None:
    """Why ``--adopt`` must not run on ``target`` here (see the module docstring), or None when it may."""
    fork = fork_point(root, branch, base)
    if fork is None:
        return (f"refused: cannot tell where {branch!r} left {base!r}, so it may have started after the split; "
                "pass --branch REV / --base REV")
    if git_ok(["cat-file", "-e", f"{fork}:{target.directory}"], root) is not None:
        return (f"refused: {branch} started after the split ({target.directory} already exists at its fork point "
                f"{fork[:10]} from {base}); --adopt would add a second fragment for every entry written under its own "
                f"file name. Edit the fragments and run tools/gen_docs.py --write")
    return None


def adopt(root: Path, target: Target) -> tuple[list[str], list[str], list[str]]:
    """Write fragments for every entry of the generated file that differs from its fragment.

    Returns the written paths, the entries that have a fragment but are absent from the file, and the entries skipped
    because their exact text is already a fragment under another name.
    """
    directory = root / target.directory
    segments = target.split(read_generated(root, target))
    written, absent, same = [], [], []
    for part, body in segments:
        if isinstance(part, Fixed):
            assert isinstance(body, str)
            path = directory / part.name
            if not path.is_file() or path.read_text(encoding="utf-8") != body:
                _write(path, body)
                written.append(str(path.relative_to(root)))
            continue
        assert isinstance(body, list)
        names = {n for n, _t in body}
        texts = {p.read_text(encoding="utf-8"): p for p in _item_files(directory, part)}
        for name, item in body:
            path = directory / part.subdir / name
            if not path.is_file() and item in texts:
                same.append(f"{path.relative_to(root)} (same text as {texts[item].relative_to(root)})")
                continue
            if not path.is_file() or path.read_text(encoding="utf-8") != item:
                _write(path, item)
                written.append(str(path.relative_to(root)))
        matched = {texts[i] for _n, i in body if i in texts}
        absent += [str(p.relative_to(root)) for p in _item_files(directory, part) if p.name not in names
                   and p not in matched]
    return written, absent, same


# --------------------------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd())
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="exit 1 if a generated file is stale")
    mode.add_argument("--write", action="store_true", help="regenerate")
    mode.add_argument("--split", action="store_true", help="one-time migration of the named targets")
    mode.add_argument("--adopt", action="store_true", help="move direct edits of the generated files into fragments")
    p.add_argument("--base", default="main", metavar="REV",
                   help="--adopt: refuse unless the branch left REV before the split (default main)")
    p.add_argument("--branch", default="HEAD", metavar="REV",
                   help="--adopt: the branch whose direct edits are adopted (default HEAD; the merge train passes the "
                        "merged branch)")
    p.add_argument("targets", nargs="*", help=f"targets (default: all): {', '.join(TARGETS)}")
    a = p.parse_args(argv)
    a.cmd = "split" if a.split else "adopt" if a.adopt else None
    top = git_ok(["rev-parse", "--show-toplevel"], a.cwd)
    root = Path(top) if top else a.cwd.resolve()
    names = a.targets or list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        p.error(f"unknown target(s): {', '.join(unknown)}")
    if a.cmd == "split" and not a.targets:
        p.error("--split needs the target(s) named")
    status = 0
    for name in names:
        target = TARGETS[name]
        try:
            if a.cmd != "split" and left_out(root, target):
                print(f"gen-docs: {name}: absent ({target.path} and {target.directory}/ are not in this tree)")
            elif a.cmd == "split":
                print(f"gen-docs: {name}: {split(root, target)} entries split into {target.directory}")
            elif a.cmd == "adopt":
                if not migrated(root, target):
                    print(f"gen-docs: {name}: not migrated")
                    continue
                refusal = started_after_split(root, target, a.branch, a.base)
                if refusal is not None:
                    print(f"gen-docs: {name}: {refusal}")
                    status = 2
                    continue
                written, absent, same = adopt(root, target)
                for w in written:
                    print(f"gen-docs: {name}: wrote {w}")
                for s in same:
                    print(f"gen-docs: {name}: not written: {s}")
                for x in absent:
                    print(f"gen-docs: {name}: {x} has no entry in {target.path} (kept; remove it only on purpose)")
                for path, text in generate_files(root, target).items():
                    if not (root / path).is_file() or text != (root / path).read_text(encoding="utf-8"):
                        _write(root / path, text)
                        print(f"gen-docs: {name}: regenerated {path} (entry order may have changed)")
            elif not migrated(root, target):
                print(f"gen-docs: {name}: not migrated")
            else:
                files = generate_files(root, target)
                stale = [rel for rel, text in files.items()
                         if not (root / rel).is_file() or (root / rel).read_text(encoding="utf-8") != text]
                stray = stray_parts(root, target, files)
                if not stale and not stray:
                    print(f"gen-docs: {name}: current")
                elif a.write:
                    for rel in stale:
                        _write(root / rel, files[rel])
                        print(f"gen-docs: {name}: wrote {rel}")
                    for rel in stray:
                        (root / rel).unlink()
                        print(f"gen-docs: {name}: removed {rel} (no longer generated)")
                else:
                    for rel in stale:
                        print(f"gen-docs: {name}: {rel} is stale; edit the fragments in {target.directory} and "
                              "run tools/gen_docs.py --write (or --adopt to keep direct edits)")
                    for rel in stray:
                        print(f"gen-docs: {name}: {rel} is no longer generated; run tools/gen_docs.py --write")
                    status = 1
        except (ValueError, OSError) as exc:
            print(f"gen-docs: {name}: {exc}")
            status = 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
