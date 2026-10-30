"""The corpus listing of the user guide, generated from the source registry, the source profiles and committed reports.

Usage::

    uv run python tools/gen_readme_corpora.py --check     # test: exit 1 if the guide's listing differs from the data
    uv run python tools/gen_readme_corpora.py --write     # rewrite the block between the markers in the guide page

The listing lives in ``docs/user-guide/14-corpora.md`` (it was in README.md until 2026-10-22; README.md now links to the
page). The block between ``BEGIN`` and ``END`` there is generated; everything else in the page is hand-written. A branch
that adds a source, part, pin or count runs ``--write``, and a conflict in the block is resolved by running ``--write``,
never by hand. Links to repository files are absolute GitHub URLs (``REPO_URL``), so they work both on GitHub and on the
guide's website, where only ``docs/user-guide/`` is published.

Inputs, all in the repository (the listing never reads a corpus, ``AGENTPROV_HOME`` or the network, so it is the same on
every machine):

- the registry (``agentprov.adapters.registry``): sources, parts, corpus ids, the sealed corpora (``Capability.sealed``,
  display only: a sealed part is listed under its sealed corpus id), statuses, licences;
- each part's source profile (``agentprov.adapters.profiles``): the pins, per-pin licence overrides, ``[withhold]`` and
  ``select.redaction_pending`` excludes, and the ``[source]`` project URL and paper (arXiv ids, DOIs and GitHub
  repositories in the paper text become links; nothing is looked up);
- ``[paper.<source>]`` in the same TOML: papers found by a web search after the source was verified, each with its
  relation to the source and how it was matched (shown as found by web search);
- ``tools/readme_corpora.toml``: one entry per registry part with its execution count and the committed report that
  records it, plus short curated notes. Every count is checked against its evidence file (the JSON pointer's value, or
  the number written in a text file), so a number in the listing always has a committed source;
- ``docs/reports/systematic-search/records-merged.jsonl``: the screening totals.

Standard library plus ``agentprov.adapters``; reads no corpus; no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import REGISTRY

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "docs" / "user-guide" / "14-corpora.md"
REPO_URL = "https://github.com/nickjones39/AgentPROV/blob/main/"
DATA = REPO / "tools" / "readme_corpora.toml"
SEARCH = REPO / "docs" / "reports" / "systematic-search" / "records-merged.jsonl"
BEGIN = "<!-- BEGIN generated: corpora (tools/gen_readme_corpora.py --write) -->"
END = "<!-- END generated: corpora -->"
BASES = ("sealed", "full import", "census", "trial import", "mapped in memory", "spec")
UNITS = ("executions", "logs", "samples", "runs", "trajectories", "traces", "streams", "files")
_COPYLEFT = re.compile(r"^(A|L)?GPL-")
_ENTRY_KEYS = frozenset({"source", "part", "count", "unit", "basis", "evidence", "pointer", "where", "notes"})


class DataError(Exception):
    """``tools/readme_corpora.toml`` disagrees with the registry or with its evidence files."""


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _short(sha: str) -> str:
    return sha[:8]


def _pointer(doc: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise DataError(f"JSON pointer {pointer!r} must start with '/'")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(doc, list):
            doc = doc[int(token)]
        elif isinstance(doc, Mapping):
            doc = doc[token]
        else:
            raise KeyError(token)
    return doc


def load_data() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str]]:
    """The curated entries keyed by ``(source, part)`` and the ``[use]`` labels keyed by ``"<source> <part>"`` (part
    ``*`` for every part of the source); :class:`DataError` on any defect."""
    doc = tomllib.loads(DATA.read_text(encoding="utf-8"))
    unknown = sorted(set(doc) - {"part", "use", "paper"})
    if unknown:
        raise DataError(f"{DATA.name}: unknown top-level key(s) {unknown}")
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in doc.get("part", []):
        extra = sorted(set(entry) - _ENTRY_KEYS)
        if extra:
            raise DataError(f"{DATA.name}: unknown key(s) {extra} in {entry.get('source')} · {entry.get('part')}")
        key = (entry["source"], entry["part"])
        if key in entries:
            raise DataError(f"{DATA.name}: {key[0]} · {key[1]} is listed twice")
        entries[key] = entry
    use: dict[str, str] = {}
    for source_id, label in doc.get("use", {}).items():
        if isinstance(label, str):
            label = {"text": label}
        text, parts = label.get("text"), label.get("parts")
        if not isinstance(text, str) or not text or set(label) - {"text", "parts"}:
            raise DataError(f"{DATA.name}: [use] {source_id} is a label or a table {{text, parts}}")
        for part in parts if parts is not None else ["*"]:
            use[f"{source_id} {part}"] = text
    return entries, use


def check_entry(entry: Mapping[str, Any]) -> None:
    """A count names a basis, a unit and a committed evidence file that records exactly that number."""
    label = f"{entry['source']} · {entry['part']}"
    if "count" not in entry:
        if not entry.get("where"):
            raise DataError(f"{label}: an entry without a count says where the number can be found (where = ...)")
        return
    count = entry["count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise DataError(f"{label}: count must be a non-negative integer")
    if entry.get("basis") not in BASES:
        raise DataError(f"{label}: basis must be one of {BASES}")
    if entry.get("unit") not in UNITS:
        raise DataError(f"{label}: unit must be one of {UNITS}")
    rel = entry.get("evidence", "")
    path = (REPO / rel).resolve()
    if not rel or REPO not in path.parents or not path.is_file():
        raise DataError(f"{label}: evidence {rel!r} is not a committed file in the repository")
    if "pointer" in entry:
        try:
            value = _pointer(json.loads(path.read_text(encoding="utf-8")), entry["pointer"])
        except (KeyError, IndexError, ValueError) as exc:
            raise DataError(f"{label}: {rel} has no value at {entry['pointer']!r}") from exc
        if value != count:
            raise DataError(f"{label}: {rel}{entry['pointer']} is {value!r}, the listing says {count}")
        return
    text = path.read_text(encoding="utf-8")
    if not re.search(rf"(?<![\d,.]){count:,}(?![\d]|,\d)|(?<![\d,.]){count}(?![\d]|,\d)", text):
        raise DataError(f"{label}: {rel} does not state {count:,} (add a JSON pointer or cite the file that does)")


def _repo_label(url: str) -> str:
    for prefix, name in (("https://github.com/", "GitHub"), ("https://huggingface.co/datasets/", "HF"),
                         ("https://gitlab.com/", "GitLab"), ("https://codeberg.org/", "Codeberg")):
        if url.startswith(prefix):
            return f"{name} [`{url[len(prefix):]}`]({url})"
    return f"[`{url}`]({url})"


def _zenodo_record(pin: Mapping[str, Any]) -> str:
    if pin.get("record"):
        return str(pin["record"])
    return str(pin.get("doi", "")).rsplit("zenodo.", 1)[-1]


def _pin_group_key(pin: Mapping[str, Any], canonical: str) -> tuple[str, ...]:
    kind = pin.get("kind", "")
    if kind == "git":
        return (kind, pin.get("repo") or canonical, pin.get("commit", ""))
    if kind == "zenodo":
        return (kind, _zenodo_record(pin), str(pin.get("version", "")), str(pin.get("doi", "")))
    if kind == "hf":
        return (kind, pin.get("dataset", ""), pin.get("revision", ""))
    return (kind,)


def _files(pins: list[Mapping[str, Any]]) -> str:
    names = [p["file"] for p in pins if p.get("file")]
    if not names:
        trees = sorted({p["tree"] for p in pins if p.get("tree")})
        return f" `{trees[0]}`" if len(trees) == 1 else ""
    if len(names) == 1:
        split = pins[0].get("parts")
        return f": `{names[0]}`" + (f" ({len(split)} parts)" if split else "")
    return f" ({len(names)} files)"


def _pin_text(key: tuple[str, ...], pins: list[Mapping[str, Any]]) -> str:
    kind = key[0]
    if kind == "git":
        return f"{_repo_label(key[1])} @ `{_short(key[2])}`{_files(pins)}"
    if kind == "zenodo":
        record, version, doi = key[1], key[2], key[3] or f"10.5281/zenodo.{key[1]}"
        return f"Zenodo [{record}](https://doi.org/{doi})" + (f" {version}" if version else "") + _files(pins)
    if kind == "hf":
        url = f"https://huggingface.co/datasets/{key[1]}"
        return f"HF [`{key[1]}`]({url}) @ `{_short(key[2])}`{_files(pins)}"
    return kind or "unknown pin kind"


def pins_of(profile: Any, part: str) -> tuple[str, int]:
    """The part's primary pins as text, and how many further pins (context, LFS objects, alternatives) it has."""
    source = profile.data["source"]
    canonical = source.get("canonical_repo", "")
    own = [p for p in source.get("pins", ()) if p.get("part") == part]
    shared = ""
    if not own and part in profile.parts:
        primary = [p for p in source.get("pins", ()) if p.get("primary")]
        if len({p.get("part") for p in primary}) == 1 and primary[0].get("part"):
            own, shared = primary, f" (the pin of part `{primary[0]['part']}`)"
    if not own:
        return "", 0
    main = [p for p in own if p.get("primary")] or own
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    for pin in main:
        groups.setdefault(_pin_group_key(pin, canonical), []).append(pin)
    text = "; ".join(_pin_text(k, v) for k, v in groups.items()) + shared
    return text, len(own) - len(main) if not shared else 0


