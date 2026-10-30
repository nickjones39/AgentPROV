"""The ``[family.agentdojo]`` part of a source profile: closed-schema check and typed access (docs/architecture D.4.1-D.4.5,
D.6.12).

The generic loader (:mod:`agentprov.adapters.profiles`) checks the generic tables and hands the family part over as data;
this module checks it against the family's closed schema ``family.schema.json`` with a small stdlib subset of JSON Schema
(``type``, ``properties``, ``additionalProperties``, ``required``, ``items``, ``enum``, ``pattern``, ``minimum`` and local
``$ref`` into ``$defs``). The tests check the same documents with ``jsonschema`` (differential, D.4.1). A violation is a
:class:`~agentprov.errors.ProfileError`: profiles are trusted package data, so a defect is a build error (exit 70).

Beyond the schema, :func:`family_table` checks what a JSON Schema cannot express:

* selector keys (``applies`` of quirks and system-prompt variants) are facets: the named components of ``[import]
  layout`` (:mod:`agentprov.adapters.agentdojo.layout`) or one of :data:`FIXED_FACETS`;
* an identity ``table`` (D.4.5) is package data under ``adapters/agentdojo/tables/``, its sha256 equals the one the profile
  pins (so the profile digest covers the table bytes), and its rows follow the closed row schema of
  :data:`TABLE_ROW_KEYS`, one row per directory name;
* the identity keys a ``model_from`` mode needs are present (``defence_suffix_regex`` for ``pipeline_name_minus_suffix``,
  ``slug_to_model`` for ``results_dir_slug``);
* every quirk with a mapper hook (:mod:`agentprov.adapters.agentdojo.quirks`) cites its hook's rules.

Quirk matching (D.4.1 "Selectors"): ``applies`` keys are ANDed, the globs of one key are ORed, ``fnmatch`` semantics,
an empty ``applies`` matches everything.
"""

from __future__ import annotations

import fnmatch
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.adapters.agentdojo.history_table import HistoryTable, load_history_table
from agentprov.adapters.agentdojo.layout import Layout, parse_layout
from agentprov.adapters.code_verification import VerifiedCode, parse_verified_code
from agentprov.adapters.profiles import SourceProfile
from agentprov.errors import ProfileError
from agentprov.io.canonical import sha256_hex
from agentprov.io.jsonschema_subset import _json_equal, pattern_matches

__all__ = [
    "FIXED_FACETS",
    "TABLE_ROW_KEYS",
    "FamilyTable",
    "PromptVariant",
    "Quirk",
    "check_against_schema",
    "family_schema",
    "family_table",
    "load_identity_table",
    "parse_identity_table",
]

_TYPES: Final = {
    "object": (dict, Mapping),
    "array": (list, tuple),
    "string": (str,),
    "boolean": (bool,),
}
#: Facets a selector may name besides the layout's components: the mapper always computes them (from the layout when it
#: names them, else from the logged fields).
#: ``introduced_under`` (D-84): the oldest pin whose history contains the commit that introduced the log's blob
#: (:func:`agentprov.adapters.agentdojo.history_table.origin_introduced_under`); ``None`` when not known.
FIXED_FACETS: Final = frozenset({"variant", "pipeline_dir", "attack_dir", "task_dir", "suite", "introduced_under"})
#: The closed row schema of an identity table (D.4.5): key -> required.
TABLE_ROW_KEYS: Final[Mapping[str, bool]] = {
    "name": True, "model": False, "defence": False, "provider": False, "provider_evidence": False, "variant": False,
    "codebase": False, "pipeline_name": False, "basis": False, "note": False, "defence_model": False,
}  # fmt: skip
_FACET_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")
#: The ``[[family.agentdojo.redact]]`` scopes each dialect's build applies (bug pass NF-12: a declared rule no build
#: applies would be ignored silently, so the profile is refused instead; fail closed). TraceLogger and DRIFT apply
#: ``pipeline_name`` (regeneration-batch item 105); the results build applies ``model_id`` (D-476).
REDACT_SCOPES_APPLIED: Final[Mapping[str, frozenset[str]]] = {
    "agentdojo.tracelogger": frozenset({"pipeline_name"}),
    "agentdojo.results_container": frozenset({"model_id"}),
}


