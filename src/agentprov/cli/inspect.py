"""``agentprov inspect``: look at one execution, artefact or corpus, read-only (MN N.2.8; N.1.13; G.8).

::

    agentprov inspect TARGET [--corpus DIR] [--view VIEW] [--record ID] [--bundle B] [--show-content] [--max-chars N]
                      [--format {text,json}]

``TARGET`` is an execution id (with ``--corpus``), a ``.aer.jsonl`` / ``.sem.jsonl`` / PROV-JSON file, a raw file (with
``--view detect``) or a corpus root. Nothing is written, and no lock is taken.

**Output.** The payload goes to stdout (text, or one JCS document with ``--format json``); with the global ``--json`` the
CLI summary goes to stdout instead and the text rendering to stderr, as for ``info``. A one-line banner on stderr says the
output can contain untrusted third-party content.

**Content never prints by default (N.1.13).** Every value is classified before it is shown:

* a digest, and a string in a *token position* (a record kind, id, status, evidence class, rule reference, role, ... that
  also matches a conservative token grammar) is printed as is, and so is a value of an ``evf``, ``unk`` or ``formats``
  map that fits its closed grammar (an evidence tag, an unknown reason, a format id);
* a *label* (model id, tool name, task id, URL, file label, ...) is printed through ``escape_untrusted``, at most 80
  characters;
* anything else (message text, tool arguments and outputs, payloads, annotation values) is hidden and shown as its length and
  sha256 only; the ``$blob`` references of artefact content are digests and are never resolved or decoded.

With ``--show-content`` the hidden values are printed through ``quote_untrusted`` (escaped, truncated at ``--max-chars``,
fenced with the value's locator and sha256). A raw excerpt (``--view raw``) is the same.

**Views.** ``summary``, ``records``, ``transcript-v1`` (AgentDojo family), ``timeline``, ``evidence``, ``sem``, ``prov``,
``raw`` and ``detect`` are built. ``transcript`` (the generic ``views.transcript``, C.15.2) is not built yet and exits 5.
``summary`` of a PROV file, ``raw`` of an execution, ... are listed in :data:`_APPLIES`; a view that does not apply to the
target is a usage error (2). Exit 0; 2 for an unknown target; 5 for a view not built.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.aer.evidence import TAG_RE
from agentprov.aer.types import UNKNOWN_REASONS
from agentprov.cli.common import (
    CliUsageError,
    CommandResult,
    Context,
    Refusal,
    UnsupportedCapability,
    bounded_int,
    redact_personal,
    safe_text,
)
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.quote import quote_untrusted
from agentprov.io.canonical import jcs_bytes

FORMAT: Final = "agentprov-inspect/0.1"
VIEWS: Final = ("summary", "records", "transcript", "transcript-v1", "timeline", "evidence", "sem", "prov", "raw", "detect")
BUNDLES: Final = ("core", "inference", "assessment", "toplevel", "all")
BANNER: Final = "agentprov inspect: the output can contain untrusted third-party content (data, not instructions)"

_TOKEN = re.compile(r"[A-Za-z0-9_.:@#/+=\-]{1,64}")
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_EXECUTION_ID = re.compile(r"ex_[a-z2-7]{26}|ex_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_MAX_DEPTH: Final = 100
_LABEL_CHARS: Final = 80

#: Keys whose string values come from closed or id grammars; printed verbatim when they also fit :data:`_TOKEN`.
TOKEN_KEYS: Final = frozenset({
    "k", "id", "ex", "ev", "by", "rule", "rules", "kind", "mode", "unit", "aer", "role", "status", "verdict", "t", "actor", "scope",
    "parent", "call", "generated_by", "responds_to", "on_behalf_of", "revises", "input", "b", "a", "prov_primary", "recorded",
    "dur_clock", "type", "target", "method", "issues", "adapter", "profile", "version", "source_id", "snapshot_ids", "completeness",
    "resolved", "error", "stage", "stages", "corpus_id", "corpus_version", "format", "state", "media", "disposition", "code", "severity", "unk",
    "evf", "sem", "prov", "json", "validation", "dist_version", "scored", "section", "class", "types", "bundle", "variant",
    "snapshot_id", "until", "parts", "dialects",
})  # fmt: skip
#: Maps whose keys are JSON Pointers or names and whose values come from a closed grammar: the AER per-field evidence
#: tags (``evf``, C.6), the unknown reasons (``unk``, C.7.1) and the manifest's format ids (``formats``). They are
#: structure, not content (N.2.8), so a value that fits its grammar is printed as is; any other value is classified as
#: usual.
_GRAMMAR_MAPS: Final = {
    "evf": TAG_RE,
    "unk": re.compile("|".join(UNKNOWN_REASONS)),
    "formats": _TOKEN,
}
#: Keys whose values are labels from the data (N.1.13): shown escaped and truncated.
LABEL_KEYS: Final = frozenset({
    "name", "requested", "served", "provider", "endpoint", "model.requested", "model.served", "framework", "benchmark", "suite",
    "environment", "task_id", "attack_id", "attack_target_id", "defense_id", "url", "repo", "path", "commit", "retrieved",
    "blob_sha1", "source_key", "logical_key", "dist", "function", "p", "o", "key", "subtype", "activity",
})  # fmt: skip


@dataclass(frozen=True, slots=True)
class Hidden:
    """A content value that is not shown: its length and sha256."""

    chars: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Plain:
    """Fixed text written by this module (never taken from data); printed as is."""

    text: str


@dataclass(frozen=True, slots=True)
class Block:
    """A fenced ``quote_untrusted`` block (printed only with ``--show-content``)."""

    text: str


def _escape_key(key: object) -> str:
    return safe_text(key, 60, redact=False)


class Safe:
    """Turns decoded (untrusted) JSON into a display tree: scalars, labels, :class:`Hidden` and :class:`Block` values."""

    def __init__(self, *, show: bool, max_chars: int, base: str) -> None:
        self.show = show
        self.max_chars = max_chars
        self.base = base

    def string(self, value: str, key: str | None, path: str) -> Any:
        if _DIGEST.fullmatch(value):
            return value
        if key in TOKEN_KEYS and _TOKEN.fullmatch(value):
            return value
        if key in LABEL_KEYS:
            return safe_text(value, _LABEL_CHARS)
        if self.show:
            return Block(quote_untrusted(value, f"{self.base}{path}", max_chars=self.max_chars))
        return Hidden(len(value), hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest())

    def tree(self, value: Any, key: str | None = None, path: str = "", depth: int = 0) -> Any:
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, Plain):
            return value.text
        if isinstance(value, str):
            return self.string(value, key, path)
        if depth >= _MAX_DEPTH:
            return "<depth limit>"
        if isinstance(value, dict):
            grammar = _GRAMMAR_MAPS.get(key) if key is not None else None
            out: dict[str, Any] = {}
            for k, v in value.items():
                label = _escape_key(k)
                if grammar is not None and isinstance(v, str) and grammar.fullmatch(v):
                    out[label] = v
                    continue
                out[label] = self.tree(v, str(k), f"{path}/{str(k).replace('~', '~0').replace('/', '~1')}", depth + 1)
            return out
        if isinstance(value, list | tuple):
            return [self.tree(v, key, f"{path}/{i}", depth + 1) for i, v in enumerate(value)]
        return safe_text(repr(type(value).__name__), 40)


# ------------------------------------------------------------------------------------------------ rendering
def to_json(node: Any) -> Any:
    if isinstance(node, Hidden):
        return {"$content": {"chars": node.chars, "sha256": node.sha256}}
    if isinstance(node, Block):
        return {"$untrusted": node.text}
    if isinstance(node, dict):
        return {k: to_json(v) for k, v in node.items()}
    if isinstance(node, list):
        return [to_json(v) for v in node]
    return node


def _scalar(node: Any) -> str:
    if node is None:
        return "null"
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, Hidden):
        return f"<content chars={node.chars} sha256={node.sha256[:16]}...>"
    return str(node)


def render_text(node: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(node, dict):
        if not node:
            return [pad + "{}"]
        for k, v in node.items():
            if isinstance(v, Block):
                lines.append(f"{pad}{k}:")
                lines.extend(f"{pad}  {line}" for line in v.text.split("\n"))
            elif isinstance(v, dict | list) and v:
                lines.append(f"{pad}{k}:")
                lines.extend(render_text(v, indent + 1))
            elif isinstance(v, dict | list):
                lines.append(f"{pad}{k}: {'{}' if isinstance(v, dict) else '[]'}")
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")
        return lines
    if isinstance(node, list):
        if not node:
            return [pad + "[]"]
        for item in node:
            if isinstance(item, Block):
                lines.append(f"{pad}-")
                lines.extend(f"{pad}  {line}" for line in item.text.split("\n"))
            elif isinstance(item, dict | list) and item:
                lines.append(f"{pad}-")
                lines.extend(render_text(item, indent + 1))
            else:
                lines.append(f"{pad}- {_scalar(item) if not isinstance(item, dict | list) else ('{}' if isinstance(item, dict) else '[]')}")
        return lines
    if isinstance(node, Block):
        return [pad + line for line in node.text.split("\n")]
    return [pad + _scalar(node)]


# ------------------------------------------------------------------------------------------------ targets
@dataclass
class Target:
    """What the TARGET resolved to. ``kind``: execution | aer | sem | prov | raw | corpus."""

    kind: str
    label: str
    reader: Any = None  # CorpusReader (execution, corpus, or --corpus given)
    row: Any = None  # IndexRow
    data: bytes | None = None  # file bytes
    path_name: str = ""


#: Which views apply to which target kinds.
_APPLIES: Final = {
    "summary": {"execution", "aer", "sem", "prov", "raw", "corpus"},
    "records": {"execution", "aer"},
    "transcript": {"execution", "aer"},
    "transcript-v1": {"execution", "aer"},
    "timeline": {"execution", "aer"},
    "evidence": {"execution", "aer"},
    "sem": {"execution", "sem"},
    "prov": {"execution", "prov"},
    "raw": {"execution", "aer"},
    "detect": {"aer", "sem", "prov", "raw"},
}


def _read_file(path: Path, limits: IngestLimits) -> bytes:
    from agentprov.ingest.paths import open_evidence, open_root

    try:
        with open_root(path.parent) as root, open_evidence(root, path.name, limits) as stream:
            return stream.read()
    except IngestError as exc:
        raise CliUsageError(f"agentprov inspect: the file cannot be read ({exc.code})") from None
    except OSError as exc:
        raise CliUsageError(f"agentprov inspect: the file cannot be read ({type(exc).__name__})") from None


def _file_kind(name: str, view: str) -> str:
    lowered = name.lower()
    if view == "detect":
        return "raw"
    if lowered.endswith(".aer.jsonl"):
        return "aer"
    if lowered.endswith(".sem.jsonl"):
        return "sem"
    if lowered.endswith(".prov.json"):
        return "prov"
    if lowered.endswith((".trig", ".prov.trig")):
        raise UnsupportedCapability(
            "TriG files cannot be inspected in this build",
            refusal=Refusal(id=safe_text(name, 80), mode="inspect", status="TriG inspection is deferred in this build",
                            lines=("Inspect the PROV-JSON file of the execution (--view prov), or use --view detect for the raw bytes.",)),
            code="cli.unsupported.inspect",
        )
    return "raw"


def resolve_target(args: argparse.Namespace, limits: IngestLimits) -> Target:
    from agentprov.corpus.reader import CorpusNotFoundError, CorpusReader

    text = args.target
    reader = None
    if args.corpus is not None:
        try:
            reader = CorpusReader.open(args.corpus, limits=limits)
        except CorpusNotFoundError as exc:
            raise CliUsageError(f"agentprov inspect: --corpus: {safe_text(str(exc), 300)}") from None
    if _EXECUTION_ID.fullmatch(text):
        if reader is None:
            raise CliUsageError("agentprov inspect: an execution id needs --corpus DIR")
        row = reader.row(text)
        if row is None:
            raise CliUsageError(f"agentprov inspect: {safe_text(text, 80)} is not in the corpus index")
        return Target("execution", text, reader=reader, row=row)
    path = Path(text)
    if path.is_dir() or Path(text + ".partial").is_dir():
        if reader is not None:
            raise CliUsageError("agentprov inspect: a corpus root is the TARGET; do not also give --corpus")
        try:
            corpus = CorpusReader.open(path, limits=limits)
        except CorpusNotFoundError as exc:
            raise CliUsageError(f"agentprov inspect: {safe_text(str(exc), 300)}") from None
        return Target("corpus", safe_text(_corpus_id(corpus), _LABEL_CHARS) or "(no corpus id)", reader=corpus)
    if path.is_file():
        kind = _file_kind(path.name, args.view)
        return Target(kind, safe_text(path.name, 80), reader=reader, data=_read_file(path, limits), path_name=path.name)
    raise CliUsageError(f"agentprov inspect: unknown target {safe_text(text, 120)!r}: not an execution id, a file or a corpus")


# ------------------------------------------------------------------------------------------------ documents
def _aer_document(target: Target) -> Any:
    from agentprov.aer.reader import load_aer_bytes

    if target.kind == "execution":
        return target.reader.read_aer(target.row)
    try:
        assert target.data is not None
        return load_aer_bytes(target.data, verify=True)
    except AgentProvError as exc:
        raise CliUsageError(f"agentprov inspect: the file is not a valid AER ({exc.code})") from None


def _aer_summary(doc: Any) -> dict[str, Any]:
    header, seal = doc.header, doc.seal
    kinds = Counter(str(r.get("k")) for r in doc.records)
    return {
        "ex": header.get("ex"),
        "aer": header.get("aer"),
        "mode": header.get("mode"),
        "unit": header.get("unit"),
        "adapter": header.get("adapter"),
        "profile": header.get("profile"),
        "task": header.get("task"),
        "model": header.get("model"),
        "artifacts": header.get("artifacts"),
        "records": dict(sorted(kinds.items())),
        "seal": {
            "n_records": seal.get("n_records"),
            "records_sha256": seal.get("records_sha256"),
            "accounting": seal.get("accounting"),
            "issues": seal.get("issues"),
        },
        "execution_digest": doc.execution_digest,
        "file_sha256": doc.file_sha256,
    }


def _records(doc: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    records = [*doc.records, doc.seal]
    if args.record is None:
        return records
    chosen = [r for r in records if r.get("id") == args.record]
    if not chosen:
        raise CliUsageError(f"agentprov inspect: no record {safe_text(args.record, 60)!r} in the execution")
    return chosen


# ------------------------------------------------------------------------------------------------ views
def view_summary(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    if target.kind == "corpus":
        return _corpus_summary(target, safe)
    if target.kind == "execution":
        doc = _aer_document(target)
        row = target.row
        return safe.tree({"index": row.to_json(), "aer": _aer_summary(doc)})
    if target.kind == "aer":
        return safe.tree(_aer_summary(_aer_document(target)))
    assert target.data is not None
    info: dict[str, Any] = {"bytes": len(target.data), "sha256": hashlib.sha256(target.data).hexdigest()}
    if target.kind == "sem":
        from agentprov.sem.reader import load_sem_bytes

        try:
            sem = load_sem_bytes(target.data, verify=True)
        except AgentProvError as exc:
            raise CliUsageError(f"agentprov inspect: the file is not a valid SEM document ({exc.code})") from None
        info.update({
            "ex": sem.ex,
            "profile": f"{sem.profile_id}@{sem.profile_version}",
            "annotations": len(sem.records) - 1,
            "by_type": dict(sorted(Counter(str(r.get("type")) for r in sem.records[1:]).items())),
            "digest": sem.digest,
        })
    elif target.kind == "prov":
        info.update(_prov_counts(_prov_view(target)))
    return safe.tree(info)


def _corpus_summary(target: Target, safe: Safe) -> Any:
    reader = target.reader
    manifest = reader.manifest()
    rows = reader.index() if reader.exists("executions.jsonl") else []
    register = reader.register() if reader.exists("register.jsonl") else []
    out: dict[str, Any] = {
        "state": reader.state,
        "root": redact_personal(str(reader.root)),
        "manifest": manifest,
        "executions": len(rows),
        "by_status": dict(sorted(Counter(r.status for r in rows).items())),
        "by_source": dict(sorted(Counter(r.source_id for r in rows).items())),
        "full_rows": sum(1 for r in rows if r.is_full),
        "register": dict(sorted(Counter(e.code for e in register).items())),
        "tombstones": reader.exists("raw/tombstones.jsonl"),
    }
    return safe.tree(out)


def view_records(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    return safe.tree({"records": _records(_aer_document(target), args)})


def view_transcript_v1(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    from agentprov.views import transcript_v1

    doc = _aer_document(target)
    adapter = doc.header.get("adapter")
    adapter_id = adapter.get("id") if isinstance(adapter, dict) else None
    if adapter_id == "adprov.transcript_v1":
        rendered = transcript_v1.render(doc)
    elif adapter_id == "agentdojo.tracelogger":
        rendered = transcript_v1.render_converted(doc)
    else:
        raise UnsupportedCapability(
            "transcript-v1 does not apply to this execution",
            refusal=Refusal(id=target.label, mode="inspect", status="the transcript-v1 view is for the AgentDojo family",
                            lines=("It renders AERs of the adprov.transcript_v1 and agentdojo.tracelogger adapters (C.15.3).",
                                   "Use --view records for this execution.")),
            code="cli.unsupported.inspect",
        )
    return safe.tree(rendered)


def view_transcript(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    raise UnsupportedCapability(
        "the generic transcript view is not built",
        refusal=Refusal(id=target.label, mode="inspect", status="--view transcript is deferred in this build",
                        lines=("The generic views.transcript (C.15.2) is not built yet.",
                               "Use --view transcript-v1 for the AgentDojo family, or --view records.")),
        code="cli.unsupported.inspect",
    )


_NO_ORDER: Final = ("actor", "scope", "execution", "seal")


def view_timeline(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    out = []
    for r in _records(_aer_document(target), args):
        if r.get("k") in _NO_ORDER:
            continue
        edges = r.get("after")
        entry: dict[str, Any] = {"id": r.get("id"), "k": r.get("k")}
        entry["after"] = [{"id": e.get("id"), "b": e.get("b")} for e in edges if isinstance(e, dict)] if edges else Plain("order unknown")
        out.append(entry)
    shown = safe.tree({"timeline": out})
    shown["note"] = "a record with no after edge has an unknown order, not a concurrent one"
    return shown


def view_evidence(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    records = _records(_aer_document(target), args)
    rows = []
    classes: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    for r in records:
        for name in ("ev",):
            if isinstance(r.get(name), str):
                classes[r[name]] += 1
        for rule in r.get("rule") or []:
            if isinstance(rule, str):
                rules[rule.split("#", 1)[0]] += 1
        rows.append({k: r[k] for k in ("id", "k", "ev", "by", "evf", "rule", "unk") if k in r})
    return safe.tree({"records": rows, "totals": {"ev": dict(sorted(classes.items())), "rules": dict(sorted(rules.items()))}})


def view_sem(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    from agentprov.sem.reader import load_sem_bytes

    docs: list[Any] = []
    if target.kind == "execution":
        docs = list(target.reader.read_sem_all(target.row).values())
        if not docs:
            raise CliUsageError("agentprov inspect: the execution has no SEM output")
    else:
        assert target.data is not None
        try:
            docs = [load_sem_bytes(target.data, verify=True)]
        except AgentProvError as exc:
            raise CliUsageError(f"agentprov inspect: the file is not a valid SEM document ({exc.code})") from None
    out = []
    for doc in docs:
        annotations = doc.records[1:]
        if args.record is not None:
            annotations = [a for a in annotations if args.record in (a.get("id"), a.get("target"))]
        out.append({"profile": f"{doc.profile_id}@{doc.profile_version}", "header": doc.header, "annotations": annotations,
                    "digest": doc.digest})
    return safe.tree({"sem": out})


def _prov_view(target: Target, spec: str = "agentprov-prov/0.1") -> Any:
    from agentprov.ingest.loaders import strict_json_loads
    from agentprov.validate._provdoc import ProvView

    try:
        if target.kind == "execution":
            document = target.reader.read_prov(target.row, spec)
        else:
            assert target.data is not None
            document = strict_json_loads(target.data, IngestLimits())
    except IngestError as exc:
        raise CliUsageError(f"agentprov inspect: the file is not strict JSON ({exc.code})") from None
    except AgentProvError as exc:
        if exc.code == "corpus.read.missing":
            raise CliUsageError("agentprov inspect: the execution has no agentprov-prov/0.1 output") from None
        raise
    return ProvView.parse(document)


def _prov_counts(view: Any) -> dict[str, Any]:
    return {
        "bundles": len(view.bundles),
        "by_kind": dict(sorted(Counter(b.kind for b in view.bundles.values()).items())),
        "statements": sum(len(b.statements) for b in view.bundles.values()) + len(view.top),
    }


def view_prov(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    view = _prov_view(target)
    want = args.bundle or "core"
    groups: list[tuple[str, str, list[Any]]] = []
    if want in ("toplevel", "all"):
        groups.append(("toplevel", "toplevel", list(view.top)))
    for iri, bundle in sorted(view.bundles.items()):
        if want == "all" or want == bundle.kind:
            groups.append((iri, bundle.kind, list(bundle.statements)))
    out: dict[str, Any] = {}
    for iri, kind, statements in groups:
        listing = []
        for st in statements:
            entry: dict[str, Any] = {"section": st.section, "key": st.key, "types": sorted(st.types), "rule": st.rule, "class": st.cls}
            if safe.show:
                entry["attributes"] = st.attrs
            listing.append(entry)
        out[iri] = {"kind": kind, "counts": dict(sorted(Counter(s.section for s in statements).items())), "statements": listing}
    return safe.tree({"bundles": out})


def view_raw(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    from agentprov.aer.locators import LocatorError, LocatorResolver

    doc = _aer_document(target)
    if args.record is None:
        listing = safe.tree({"artifacts": doc.header.get("artifacts")})
        listing["note"] = "name a record with --record ID to resolve its source locators to excerpts"
        return listing
    record = doc.get(args.record)
    if record is None:
        raise CliUsageError(f"agentprov inspect: no record {safe_text(args.record, 60)!r} in the execution")
    reader = target.reader
    if reader is None:
        raise CliUsageError("agentprov inspect: --view raw needs the raw store: give --corpus DIR")
    resolver = LocatorResolver(doc.header, reader.raw_store())
    out = []
    for n, locator in enumerate(record.get("src") or []):
        entry: dict[str, Any] = {"locator": locator}
        try:
            value = resolver.resolve(locator)
        except LocatorError as exc:
            entry["error"] = exc.code
            out.append(safe.tree(entry))
            continue
        excerpt = value if isinstance(value, bytes) else jcs_bytes(value)
        entry["resolved"] = "bytes" if isinstance(value, bytes) else "json"
        entry["bytes"] = len(excerpt)
        entry["sha256"] = hashlib.sha256(excerpt).hexdigest()
        tree = safe.tree(entry, None, f"/src/{n}")
        if safe.show:
            where = f"{doc.ex}:{args.record}:src[{n}]"
            tree["excerpt"] = Block(quote_untrusted(excerpt, where, max_chars=safe.max_chars))
        out.append(tree)
    return {"record": args.record, "excerpts": out}


def view_detect(target: Target, safe: Safe, args: argparse.Namespace) -> Any:
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory
    from agentprov.ingest.loaders import strict_json_loads

    assert target.data is not None
    limits = IngestLimits()
    sniffs = []
    for dialect in sorted(READERS):
        entry: dict[str, Any] = {"dialect": dialect}
        try:
            result = resolve_factory(READERS[dialect])().sniff(target.data, label=target.path_name, limits=limits)
            entry.update({"match": result.match, "dialect_id": result.dialect, "variant": result.variant,
                          "flags": sorted(result.flags), "reasons": [safe_text(r, 200) for r in result.reasons]})
        except (AgentProvError, ValueError) as exc:
            entry["error"] = getattr(exc, "code", type(exc).__name__)
        sniffs.append(entry)
    keys: dict[str, Any] = {"parsed_as": None}
    for name, chunk in (("json", target.data), ("first_line", target.data.split(b"\n", 1)[0])):
        try:
            value = strict_json_loads(chunk, limits)
        except IngestError:
            continue
        keys["parsed_as"] = name
        if isinstance(value, dict):
            keys["type"] = "object"
            keys["keys"] = [safe_text(k, 60, redact=False) for k in list(value)[:100]]
            keys["n_keys"] = len(value)
        else:
            keys["type"] = "array" if isinstance(value, list) else type(value).__name__
        break
    return {
        "file": {"bytes": len(target.data), "sha256": hashlib.sha256(target.data).hexdigest()},
        "sniff": [_plain(e) for e in sniffs],
        "key_set": keys,
    }


def _plain(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: (safe_text(v, 80) if isinstance(v, str) and k in ("dialect", "dialect_id", "variant") else v) for k, v in entry.items()}


VIEW_FUNCTIONS: Final = {
    "summary": view_summary,
    "records": view_records,
    "transcript": view_transcript,
    "transcript-v1": view_transcript_v1,
    "timeline": view_timeline,
    "evidence": view_evidence,
    "sem": view_sem,
    "prov": view_prov,
    "raw": view_raw,
    "detect": view_detect,
}


# ------------------------------------------------------------------------------------------------ command
def _positive(text: str) -> int:
    value = bounded_int(text)
    if not 1 <= value <= 1_000_000:
        raise argparse.ArgumentTypeError("must be between 1 and 1000000")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "inspect",
        parents=[shared],
        help="look at one execution, artefact or corpus (read-only; content hidden unless --show-content)",
        description=(
            "Look at an execution id (with --corpus), an .aer.jsonl / .sem.jsonl / PROV-JSON file, a raw file (--view detect) "
            "or a corpus root (N.2.8). Read-only. Without --show-content only structure is printed: ids, kinds, locators, "
            "digests, lengths, rule ids and labels; with it, content is printed through quote_untrusted (escaped, fenced, "
            "truncated at --max-chars)."
        ),
        allow_abbrev=False,
    )
    p.set_defaults(command="inspect", handler=run_inspect, feedback=False)
    p.add_argument("target", metavar="TARGET", help="an execution id, a file, or a corpus root")
    p.add_argument("--corpus", metavar="DIR", help="the corpus (sealed, working or DIR.partial) for an execution id or the raw store")
    p.add_argument("--view", choices=VIEWS, default="summary", help="what to show (default summary)")
    p.add_argument("--record", metavar="ID", help="one record (records, evidence, timeline, sem, raw)")
    p.add_argument("--bundle", choices=BUNDLES, help="prov view: which bundles (default core)")
    p.add_argument("--max-chars", type=_positive, default=500, metavar="N", help="with --show-content: characters per value (default 500)")
    p.add_argument("--format", choices=["text", "json"], default="text", help="payload format (default text)")


def run_inspect(ctx: Context) -> CommandResult:
    args = ctx.args
    if args.record is not None and args.view not in ("records", "evidence", "timeline", "sem", "raw"):
        raise CliUsageError("agentprov inspect: --record applies to the records, evidence, timeline, sem and raw views")
    if args.bundle is not None and args.view != "prov":
        raise CliUsageError("agentprov inspect: --bundle applies to the prov view")
    limits = IngestLimits()
    target = resolve_target(args, limits)
    if target.kind not in _APPLIES[args.view]:
        raise CliUsageError(
            f"agentprov inspect: --view {args.view} does not apply to a {target.kind} target "
            f"(it applies to: {', '.join(sorted(_APPLIES[args.view]))})"
        )
    safe = Safe(show=bool(args.show_content), max_chars=args.max_chars, base=f"{target.label}:{args.view}")
    tree = VIEW_FUNCTIONS[args.view](target, safe, args)
    result = CommandResult()
    result.output(BANNER)
    if target.reader is not None and target.reader.state != "sealed":
        result.notices.append("working corpus: not sealed or verified (N.1.5)")
    result.counters = {"views": 1}
    document = {"format": FORMAT, "target": {"kind": target.kind, "label": target.label}, "view": args.view,
                "content_shown": bool(args.show_content), "data": tree}
    if args.format == "json":
        text = (jcs_bytes(to_json(document)).decode("utf-8")) + "\n"
    else:
        head = f"{args.view} of {target.kind} {target.label}" + (" (content shown, escaped)" if args.show_content else "")
        text = "\n".join([head, *render_text(tree)]) + "\n"
    if args.json:
        for line in text.splitlines():
            result.info(line)
    else:
        result.payload = text.encode("utf-8")
    if target.reader is not None:
        result.corpus = {
            "content_digest": None,
            "corpus_id": _corpus_id(target.reader),
            "root": redact_personal(str(target.reader.root)),
            "state": "sealed" if target.reader.sealed else "working",
        }
    return result


def _corpus_id(reader: Any) -> str:
    manifest = reader.manifest()
    value = manifest.get("corpus_id") if manifest else None
    return value if isinstance(value, str) else ""