def _licence(src: Any, profile: Any, part: str, use: Mapping[str, str]) -> tuple[str, list[str]]:
    lic = src.licence
    spdx, policy = lic.spdx or lic.licence_ref or "unassessed", lic.policy
    if profile is not None:
        roles = {p.get("role") for p in profile.data["source"].get("pins", ()) if p.get("part") == part}
        for override in profile.data["licence"].get("overrides", ()):
            if override.get("role") in roles:
                spdx, policy = override.get("spdx", spdx), override.get("policy", policy)
    notes: list[str] = []
    if _COPYLEFT.match(spdx):
        notes.append("copyleft: its own corpus (D-94)")
    elif lic.restrictions:
        if not any(key.startswith(f"{src.source_id} ") for key in use):
            raise DataError(f"{src.source_id}: the licence carries a use restriction; give it a [use] label")
        text = use.get(f"{src.source_id} {part}") or use.get(f"{src.source_id} *")
        if text:
            notes.append(f"restricted use: {text}")
    if policy == "reference":
        notes.append("licence policy `reference`: registered and censused, never released")
    elif policy == "nc_partition":
        notes.append("non-commercial: kept apart from permissive data")
    elif policy == "forbidden":
        notes.append("licence forbids redistribution: not imported")
    return f"{spdx}", notes


