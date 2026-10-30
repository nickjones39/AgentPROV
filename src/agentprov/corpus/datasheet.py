"""``DATASHEET.md``: the generated datasheet of a sealed corpus (HL H.9; G.8.5; MN N.2.11 step 1).

``render`` turns the manifest, the corpus card (``rules/CARD.md``) and the decided statements into Markdown. **Every
number comes from the manifest** (or a statement figure with its cited source, below); the prose comes only from the card
and the statements table (H.9(1)-(2)). Placeholders (H.9(3)):

* ``{{v:<JSON Pointer into corpus.json>}}`` inserts a value (a string or an integer);
* ``{{t:<table id>}}`` inserts a generated table (:data:`TABLES`);
* ``{{claim:<id>}}`` inserts the sentence of a registered claim, which is evaluated over the manifest: a claim that does
  not hold fails the build (H.9(4)); the results go to ``corpus.json.datasheet.claims``;
* ``{{f:<name>}}`` (statements only) inserts a figure of the statement, which names its source.

**The claims library is injected** (``checker``; M.5.2(1)): it is ``agentprov.adapters.registry.claims.CHECKER``, an L6
module this L5 module never imports. It lints the card (``validate --card``: digits outside placeholders, the claim and
text rules), evaluates the claims and lints the rendered datasheet (the G.8.5 section). The field-group/information-loss
table of ``agentprov stats`` (R-57) is injected the same way (``field_groups``), so the datasheet and ``stats`` share one
computation (M.5.2(1)); without it the section says that the table is produced by ``agentprov stats``.

**Decided statements** (``docs/reports/analysis/datasheet-items.md``). The statements the user decided for the datasheet
(C4; D-27 c1, c2, c5; the source-artefact disclosures; the DTap-Bench rows) live in one committed, data-only table,
``corpora/datasheet-statements.toml`` (:func:`load_statements`). Each statement names the corpora it applies to
(``corpora = ["rope", …]`` or ``["*"]``), its section, its decision and source, and its text; any number in the text is a
**figure** ``{{f:<name>}}`` declared with its value and the analysis that measured it (a figure is not recomputed by this
build: it is rendered with its source). Adding a row for a new corpus is a data change only (no code change here); the
statements' text passes the same lint as a card. ``render`` emits exactly the statements whose ``corpora`` name the
sealing corpus, and the manifest records their ids and the table digest.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from agentprov.errors import AgentProvError
from agentprov.ingest.quote import escape_markdown, escape_untrusted_line
from agentprov.io.canonical import sha256_hex

__all__ = [
    "SECTIONS",
    "TABLES",
    "CardChecker",
    "DatasheetError",
    "Rendered",
    "Statement",
    "StatementTable",
    "card_mode",
    "load_statements",
    "render",
]

#: The datasheet sections in order: the baseline's seven (H.9(6)) and the three generated ones.
SECTIONS: Final = (
    ("motivation", "Motivation"),
    ("composition", "Composition"),
    ("collection", "Collection process"),
    ("preprocessing", "Preprocessing and labelling"),
    ("uses", "Uses"),
    ("evidence", "Evidence and information loss"),
    ("integrity", "Integrity and verification"),
    ("known_issues", "Known issues and validity caveats"),
    ("distribution", "Distribution and licensing"),
    ("maintenance", "Maintenance"),
)
_SECTION_IDS: Final = frozenset(s for s, _ in SECTIONS)
_PLACEHOLDER: Final = re.compile(r"\{\{(v|t|claim|f):([^{}]*)\}\}")
_FRONT: Final = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
#: The fixed start of the one line on which the renderer quotes third-party text verbatim (a source's required attribution,
#: D-910); the claims lint skips the AR-12 and NC-ALL-03 word rules on a line that starts with it
#: (``adapters/registry/claims.py`` holds the same string). No HTML comment: K.12.6(e) keeps ``<!--`` out of a datasheet.
ATTRIBUTION_PREFIX: Final = "- Required attribution (verbatim): "
_STATEMENT_ID: Final = re.compile(r"[a-z0-9][a-z0-9-]*")
_FIGURE_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")


class DatasheetError(AgentProvError):
    """The datasheet cannot be rendered: a mode mismatch or a card that fails the lint (exit 4, a refused precondition),
    a claim that does not hold or a broken placeholder (exit 1)."""

    code = "corpus.datasheet.invalid"
    exit_code = 1


class CardChecker(Protocol):
    """What the renderer needs from the claims library (``agentprov.adapters.registry.claims.CHECKER``)."""

    def lint_card(self, text: str, *, source_ids: Sequence[str] = ()) -> list[tuple[str, str, str]]: ...

    def evaluate_claims(self, ids: Sequence[str], manifest: Mapping[str, Any], *, source_ids: Sequence[str] = ()) -> tuple[
        list[dict[str, Any]], list[tuple[str, str, str]]]: ...

    def claim_text(self, claim_id: str) -> str: ...

    def lint_datasheet(self, text: str) -> list[tuple[str, str, str]]: ...


# ------------------------------------------------------------------------------------------------ statements
@dataclass(frozen=True)
class Statement:
    """One decided datasheet statement (see the module docstring)."""

    id: str
    item: str
    corpora: tuple[str, ...]
    section: str
    decided: str
    source: str
    text: str
    figures: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def applies_to(self, corpus_id: str) -> bool:
        return "*" in self.corpora or corpus_id in self.corpora


@dataclass(frozen=True)
class StatementTable:
    statements: tuple[Statement, ...]
    sha256: str  # hex digest of the table bytes

    def for_corpus(self, corpus_id: str) -> list[Statement]:
        return [s for s in self.statements if s.applies_to(corpus_id)]


def load_statements(data: bytes, *, source: str = "datasheet-statements.toml") -> StatementTable:
    """Parse the statements table strictly (closed keys; every figure placeholder declared, every declared figure used
    and sourced; unique ids; known sections)."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise DatasheetError(f"{source}: not valid UTF-8 TOML", code="corpus.datasheet.statements") from None
    if set(doc) - {"table", "statement"} or not isinstance(doc.get("table"), dict) or doc["table"].get("version") != 1:
        raise DatasheetError(f"{source}: a [table] version = 1 and [[statement]] entries", code="corpus.datasheet.statements")
    out: list[Statement] = []
    for i, entry in enumerate(doc.get("statement", [])):
        where = f"{source}: statement #{i}"
        keys = {"id", "item", "corpora", "section", "decided", "source", "text"}
        if not isinstance(entry, dict) or not keys <= set(entry) or set(entry) - keys - {"figures"}:
            raise DatasheetError(f"{where}: keys {sorted(keys)} and optional figures", code="corpus.datasheet.statements")
        if not isinstance(entry["id"], str) or _STATEMENT_ID.fullmatch(entry["id"]) is None:
            raise DatasheetError(f"{where}: malformed id", code="corpus.datasheet.statements")
        if entry["section"] not in _SECTION_IDS:
            raise DatasheetError(f"{where}: unknown section", code="corpus.datasheet.statements")
        corpora = entry["corpora"]
        if not isinstance(corpora, list) or not corpora or not all(isinstance(c, str) and c for c in corpora):
            raise DatasheetError(f"{where}: corpora is a non-empty array of corpus ids or [\"*\"]", code="corpus.datasheet.statements")
        figures = entry.get("figures", {})
        if not isinstance(figures, dict):
            raise DatasheetError(f"{where}: figures is a table", code="corpus.datasheet.statements")
        for name, figure in figures.items():
            if (_FIGURE_NAME.fullmatch(name) is None or not isinstance(figure, dict) or set(figure) != {"value", "source"}
                    or not all(isinstance(v, str) and v for v in figure.values())):
                raise DatasheetError(f"{where}: figure {name!r} is {{value, source}}", code="corpus.datasheet.statements")
        text = entry["text"]
        if not all(isinstance(entry[k], str) and entry[k] for k in ("item", "decided", "source", "text")):
            raise DatasheetError(f"{where}: item, decided, source and text are non-empty strings", code="corpus.datasheet.statements")
        used = {m.group(2) for m in _PLACEHOLDER.finditer(text) if m.group(1) == "f"}
        if used != set(figures):
            raise DatasheetError(f"{where}: the figure placeholders and the declared figures differ",
                                 code="corpus.datasheet.statements")
        out.append(Statement(entry["id"], entry["item"], tuple(corpora), entry["section"], entry["decided"], entry["source"],
                             text, {k: dict(v) for k, v in figures.items()}))
    ids = [s.id for s in out]
    if len(set(ids)) != len(ids):
        raise DatasheetError(f"{source}: duplicate statement id", code="corpus.datasheet.statements")
    return StatementTable(tuple(out), sha256_hex(data))


