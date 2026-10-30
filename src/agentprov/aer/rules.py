"""Rule references and rule catalogues (C.6.4; format owner D.5.1-D.5.2).

A *rule reference* is ``<ns>.<rule>@<n>`` optionally followed by ``#<JSON Pointer>`` that scopes it to a field
(grammar of C.6.4); the *rule id* is the reference without ``#...``. A *catalogue* is a TOML file
``<ns>.rules.toml`` with ``[catalogue] id = "<ns>"``, an integer ``version`` and one ``[[rule]]`` table per rule.

Catalogues are package data, read through :mod:`importlib.resources`; a corpus's copy under ``rules/`` is a
record, never an authority, and is never loaded here (AD-14). :class:`RuleRegistry` resolves the catalogues
named by an execution header (``rules: {"<ns>": <int>}``) and answers class and declaration questions for the
validator, the writer, SEM and the provenance engine.

Archived versions: the *current* catalogue is ``<home>/rules/<ns>.rules.toml``. A superseded integer version that
the package still ships (D.5.1: "the package ships every released version") lives at
``<home>/rules/archive/<ns>.rules.v<version>.toml``. (The specification fixes the current path only; the archive
path is this implementation's resolution.)
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import resources
from types import MappingProxyType
from typing import Final

from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex

__all__ = [
    "CATALOGUE_FORMAT",
    "CATALOGUE_HOMES",
    "RULE_ID_RE",
    "RULE_REF_RE",
    "CatalogueError",
    "CatalogueUnavailableError",
    "RuleCatalogue",
    "RuleEntry",
    "RuleRef",
    "RuleRegistry",
    "Verification",
    "load_catalogue",
    "parse_catalogue",
    "parse_rule_ref",
    "rule_id_of",
]

CATALOGUE_FORMAT: Final = "agentprov-rule-catalogue/0.1"
#: C.6.4 grammar, verbatim.
RULE_REF_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+@[1-9][0-9]*(?:#/.*)?", re.DOTALL)
RULE_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+@[1-9][0-9]*")
_RULE_NAME_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_NS_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_COMMIT_RE: Final = re.compile(r"[0-9a-f]{40}")
_ASSUMPTION_RE: Final = re.compile(r"(?:apv:[A-Za-z][A-Za-z0-9]*|[a-z][a-z0-9_]*:[A-Za-z][A-Za-z0-9]*)")

#: Catalogue homes that break the convention (D.5.1 homes). By convention, namespace ``<ns>`` is shipped by the adapter
#: family package of the same name, as ``agentprov/adapters/<ns>/rules/<ns>.rules.toml`` (found as package data, so a
#: new adapter family needs no entry here, DoD Q.3). This table lists only the core namespaces and the namespaces that
#: live in another family's package.
CATALOGUE_HOMES: Final[Mapping[str, str]] = {
    "aer": "agentprov.aer",
    "corpus": "agentprov.corpus",
    # C.6.4 home of `cap`: the capture distribution ships it (agentprov_capture/rules/cap.rules.toml); read as package
    # data through importlib.resources, never imported as code by this module (phase 8, D.10.4a).
    "cap": "agentprov_capture",
    "rope": "agentprov.adapters.agentdojo",
    "agentdyn": "agentprov.adapters.agentdojo",
    "drift": "agentprov.adapters.agentdojo",
    "mandate": "agentprov.adapters.agentdojo",
    "survey": "agentprov.adapters.agentdojo",
    "autodojo": "agentprov.adapters.agentdojo",
    "rescont": "agentprov.adapters.agentdojo",  # phase 10q results containers (D-472, routed R-10q-3)
    "defence": "agentprov.adapters.agentdojo",  # live defended pipelines (D-670, D-677; invariant-5 note in AGENTS.md)
    "anthropic_messages": "agentprov.adapters.agentdojo",  # the Anthropic Messages wire of live captures (D-656)
}


class CatalogueError(AgentProvError):
    """A catalogue file is malformed or violates the self-test of D.5.2 (broken package data, exit 70)."""

    code = "rules.catalogue_invalid"


class CatalogueUnavailableError(AgentProvError):
    """The requested catalogue or integer version is not shipped in the package (AD-14 ``rules.unavailable``)."""

    code = "rules.unavailable"
    exit_code = 3


@dataclass(frozen=True, slots=True)
class RuleRef:
    """A parsed rule reference."""

    namespace: str
    name: str  # the dotted rule name after the namespace, e.g. ``acc.reported_counts``
    version: int
    pointer: str | None = None

    @property
    def rule_id(self) -> str:
        """The reference without ``#...``: ``<ns>.<name>@<n>``."""
        return f"{self.namespace}.{self.name}@{self.version}"

    @property
    def text(self) -> str:
        return self.rule_id if self.pointer is None else f"{self.rule_id}#{self.pointer}"