def _profile_notes(profile: Any) -> list[str]:
    notes = []
    withhold = profile.data.get("withhold")
    if withhold:
        what = withhold.get("public_note") or withhold.get("reason") or "see the profile"
        notes.append(f"a release seal withholds `[withhold]` matches: {what}")
    excludes = profile.data.get("import", {}).get("exclude", ())
    if any(e.get("code") == "select.redaction_pending" for e in excludes):
        notes.append("logs with account paths held back (`select.redaction_pending`) until the D-182 redaction")
    return notes


def _status(cap: Any) -> str:
    if cap.role != "source":
        return cap.role.replace("_", " ") + (f" ({cap.owner})" if cap.owner else "")
    parts = []
    if cap.import_status:
        parts.append(f"import {cap.import_status}")
    if cap.live_status:
        parts.append(f"live {cap.live_status}")
    parts += [f"sealed `{s.tag}`" for s in cap.sealed]
    return ", ".join(parts) if parts else "no status (toy format)"


def _format(profile: Any, cap: Any) -> str:
    """The part's dialects and variants as the registry declares them; the profile's ``[import]`` only as a fallback."""
    imp = profile.data.get("import", {}) if profile is not None else {}
    dialects = list(cap.dialects) or ([imp["dialect"]] if imp.get("dialect") else [])
    variants = list(cap.variants) if cap.dialects else list(imp.get("variants", ()))
    if not dialects:
        return "—"
    return ", ".join(f"`{d}`" for d in dialects) + (f" ({', '.join(f'`{v}`' for v in variants)})" if variants else "")


def _count(entry: Mapping[str, Any]) -> str:
    if "count" not in entry:
        return f"not in the repository: {entry['where']}"
    unit = "" if entry["unit"] == "executions" else f" {entry['unit']}"
    return f"[{entry['count']:,}]({REPO_URL}{entry['evidence']}){unit} ({entry['basis']})"


_ARXIV = re.compile(r"arXiv:(\d{4}\.\d{4,5})")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s;,()]+[^\s;,().])")
_GITHUB = re.compile(r"\bgithub\.com/[\w.-]+/[\w-]+(?:\.[\w-]+)*")
#: ``[source] paper`` texts that record a search, a draft or a non-paper; shown as "none recorded".
_NO_PAPER = ("none", "the ", "an ", "paper/", "manuscript/", "AgentDojo-PROV")