# ------------------------------------------------------------------------------------------------ card
def card_mode(card: str) -> str | None:
    """The ``mode`` of the card's front matter, or ``None``."""
    match = _FRONT.match(card)
    if match is None:
        return None
    for line in match.group("body").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "mode":
            return value.strip()
    return None


def _card_sections(card: str) -> dict[str, str]:
    """The card body split at ``## <Section title>`` headings that name a datasheet section; text before the first
    heading belongs to ``motivation``."""
    match = _FRONT.match(card)
    body = card[match.end():] if match else card
    titles = {title.lower(): sid for sid, title in SECTIONS}
    out: dict[str, list[str]] = {}
    current = "motivation"
    for line in body.splitlines():
        heading = re.fullmatch(r"##\s+(.+?)\s*", line)
        if heading is not None and heading.group(1).lower() in titles:
            current = titles[heading.group(1).lower()]
            continue
        out.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


# ------------------------------------------------------------------------------------------------ values and tables
def _pointer(manifest: Mapping[str, Any], pointer: str) -> Any:
    node: Any = manifest
    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping) and key in node:
            node = node[key]
        elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            raise DatasheetError(f"{{{{v:{pointer}}}}} names no value of corpus.json", code="corpus.datasheet.placeholder")
    if isinstance(node, bool) or not isinstance(node, int | str):
        raise DatasheetError(f"{{{{v:{pointer}}}}} is not a string or an integer", code="corpus.datasheet.placeholder")
    return node


