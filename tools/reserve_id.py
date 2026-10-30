"""Hands out decision numbers, regen-batch items, spec item numbers and routing ids from one ledger (D-423).

Usage::

    uv run python tools/reserve_id.py reserve decision --count 10 --purpose "multi-agent workflow tooling"
    uv run python tools/reserve_id.py reserve regen-item --purpose "U6-d"
    uv run python tools/reserve_id.py reserve spec-item --list D.2.9 --purpose "streamed multi-execution files"
    uv run python tools/reserve_id.py reserve routing --prefix R-10q --purpose "runner follow-up"
    uv run python tools/reserve_id.py reserve spec-section --list D.6 --purpose "TraceLogger robustness"  # D.6.22
    uv run python tools/reserve_id.py reserve spec-item --list D.6.20 --first 1 --count 11 --purpose "..."  # explicit
    uv run python tools/reserve_id.py void <rid> --reason "reserved the wrong range"   # append-only withdrawal
    uv run python tools/reserve_id.py list [--kind K] [--session S]
    uv run python tools/reserve_id.py scan [--json] [--strict]      # collisions; writes nothing
    uv run python tools/reserve_id.py seed                          # one-time: ledger from what the files define
    uv run python tools/reserve_id.py sync [--ref origin/main]      # import the committed mirror

**Why a ledger.** Numbers used to be chosen by reading a file that other branches had not merged yet, so two
sessions could both take D-150 or both write "D.2.9 item 14". The ledger hands out each number once.

**Where it lives.** The authority is ``<ids-dir>/ledger.jsonl`` (``$AGENTPROV_IDS_DIR``, else ``$AGENTPROV_HOME/ids``,
else ``~/.agentprov/ids``), appended under an exclusive ``flock`` on ``<ids-dir>/ledger.lock``, so every worktree on
the machine sees a reservation at once. Each reservation is also appended to the committed mirror
``docs/workflow/id-ledger.jsonl`` in the current worktree (``--no-mirror`` skips it; so does a repository whose
``.gitignore`` ignores it, as the public export's does, D-1004). The mirror reaches ``main`` with
the branch, is the audit trail, and lets another machine resume (``sync``). It is the one file with ``merge=union``
(``.gitattributes``): every line is a self-contained JSON object with a unique ``rid``, lines are never edited, and
readers sort, so a union merge cannot corrupt it.

**The next number** of a kind is one more than the largest number that is reserved in the ledger, defined in the
files on any scanned ref, or (for decisions) named in a range in AGENTS.md. A number used without a reservation can
therefore never be handed out again. Gaps are not reused. Decision ranges start at a multiple of ``--align`` (10).

**Scanned refs.** ``origin/main`` and every local branch except ``review/*`` and ``review-base/*`` (read through
``git cat-file``; nothing is checked out), plus the working tree. ``--scan-ref`` (repeatable) replaces the list.

**What ``scan`` reports.**

* ``duplicate``: one file on one ref defines a number twice (two ``D-150`` entries, two regen-batch rows 29, two
  ``14.`` in one spec list), or two section headings in ``docs/architecture/*.md`` on one ref carry the same number
  (two ``### D.6.21``, in one file or two);
* ``collision``: two refs introduce the same number, absent from the base, with different content (``ingest-formats-3``
  and ``d323-stream`` each adding D.2.9 item 14); or a ref (the working tree included) defines, with different content,
  a number the base gained after the ref's merge-base with it (a held branch's ``### D.6.21`` written while another
  branch's D.6.21 landed on main);
* ``jump``: a spec list item that does not follow its predecessor (a gap, or a wrapped line that starts with a number);
* ``unreserved`` (with a ledger): a number defined on a ref but in no reservation. Section headings
  (``spec-section``, reserved with ``--list`` naming the parent: ``--list D.6`` hands out D.6.22) count only with
  ``--require-reserved-sections``; a lettered heading (``D.10.4a``) is never required to have one.

Standard library only; no network (git runs with ``GIT_NO_LAZY_FETCH=1``).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import socket
import subprocess
import sys
import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git_ok, safe_name, safe_text, utc_now  # noqa: E402

KINDS = ("decision", "regen-item", "spec-item", "spec-section", "routing")
DECISIONS = "docs/architecture/DECISIONS.md"
#: DECISIONS.md's generated parts (D-1003): the entries live there once the file is an index
DECISION_PARTS_GLOB = "docs/architecture/decision-log/DECISIONS-*.md"
REGEN_BATCH = "docs/reports/analysis/regen-batch.md"
SPEC = "docs/architecture/D_adapters.md"
AGENTS = "AGENTS.md"
MIRROR = "docs/workflow/id-ledger.jsonl"
ROUTING_GLOBS = ("docs/reports/*/routing.md", "AGENTS.md")
SCANNED = (DECISIONS, REGEN_BATCH, SPEC, AGENTS)
#: Every spec file whose section headings are numbered (``### D.6.21 …``); one number may head one section only.
SECTION_GLOB = "docs/architecture/*.md"
EXCLUDED_REF_PREFIXES = ("review/", "review-base/")
WORKTREE = ":worktree"

_DECISION = re.compile(r"^- \*\*D-(\d+)(?!\d)(.*)$")
_RANGE_TAIL = re.compile(r"\s*(?:\.\.|–|—|-|to\b)\s*D-\d")
_RANGE = re.compile(r"\bD-(\d+)\s*(?:–|—|-|\.\.)\s*D-(\d+)\b")
_ROW = re.compile(r"^\|\s*([^|]*?)\s*\|\s*([^|]*)\|")
_SECTION_ITEMS = re.compile(r"^## Items?\s+([0-9][0-9 ,and–-]*)")
#: A section heading, or a bold paragraph label that opens a numbered subsection (``**D.6.6.1 Call-to-result …**``).
_HEADING = re.compile(r"^(?:#{2,6}\s+§?|\*\*)(D\.\d+(?:\.\d+)*[a-z]?)(?![\w.])")
_LIST_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
#: A numbered section heading in any spec file: the parent (``D.6``), the last number (21), a letter (``D.10.4a``).
_SECTION_HEADING = re.compile(r"^#{1,6}\s+§?([A-Q](?:\.\d+)*)\.(\d+)([a-z]?)(?![\w.])\s*(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


# --------------------------------------------------------------------------------------------------- definitions


@dataclass(frozen=True)
class Definition:
    """One number defined in one file on one ref."""

    kind: str
    scope: str  # "" for decisions and regen items; the list id for spec items; the parent section for spec
    # sections ("D.6", "D.10~a" for a lettered D.10.4a); the prefix for routing ids
    number: int
    ref: str
    path: str
    line: int
    fingerprint: str  # stable part of the definition, to tell an edit of one entry from two different entries

    @property
    def label(self) -> str:
        return label(self.kind, self.scope, self.number)


def label(kind: str, scope: str, number: int) -> str:
    if kind == "decision":
        return f"D-{number}"
    if kind == "regen-item":
        return f"regen-batch item {number}"
    if kind == "spec-item":
        return f"{scope} item {number}"
    if kind == "spec-section":
        parent, _, letter = scope.partition("~")
        return f"section {parent}.{number}{letter}"
    return f"{scope}-{number}"


def span_label(kind: str, scope: str, first: int, last: int) -> str:
    """``D-430–D-439``, ``regen-batch items 29–31``, ``D.2.9 items 14–15``, ``R-10q-1–R-10q-2``; one number alone."""
    if first == last:
        return label(kind, scope, first)
    if kind == "regen-item":
        return f"regen-batch items {first}–{last}"
    if kind == "spec-item":
        return f"{scope} items {first}–{last}"
    if kind == "spec-section":
        return f"sections {scope}.{first}–{scope}.{last}"
    return f"{label(kind, scope, first)}–{label(kind, scope, last)}"


def _norm(text: str, limit: int = 48) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*_]", "", text)).strip().lower()[:limit]


def parse_decisions(text: str, ref: str, path: str = DECISIONS) -> list[Definition]:
    """``- **D-N (date, context…).**`` entries; a top-level ``D-N addendum`` or ``D-N amendment`` is not a second definition, and neither is
    an umbrella bullet announcing a block (``- **D-390..D-399 (…)**``), whose entries follow it."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _DECISION.match(line)
        if not m or m.group(2).lstrip().lower().startswith(("addendum", "amendment")) or _RANGE_TAIL.match(m.group(2)):
            continue
        rest = m.group(2).strip()
        paren = re.match(r"\(([^,:)]*)[,:]?\s*([^,;:)]*)", rest)
        fingerprint = _norm(f"{paren.group(1)} {paren.group(2)}") if paren else _norm(rest, 24)
        out.append(Definition("decision", "", int(m.group(1)), ref, path, lineno, fingerprint))
    return out