def paper_cell(text: str) -> str:
    """Links for the identifiers a profile's ``paper`` text names (arXiv, DOI, GitHub); a bare title as plain text."""
    links = [f"[arXiv:{a}](https://arxiv.org/abs/{a})" for a in dict.fromkeys(_ARXIV.findall(text))]
    links += [f"[doi:{d}](https://doi.org/{d})" for d in dict.fromkeys(_DOI.findall(text))]
    links += [f"[{g}](https://{g})" for g in dict.fromkeys(_GITHUB.findall(text))]
    title = text.split(" (", 1)[0].strip()
    if not text or text.startswith(_NO_PAPER):
        return ", ".join(links) or "none recorded"
    if re.fullmatch(r"arXiv:\S+", title):
        return ", ".join(links)
    return f"{_cell(title)}" + (f" ({', '.join(links)})" if links else " (no identifier recorded)")


def _project(url: str) -> str:
    if url.startswith("https://doi.org/"):
        return f"Zenodo [{url.rsplit('zenodo.', 1)[-1]}]({url})" if "zenodo." in url else f"[{url}]({url})"
    return _repo_label(url) if url else "—"


_PAPER_KEYS = frozenset({"arxiv", "title", "relation", "found"})
_RELATIONS = {"describes": "", "preprint": "preprint under an earlier title: ", "builds_on": "builds on "}


def load_papers() -> dict[str, dict[str, str]]:
    """``[paper.<source>]``: papers found after the source was verified (title, arXiv id, relation, how it was found)."""
    papers = tomllib.loads(DATA.read_text(encoding="utf-8")).get("paper", {})
    known = {s.source_id for s in REGISTRY}
    for source_id, paper in papers.items():
        if source_id not in known:
            raise DataError(f"{DATA.name}: [paper.{source_id}] names no registry source")
        if set(paper) != _PAPER_KEYS or paper["relation"] not in _RELATIONS:
            raise DataError(f"{DATA.name}: [paper.{source_id}] needs exactly {sorted(_PAPER_KEYS)}; relation one of "
                            f"{sorted(_RELATIONS)}")
        if not re.fullmatch(r"\d{4}\.\d{4,5}", paper["arxiv"]) or not paper["title"] or not paper["found"]:
            raise DataError(f"{DATA.name}: [paper.{source_id}] has a malformed arxiv id or an empty title or found")
    return papers


def found_paper_cell(paper: Mapping[str, str]) -> str:
    link = f"[arXiv:{paper['arxiv']}](https://arxiv.org/abs/{paper['arxiv']})"
    return f"{_RELATIONS[paper['relation']]}{_cell(paper['title'])} ({link}; found by web search)"


def _sources_table() -> list[str]:
    papers = load_papers()
    rows = []
    for src in REGISTRY:
        ids = [c.profile for c in src.capabilities if c.profile]
        if not ids:
            continue
        data = load_profile(ids[0]).data["source"]
        paper = paper_cell(str(data.get("paper", "")))
        if src.source_id in papers:
            found = found_paper_cell(papers[src.source_id])
            relation = papers[src.source_id]["relation"]
            if paper == "none recorded" or (relation == "describes" and "no identifier recorded" in paper):
                paper = found
            else:
                paper = f"{paper.removesuffix(' (no identifier recorded)')}; {found}"
        rows.append(f"| `{src.source_id}` | {_cell(src.name)} | {_project(data.get('canonical_repo', ''))} | {paper} |")
    return ["| Source | Name | Project | Paper |", "|---|---|---|---|", *rows]


def _search_summary() -> str:
    rows = [json.loads(line) for line in SEARCH.read_text(encoding="utf-8").splitlines() if line.strip()]
    decisions = Counter(r["decision"] for r in rows)
    codes = Counter(r["exclusion_code"] for r in rows if r["decision"] == "excluded")
    licence = codes["EX-LIC-1"] + codes["EX-LIC-2"]
    return (f"The systematic search lists {len(rows):,} distinct sources: {decisions['included']:,} included and "
            f"{decisions['excluded']:,} excluded, {licence:,} of them only for their licence (no licence: "
            f"{codes['EX-LIC-1']:,}; redistribution forbidden: {codes['EX-LIC-2']:,}). Counts from "
            f"[`records-merged.jsonl`]({REPO_URL}docs/reports/systematic-search/records-merged.jsonl).")


