"""Provenance specifications: ``agentprov-prov/0.1`` and its rule catalogue ``aprov`` (EF E.0.3, E.3.3; MN M.1.2).

The catalogue is package data (``catalogue/agentprov-prov-0.1.toml``), read through :mod:`importlib.resources` only. Its
SHA-256 enters every derivation key (E.3.4). The frozen ``adprov-v2.3-compat`` profile is not a :class:`ProvSpec` of
this engine: it lives in :mod:`agentprov.prov.compat` and is imported lazily by its callers (M.5.2(3)).

**Lazy compat loader** (MN M.5.2(3); DECISIONS D-37). :func:`load_compat_spec` is the one place outside
``agentprov.migration`` and the tests that may import :mod:`agentprov.prov.compat`, and it does so only when
``adprov-v2.3-compat`` is explicitly requested (``derive --prov-spec adprov-v2.3-compat``). It returns the frozen oracle's
``CompatSpec`` object (``build``, ``serialise``, ``validate``); its output is a regression oracle
(:data:`REGRESSION_ORACLE`, R-55) and every caller that writes or loads it prints :func:`compat_notice`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex
from agentprov.prov.evidence import LETTER, EvidenceClass

__all__ = [  # noqa: F822  (AGENTPROV_PROV_0_1 is a lazy module attribute)
    "AGENTPROV_PROV_0_1",
    "CATALOGUE_FORMAT",
    "COMPAT_SPEC_ID",
    "KNOWN_SPECS",
    "REGRESSION_ORACLE",
    "SPEC_ID",
    "ProvRule",
    "ProvSpec",
    "SpecError",
    "compat_notice",
    "load_compat_spec",
    "load_spec",
    "parse_spec_catalogue",
]

SPEC_ID: Final = "agentprov-prov/0.1"
CATALOGUE_FORMAT: Final = "agentprov-prov-catalogue/0.1"
CATALOGUE_RESOURCE: Final = "catalogue/agentprov-prov-0.1.toml"
#: The frozen regression-oracle spec (EF E.8; R-55). Kept here as a string so that naming it imports nothing.
COMPAT_SPEC_ID: Final = "adprov-v2.3-compat"
#: Every provenance spec id this build can produce: the engine's and the frozen oracle.
KNOWN_SPECS: Final = (SPEC_ID, COMPAT_SPEC_ID)
#: The status of a regression-oracle output in the manifest (``oracle_specs``) and the index (``oracles``) (R-55).
REGRESSION_ORACLE: Final = "apv:RegressionOracle"


class SpecError(AgentProvError):
    """The engine catalogue is malformed (broken package data, exit 70)."""

    code = "prov.catalogue_invalid"


@dataclass(frozen=True, slots=True)
class ProvRule:
    id: str  # dotted, without @n
    version: int
    ceiling: EvidenceClass
    statement: str
    caps: Mapping[str, EvidenceClass] = field(default_factory=dict)
    assumptions_by_path: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return f"{self.id}@{self.version}"

    def cap(self, path: str | None) -> EvidenceClass:
        """The ceiling on ``path`` (a rule's per-path cap, never above the rule ceiling)."""
        if path is None:
            return self.ceiling
        return min(self.ceiling, self.caps.get(path, self.ceiling))


@dataclass(frozen=True, slots=True)
class ProvSpec:
    """``agentprov-prov/0.1``: the spec id, the ``aprov`` catalogue and its digest, and the vocabulary version."""

    id: str
    catalogue_id: str
    catalogue_version: int
    catalogue_sha256: str
    vocabulary_version: str
    rules: Mapping[str, ProvRule]

    def rule(self, rule_id: str) -> ProvRule:
        found = self.rules.get(rule_id)
        if found is None:
            raise SpecError(f"rule {rule_id} is not in the {self.catalogue_id} catalogue")
        return found

    @property
    def plan(self) -> str:
        """The plan entity of the derive activity: ``rules:agentprov-prov.0.1``."""
        return "rules:" + self.id.replace("/", ".")


def parse_spec_catalogue(data: bytes, *, source: str = "<bytes>") -> ProvSpec:
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SpecError(f"{source}: not valid TOML/UTF-8") from exc
    head = doc.get("catalogue")
    if not isinstance(head, dict) or head.get("format") != CATALOGUE_FORMAT or head.get("id") != "aprov":
        raise SpecError(f"{source}: not an aprov catalogue")
    rules: dict[str, ProvRule] = {}
    for table in doc.get("rule", []):
        rid, ver, ceiling = table.get("id"), table.get("version"), table.get("ceiling")
        if not (isinstance(rid, str) and rid.startswith("aprov.") and isinstance(ver, int) and ceiling in LETTER):
            raise SpecError(f"{source}: malformed rule {rid!r}")
        caps = {str(k): LETTER[str(v)] for k, v in dict(table.get("caps", {})).items()}
        by_path = {str(k): tuple(str(a) for a in v) for k, v in dict(table.get("assumptions_by_path", {})).items()}
        rule = ProvRule(rid, ver, LETTER[ceiling], str(table.get("statement", "")), caps, by_path)
        if rule.rule_id in rules:
            raise SpecError(f"{source}: duplicate rule {rule.rule_id}")
        rules[rule.rule_id] = rule
    return ProvSpec(
        id=str(head.get("spec", SPEC_ID)),
        catalogue_id="aprov",
        catalogue_version=int(head["version"]),
        catalogue_sha256=sha256_hex(data),
        vocabulary_version=str(head.get("vocabulary", "")),
        rules=dict(sorted(rules.items())),
    )


def archived_catalogue_sha256(version: int) -> str | None:
    """The sha256 of the archived ``aprov`` catalogue at ``version`` (``catalogue/archive/agentprov-prov-0.1.v<n>.toml``,
    kept byte-exact because stored corpora record it; D-621, D-31), else ``None``. A digest authority, not a loadable
    spec: derivation always uses the current catalogue."""
    node = resources.files("agentprov.prov") / "catalogue" / "archive" / f"agentprov-prov-0.1.v{int(version)}.toml"
    try:
        return sha256_hex(node.read_bytes())
    except (FileNotFoundError, OSError):
        return None


@cache
def load_spec() -> ProvSpec:
    """``agentprov-prov/0.1`` from package resources (cached; pure data)."""
    data = (resources.files("agentprov.prov") / CATALOGUE_RESOURCE).read_bytes()
    return parse_spec_catalogue(data, source=f"agentprov.prov:{CATALOGUE_RESOURCE}")


def __getattr__(name: str) -> ProvSpec:  # lazy module attribute: the catalogue is read on first use only
    if name == "AGENTPROV_PROV_0_1":
        return load_spec()
    raise AttributeError(name)


def load_compat_spec() -> Any:
    """The frozen ``adprov-v2.3-compat`` spec object, imported lazily (M.5.2(3); see the module docstring).

    The import is cheap: the oracle modules load only when a method of the returned object is called."""
    from agentprov.prov.compat.adprov_v2_3 import SPEC

    return SPEC


def compat_notice() -> str:
    """The notice printed whenever ``adprov-v2.3-compat`` output is written or loaded (R-55; Q.30)."""
    from agentprov.prov.compat.adprov_v2_3 import NOTICE

    return str(NOTICE)