def rule_id_of(ref: str) -> str:
    """The rule id of a reference (the part before ``#``)."""
    return ref.split("#", 1)[0]


def parse_rule_ref(ref: str) -> RuleRef:
    """Parse a reference by the grammar of C.6.4; ``ValueError`` when it does not match."""
    if RULE_REF_RE.fullmatch(ref) is None:
        raise ValueError("not a rule reference")
    head, sep, pointer = ref.partition("#")
    dotted, _, version = head.partition("@")
    namespace, _, name = dotted.partition(".")
    return RuleRef(namespace, name, int(version), pointer if sep else None)


@dataclass(frozen=True, slots=True)
class Verification:
    """One ``verification`` entry of a rule: the status of one assumption (D.5.2)."""

    assumption: str
    status: str  # "verified" | "asserted"
    framework_identity: tuple[str, ...] = ()
    code_ref: str = ""
    test: str = ""


@dataclass(frozen=True, slots=True)
class RuleEntry:
    """One immutable rule of a catalogue."""

    id: str  # dotted, without @n
    version: int
    cls: str  # "D" | "I"
    status: str  # "active" | "superseded" | "reserved"
    statement: str
    premises: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    verification: tuple[Verification, ...] = ()
    emits: tuple[str, ...] = ()

    @property
    def rule_id(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def citable(self) -> bool:
        """A rule that is ``reserved`` (a planned name) is not citable in an AER."""
        return self.status in ("active", "superseded")

    def verified_identities(self) -> tuple[str, ...]:
        """Framework identities named by this rule's ``verified`` assumptions (D.5.2 validation item 3)."""
        return tuple(i for v in self.verification if v.status == "verified" for i in v.framework_identity)


@dataclass(frozen=True, slots=True)
class RuleCatalogue:
    """A loaded catalogue (immutable)."""

    namespace: str
    version: int
    format: str
    issue_codes: frozenset[str]
    subtypes: frozenset[str]
    types: frozenset[str]
    rules: Mapping[str, RuleEntry]  # keyed by rule id ``<id>@<n>``
    assumptions: frozenset[str] = frozenset()
    digest: str = ""  # SHA-256 of the file bytes (``rules.mismatch`` compares it with a corpus copy)
    source: str = ""

    def get(self, rule_id: str) -> RuleEntry | None:
        return self.rules.get(rule_id)

    def declares_issue_code(self, code: str) -> bool:
        """``code`` is ``<ns>.<code>`` with this namespace and ``<code>`` listed in ``issue_codes``."""
        ns, _, tail = code.partition(".")
        return ns == self.namespace and tail in self.issue_codes


def _tuple_str(table: Mapping[str, object], key: str, where: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise CatalogueError(f"{where}: {key!r} must be an array of strings")
    return tuple(value)


def parse_catalogue(data: bytes, *, source: str = "<bytes>") -> RuleCatalogue:
    """Parse and self-test a catalogue (D.5.2 validation items 1-5); ``CatalogueError`` on any violation."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise CatalogueError(f"{source}: not valid TOML/UTF-8") from exc
    head = doc.get("catalogue")
    if not isinstance(head, dict):
        raise CatalogueError(f"{source}: missing [catalogue] table")
    namespace, version = head.get("id"), head.get("version")
    if not isinstance(namespace, str) or _NS_RE.fullmatch(namespace) is None:
        raise CatalogueError(f"{source}: catalogue id must be the bare namespace")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise CatalogueError(f"{source}: catalogue version must be a positive integer")
    fmt = head.get("format", CATALOGUE_FORMAT)
    if fmt != CATALOGUE_FORMAT:
        raise CatalogueError(f"{source}: unsupported catalogue format")
    declared = doc.get("assumption", [])
    declared_ids = frozenset(str(a["id"]) for a in declared if isinstance(a, dict) and isinstance(a.get("id"), str))
    rules: dict[str, RuleEntry] = {}
    for index, table in enumerate(doc.get("rule", [])):
        where = f"{source}: rule #{index}"
        if not isinstance(table, dict):
            raise CatalogueError(f"{where}: not a table")
        rid, rver = table.get("id"), table.get("version")
        if not isinstance(rid, str) or _RULE_NAME_RE.fullmatch(rid) is None or rid.split(".", 1)[0] != namespace:
            raise CatalogueError(f"{where}: id must be <namespace>.<name>")
        if not isinstance(rver, int) or isinstance(rver, bool) or rver < 1:
            raise CatalogueError(f"{where}: version must be a positive integer")
        key = f"{rid}@{rver}"
        if key in rules:
            raise CatalogueError(f"{where}: duplicate rule id {key}")  # item 1
        cls = table.get("class")
        if cls not in ("D", "I"):
            raise CatalogueError(f"{where}: class must be D or I")  # item 2
        status = table.get("status", "active")
        if status not in ("active", "superseded", "reserved"):
            raise CatalogueError(f"{where}: bad status")
        assumptions = _tuple_str(table, "assumptions", where)
        verification: list[Verification] = []
        for v in table.get("verification", []):
            if not isinstance(v, dict) or v.get("status") not in ("verified", "asserted"):
                raise CatalogueError(f"{where}: verification status must be verified or asserted")
            identity = _tuple_str(v, "framework_identity", where)
            if v["status"] == "verified" and not (identity and v.get("code_ref") and v.get("test")):
                raise CatalogueError(f"{where}: a verified assumption needs framework_identity, code_ref and test")
            verification.append(
                Verification(str(v.get("assumption", "")), v["status"], identity, str(v.get("code_ref", "")), str(v.get("test", "")))
            )
        by_assumption = {v.assumption: v for v in verification}
        for assumption in assumptions:  # item 3
            if _ASSUMPTION_RE.fullmatch(assumption) is None or (
                not assumption.startswith("apv:") and assumption not in declared_ids
            ):
                raise CatalogueError(f"{where}: assumption {assumption!r} is neither core nor declared")
            if assumption not in by_assumption:
                raise CatalogueError(f"{where}: assumption {assumption!r} needs exactly one verification entry")
        if len(by_assumption) != len(verification):
            raise CatalogueError(f"{where}: more than one verification entry for an assumption")
        if cls == "D" and any(by_assumption[a].status != "verified" for a in assumptions):  # item 4
            raise CatalogueError(f"{where}: a class-D rule may have only verified assumptions")
        for code in table.get("code", []):  # item 5
            if not isinstance(code, dict) or not _COMMIT_RE.fullmatch(str(code.get("commit", ""))):
                raise CatalogueError(f"{where}: every code entry names a full 40-hex commit")
        rules[key] = RuleEntry(
            id=rid,
            version=rver,
            cls=cls,
            status=status,
            statement=str(table.get("statement", "")),
            premises=_tuple_str(table, "premises", where),
            assumptions=assumptions,
            verification=tuple(verification),
            emits=_tuple_str(table, "emits", where),
        )
    return RuleCatalogue(
        namespace=namespace,
        version=version,
        format=fmt,
        issue_codes=frozenset(_tuple_str(head, "issue_codes", source)),
        subtypes=frozenset(_tuple_str(head, "subtypes", source)),
        types=frozenset(_tuple_str(head, "types", source)),
        rules=MappingProxyType(dict(sorted(rules.items()))),  # read-only: the D-410 cache shares it (BF-5)
        assumptions=declared_ids,
        digest=sha256_hex(data),
        source=source,
    )


#: Parsed catalogues by ``(source, sha256 of the bytes)``. :func:`parse_catalogue` is a pure function of those two and
#: returns an immutable catalogue, so a cache keyed by them cannot change a result (G.4.7: module-level caches are pure
#: functions of their inputs). The bytes are still read on every load, so changed bytes are parsed again. Mapping cites
#: rules record by record, which otherwise parsed the TOML some twenty times per execution.
_PARSED: dict[tuple[str, str], RuleCatalogue] = {}


def _parse_cached(data: bytes, source: str) -> RuleCatalogue:
    key = (source, sha256_hex(data))
    catalogue = _PARSED.get(key)
    if catalogue is None:
        catalogue = _PARSED[key] = parse_catalogue(data, source=source)
    return catalogue


def _read_resource(package: str, relative: str) -> bytes | None:
    try:
        if package.startswith("agentprov.adapters."):  # package data only: never import an adapter family (D.2.1)
            node = resources.files("agentprov").joinpath("adapters", package.removeprefix("agentprov.adapters."))
        else:
            node = resources.files(package)
    except (ModuleNotFoundError, TypeError):
        return None
    for part in relative.split("/"):
        node = node / part
    try:
        return node.read_bytes() if node.is_file() else None
    except OSError:
        return None


def load_catalogue(namespace: str, version: int | None = None, *, package: str | None = None) -> RuleCatalogue:
    """Load the catalogue ``namespace`` from package resources (never from a corpus copy, AD-14).

    ``version`` selects an integer version: the current file if it matches, else the archived file. ``None``
    means the current one. :class:`CatalogueUnavailableError` (``rules.unavailable``) when the package does not
    ship it.
    """
    if _NS_RE.fullmatch(namespace) is None:
        raise CatalogueUnavailableError(f"no catalogue home is known for namespace {namespace!r}")
    home = package or CATALOGUE_HOMES.get(namespace) or f"agentprov.adapters.{namespace}"
    candidates = [f"rules/{namespace}.rules.toml"]
    if version is not None:
        candidates.append(f"rules/archive/{namespace}.rules.v{version}.toml")
    for relative in candidates:
        data = _read_resource(home, relative)
        if data is None:
            continue
        catalogue = _parse_cached(data, f"{home}:{relative}")
        if catalogue.namespace != namespace:
            raise CatalogueError(f"{relative}: catalogue id does not match its file name")
        if version is None or catalogue.version == version:
            return catalogue
    raise CatalogueUnavailableError(f"catalogue {namespace!r} version {version} is not shipped")


class RuleRegistry:
    """The catalogues a producer or validator works with, keyed by ``(namespace, version)``.

    Catalogues are added explicitly (tests, adapters supplying theirs) or autoloaded from package resources on
    first use (:func:`load_catalogue`). Autoload failures raise :class:`CatalogueUnavailableError`; they are
    cached as absent so a missing catalogue is reported consistently.
    """

    def __init__(
        self,
        catalogues: Iterable[RuleCatalogue] = (),
        *,
        autoload: bool = True,
        loader: Callable[[str, int | None], RuleCatalogue] | None = None,
    ) -> None:
        self._catalogues: dict[tuple[str, int], RuleCatalogue] = {}
        self._missing: set[tuple[str, int]] = set()
        self._autoload = autoload
        self._loader = loader or (lambda ns, ver: load_catalogue(ns, ver))
        for catalogue in catalogues:
            self.add(catalogue)

    def add(self, catalogue: RuleCatalogue) -> None:
        key = (catalogue.namespace, catalogue.version)
        self._catalogues[key] = catalogue
        self._missing.discard(key)

    def get(self, namespace: str, version: int) -> RuleCatalogue:
        key = (namespace, version)
        found = self._catalogues.get(key)
        if found is not None:
            return found
        if self._autoload and key not in self._missing:
            try:
                catalogue = self._loader(namespace, version)
            except CatalogueUnavailableError:
                self._missing.add(key)
            else:
                self.add(catalogue)
                return catalogue
        raise CatalogueUnavailableError(f"catalogue {namespace!r} version {version} is not available")

    def has(self, namespace: str, version: int) -> bool:
        try:
            self.get(namespace, version)
        except CatalogueUnavailableError:
            return False
        return True

    def lookup(self, rule_id: str, declared: Mapping[str, int]) -> RuleEntry | None:
        """The entry for ``rule_id`` in the catalogue ``declared`` names for its namespace, else ``None``."""
        if RULE_ID_RE.fullmatch(rule_id) is None:
            return None
        namespace = rule_id.split(".", 1)[0]
        version = declared.get(namespace)
        if version is None:
            return None
        try:
            catalogue = self.get(namespace, version)
        except CatalogueUnavailableError:
            return None
        return catalogue.get(rule_id)

    @classmethod
    def default(cls) -> RuleRegistry:
        """A registry that autoloads every catalogue the package ships."""
        return cls()