def render() -> str:
    entries, use = load_data()
    wanted = {(s.source_id, c.part) for s in REGISTRY for c in s.capabilities}
    missing = sorted(wanted - set(entries))
    stale = sorted(set(entries) - wanted)
    if missing or stale:
        raise DataError(f"{DATA.name}: missing registry parts {missing}; parts not in the registry {stale}")
    for entry in entries.values():
        check_entry(entry)

    corpora: dict[str, list[str]] = {}
    other: list[str] = []
    sealed: dict[str, int] = {}  # sealed corpus id -> released executions
    versions: set[str] = set()
    for src in REGISTRY:
        for cap in src.capabilities:
            entry = entries[(src.source_id, cap.part)]
            profile = load_profile(cap.profile) if cap.profile else None
            pins, more = pins_of(profile, cap.part) if profile is not None else ("", 0)
            pin_cell = (pins or "no pin of its own") + (f" (+{more} more pin{'s' if more > 1 else ''})" if more else "")
            licence, notes = _licence(src, profile, cap.part, use)
            notes = notes + (_profile_notes(profile) if profile is not None else []) + list(entry.get("notes", ()))
            name = f"`{src.source_id}` · `{cap.part}`"
            corpus_id = cap.sealed[0].corpus_id if cap.sealed else cap.corpus_id
            if corpus_id and cap.role == "source":
                if cap.sealed and cap.via is None:  # a part served by another source counts under that source's corpus
                    sealed.setdefault(corpus_id, 0)
                    versions.update(s.version for s in cap.sealed)
                    if entry.get("basis") == "sealed":
                        sealed[corpus_id] += entry["count"]
                corpora.setdefault(corpus_id, []).append(
                    f"| `{corpus_id}` | {name} | {_format(profile, cap)} | {_cell(pin_cell)} | {_cell(licence)} | "
                    f"{_cell(_count(entry))} | {_cell(_status(cap))} | {_cell('; '.join(notes)) or '—'} |"
                )
            else:
                count = _count(entry) if "count" in entry or entry.get("where") else "—"
                other.append(f"| {name} | {_cell(_status(cap))} | {_cell(pin_cell)} | {_cell(count)} | "
                             f"{_cell('; '.join(notes)) or '—'} |")

    n_parts = sum(len(rows) for rows in corpora.values())
    rest = len(corpora) - len(sealed)
    version = f"version {next(iter(versions))}" if len(versions) == 1 else "their own versions"
    out = [
        BEGIN, "",
        f"{len(corpora)} corpora are declared, built from {n_parts} source parts. {len(sealed)} are sealed ({version}) and "
        f"hold {sum(sealed.values()):,} released executions"
        + (f"; {rest} {'is' if rest == 1 else 'are'} not yet imported in full. " if rest else ". ")
        + _search_summary(), "",
        "| Corpus | Source · part | Format (dialect, variants) | Pinned origin | Licence | Executions | Status | Caveats |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for corpus_id in corpora:
        out += corpora[corpus_id]
    out += [
        "", "Where each source is published, and the paper that describes it (from the profiles' `[source]` table; "
        "\"none recorded\" means none was found when the source was verified):", "",
        *_sources_table(),
        "", "<details>", f"<summary>{len(other)} registered parts that are not a corpus of their own</summary>", "",
        "| Source · part | Role or status | Pinned origin | Executions | Caveats |", "|---|---|---|---|---|",
        *other, "", "</details>", "", END,
    ]
    return "\n".join(out)


def splice(text: str, block: str) -> str:
    try:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
    except ValueError:
        raise SystemExit(f"{TARGET.name}: the generated-block markers are missing") from None
    return head + block + tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    try:
        block = render()
    except DataError as exc:
        print(f"{DATA.name}: {exc}", file=sys.stderr)
        return 1
    current = TARGET.read_text(encoding="utf-8")
    wanted = splice(current, block)
    if args.write:
        if wanted != current:
            TARGET.write_text(wanted, encoding="utf-8")
        return 0
    if wanted != current:
        print(f"{TARGET.relative_to(REPO)}: the corpus listing differs from the data; run tools/gen_readme_corpora.py --write",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