def _num(n: int) -> str:
    return f"{n:,}"


def _md(value: Any, *, line_start: bool = False) -> str:
    """A manifest value as Markdown text (F-12C-03; G.8.2, G.8.6, K.12.6(e)): one line with every control escaped
    (``escape_untrusted_line``), then its markup escaped (``escape_markdown``). A value that needs neither is unchanged."""
    return escape_markdown(escape_untrusted_line(str(value)), line_start=line_start)


def _building(steps: Any) -> str:
    """The building commits of a corpus (D-780) in plain words, one clause per recorded step, in order. A corpus built
    before the commit was recorded says so."""
    if not isinstance(steps, list) or not steps:
        return "building commit not recorded"
    parts = []
    for step in steps:
        wrote = ", ".join(_md(x) for x in step["stages"]) or "no stage"
        if "git_commit" in step:
            where = f"at commit {_code(step['git_commit'])}"
        else:
            where = (f"with no git checkout ({_md(step['git_commit_absent_reason'])}; agentprov "
                     f"{_code(step['agentprov_version'])}; installed distributions {_code(step['distributions_sha256'])})")
        parts.append(f"{_md(step['command'])} {where}, which wrote {wrote}")
    return "; ".join(parts)


def _code(value: Any) -> str:
    """A manifest value as a code span when it needs no escaping (it then renders, and is written, exactly as before);
    otherwise its escaped text without a code span: CommonMark interprets nothing inside a code span, so neither a
    backslash escape nor a character reference could neutralise a backtick or a ``|`` there."""
    text = str(value)
    shown = _md(text)
    return f"`{shown}`" if shown == text else shown