def parse_agents_ranges(text: str) -> list[tuple[int, int]]:
    """Every ``D-a–D-b`` range named in AGENTS.md (announced or used; all count as taken)."""
    out = []
    for m in _RANGE.finditer(text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi and hi - lo < 100:
            out.append((lo, hi))
    return out


def parse_regen_batch(text: str, ref: str, path: str = REGEN_BATCH) -> list[Definition]:
    """Numbered rows of the item table (the one headed ``| # | Item |``) and ``## Item N`` / ``## Items N and M``."""
    out = []
    in_table = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\|\s*#\s*\|\s*Item\b", line):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            in_table = False
        row = _ROW.match(line) if in_table else None
        if row and row.group(1).isdigit():
            out.append(Definition("regen-item", "", int(row.group(1)), ref, path, lineno, _norm(row.group(2), 24)))
            continue
        sec = _SECTION_ITEMS.match(line)
        if sec:
            for num in re.findall(r"\d+", sec.group(1)):
                out.append(Definition("regen-item", "section", int(num), ref, path, lineno, ""))
    return out


_LIST_SUFFIXES = "abcdefghijklmnopqrstuvwxyz"


def parse_spec_items(text: str, ref: str, path: str = SPEC) -> tuple[list[Definition], list[dict[str, Any]]]:
    """Column-0 numbered items per section heading, and the jumps found while reading them.

    A list that restarts at 1 under the same heading is that section's next list (``D.9.5b``). A bold label at the
    start of a line (``**D.6.6.1 …**``) opens a section as a heading does. Indented (nested) lists and lines inside
    fenced code blocks are ignored. A numbered line that directly follows paragraph text outside a list and skips
    numbers (``220. Measured here`` after item 10) is that paragraph wrapped: it is reported as a jump but is not an
    item. A list may still go on right after a bold label (``**Behaviour.**`` then ``5.``).
    """
    defs: list[Definition] = []
    jumps: list[dict[str, Any]] = []
    section, list_id, previous, lists = "", "", 0, 0
    fenced = False
    in_list = after_blank = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        head = _HEADING.match(line)
        if head:
            section = list_id = head.group(1)
            previous, lists = 0, 0
            in_list, after_blank = False, True
            continue
        item = _LIST_ITEM.match(line)
        if not item:
            if not line.strip():
                after_blank = True
            elif not line[0].isspace():
                in_list = in_list and not after_blank  # a lazy continuation keeps the list; a new paragraph ends it
                after_blank = False
            continue
        number = int(item.group(1))
        wrapped = not in_list and not after_blank and number > previous + 1
        in_list, after_blank = not wrapped, False
        if not section:
            continue
        if wrapped:
            jumps.append({"list": list_id, "after": previous, "number": number, "ref": ref, "path": path,
                          "line": lineno})
            continue
        if number == 1 and previous:
            lists += 1
            list_id = section + _LIST_SUFFIXES[min(lists, len(_LIST_SUFFIXES) - 1)]
            previous = 0
        if number > previous + 1:
            jumps.append({"list": list_id, "after": previous, "number": number, "ref": ref, "path": path,
                          "line": lineno})
        bold = _BOLD.search(item.group(2))
        fingerprint = _norm(bold.group(1) if bold else item.group(2), 40)
        defs.append(Definition("spec-item", list_id, number, ref, path, lineno, fingerprint))
        previous = max(previous, number)
    return defs, jumps


def parse_spec_sections(text: str, ref: str, path: str) -> list[Definition]:
    """Numbered section headings (``### D.6.21 Title``) outside fenced code blocks; the title is the fingerprint."""
    out: list[Definition] = []
    fenced = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else _SECTION_HEADING.match(line)
        if m:
            scope = m.group(1) + (f"~{m.group(3)}" if m.group(3) else "")
            out.append(Definition("spec-section", scope, int(m.group(2)), ref, path, lineno, _norm(m.group(4))))
    return out


def parse_routing_ids(text: str, ref: str, path: str) -> list[Definition]:
    """Routing ids (``R-10k-1``, ``R-9b-2``, ``RT-3``) as used: their files cite and define alike."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"\b(R[A-Z]?-[0-9]+[a-z]?|R[A-Z]?)-(\d+)\b", line):
            out.append(Definition("routing", m.group(1), int(m.group(2)), ref, path, lineno, ""))
    return out


# --------------------------------------------------------------------------------------------------- reading refs


class Repo:
    """Reads files from refs (``git cat-file``, nothing checked out) or from the working tree."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def refs(self, base: str) -> list[str]:
        heads = git_ok(["for-each-ref", "--format=%(refname:short)", "refs/heads"], self.root) or ""
        out = [base] if git_ok(["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], self.root) else []
        for name in heads.splitlines():
            if name and not name.startswith(EXCLUDED_REF_PREFIXES) and name not in out:
                out.append(name)
        return out

    def read_many(self, ref: str, paths: Iterable[str]) -> dict[str, str]:
        if ref == WORKTREE:
            found = {}
            for rel in paths:
                p = self.root / rel
                if p.is_file():
                    found[rel] = p.read_text(encoding="utf-8", errors="replace")
            return found
        specs = [f"{ref}:{rel}" for rel in paths]
        env = dict(os.environ, GIT_NO_LAZY_FETCH="1")
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=self.root, input=("\n".join(specs) + "\n").encode(),
                              capture_output=True, env=env, check=False, text=False)
        data, pos, found = proc.stdout, 0, {}
        for rel in paths:
            nl = data.index(b"\n", pos)
            header = data[pos:nl].decode("utf-8", "replace").split()
            pos = nl + 1
            if len(header) == 3 and header[1] == "blob":
                size = int(header[2])
                found[rel] = data[pos:pos + size].decode("utf-8", errors="replace")
                pos += size + 1
        return found

    def list_files(self, ref: str, pattern: str) -> list[str]:
        if ref == WORKTREE:
            return sorted(str(p.relative_to(self.root)) for p in self.root.glob(pattern) if p.is_file())
        listing = git_ok(["ls-tree", "-r", "--name-only", ref, "--", "docs/reports", "docs/architecture", "AGENTS.md"],
                         self.root) or ""
        rx = re.compile("^" + re.escape(pattern).replace(r"\*", "[^/]*") + "$")
        return [p for p in listing.splitlines() if rx.match(p)]


@dataclass
class Survey:
    definitions: list[Definition] = field(default_factory=list)
    jumps: list[dict[str, Any]] = field(default_factory=list)
    agents_ranges: list[tuple[int, int, str]] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)


def survey(repo: Repo, refs: list[str]) -> Survey:
    out = Survey(refs=list(refs))
    for ref in refs:
        files = repo.read_many(ref, SCANNED)
        if DECISIONS in files:
            out.definitions += parse_decisions(files[DECISIONS], ref)
        for path, text in repo.read_many(ref, repo.list_files(ref, DECISION_PARTS_GLOB)).items():
            out.definitions += parse_decisions(text, ref, path)
        if REGEN_BATCH in files:
            out.definitions += parse_regen_batch(files[REGEN_BATCH], ref)
        if SPEC in files:
            defs, jumps = parse_spec_items(files[SPEC], ref)
            out.definitions += defs
            out.jumps += jumps
        if AGENTS in files:
            out.agents_ranges += [(lo, hi, ref) for lo, hi in parse_agents_ranges(files[AGENTS])]
        for path, text in repo.read_many(ref, repo.list_files(ref, SECTION_GLOB)).items():
            out.definitions += parse_spec_sections(text, ref, path)
        routing_paths = sorted({p for g in ROUTING_GLOBS for p in repo.list_files(ref, g)})
        for path, text in repo.read_many(ref, routing_paths).items():
            out.definitions += parse_routing_ids(text, ref, path)
    return out


def find_problems(sv: Survey, base: str, inherited: Mapping[str, set[str]] | None = None
                  ) -> dict[str, list[dict[str, Any]]]:
    """Duplicates within one file on one ref, and collisions between refs (see the module docstring).

    ``inherited`` maps a ref to the duplicate labels its merge-base with ``base`` already had; those are left out
    (they were fixed, or are reported, on the base itself).
    """
    inherited = inherited or {}
    duplicates, collisions = [], []
    per_file: dict[tuple[str, str, str, str, int], list[Definition]] = defaultdict(list)
    for d in sv.definitions:
        if d.kind in ("routing",) or d.scope == "section":
            continue
        # a section number heads one section in the whole spec, so its "file" is every spec file
        per_file[(d.ref, SECTION_GLOB if d.kind == "spec-section" else d.path, d.kind, d.scope, d.number)].append(d)
    for (ref, _path, _kind, _scope, _n), defs in sorted(per_file.items()):
        if len(defs) > 1 and defs[0].label not in inherited.get(ref, set()):
            defs = sorted(defs, key=lambda d: (d.path, d.line))
            entry: dict[str, Any] = {"label": defs[0].label, "ref": ref, "path": defs[0].path,
                                     "lines": [d.line for d in defs]}
            if len({d.path for d in defs}) > 1:  # a section number used in two spec files
                entry["path"] = ", ".join(dict.fromkeys(d.path for d in defs))
                entry["where"] = [f"{d.path}:{d.line}" for d in defs]
            duplicates.append(entry)
    on_base = {(d.kind, d.scope, d.number) for d in sv.definitions if d.ref == base}
    by_label: dict[tuple[str, str, int], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for d in sv.definitions:
        if d.kind == "routing" or d.scope == "section" or (d.kind, d.scope, d.number) in on_base:
            continue
        by_label[(d.kind, d.scope, d.number)][d.fingerprint].add(d.ref)
    for (kind, scope, number), prints in sorted(by_label.items()):
        if len(prints) > 1:
            collisions.append({"label": label(kind, scope, number),
                               "variants": [{"fingerprint": fp, "refs": sorted(refs)}
                                            for fp, refs in sorted(prints.items())]})
    return {"duplicates": duplicates, "collisions": collisions, "jumps": sv.jumps}


def merge_base_surveys(repo: Repo, refs: list[str], base: str) -> dict[str, Survey]:
    """For each ref other than ``base`` (the working tree through ``HEAD``), the survey of its merge-base with
    ``base``; refs without one are left out. Surveys are shared between refs with the same merge-base."""
    out: dict[str, Survey] = {}
    cache: dict[str, Survey] = {}
    for ref in refs:
        if ref == base:
            continue
        mb = git_ok(["merge-base", base, "HEAD" if ref == WORKTREE else ref], repo.root)
        if not mb:
            continue
        if mb not in cache:
            cache[mb] = survey(repo, [mb])
        out[ref] = cache[mb]
    return out


def inherited_duplicates(repo: Repo, refs: list[str], base: str,
                         surveys: Mapping[str, Survey] | None = None) -> dict[str, set[str]]:
    """For each ref other than ``base``, the duplicate labels already present at its merge-base with ``base``."""
    surveys = merge_base_surveys(repo, refs, base) if surveys is None else surveys
    out: dict[str, set[str]] = {}
    for ref, sv in surveys.items():
        if ref != WORKTREE:
            mb = sv.refs[0]
            out[ref] = {d["label"] for d in find_problems(sv, mb)["duplicates"]}
    return out


def base_collisions(sv: Survey, base: str, surveys: Mapping[str, Survey]) -> list[dict[str, Any]]:
    """Numbers a ref defines that the base gained after their merge-base, with different content: both sides
    introduced the number on their own (``surveys`` from :func:`merge_base_surveys`)."""
    on_base = {(d.kind, d.scope, d.number): d.fingerprint for d in sv.definitions if d.ref == base}
    out: dict[tuple[str, str, int], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for d in sv.definitions:
        key = (d.kind, d.scope, d.number)
        if d.ref == base or d.ref not in surveys or d.kind == "routing" or d.scope == "section" or key not in on_base:
            continue
        if on_base[key] == d.fingerprint or any((m.kind, m.scope, m.number) == key
                                                for m in surveys[d.ref].definitions):
            continue
        out[key][on_base[key]].add(base)
        out[key][d.fingerprint].add(d.ref)
    return [{"label": label(*key), "variants": [{"fingerprint": fp, "refs": sorted(refs)}
                                                for fp, refs in sorted(prints.items())]}
            for key, prints in sorted(out.items())]


# --------------------------------------------------------------------------------------------------- the ledger


def ids_dir(environ: Mapping[str, str] = os.environ) -> Path:
    explicit = environ.get("AGENTPROV_IDS_DIR")
    return Path(explicit).expanduser() if explicit else agentprov_home(environ) / "ids"


@contextlib.contextmanager
def ledger_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / "ledger.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def read_ledger(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Valid records and the number of lines skipped (a torn or hand-damaged line never stops the tool)."""
    if not path.is_file():
        return [], 0
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(rec, dict) and rec.get("kind") in KINDS and isinstance(rec.get("first"), int) and isinstance(
                rec.get("last"), int) and isinstance(rec.get("rid"), str):
            records.append(rec)
        else:
            bad += 1
    return records, bad


def effective(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reservations in force: void records and the records they void are left out (the ledger is append-only,
    so a reservation is withdrawn by a later ``void`` record, never by editing a line)."""
    voided = {rec["void"] for rec in ledger if isinstance(rec.get("void"), str)}
    return [rec for rec in ledger if "void" not in rec and rec["rid"] not in voided]


def _line(record: Mapping[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"


def append_records(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(_line(r) for r in records).encode("utf-8")
    if not data:
        return
    with path.open("a+b") as fh:
        if fh.seek(0, os.SEEK_END) > 0:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":  # a hand edit or a short write left the last line open: never glue onto it
                data = b"\n" + data
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def taken_numbers(kind: str, scope: str, ledger: list[dict[str, Any]], sv: Survey) -> set[int]:
    taken: set[int] = set()
    for rec in effective(ledger):
        if rec["kind"] == kind and rec.get("scope", "") == scope:
            taken.update(range(rec["first"], rec["last"] + 1))
    for d in sv.definitions:
        if d.kind == kind and (d.scope == scope or (kind == "regen-item" and d.scope == "section")):
            taken.add(d.number)
    if kind == "decision":
        for lo, hi, _ref in sv.agents_ranges:
            taken.update(range(lo, hi + 1))
    return taken


def next_range(taken: set[int], count: int, align: int) -> tuple[int, int]:
    start = max(taken, default=0) + 1
    if align > 1:
        start = -(-start // align) * align
    return start, start + count - 1


def reserve(*, kind: str, scope: str, count: int, align: int, session: str, branch: str, purpose: str,
            ledger_dir: Path, sv: Survey, mirror: Path | None, host: str | None = None) -> dict[str, Any]:
    """Reserve ``count`` numbers under the ledger lock and return the record (also appended to ``mirror``)."""
    if count < 1:
        raise ValueError("--count must be at least 1")
    with ledger_lock(ledger_dir):
        ledger, _bad = read_ledger(ledger_dir / "ledger.jsonl")
        first, last = next_range(taken_numbers(kind, scope, ledger, sv), count, align)
        record = {"rid": str(uuid.uuid4()), "kind": kind, "scope": scope, "first": first, "last": last,
                  "session": session, "branch": branch, "purpose": purpose, "at": utc_now(),
                  "host": host or socket.gethostname(), "source": "reserve"}
        append_records(ledger_dir / "ledger.jsonl", [record])
    if mirror is not None:
        append_records(mirror, [record])
    return record


def _runs(numbers: Iterable[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for n in sorted(set(numbers)):
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def seed_records(ledger: list[dict[str, Any]], sv: Survey, host: str) -> list[dict[str, Any]]:
    """Records covering every number the scanned refs define or AGENTS.md names, that the ledger lacks."""
    have: dict[tuple[str, str], set[int]] = defaultdict(set)
    for rec in effective(ledger):
        have[(rec["kind"], rec.get("scope", ""))].update(range(rec["first"], rec["last"] + 1))
    want: dict[tuple[str, str], set[int]] = defaultdict(set)
    for d in sv.definitions:
        if d.kind == "spec-section":
            continue  # headings were never reserved; the next free one is read from the files
        want[(d.kind, "" if d.scope == "section" else d.scope)].add(d.number)
    for lo, hi, _ref in sv.agents_ranges:
        want[("decision", "")].update(range(lo, hi + 1))
    out = []
    now = utc_now()
    for (kind, scope), numbers in sorted(want.items()):
        for first, last in _runs(numbers - have[(kind, scope)]):
            out.append({"rid": str(uuid.uuid4()), "kind": kind, "scope": scope, "first": first, "last": last,
                        "session": "seed", "branch": "", "purpose": "defined or announced before the ledger",
                        "at": now, "host": host, "source": "seed"})
    return out


def unreserved(ledger: list[dict[str, Any]], sv: Survey, refs: set[str] | None = None,
               base: str | None = None, *, sections: bool = False) -> list[str]:
    """Labels defined but in no reservation in force. With ``refs``, only definitions on those refs; with ``base``,
    only those the base does not define (new on the commit under test). Section headings only with ``sections``
    (only the unlettered ones), and then nothing else."""
    have: dict[tuple[str, str], set[int]] = defaultdict(set)
    for rec in effective(ledger):
        have[(rec["kind"], rec.get("scope", ""))].update(range(rec["first"], rec["last"] + 1))
    on_base = {(d.kind, d.scope, d.number) for d in sv.definitions if base is not None and d.ref == base}
    missing = {(d.kind, d.scope, d.number) for d in sv.definitions
               if d.kind != "routing" and d.scope != "section" and d.number not in have[(d.kind, d.scope)]
               and (d.kind == "spec-section") == sections and "~" not in d.scope
               and (refs is None or d.ref in refs) and (d.kind, d.scope, d.number) not in on_base}
    return [label(k, s, n) for k, s, n in sorted(missing)]


def claim(*, kind: str, scope: str, first: int, count: int, session: str, branch: str, purpose: str,
          ledger_dir: Path, mirror: Path | None, host: str | None = None) -> dict[str, Any] | None:
    """Reserve the explicit range ``first .. first+count-1`` (numbers a branch already wrote, e.g. a spec list it
    defined before reserving). Refused if another session holds any of them; a pre-ledger ``seed`` record does not
    block (it only records numbers that existed). None when this session already holds the whole range."""
    if count < 1 or first < 1:
        raise ValueError("--first and --count must be at least 1")
    wanted = set(range(first, first + count))
    with ledger_lock(ledger_dir):
        ledger, _bad = read_ledger(ledger_dir / "ledger.jsonl")
        mine: set[int] = set()
        for rec in effective(ledger):
            if rec["kind"] != kind or rec.get("scope", "") != scope:
                continue
            held = wanted & set(range(rec["first"], rec["last"] + 1))
            if not held:
                continue
            if rec.get("session") == session:
                mine |= held
            elif rec.get("source") != "seed":
                raise ValueError(f"{span_label(kind, scope, min(held), max(held))} is reserved by "
                                 f"{rec.get('session', '?')} ({rec['rid']}); void that record first if it is wrong")
        if mine >= wanted:
            return None
        record = {"rid": str(uuid.uuid4()), "kind": kind, "scope": scope, "first": first, "last": first + count - 1,
                  "session": session, "branch": branch, "purpose": purpose, "at": utc_now(),
                  "host": host or socket.gethostname(), "source": "claim"}
        append_records(ledger_dir / "ledger.jsonl", [record])
    if mirror is not None:
        append_records(mirror, [record])
    return record


def void(*, rid: str, reason: str, session: str, ledger_dir: Path, mirror: Path | None,
         host: str | None = None) -> dict[str, Any]:
    """Withdraw reservation ``rid`` by appending a void record (to the ledger and the mirror)."""
    if not reason.strip():
        raise ValueError("--reason is required")
    with ledger_lock(ledger_dir):
        ledger, _bad = read_ledger(ledger_dir / "ledger.jsonl")
        target = next((rec for rec in ledger if rec["rid"] == rid), None)
        if target is None:
            raise ValueError(f"no record {rid}")
        if "void" in target:
            raise ValueError(f"{rid} is itself a void record")
        if any(rec.get("void") == rid for rec in ledger):
            raise ValueError(f"{rid} is already void")
        record = {"rid": str(uuid.uuid4()), "kind": target["kind"], "scope": target.get("scope", ""),
                  "first": target["first"], "last": target["last"], "void": rid, "session": session,
                  "branch": "", "purpose": reason, "at": utc_now(), "host": host or socket.gethostname(),
                  "source": "void"}
        append_records(ledger_dir / "ledger.jsonl", [record])
    if mirror is not None:
        append_records(mirror, [record])
    return record


# --------------------------------------------------------------------------------------------------- CLI


def _toplevel(cwd: Path) -> Path:
    top = git_ok(["rev-parse", "--show-toplevel"], cwd)
    if top is None:
        raise SystemExit(f"reserve-id: {cwd} is not inside a git worktree")
    return Path(top)


def _scope(a: argparse.Namespace) -> str:
    if a.kind == "spec-item":
        if not a.list or not re.fullmatch(r"D\.\d+(?:\.\d+)*[a-z]?", a.list):
            raise SystemExit("reserve-id: spec-item needs --list like D.2.9")
        return str(a.list)
    if a.kind == "spec-section":
        if not a.list or not re.fullmatch(r"[A-Q](?:\.\d+)*", a.list):
            raise SystemExit("reserve-id: spec-section needs --list naming the parent section, like D.6")
        return str(a.list)
    if a.kind == "routing":
        if not a.prefix or not re.fullmatch(r"R[A-Z]?(?:-[0-9]+[a-z]?)?", a.prefix):
            raise SystemExit("reserve-id: routing needs --prefix like R-10q")
        return str(a.prefix)
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd(), help="worktree (default: here)")
    p.add_argument("--ids-dir", type=Path, help="ledger directory (default $AGENTPROV_IDS_DIR, else "
                                                "$AGENTPROV_HOME/ids)")
    p.add_argument("--base", default="origin/main", help="base ref (default origin/main)")
    p.add_argument("--scan-ref", dest="scan_refs", action="append", metavar="REF",
                   help="a ref to scan instead of the base and all local branches (repeatable)")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reserve", allow_abbrev=False, help="reserve the next number(s)")
    r.add_argument("kind", choices=KINDS)
    r.add_argument("--count", type=int)
    r.add_argument("--align", type=int, help="decisions start at a multiple of this (default 10; others 1)")
    r.add_argument("--list", help="spec-item: the list, e.g. D.2.9 (a second list in a section: D.9.5b); "
                                  "spec-section: the parent section, e.g. D.6 for D.6.22")
    r.add_argument("--prefix", help="routing: the prefix, e.g. R-10q")
    r.add_argument("--session", help="default $AGENTPROV_SESSION_NAME, else the branch")
    r.add_argument("--purpose", required=True)
    r.add_argument("--no-mirror", action="store_true", help="do not append to docs/workflow/id-ledger.jsonl")
    r.add_argument("--first", type=int, help="claim this explicit first number (with --count; default 1 number) "
                                            "instead of the next free ones; refused if another session holds any")
    v = sub.add_parser("void", allow_abbrev=False, help="withdraw a reservation by its rid (append-only void record)")
    v.add_argument("rid")
    v.add_argument("--reason", required=True)
    v.add_argument("--session", help="default $AGENTPROV_SESSION_NAME, else the branch")
    v.add_argument("--no-mirror", action="store_true")
    ls = sub.add_parser("list", allow_abbrev=False, help="print reservations")
    ls.add_argument("--kind", choices=KINDS)
    ls.add_argument("--session")
    sc = sub.add_parser("scan", allow_abbrev=False, help="report duplicates, collisions, jumps and unreserved numbers")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--strict", action="store_true", help="exit 1 on any duplicate or collision")
    sc.add_argument("--all", action="store_true", help="also report duplicates a branch inherited from its merge-base")
    sc.add_argument("--require-reserved", action="store_true",
                    help="with --strict: also fail on a definition in the working tree that the base lacks and no "
                         "reservation covers (the gate form: --scan-ref origin/main scan --strict --require-reserved)")
    sc.add_argument("--require-reserved-sections", action="store_true",
                    help="with --strict: the same for new unlettered section headings (spec-section)")
    sub.add_parser("seed", allow_abbrev=False, help="add ledger records for everything already defined or announced")
    sy = sub.add_parser("sync", allow_abbrev=False, help="import mirror records from a ref")
    sy.add_argument("--ref", default="origin/main")
    a = p.parse_args(argv)

    root = _toplevel(a.cwd.resolve())
    repo = Repo(root)
    ledger_dir = (a.ids_dir or ids_dir()).expanduser()
    refs = a.scan_refs if a.scan_refs else repo.refs(a.base)

    if a.cmd == "list":
        ledger, bad = read_ledger(ledger_dir / "ledger.jsonl")
        in_force = {rec["rid"] for rec in effective(ledger)}
        for rec in sorted(ledger, key=lambda x: (x["kind"], x.get("scope", ""), x["first"])):
            if (a.kind and rec["kind"] != a.kind) or (a.session and rec.get("session") != a.session):
                continue
            if "void" in rec:
                continue  # shown through the record it withdraws
            span = span_label(rec["kind"], rec.get("scope", ""), rec["first"], rec["last"])
            if rec["rid"] not in in_force:
                span += " [void]"
            print(f"{span:<28} {safe_text(rec.get('session', ''), 30):<30} {safe_text(rec.get('at', ''), 20)}  "
                  f"{safe_text(rec.get('purpose', ''), 80)}")
        if bad:
            print(f"reserve-id: {bad} unreadable ledger line(s) skipped", file=sys.stderr)
        return 0

    if a.cmd == "sync":
        text = git_ok(["show", f"{a.ref}:{MIRROR}"], root)
        if text is None:
            print(f"reserve-id: no {MIRROR} on {a.ref}", file=sys.stderr)
            return 1
        with ledger_lock(ledger_dir):
            ledger, _ = read_ledger(ledger_dir / "ledger.jsonl")
            known = {rec["rid"] for rec in ledger}
            tmp = ledger_dir / f".mirror.{os.getpid()}.jsonl"
            tmp.write_text(text + "\n", encoding="utf-8")
            try:
                incoming, bad = read_ledger(tmp)
            finally:
                tmp.unlink()
            new = [rec for rec in incoming if rec["rid"] not in known]
            append_records(ledger_dir / "ledger.jsonl", new)
        print(f"reserve-id: {len(new)} record(s) imported from {a.ref}" + (f"; {bad} unreadable" if bad else ""))
        return 0

    sv = survey(repo, [*refs, WORKTREE])

    if a.cmd == "scan":
        surveys = merge_base_surveys(repo, [*refs, WORKTREE], a.base)
        problems = find_problems(sv, a.base, None if a.all else inherited_duplicates(repo, refs, a.base, surveys))
        problems["collisions"] += base_collisions(sv, a.base, surveys)
        ledger, _ = read_ledger(ledger_dir / "ledger.jsonl")
        problems["unreserved"] = [{"label": x} for x in unreserved(ledger, sv)] if ledger else []
        problems["unreserved_new"] = ([{"label": x} for x in unreserved(ledger, sv, {WORKTREE}, a.base)]
                                      if ledger else [])
        problems["unreserved_new_sections"] = ([{"label": x} for x in unreserved(ledger, sv, {WORKTREE}, a.base,
                                                                                 sections=True)] if ledger else [])
        if a.json:
            print(json.dumps({"refs": refs, **problems}, indent=2, sort_keys=True, ensure_ascii=True))
        else:
            for d in problems["duplicates"]:
                where = (", ".join(d["where"]) if "where" in d
                         else f"{d['path']} lines {', '.join(map(str, d['lines']))}")
                print(f"duplicate  {d['label']}: {safe_text(d['ref'])}:{where}")
            for c in problems["collisions"]:
                variants = "; ".join(f"{safe_text(v['fingerprint'], 50)!r} on {', '.join(map(safe_text, v['refs']))}"
                                     for v in c["variants"])
                print(f"collision  {c['label']}: {variants}")
            for j in problems["jumps"]:
                if j["ref"] in (a.base, WORKTREE):
                    print(f"jump       {j['list']}: {j['after']} -> {j['number']} at {safe_text(j['ref'])}:"
                          f"{j['path']}:{j['line']}")
            if ledger:
                print(f"unreserved {len(problems['unreserved'])} label(s)")
                for u in problems["unreserved_new"] + (problems["unreserved_new_sections"]
                                                       if a.require_reserved_sections else []):
                    print(f"unreserved-new {u['label']} (defined here, not on {a.base}, in no reservation)")
            print(f"scanned {len(refs)} ref(s) and the working tree")
        failing = problems["duplicates"] or problems["collisions"] or (
            a.require_reserved and problems["unreserved_new"]) or (
            a.require_reserved_sections and problems["unreserved_new_sections"])
        return 1 if a.strict and failing else 0

    if a.cmd == "seed":
        with ledger_lock(ledger_dir):
            ledger, _ = read_ledger(ledger_dir / "ledger.jsonl")
            records = seed_records(ledger, sv, socket.gethostname())
            append_records(ledger_dir / "ledger.jsonl", records)
        print(f"reserve-id: seeded {len(records)} record(s) into {ledger_dir / 'ledger.jsonl'}")
        return 0

    branch = git_ok(["symbolic-ref", "--quiet", "--short", "HEAD"], root) or "(detached)"
    session = safe_name(a.session or os.environ.get("AGENTPROV_SESSION_NAME") or branch)
    if a.cmd == "void":
        try:
            rec = void(rid=a.rid, reason=a.reason, session=session, ledger_dir=ledger_dir,
                       mirror=mirror_path(root, a.no_mirror))
        except ValueError as exc:
            print(f"reserve-id: {exc}", file=sys.stderr)
            return 2
        print(f"void {span_label(rec['kind'], rec['scope'], rec['first'], rec['last'])} ({a.rid})")
        return 0

    # reserve
    scope = _scope(a)
    if a.first is not None:
        try:
            claimed = claim(kind=a.kind, scope=scope, first=a.first, count=a.count or 1, session=session,
                            branch=branch, purpose=a.purpose, ledger_dir=ledger_dir,
                            mirror=mirror_path(root, a.no_mirror))
        except ValueError as exc:
            print(f"reserve-id: {exc}", file=sys.stderr)
            return 2
        last = a.first + (a.count or 1) - 1
        print(span_label(a.kind, scope, a.first, last) + (" (already yours)" if claimed is None else ""))
        return 0
    count = a.count if a.count is not None else (10 if a.kind == "decision" else 1)
    align = a.align if a.align is not None else (10 if a.kind == "decision" else 1)
    record = reserve(kind=a.kind, scope=scope, count=count, align=align, session=session, branch=branch,
                     purpose=a.purpose, ledger_dir=ledger_dir, sv=sv,
                     mirror=mirror_path(root, a.no_mirror))
    print(span_label(a.kind, scope, record["first"], record["last"]))
    return 0


def mirror_path(root: Path, no_mirror: bool) -> Path | None:
    """The committed mirror, or None with ``--no-mirror`` or where ``.gitignore`` ignores it (the public export, which
    leaves out ``docs/workflow/``; D-1004)."""
    if no_mirror:
        return None
    ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", MIRROR], cwd=root, capture_output=True)
    if ignored.returncode == 0:
        print(f"reserve-id: {MIRROR} is ignored here; the reservation is in the machine ledger only", file=sys.stderr)
        return None
    return root / MIRROR


if __name__ == "__main__":
    raise SystemExit(main())