@cache
def family_schema() -> Mapping[str, Any]:
    """The family's closed schema (package data)."""
    data = resources.files("agentprov.adapters.agentdojo").joinpath("family.schema.json").read_bytes()
    loaded: Mapping[str, Any] = json.loads(data)
    return loaded


def _type_ok(value: object, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def _resolve(schema: Mapping[str, Any], root: Mapping[str, Any]) -> Mapping[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith("#/$defs/"):
        raise ProfileError(f"family schema: only local $defs references are supported, not {ref!r}")
    target = root.get("$defs", {}).get(ref.removeprefix("#/$defs/"))
    if not isinstance(target, Mapping):
        raise ProfileError(f"family schema: unresolved reference {ref!r}")
    return {**target, **{k: v for k, v in schema.items() if k != "$ref"}}


def check_against_schema(value: object, schema: Mapping[str, Any], where: str = "",
                         root: Mapping[str, Any] | None = None) -> list[str]:
    """Problems of ``value`` under ``schema`` (the subset named in the module docstring); ``[]`` when it conforms."""
    root = schema if root is None else root
    schema = _resolve(schema, root)
    out: list[str] = []
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_ok(value, expected):
        return [f"{where or '/'}: expected {expected}"]
    if "enum" in schema and not any(_json_equal(value, option) for option in schema["enum"]):  # item 78: true is not 1
        out.append(f"{where or '/'}: not one of {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not pattern_matches(schema["pattern"], value):
        out.append(f"{where or '/'}: does not match {schema['pattern']}")
    if isinstance(value, int) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        out.append(f"{where or '/'}: below {schema['minimum']}")
    if isinstance(value, Mapping):
        props: Mapping[str, Any] = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for name in schema.get("required", ()):
            if name not in value:
                out.append(f"{where}/{name}: required")
        for key, item in value.items():
            if key in props:
                out.extend(check_against_schema(item, props[key], f"{where}/{key}", root))
            elif extra is False:
                out.append(f"{where}/{key}: not allowed (closed schema)")
            elif isinstance(extra, Mapping):
                out.extend(check_against_schema(item, extra, f"{where}/{key}", root))
    if isinstance(value, list | tuple) and isinstance(schema.get("items"), Mapping):
        for i, item in enumerate(value):
            out.extend(check_against_schema(item, schema["items"], f"{where}/{i}", root))
    return out


def _thaw(value: Any) -> Any:
    """Plain dicts and lists from the loader's frozen mapping proxies and tuples."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw(v) for v in value]
    return value


def _matches(selector: Mapping[str, Sequence[str]], facets: Mapping[str, str | None]) -> bool:
    for key, globs in selector.items():
        value = facets.get(key)
        if value is None or not any(fnmatch.fnmatchcase(value, g) for g in globs):
            return False
    return True


@dataclass(frozen=True, slots=True)
class Quirk:
    """One ``[[family.agentdojo.quirk]]`` entry (D.4.2, D.6.4)."""

    id: str
    applies: Mapping[str, Sequence[str]]
    rules: tuple[str, ...]
    params: Mapping[str, Any]
    observed: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    note: str | None = None

    def matches(self, facets: Mapping[str, str | None]) -> bool:
        """``applies`` against the file's facets (the layout components, ``variant`` and :data:`FIXED_FACETS`)."""
        return _matches(self.applies, facets)


@dataclass(frozen=True, slots=True)
class PromptVariant:
    """One ``system_prompt_variants`` entry: a label, the pinned text digest it is recognised by, and its selector."""

    label: str
    sha256: str | None
    applies: Mapping[str, Sequence[str]]
    source: str | None = None

    def matches(self, facets: Mapping[str, str | None]) -> bool:
        return _matches(self.applies, facets)


@dataclass(frozen=True, slots=True)
class FamilyTable:
    """The checked ``[family.agentdojo]`` table of one profile."""

    data: Mapping[str, Any]
    quirks: tuple[Quirk, ...]
    layout: Layout | None = None
    #: Identity-table rows by directory name (D.4.5); empty without a ``table``.
    table_rows: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: ``[identity] part_tables``: the rows of a part with its own git pin, by that pin's commit (regeneration-batch item
    #: 95, R-10j-2: a directory name the head pin also uses may name other runs at an older commit).
    part_rows: Mapping[str, Mapping[str, Mapping[str, Any]]] = field(default_factory=dict)
    prompt_variants: tuple[PromptVariant, ...] = ()
    #: The history table (D.6.16) when the profile declares ``[family.agentdojo.benchmark.history]``.
    history: HistoryTable | None = None
    #: ``[harness] verified_code``: the commits whose code produced the profile's logs (D.5.4, D-24).
    verified_code: tuple[VerifiedCode, ...] = ()

    @property
    def identity(self) -> Mapping[str, Any]:
        return self.data.get("identity", {})

    def rows_for(self, origin: Any) -> Mapping[str, Mapping[str, Any]]:
        """The identity rows for a file of this origin: a part table's when its git commit is that part's pin, else
        the profile's table."""
        commit = origin.data.get("commit") if getattr(origin, "kind", None) == "git" else None
        return self.part_rows.get(commit, self.table_rows) if isinstance(commit, str) else self.table_rows

    @property
    def benchmark(self) -> Mapping[str, Any]:
        return self.data["benchmark"]

    @property
    def harness(self) -> Mapping[str, Any]:
        return self.data["harness"]

    @property
    def outcomes(self) -> Mapping[str, Any]:
        return self.data["outcomes"]

    def benchmark_of(self, suite: str) -> str:
        """``[benchmark] suites[suite]``, else the profile's ``benchmark`` (D.6.5 Step 1)."""
        bench = self.benchmark
        return str(bench.get("suites", {}).get(suite, bench.get("benchmark", "agentdojo")))

    def version_label_semantics(self, suite: str) -> str:
        """The meaning of the logged ``benchmark_version`` label for a file of ``suite`` (D.6.12 item 5):
        ``suite_version`` or the profile's non-version reading; ``suite_version_for_agentdojo_suites_only`` resolves
        per suite."""
        value = str(self.benchmark.get("version_label_semantics", "suite_version"))
        if value == "suite_version_for_agentdojo_suites_only":
            return "suite_version" if self.benchmark_of(suite) == "agentdojo" else "label_not_suite_version"
        return value

    @property
    def retry_semantics(self) -> str:
        return str(self.harness.get("retry_semantics", "agentdojo.final_content_none_max3"))

    def quirk(self, quirk_id: str) -> Quirk | None:
        for quirk in self.quirks:
            if quirk.id == quirk_id:
                return quirk
        return None

    def applies(self, quirk_id: str, facets: Mapping[str, str | None]) -> bool:
        """Whether quirk ``quirk_id`` is declared and its selector matches ``facets``."""
        quirk = self.quirk(quirk_id)
        return quirk is not None and quirk.matches(facets)


_CHECKED: dict[str, FamilyTable] = {}


def load_identity_table(path: str, sha256: str) -> dict[str, Mapping[str, Any]]:
    """An identity table (D.4.5) from package data: digest-checked, rows closed (:data:`TABLE_ROW_KEYS`), keyed by name."""
    node = resources.files("agentprov.adapters.agentdojo").joinpath(*path.split("/"))
    if not node.is_file():
        raise ProfileError(f"identity table {path!r} is not shipped in the package")
    data = node.read_bytes()
    if sha256_hex(data) != sha256:
        raise ProfileError(f"identity table {path!r}: its sha256 differs from the one the profile pins")
    return parse_identity_table(data, path)


def parse_identity_table(data: bytes, path: str) -> dict[str, Mapping[str, Any]]:
    """The rows of an identity table's bytes by directory name (closed row schema; one row per name; D.4.5)."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError(f"identity table {path!r}: not valid TOML/UTF-8") from exc
    if set(doc) != {"dir"} or not isinstance(doc["dir"], list):
        raise ProfileError(f"identity table {path!r}: a table holds [[dir]] rows only")
    rows: dict[str, Mapping[str, Any]] = {}
    for row in doc["dir"]:
        if not isinstance(row, dict):
            raise ProfileError(f"identity table {path!r}: a row is a table")
        unknown = sorted(set(row) - set(TABLE_ROW_KEYS))
        missing = sorted(k for k, required in TABLE_ROW_KEYS.items() if required and k not in row)
        if unknown or missing or not all(isinstance(v, str) for v in row.values()):
            raise ProfileError(f"identity table {path!r}: row {row.get('name')!r} has unknown {unknown} or missing {missing} "
                               "keys, or a value that is not a string")
        if row.get("model", "not_recorded") == "not_recorded" and "defence" not in row:
            # phase-10d R4: a row may omit its model only to name a defence (the model stays unresolved, D-92)
            raise ProfileError(f"identity table {path!r}: row {row['name']!r} names neither a model nor a defence")
        if row.get("provider_evidence", "I") not in ("I",):
            raise ProfileError(f"identity table {path!r}: provider_evidence may only weaken the row (I)")
        if row["name"] in rows:
            raise ProfileError(f"identity table {path!r}: more than one row for {row['name']!r} (D.4.5)")
        rows[row["name"]] = row
    return rows


def _check_facets(where: str, selector: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(k for k in selector if k not in allowed or not _FACET_NAME.fullmatch(k))
    if unknown:
        raise ProfileError(f"{where}: selector facet(s) {unknown} are neither layout components nor {sorted(FIXED_FACETS)}")


def family_table(profile: SourceProfile) -> FamilyTable:
    """The checked family table of ``profile`` (cached by profile digest). ``ProfileError`` on a schema violation."""
    hit = _CHECKED.get(profile.sha256)
    if hit is not None:
        return hit
    if profile.family != "agentdojo":
        raise ProfileError(f"profile {profile.id!r} is not of the agentdojo family")
    data = _thaw(profile.family_table())
    problems = check_against_schema(data, family_schema())
    if problems:
        raise ProfileError(f"profile {profile.id!r}: [family.agentdojo] violates family.schema.json: {'; '.join(problems[:5])}")
    if "via" not in profile.data["profile"]:  # a profile served by another's import (D.4.4) carries no mapping tables
        missing = [t for t in ("benchmark", "harness", "outcomes") if t not in data]
        if missing:
            raise ProfileError(f"profile {profile.id!r}: [family.agentdojo] lacks {missing}")
    imp = profile.data.get("import", {})
    layout_text = imp.get("layout")
    layout = parse_layout(str(layout_text), where=f"profile {profile.id!r}") if isinstance(layout_text, str) else None
    allowed = FIXED_FACETS | (layout.names if layout is not None else frozenset())
    if imp.get("mapper") == "agentdojo.tracelogger" and "identity" not in data:
        raise ProfileError(f"profile {profile.id!r}: a TraceLogger import profile declares [family.agentdojo.identity]")
    ident = data.get("identity", {})
    mode = ident.get("model_from")
    if mode == "pipeline_name_minus_suffix" and not ident.get("defence_suffix_regex"):
        raise ProfileError(f"profile {profile.id!r}: model_from = pipeline_name_minus_suffix needs defence_suffix_regex")
    if mode == "pipeline_name_minus_suffix":
        try:
            re.compile(str(ident["defence_suffix_regex"]))
        except re.error as exc:
            raise ProfileError(f"profile {profile.id!r}: defence_suffix_regex does not compile") from exc
    if mode == "results_dir_slug" and (not ident.get("slug_to_model") or layout is None or "results_dir" not in layout.names):
        raise ProfileError(f"profile {profile.id!r}: model_from = results_dir_slug needs slug_to_model and a {{results_dir}} "
                           "layout component")
    if mode == "model_dir" and (layout is None or "model_dir" not in layout.names):
        raise ProfileError(f"profile {profile.id!r}: model_from = model_dir needs a {{model_dir}} layout component")
    rows: dict[str, Mapping[str, Any]] = {}
    if "table" in ident:
        rows = load_identity_table(str(ident["table"]["path"]), str(ident["table"]["sha256"]))
    dialect = str(imp.get("dialect", ""))
    for rule in data.get("redact", ()):
        scope = rule.get("scope") if isinstance(rule, Mapping) else None
        if scope not in REDACT_SCOPES_APPLIED.get(dialect, frozenset()):
            rid = rule.get("id") if isinstance(rule, Mapping) else None
            raise ProfileError(f"profile {profile.id!r}: redaction rule {rid!r} has scope {scope!r}, which the "
                               f"{dialect or 'declared'} build does not apply (fail closed)")
    part_rows: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    for part, ref in ident.get("part_tables", {}).items():
        pins = [p for p in profile.data.get("source", {}).get("pins", ()) if p.get("part") == part and p.get("kind") == "git"]
        if part not in profile.data["profile"].get("parts", ()) or len(pins) != 1:
            raise ProfileError(f"profile {profile.id!r}: part_tables names {part!r}, which needs to be a part with exactly "
                               "one git pin of its own")
        part_rows[str(pins[0]["commit"])] = load_identity_table(str(ref["path"]), str(ref["sha256"]))
    quirks = []
    for q in data.get("quirk", ()):
        _check_facets(f"profile {profile.id!r} quirk {q['id']}", q.get("applies", {}), allowed)
        quirks.append(Quirk(id=q["id"], applies=q.get("applies", {}), rules=tuple(q.get("rules", ())),
                            params=q.get("params", {}), observed=q.get("observed", {}), note=q.get("note")))
    if len({q.id for q in quirks}) != len(quirks):
        raise ProfileError(f"profile {profile.id!r}: a quirk id is declared twice")
    variants = []
    for v in data.get("harness", {}).get("system_prompt_variants", ()):
        _check_facets(f"profile {profile.id!r} system prompt variant {v['label']}", v.get("applies", {}), allowed)
        variants.append(PromptVariant(label=v["label"], sha256=v.get("sha256"), applies=v.get("applies", {}),
                                      source=v.get("source")))
    declared = data.get("benchmark", {}).get("history")  # a `via` profile (D.4.4) has no [benchmark] table
    history = load_history_table(str(declared["table"]["path"]), str(declared["table"]["sha256"])) if declared else None
    if history is not None and history.repo != declared["repo"]:
        raise ProfileError(f"profile {profile.id!r}: the history table is for {history.repo}, not {declared['repo']}")
    verified = data.get("harness", {}).get("verified_code", ())
    for v in verified:
        _check_facets(f"profile {profile.id!r} verified_code {v['commit'][:12]}", v.get("applies", {}), allowed)
    table = FamilyTable(data=data, quirks=tuple(quirks), layout=layout, table_rows=rows, part_rows=part_rows,
                        prompt_variants=tuple(variants),
                        history=history, verified_code=parse_verified_code(verified, f"profile {profile.id!r}"))
    from agentprov.adapters.agentdojo.quirks import check_profile_hooks  # the hook registry imports this module

    check_profile_hooks(profile.id, table)
    _CHECKED[profile.sha256] = table
    return table