def _table(header: Sequence[str], rows: Sequence[Sequence[str]], *, empty: str) -> str:
    """A GFM table. The cells are Markdown already: every manifest value in them went through :func:`_md` or
    :func:`_code`. A table without rows is the sentence ``empty``, which says what there is none of (F-8: a bare
    "(none)" line named nothing)."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines) if rows else empty


def _t_counts(m: Mapping[str, Any]) -> str:
    c = m["counts"]
    rows = [("candidates", _num(c["candidates"])), ("executions (records of every unit)", _num(c["executions"])),
            ("not imported", _num(c["not_imported"]))]
    rows += [(f"unit {_code(k)}", _num(v)) for k, v in c["by_unit"].items()]
    rows += [(f"status {_code(k)}", _num(v)) for k, v in c["by_status"].items()]
    rows += [(f"completeness {_code(k)}", _num(v)) for k, v in c["by_completeness"].items()]
    rows += [(f"execution observed {_code(k)}", _num(v)) for k, v in c["execution_observed"].items()]
    return _table(("Count", "Value"), rows, empty="Counts: none.")


def _t_snapshots(m: Mapping[str, Any]) -> str:
    rows = []
    for source in m["sources"]:
        for s in source["snapshots"]:
            where = _origin_text(s["origin"])  # ultra seal-release #10: the pin, not only its kind word
            c = s["counts"]
            excluded = ", ".join(f"{_code(k)} {_num(v)}" for k, v in c["selection_excluded"].items()) or "none"
            rows.append((_code(s["snapshot_id"]), where, _md(s["raw_policy"]), _num(c["candidates"]),
                         _num(c["executions"]), _num(c["not_imported"]), excluded))
    return _table(("Snapshot", "Pinned origin", "Raw policy", "Candidates", "Executions", "Not imported",
                   "Selection exclusions"), rows, empty="Snapshots: none.")


def _origin_text(o: Mapping[str, Any]) -> str:
    """A sealed snapshot origin, a context origin or an object origin, as a datasheet cell (every value escaped,
    F-12C-03): git ``repo @ commit [subtree]``, corpus ``corpus version @ producer_commit``, Zenodo ``DOI file``, Hugging
    Face ``dataset @ revision [path]``, URL; any other kind (``capture``) by its kind word."""
    kind = o.get("kind")
    if kind == "git":
        return f"{_md(o['repo'])} @ {_code(o['commit'])}" + (f" {_code(o['subtree'])}" if o.get("subtree") else "")
    if kind == "corpus":
        return f"{_md(o['corpus'])} {_md(o['version'])} @ {_code(o['producer_commit'])}"
    if kind == "zenodo":
        return f"Zenodo {_code(o['doi'])} {_md(o['file'])}"
    if kind == "hf":
        return f"{_md(o.get('dataset') or o.get('repo'))} @ {_code(o['revision'])}" + (
            f" {_md(o['path'])}" if o.get("path") else "")
    if kind == "url":
        return _md(o["url"])
    return _md(str(kind))


def _has_per_unit(m: Mapping[str, Any]) -> bool:
    return any(s.get(k) for source in m["sources"] for s in source["snapshots"]
               for k in ("context", "pinned_objects", "context_skipped"))


def _t_context(m: Mapping[str, Any]) -> str:
    """D-221: the per-unit inputs of each snapshot (D.16.14): its context trees, pinned objects and skipped roles."""
    rows = []
    for source in m["sources"]:
        for s in source["snapshots"]:
            sid = _code(s["snapshot_id"])
            for c in s.get("context") or ():
                archive = f"archive {_md(c['input']['label'])}" if c.get("input") else "tree"
                rows.append((sid, f"context {_code(c['role'])}", _origin_text(c["origin"]), archive, _num(c["stored"]),
                             _md(c["verification"]["kind"])))
            for o in s.get("pinned_objects") or ():
                rows.append((sid, f"pinned object {_md(o['label'])}", _origin_text(o["origin"]), "object", _num(1),
                             "sha256"))
            for role in s.get("context_skipped") or ():
                rows.append((sid, f"context {_code(role)}", "skipped at import (`--no-context`)", "-", _num(0), "-"))
    return _table(("Snapshot", "Input", "Pinned origin", "Stored as", "Files", "Vouched by"), rows,
                  empty="Per-unit inputs: none.")


def _t_issues(m: Mapping[str, Any], rules_by_code: Mapping[str, Sequence[str]]) -> str:
    rows = [(_code(code), _num(n), ", ".join(_code(r) for r in rules_by_code.get(code, ())) or "-")
            for code, n in m["counts"]["issues_by_code"].items()]
    return _table(("Register code", "Entries", "Rules that raised it"), rows, empty="Register entries: none.")


def _t_records(m: Mapping[str, Any]) -> str:
    return _table(("AER record kind", "Records"), [(_code(k), _num(v)) for k, v in m["counts"]["records_by_kind"].items()],
                  empty="AER records: none.")


def _t_generic(m: Mapping[str, Any]) -> str:
    g = m["counts"]["generic_types"]
    rows = [(kind, _code(t), _num(n)) for kind in ("activity", "artefact") for t, n in g[kind].items()]
    return _table(("Generic kind", "Type", "Records"), rows, empty="Generic `activity` and `artefact` records: none.")


def _t_models(m: Mapping[str, Any]) -> str:
    rows = [(_code(x["requested"]) if x["requested"] else "unknown",
             ", ".join(_code(s) for s in x["served"]) or "not recorded",
             _md(x["provider"]) if x["provider"] else "not recorded",
             _md(x["ev"]["requested"]) if x["ev"]["requested"] else "-", _num(x["executions"])) for x in m["models"]]
    return _table(("Requested model", "Served model", "Provider", "Evidence (requested)", "Executions"), rows,
                  empty="Models: none recorded.")


def _t_frameworks(m: Mapping[str, Any]) -> str:
    rows = [(_code(f["fw"]), _md(f["distribution"]) if f["distribution"] else "-",
             _md(f["reported_version"]) if f["reported_version"] else "-", _md(f["suite_set"]) if f["suite_set"] else "-",
             "recorded" if f["tool_definitions_sha256"] else "not recorded",
             "recorded" if f["system_prompt_sha256"] else "not recorded", _num(f["executions"]))
            for f in m["framework_identities"]]
    return _table(("Framework id", "Distribution", "Reported version", "Suite set", "Tool definitions", "System prompt",
                   "Executions"), rows, empty="Framework identities: none recorded.")


def _t_validation(m: Mapping[str, Any]) -> str:
    v = m["validation"]
    rows = [(_md(t["tier"]), _num(t["checks"]), _num(t["executions"]), _num(t["executions_passed"]), _num(t["fail"]),
             _num(t["skipped"])) for t in v["tiers"]]
    return _table(("Tier", "Checks", "Executions", "Executions passing every check", "Failed results", "Skipped results"), rows,
                  empty="Validation tiers: none run.")


#: Table ids a card may insert with ``{{t:<id>}}``.
TABLES: Final = ("counts", "snapshots", "issues", "records", "generic_types", "models", "frameworks", "validation",
                 "field_groups", "context")  # fmt: skip


# ------------------------------------------------------------------------------------------------ rendering
@dataclass(frozen=True)
class Rendered:
    """The rendered datasheet and what the manifest records about it (``corpus.json.datasheet``)."""

    text: str
    claims: list[dict[str, Any]]
    statements: list[str]
    card_sha256: str
    statements_sha256: str


def _fill(text: str, manifest: Mapping[str, Any], tables: Mapping[str, Callable[[], str]], checker: CardChecker,
          claim_ids: list[str], figures: Mapping[str, Mapping[str, str]] | None = None) -> str:
    def replace(match: re.Match[str]) -> str:
        kind, body = match.group(1), match.group(2)
        if kind == "v":
            value = _pointer(manifest, body)
            if isinstance(value, int):
                return _num(value)
            return _md(value, line_start=match.start() == 0 or text[match.start() - 1] == "\n")
        if kind == "t":
            if body not in tables:
                raise DatasheetError(f"unknown table {{{{t:{body}}}}}", code="corpus.datasheet.placeholder")
            return "\n\n" + tables[body]() + "\n\n"
        if kind == "claim":
            claim_ids.append(body)
            return checker.claim_text(body)
        if figures is None or body not in figures:
            raise DatasheetError("a figure placeholder outside a statement", code="corpus.datasheet.placeholder")
        figure = figures[body]
        return f"{figure['value']} [{figure['source']}]"

    return _PLACEHOLDER.sub(replace, text)


def _licence_lines(m: Mapping[str, Any]) -> list[str]:
    lic = m["licences"]
    lines = []
    for raw in lic["raw"]:
        lines.append(f"- Source `{raw['source_id']}`: {raw['spdx'] or 'no SPDX id'}; basis (verbatim): \"{raw['basis']}\".")
        if raw["licence_files"]:
            lines.append("  Licence files: " + ", ".join(f"`{p}`" for p in raw["licence_files"]) + ".")
        if raw["copyright"]:
            lines.append("  Copyright holders: " + "; ".join(raw["copyright"]) + ".")
    derived = lic["derived"]
    lines.append(f"- Derived artefacts (AER, SEM, PROV, index, views): {derived['spdx']} (`{derived['basis']}`, decided by "
                 f"{derived['decided_by']}); text in `{derived['text_path']}`.")
    lines.append(f"- Licence policy `{lic['policy']['licence_policy']}`, raw policy `{lic['policy']['raw_policy']}`; "
                 f"redistribution: {lic['redistribution']}.")
    lines.append("- Licence class (deposit grouping, AD-20(b)): " + lic["class"]["spdx"] + (
        "; restrictions: " + "; ".join(f"\"{r}\"" for r in lic["class"]["restrictions"]) if lic["class"]["restrictions"]
        else "; no restriction") + ".")
    if lic["restrictions"]:
        lines.append("- Restrictions (verbatim): " + " ".join(f"\"{r}\"." for r in lic["restrictions"]))
    for item in lic["embedded"]:
        lines.append(f"- Embedded content: {item['what']}: {item['status']}.")
    if lic["attribution"]:  # third-party credit, quoted on one line (escaped: no line break, no markup); D-910
        lines.append(ATTRIBUTION_PREFIX + "; ".join(f"\"{_md(a)}\"" for a in lic["attribution"]) + ".")
    lines.append(f"- Assessment: {lic['assessment']}")
    return lines


_BASIS_TEXT: Final = {"purge": "purged from the private raw store (G.9.6)",
                      "raw_policy": "a snapshot with raw policy withhold (H.4.1)",
                      "profile_rule": "a withholding rule of the source profile matched",
                      "container": "an archive that holds a withheld member (AD-12)"}


def _withheld_lines(withheld: int, summary: Sequence[Mapping[str, Any]]) -> list[str]:
    """The withheld statement (H.4.5, H.9): the unchanged one-line count when nothing is withheld; otherwise the counts,
    what was withheld and why (closed vocabulary plus the escaped public notes), and where the ledger is. Values never
    appear: ``WITHHELD.json`` holds none (G.9.5)."""
    if not summary:
        return [f"Withheld items: {_num(withheld)} (H.4.5)."]
    objects = sum(int(r["objects"]) for r in summary)
    lines = [f"Withheld items: {_num(withheld)} (H.4.5): {_num(objects)} raw objects and the executions derived from "
             "them that could carry their content left this release; each is listed with its digest and pinned origin in "
             "`WITHHELD.json`, and a withheld execution keeps its id, snapshots and stage digests there, so it can be "
             "recomputed locally from the pin. Their register entries carry the code `release.withheld`. No withheld "
             "value, or any fragment of one, is recorded."]
    rows = [(_md(r["reason"]), _md(_BASIS_TEXT.get(str(r["basis"]), r["basis"])), _num(int(r["objects"])),
             _num(int(r["executions"])), "; ".join(_md(n) for n in r["notes"]) or "-") for r in summary]
    lines.append(_table(("Reason", "Withheld because", "Raw objects", "Executions", "Note"), rows, empty="Withheld reasons: none."))
    return lines


def _generated(section: str, m: Mapping[str, Any], tables: Mapping[str, Callable[[], str]], withheld: int,
               summary: Sequence[Mapping[str, Any]] = ()) -> list[str]:
    c = m["counts"]
    if section == "composition":
        return [
            "Counts are computed from the index, the register and `raw/members.jsonl` at sealing. A claim about agent "
            "executions uses only records with `unit == agent_execution` and `execution_observed == true` "
            f"({_num(c['by_unit']['agent_execution'])} records have unit `agent_execution`; "
            f"{_num(c['execution_observed']['false'])} records hold no observed execution).",
            tables["counts"](), tables["snapshots"](),
            *(["Per-unit inputs of the snapshots (context trees, pinned objects and skipped roles; D-221):",
               tables["context"]()] if _has_per_unit(m) else []),
            tables["models"](), tables["frameworks"](),
        ]
    if section == "evidence":
        return [
            "Field-group coverage (R-57) is the headline measure of information loss: per field group, the share of agent "
            "executions whose fields are observed (O) or derived (D).",
            tables["field_groups"](),
            "Records by kind, and the generic `activity` and `artefact` records by type (disclosed extensions, Addendum B "
            "AD-15):",
            tables["records"](), tables["generic_types"](),
        ]
    if section == "integrity":
        v = m["validation"]
        pct = v["linkage_resolved_pct"]["$dec"] if v["linkage_resolved_pct"] else "not applicable"
        return [
            f"- Content digest: {_code(m.get('content_digest', 'not yet computed'))} (H.5.4). The root digest (the sha256 of `checksums.sha256`) is "
            "published outside the corpus.",
            "- Verify: `agentprov verify --corpus <root> --level chain` (or `checksums`, `rederive`).",
            f"- Formats: {_code(m['formats']['corpus'])}, {_code(m['formats']['aer'])}, {_code(m['formats']['sem'])}; "
            "provenance specs: " + ", ".join(_code(s) for s in m["prov_specs"])
            + f"; ontology apv {_code(m['ontology']['version'])}.",
            "- Source profile: " + ", ".join(_code(f"{p['id']}@{p['version']}") for p in m["profiles"]["source"])
            + "; semantics profiles: " + (", ".join(_code(f"{p['id']}@{p['version']}") for p in m["profiles"]["semantics"])
                                          or "none")
            + "; rule catalogues: " + ", ".join(f"{_code(r['id'])} v{_md(r['version'])}" for r in m["rule_catalogues"]) + ".",
            "- Adapters: " + ", ".join(_code(f"{a['id']}@{a['version']}") for a in m["adapters"]) + ".",
            f"- Producer: agentprov {_code(m['producer']['agentprov_version'])} at commit {_code(m['producer']['git_commit'])}; "
            f"Python {_md(m['producer']['python']['implementation'])} {_code(m['producer']['python']['version'])}.",
            "- Building commit: " + _building(m["producer"].get("build_steps")) + ".",
            f"- Validation mode {_code(v['mode'])}; evidence linkage resolved for {pct} % of the applicable executions "
            f"({_num(v['linkage']['resolved'])} of {_num(v['linkage']['applicable'])}).",
            tables["validation"](),
            "The corpus is derivation-reproducible: re-deriving it from its raw evidence with the recorded versions gives "
            "the same bytes; execution reproducibility is not claimed (L.2.1).",
        ]
    if section == "known_issues":
        lines = [
            "Register codes and the rules that raised them:",
            tables["issues"](),
            f"Outcome-only and scenario records are counted separately from agent executions: "
            f"{_num(c['by_unit']['outcome_only'])} outcome-only, {_num(c['by_unit']['scenario'])} scenario records (R-28).",
            "Core PROV bundles contain configuration ground truth (attack and target ids, payload fixtures, attacker "
            "attributions, outcome values and checker runs) as genuine configuration provenance, so they are not a blind "
            "input for detectors or learning (NC-PROV-01, AD-11).",
        ]
        if m["oracle_specs"]:
            lines.append("Regression-oracle graphs (" + ", ".join(_code(o["spec"]) for o in m["oracle_specs"])
                         + ") are flagged `apv:RegressionOracle`; they reproduce the frozen baseline and are not the "
                         "recommended semantics (R-55).")
        lines.extend(_withheld_lines(withheld, summary))
        return lines
    if section == "distribution":
        return _licence_lines(m) + [
            "- Provider terms on redistributing model outputs were not assessed.",
            "- The corpus contains prompt-injection payloads by design (H.4.1(3)).",
        ]
    return []


_UNTRUSTED: Final = """## Untrusted content

- This corpus contains prompt-injection payloads and other adversarial text by design (H.4.1(3)): they are the subject of
  the source benchmarks.
- LLM-based consumers (analysis agents, retrieval, fine-tuning) that read the corpus are exposed to them.
- Treat every string of the corpus as data, never as instructions.
- Display text through the safe-display helper `agentprov.ingest.quote.quote_untrusted`; AgentPROV itself forwards no
  corpus content to any model."""


def render(
    manifest: Mapping[str, Any], card: str, register_stats: Mapping[str, Any], index_stats: Mapping[str, Any], *,
    checker: CardChecker, statements: StatementTable, field_groups: Callable[[Mapping[str, Any]], str] | None = None,
) -> Rendered:
    """Render ``DATASHEET.md`` (H.9(1)). ``manifest`` is the complete manifest without its ``datasheet`` member (the claims
    are evaluated over it); ``register_stats`` may give ``rules_by_code`` (register code -> rule ids), ``withheld`` (the
    number of withheld items: objects plus executions) and ``withheld_summary``
    (:func:`agentprov.corpus.withheld.withheld_summary`); ``index_stats`` is reserved for index-derived tables. Raises :class:`DatasheetError`:
    exit 4 for a card mode that differs from the manifest's (H.9(5)) or a card that fails the lint, exit 1 for a claim
    that does not hold, a broken placeholder or a datasheet that fails the claims lint."""
    del index_stats
    mode = card_mode(card)
    if mode != manifest["mode"]:
        raise DatasheetError("the card's mode differs from corpus.json's (H.9(5)); a card is written for its mode",
                             code="corpus.datasheet.mode", exit_code=4)
    source_ids = [s["source_id"] for s in manifest["sources"]]
    findings = checker.lint_card(card, source_ids=source_ids)
    if findings:
        shown = "; ".join(f"{loc}: {code} {detail}" for code, loc, detail in findings[:5])
        raise DatasheetError(f"the card fails the lint ({len(findings)} finding(s)): {shown}", code="corpus.datasheet.card",
                             exit_code=4)
    selected = statements.for_corpus(manifest["corpus_id"])
    for statement in selected:
        found = checker.lint_card("---\nmode: import\n---\n" + statement.text)
        if found:
            raise DatasheetError(f"statement {statement.id} fails the lint: {found[0][2]}", code="corpus.datasheet.statements")
    rules_by_code = register_stats.get("rules_by_code", {})
    withheld = int(register_stats.get("withheld", 0))
    summary = list(register_stats.get("withheld_summary") or ())

    def field_group_table() -> str:
        if field_groups is None:
            return ("(The field-group coverage table is produced by `agentprov stats --tables field_groups` over this "
                    "corpus; it was not computed by this build.)")
        return field_groups(manifest)

    tables: dict[str, Callable[[], str]] = {
        "counts": lambda: _t_counts(manifest), "snapshots": lambda: _t_snapshots(manifest),
        "issues": lambda: _t_issues(manifest, rules_by_code), "records": lambda: _t_records(manifest),
        "generic_types": lambda: _t_generic(manifest), "models": lambda: _t_models(manifest),
        "frameworks": lambda: _t_frameworks(manifest), "validation": lambda: _t_validation(manifest),
        "field_groups": field_group_table, "context": lambda: _t_context(manifest),
    }  # fmt: skip
    claim_ids: list[str] = []
    card_sections = _card_sections(card)
    out = [f"# Datasheet: {_md(manifest['title'])}", "",
           f"Corpus {_code(manifest['corpus_id'])} version {_code(manifest['corpus_version'])} (mode {_code(manifest['mode'])}). "
           "This datasheet is generated at sealing; every number in it is computed from `corpus.json`, the index and the "
           "register, or is a figure of a decided statement shown with the analysis that measured it."]  # fmt: skip
    for section, title in SECTIONS:
        parts: list[str] = []
        if section in card_sections and card_sections[section]:
            parts.append(_fill(card_sections[section], manifest, tables, checker, claim_ids))
        parts.extend(_generated(section, manifest, tables, withheld, summary))
        for statement in (s for s in selected if s.section == section):
            text = _fill(statement.text, manifest, tables, checker, claim_ids, statement.figures)
            parts.append(f"- {text} (Decided: {statement.decided}; source: {statement.source}.)")
        if parts:
            out += ["", f"## {title}", "", "\n\n".join(p.strip() for p in parts if p.strip())]
    out += ["", _UNTRUSTED, ""]
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    results, violations = checker.evaluate_claims(claim_ids, manifest, source_ids=source_ids)
    if violations:
        shown = "; ".join(f"{code} {detail}" for code, _loc, detail in violations[:5])
        raise DatasheetError(f"a datasheet claim fails (H.9(4)): {shown}", code="corpus.datasheet.claim")
    lint = checker.lint_datasheet(text)
    if lint:
        shown = "; ".join(f"{loc}: {code} {detail}" for code, loc, detail in lint[:5])
        raise DatasheetError(f"the datasheet fails the claims lint: {shown}", code="corpus.datasheet.lint")
    return Rendered(text=text, claims=results, statements=[s.id for s in selected],
                    card_sha256="sha256:" + sha256_hex(card.encode("utf-8")), statements_sha256="sha256:" + statements.sha256)
