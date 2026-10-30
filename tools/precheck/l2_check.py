"""Level 2 of the corpus pre-check: the checks of a scratch corpus imported by ``l2_import.py`` (README §4).

    uv run python tools/precheck/l2_check.py --corpus DIR.partial --out l2-<part>.json [--sample SAMPLE.json]
        [--l1-units l1-units-<part>.jsonl] [--compare-with OTHER.partial] [--no-commands] [--jobs N]
        [--tiers aer,sem,prov,linkage,shacl,regression] [--seal]

Run it through the queue like the import (README §4). Read-only on the scratch corpus (``--seal`` works on a copy). The
report holds counts, codes, rule ids, labels, model and arm names and normalised JSON pointers only: never source text,
never a secret-like value or an account path (both are masked before anything is written).

**From the corpus** (product readers: ``CorpusReader``, ``read_aer``, ``read_prov``, ``ProvView``):

* ``executions``: index rows by status, completeness, unit, observed; degenerate (a seal issue in
  ``unparseable_artefact``/``unsupported_variant``/``adapter_defect``) and ``adapter_defect``; stage states; validation
  checks that failed (``validation/results.jsonl``); register codes; unreadable AERs.
* ``issues``: executions per index issue code; AER seal issue codes.
* ``evidence``: PROV statements by bundle kind (top/core/inference/assessment) and class (O/D/I/none); the statements
  that rest on an ``_unverified`` twin (an ``apv:basisRule`` id containing ``_unverified``, or an inference bundle whose
  method is one).
* ``a3`` (PI classes): ``dangling`` (a relation argument naming no declared element, bundle or statement),
  ``missing_generation`` (an AER message with ``generated_by`` without a ``wasGeneratedBy`` of its entity),
  ``missing_use_request`` (a tool execution with ``call`` without a ``used`` by its activity), ``missing_use_input`` (a
  model call with inputs without a ``used`` by its activity), ``time_not_run_scope`` (PROV times on nodes other than a
  ``run`` scope, by AER record kind) and ``time_inferred`` (a PROV time whose AER time field is class I: forbidden,
  D-28 addendum), ``unexecuted`` (``unexecuted_tool_call`` parts with and without ``apv:NotDispatched``, read from
  the core and the inference bundles: D-80 addendum (d), POST-tool-01), ``forbidden``
  (``wasInfluencedBy`` anywhere, ``alternateOf``, and ``used``/``wasDerivedFrom``/``wasInformedBy``/``wasAttributedTo`` in
  an assessment bundle, NE-10), ``invented`` (a statement whose ``apv:rule`` is not in the engine catalogue ``aprov``, a
  bundle relation without a rule, and ``apv:basisRule`` ids no adapter catalogue the AER declares resolves).
* ``identity``: per execution the AER header's model (agent actors' ``/model``), defence, attack, suite, task and
  benchmark, joined to the label (primary raw object -> L1 ``sha256`` or the origin chain) and its L1 facets: pair tables
  (L1 facet value -> AER value) for the comparable facets, the L1 values that map to several AER values, and the direct
  mismatches (suite and attack, ``none``/``<none>``/null equal).
* ``redaction``: every AER, SEM, PROV, view, index, register, validation and raw-index file searched for account paths
  (``/Users/<x>/``, ``/home/<x>/``), the operator's own home path and host name (``tools/release_scan.py``
  ``personal_needles``) and secret-like shapes; counts by object kind, rule and normalised pointer, plus the executions
  hit. The raw store is not searched (raw ships as is, D-186 (c)); the L1 per-unit flags of the sampled labels are counted.
* ``withholding``: the profile's ``[withhold]`` policy (rule ids, kinds, scopes) and the product's own plan of it over this
  corpus (``agentprov.corpus.withhold.plan_withholding``, as ``package`` computes it; nothing is moved): objects and
  executions withheld.
* ``outcomes``: per arm (model | defence | attack) every boolean judgement (the latest one; ``harness_default`` origins
  counted apart) with n, k and the Wilson 95% interval (``tools/analysis2/exam2_lib.wilson``); for the AgentDojo-format
  dialects ``utility`` and ``attack_success`` (``security`` on attacked runs that are not injection-task pre-passes).

**Commands** (unless ``--no-commands``): ``agentprov validate --corpus`` (``--tiers``), ``agentprov verify --level chain``
on the working tree, ``agentprov recompute --dry-run`` run **in this process** under the ``AnyOf`` matcher shim (the
recorded selection of an ``any-glob`` import is the shim's marker string; without the shim a replay selects nothing),
the determinism comparison with ``--compare-with`` (``tools/agentdojo/phase10d_trial.py`` ``compare_corpora``: byte
identity of every file but logs, locks and ``derivation.json``), and with ``--seal`` an attempt to seal a copy
(``agentprov package``, generated scratch spec) and ``verify --level chain --release`` on it. ``package`` refuses a
partial corpus (any filter), a dev-mode validation and a dirty producer tree: the refusal is recorded as the result. The
scratch spec's snapshot origins are the ones ``package`` derives from the recorded pin (D-33, the product's own
functions), and its ``CARD.md`` carries the front matter and passes the card lint (H.9(3), H.9(5)).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from functools import cache
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (  # noqa: E402
    guard_output,
    ACCOUNT_PATH,
    CHECK_FORMAT,
    LOCAL_PATH_MODEL,
    REPO,
    SECRET_PATTERNS,
    guard_scratch,
    iter_strings,
    load_tool,
    personal_needles,
    pointer_text,
    read_jsonl,
    scrub,
    sha256_file,
    tilde,
    write_json,
)

DEGENERATE_CODES: Final = frozenset({"unparseable_artefact", "unsupported_variant", "adapter_defect"})
AGENTDOJO_DIALECTS: Final = frozenset({"agentdojo.tracelogger", "adprov.transcript_v1"})
ASSESS_FORBIDDEN: Final = frozenset({"used", "wasDerivedFrom", "wasInformedBy", "wasAttributedTo", "wasInfluencedBy"})
TIME_KEYS: Final = ("prov:startTime", "prov:endTime", "prov:time")
NONE_VALUES: Final = frozenset({"", "none", "<none>", "null"})
#: L1 facet keys compared with the AER header fields (first present key wins for the direct comparison).
FACETS: Final = {
    "suite": ("suite", "h_suite", "suite_name"),
    "attack": ("attack_dir", "h_attack", "attack", "attack_type"),
    "model": ("model", "h_model", "pipeline_dir", "h_pipeline", "model_dir", "model_folder", "results_dir"),
    "defence": ("defence", "defense", "pipeline_dir", "arm"),
}
DIRECT: Final = frozenset({"suite", "attack"})
_MAX_LIST: Final = 200
_MAX_PARSE: Final = 256 << 20


def _norm(value: Any) -> str:
    if value is None:
        return "none"
    text = str(value)
    if LOCAL_PATH_MODEL.search(text) or ACCOUNT_PATH.search(text.encode("utf-8", "replace")):
        return "<account-path>"
    return "none" if text.strip().lower() in NONE_VALUES else text


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


# ================================================================================================ sample and L1 rows
def bundle_rules(bundle: str | None) -> list[str]:
    """The rule refs of an inference-bundle id: ``xd:bundle.inf.<slug>[--<slug>...].<hash>`` with each slug the engine's
    ``iri.rule_slug`` (``<ns>.<name>@<n>`` -> ``<ns>-<name>-v<n>``), decoded back to ``<ns>.<name>@<n>``. Other ids
    give []. Namespaces hold no ``-`` (rule ids are ``<ns>.<name>``)."""
    if not bundle or ".inf." not in bundle:
        return []
    body = bundle.split(".inf.", 1)[1].rsplit(".", 1)[0]
    out: list[str] = []
    for slug in body.split("--"):
        ns, _, rest = slug.partition("-")
        name, sep, version = rest.rpartition("-v")
        if ns and sep and name and version.isdigit():
            out.append(f"{ns}.{name}@{version}")
    return out


def is_twin(ref: str) -> bool:
    """Whether a rule reference is an ``_unverified`` twin of a catalogued class-D rule (D.5.4), not a native class-I
    rule that merely has ``_unverified`` in its id."""
    from agentprov.adapters.code_verification import TWIN_SUFFIX

    name, _, version = ref.partition("#")[0].rsplit("/", 1)[-1].partition("@")
    name = name.rsplit(":", 1)[-1]
    if not name.endswith(TWIN_SUFFIX):
        return False
    return _rule_cls(name.removesuffix(TWIN_SUFFIX), version) == "D"


@cache
def _rule_cls(rule_id: str, version: str) -> str | None:
    """The class of ``<rule_id>@<version>`` (any version when ``version`` is empty), ``None`` when not catalogued."""
    from agentprov.aer.rules import CatalogueUnavailableError, load_catalogue

    try:
        catalogue = load_catalogue(rule_id.split(".", 1)[0])
    except CatalogueUnavailableError:
        return None
    entry = catalogue.get(f"{rule_id}@{version}") if version else next(
        (e for k, e in catalogue.rules.items() if k.partition("@")[0] == rule_id), None)  # fmt: skip
    return entry.cls if entry is not None else None


class SampleInfo:
    """The sample's labels, the L1 rows of those labels (facets, flags, sha256) and the sha256 -> label map."""

    def __init__(self, sample: Path | None, l1_units: Path | None) -> None:
        self.labels: set[str] = set()
        self.doc: dict[str, Any] = {}
        self.rows: dict[str, dict[str, Any]] = {}
        self.by_sha: dict[str, str] = {}
        if sample is not None:
            self.doc = json.loads(sample.read_text(encoding="utf-8"))
            self.labels = {str(x) for x in self.doc.get("labels", ())}
            for label, sha in (self.doc.get("sha256") or {}).items():
                self.by_sha[str(sha).removeprefix("sha256:")] = str(label)
        if l1_units is not None:
            for row in read_jsonl(l1_units):
                label = str(row.get("label"))
                if self.labels and label not in self.labels:
                    continue
                self.rows[label] = row
                if isinstance(row.get("sha256"), str):
                    self.by_sha.setdefault(str(row["sha256"]).removeprefix("sha256:"), label)


class LabelResolver:
    """Label of a raw object: the L1/sample sha256 map, else its origins (git/local path, archive chain labels)."""

    def __init__(self, origins: Sequence[Any], info: SampleInfo) -> None:
        self.info = info
        self.origins: dict[str, list[Any]] = defaultdict(list)
        for row in origins:
            self.origins[row.sha256].append(row.origin)
        self.memo: dict[str, str | None] = {}

    def __call__(self, sha: str, depth: int = 0) -> str | None:
        if sha in self.memo:
            return self.memo[sha]
        label = self.info.by_sha.get(sha)
        if label is None and depth < 8:
            for origin in self.origins.get(sha, ()):
                label = self._from_origin(origin, depth)
                if label is not None:
                    break
        self.memo[sha] = label
        return label

    def _from_origin(self, origin: Any, depth: int) -> str | None:
        data = origin.data
        kind = origin.kind
        wanted = self.info.labels
        if kind == "git":
            return str(data.get("path"))
        if kind == "local":
            path = str(data.get("path"))
            hit = next((label for label in wanted if path.endswith("/" + label)), None)
            return hit or path.rsplit("/", 1)[-1]
        if kind in ("zenodo", "hf", "split"):
            name = data.get("file") or data.get("path") or data.get("label")
            return str(name).rsplit("/", 1)[-1] if name else None
        if kind == "member":
            container = str(data.get("container"))
            parent = self(container, depth + 1)
            member = str(data.get("label"))
            root = any(o.kind in ("zenodo", "hf", "split") for o in self.origins.get(container, ()))
            chain = member if root or parent is None else f"{parent}!/{member}"
            if chain in wanted or parent not in wanted:
                return chain
            return parent  # a member of a container unit (an Inspect .eval's sample)
        return None


# ================================================================================================ PROV analysis
class ProvStats:
    """Aggregates over every PROV document of the corpus (evidence classes and the A3 PI classes)."""

    def __init__(self, engine_rules: set[str], rule_registry: Any) -> None:
        self.engine_rules = engine_rules
        self.registry = rule_registry
        self.evidence: Counter[str] = Counter()
        self.unverified: Counter[str] = Counter()
        self.native_unverified: Counter[str] = Counter()
        self.mixed_unverified: Counter[str] = Counter()
        self.pi: Counter[str] = Counter()
        self.pi_executions: dict[str, set[str]] = defaultdict(set)
        self.pi_detail: dict[str, Counter[str]] = defaultdict(Counter)
        self.examples: dict[str, list[str]] = defaultdict(list)
        self.checked: Counter[str] = Counter()  # the denominators of the PI classes
        self.documents = 0

    def _hit(self, cls: str, ex: str, label: str | None, detail: str | None = None, n: int = 1) -> None:
        self.pi[cls] += n
        self.pi_executions[cls].add(ex)
        if detail is not None:
            self.pi_detail[cls][detail] += n
        if len(self.examples[cls]) < 10:
            self.examples[cls].append(scrub(label or ex, 200))

    def add(self, ex: str, label: str | None, doc: Any, aer: Any) -> None:
        from agentprov.validate._provdoc import UNIDENTIFIED, ProvView

        self.documents += 1
        view = ProvView.parse(doc)
        declared = rules_of(aer.header)
        containers: list[tuple[str, list[Any]]] = [("top", view.top)]
        containers += [(b.kind, b.statements) for b in view.bundles.values()]
        unverified_bundles = {iri for iri in view.bundles if "_unverified" in iri}
        generated: set[str] = set()
        used_by: set[str] = set()
        for kind, statements in containers:
            for st in statements:
                cls = st.cls or "none"
                self.evidence[f"{kind}:{cls}"] += 1
                basis = [b for b in _as_list(st.attrs.get("apv:basisRule")) if isinstance(b, str)]
                # statement level: the statement's apv:basisRule refs; the bundle's method set (decoded) only when the
                # basis names no _unverified rule. A twin restates a catalogued D rule (D.5.4); a native class-I rule
                # merely has _unverified in its id. Three-way split (CC-08): twin only, native only, mixed (both)
                refs = [r for r in basis if "_unverified" in r]
                if not refs and st.bundle in unverified_bundles:
                    refs = [r for r in bundle_rules(st.bundle) if "_unverified" in r]
                if refs:
                    twins = sum(1 for r in refs if is_twin(r))
                    if twins == len(refs):
                        self.unverified[f"{kind}:{cls}"] += 1
                    elif twins == 0:
                        self.native_unverified[f"{kind}:{cls}"] += 1
                    else:
                        self.mixed_unverified[f"{kind}:{cls}"] += 1
                if kind in ("core", "inference") and st.section == "wasGeneratedBy" and st.arg("prov:entity"):
                    generated.add(str(st.arg("prov:entity")))
                if kind in ("core", "inference") and st.section == "used" and st.arg("prov:activity"):
                    used_by.add(str(st.arg("prov:activity")))
                self._statement(ex, label, kind, st, view, declared, UNIDENTIFIED, aer)
        self._completeness(ex, label, aer, generated, used_by)
        self._unexecuted(ex, label, aer, view)

    def _statement(self, ex: str, label: str | None, kind: str, st: Any, view: Any, declared: Mapping[str, int],
                   unidentified: frozenset[str], aer: Any) -> None:
        if not st.is_element:
            for key, value in st.args().items():
                self.checked["relation_arguments"] += 1
                if key in ("prov:generation", "prov:usage"):
                    ok = value in view.by_key
                elif key == "prov:bundle":
                    ok = value in view.bundles or value in view.top_elements
                else:
                    ok = value in view.elements or value in view.top_elements or value in view.bundles
                if not ok:
                    self._hit("dangling", ex, label, f"{st.section}:{key}")
        if st.section in ("wasInfluencedBy", "alternateOf"):
            self._hit("forbidden", ex, label, st.section)
        elif kind == "assessment" and st.section in ASSESS_FORBIDDEN:
            self._hit("forbidden", ex, label, f"assessment:{st.section}")
        rule = st.rule
        if rule is not None and rule not in self.engine_rules:
            self._hit("invented", ex, label, f"rule:{rule}")
        elif rule is None and kind != "top" and not st.is_element and st.section not in unidentified:
            self._hit("invented", ex, label, f"no_rule:{st.section}")
        for basis in _as_list(st.attrs.get("apv:basisRule")):
            if isinstance(basis, str) and self.registry.lookup(basis, declared) is None:
                self._hit("invented", ex, label, f"basis_unresolved:{basis}")
        self.checked["statements"] += 1
        times = [k for k in TIME_KEYS if k in st.attrs]
        if times:
            self.checked["statements_with_time"] += 1
            rid = _aer_id(st)
            record = aer.get(rid) if rid else None
            rec_kind = "unknown" if record is None else str(record.get("k"))
            if record is not None and rec_kind == "scope" and record.get("kind") == "run":
                self.pi["time_run_scope"] += 1
            else:
                sub = f"{rec_kind}:{record.get('kind')}" if record is not None and rec_kind == "scope" else rec_kind
                self._hit("time_not_run_scope", ex, label, f"{st.section}:{sub}")
            if record is not None and _time_class(record) == "I":
                self._hit("time_inferred", ex, label, f"{st.section}:{rec_kind}")

    def _completeness(self, ex: str, label: str | None, aer: Any, generated: set[str], used_by: set[str]) -> None:
        for record in aer.records:
            k, rid = record.get("k"), str(record.get("id"))
            if k == "message" and record.get("generated_by"):
                self.checked["messages_with_generated_by"] += 1
                if f"x:{rid}" not in generated:
                    self._hit("missing_generation", ex, label, str(record.get("role")))
            elif k == "tool_execution" and record.get("call"):
                self.checked["tool_executions_with_call"] += 1
                if f"x:{rid}" not in used_by:
                    self._hit("missing_use_request", ex, label)
            elif k == "model_call" and record.get("input"):
                self.checked["model_calls_with_input"] += 1
                if f"x:{rid}" not in used_by:
                    self._hit("missing_use_input", ex, label)

    def _unexecuted(self, ex: str, label: str | None, aer: Any, view: Any) -> None:
        """Each ``unexecuted_tool_call`` part needs an ``apv:dispatchStatus apv:NotDispatched`` on its node, in the core
        bundle or in an inference-bundle mention: D-80 addendum (d) (regeneration-batch item 103) puts it in the
        inference bundle where the unexecuted rule is the ``_unverified`` twin (POST-tool-01). ``by`` of
        ``unexecuted_represented`` counts where it was found."""
        from agentprov.validate._provdoc import qname_value

        found: dict[str, list[tuple[str, str | None]]] = defaultdict(list)  # node key -> (bundle kind, status)
        for bundle in view.bundles.values():
            if bundle.kind in ("core", "inference"):
                for st in bundle.statements:
                    if st.is_element:
                        found[st.key].append((bundle.kind, qname_value(st.attrs.get("apv:dispatchStatus"))))
        for issue in aer.seal.get("issues", ()):
            if not isinstance(issue, dict) or issue.get("code") != "unexecuted_tool_call":
                continue
            for pid in issue.get("ids", ()):
                self.checked["unexecuted_call_parts"] += 1
                nodes = found.get(f"x:{str(pid).replace('#', '-')}", [])
                where = sorted({kind for kind, status in nodes if status == "apv:NotDispatched"})
                if where:
                    self.pi["unexecuted_represented"] += 1
                    self.pi_detail["unexecuted_represented"]["+".join(where)] += 1
                else:
                    statuses = sorted({str(status) for _kind, status in nodes})
                    self._hit("unexecuted_missing", ex, label, "no_node" if not nodes else ",".join(statuses))

    def to_json(self) -> dict[str, Any]:
        return {
            "documents": self.documents, "checked": dict(sorted(self.checked.items())),
            "evidence_by_bundle_class": dict(sorted(self.evidence.items())),
            "unverified_twin_by_bundle_class": dict(sorted(self.unverified.items())),
            "native_unverified_rule_by_bundle_class": dict(sorted(self.native_unverified.items())),
            "mixed_twin_and_native_by_bundle_class": dict(sorted(self.mixed_unverified.items())),
            "unverified_split_rule": "statement level: apv:basisRule refs, else the decoded inference-bundle method set; "
                                     "twin = restates a catalogued D rule (D.5.4); native = class-I rule with _unverified "
                                     "in its id; mixed = both (CC-08, 2026-10-15)",
            "a3": {cls: {"count": n, "executions": len(self.pi_executions.get(cls, ())),
                         "by": dict(self.pi_detail[cls].most_common(40)), "examples": self.examples.get(cls, [])}
                   for cls, n in sorted(self.pi.items())},
        }


def rules_of(header: Mapping[str, Any]) -> dict[str, int]:
    rules = header.get("rules")
    return {str(k): int(v) for k, v in rules.items()} if isinstance(rules, Mapping) else {}


def _aer_id(st: Any) -> str | None:
    """The AER record id a PROV statement is about: an ``x:<id>`` element, else its ``apv:sourcePointer`` head."""
    if st.is_element and st.key.startswith("x:"):
        return str(st.key[2:]).split(".", 1)[0]
    pointer = st.attrs.get("apv:sourcePointer")
    if isinstance(pointer, str) and pointer:
        return pointer.split("/", 1)[0]
    return None


def _time_class(record: Mapping[str, Any]) -> str | None:
    found = record.get("evf")
    evf: Mapping[str, Any] = found if isinstance(found, Mapping) else {}
    for pointer in ("/t/start", "/t/end", "/t"):
        if pointer in evf:
            return str(evf[pointer])
    return str(record.get("ev")) if record.get("ev") is not None else None


# ================================================================================================ per execution
def degenerate_of(codes: Iterable[str]) -> bool:
    return any(code.removeprefix("map.") in DEGENERATE_CODES for code in codes)


def identity_of(aer: Any) -> dict[str, str]:
    task = aer.header.get("task") if isinstance(aer.header.get("task"), Mapping) else {}
    models: set[str] = set()
    for record in aer.of_kind("actor"):
        model = record.get("model")
        if isinstance(model, Mapping) and "agent" in str(record.get("kind")):
            value = model.get("served") or model.get("requested")
            if value:
                models.add(str(value))
    return {
        "model": "+".join(sorted(_norm(m) for m in models)) if models else "none",
        "defence": _norm(task.get("defense_id")), "attack": _norm(task.get("attack_id")),
        "suite": _norm(task.get("suite")), "task": _norm(task.get("task_id")), "benchmark": _norm(task.get("benchmark")),
    }


def judgements_of(aer: Any) -> tuple[dict[str, bool], int]:
    """The latest boolean judgement per name (revised ones dropped); ``harness_default`` ones are counted apart."""
    records = aer.of_kind("judgement")
    revised = {str(r.get("revises")) for r in records if r.get("revises")}
    out: dict[str, bool] = {}
    defaults = 0
    for record in records:
        if str(record.get("id")) in revised or not isinstance(record.get("value"), bool):
            continue
        if record.get("origin") == "harness_default":
            defaults += 1
            continue
        out[str(record.get("name"))] = bool(record["value"])
    return out, defaults


class Outcomes:
    def __init__(self) -> None:
        self.cells: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        self.harness_default = 0

    def add(self, identity: Mapping[str, str], dialect: str, values: Mapping[str, bool], defaults: int) -> None:
        self.harness_default += defaults
        arm = f"{identity['model']}|{identity['defence']}|{identity['attack']}"
        cell = self.cells[arm]
        for name, value in values.items():
            cell[name][0] += int(value)
            cell[name][1] += 1
        if dialect in AGENTDOJO_DIALECTS:
            prepass = identity["task"].startswith("injection_task")
            if prepass:
                cell["prepass_runs"][1] += 1
                return
            if "utility" in values:
                cell["utility_user_tasks"][0] += int(values["utility"])
                cell["utility_user_tasks"][1] += 1
            if identity["attack"] != "none" and "security" in values:
                cell["attack_success"][0] += int(values["security"])
                cell["attack_success"][1] += 1

    def to_json(self) -> dict[str, Any]:
        wilson = load_tool("analysis2/exam2_lib.py", "precheck_dep_exam2_lib").wilson
        table: dict[str, Any] = {}
        for arm in sorted(self.cells):
            row: dict[str, Any] = {}
            for name, (k, n) in sorted(self.cells[arm].items()):
                if name == "prepass_runs":
                    row[name] = n
                    continue
                low, high = wilson(k, n)
                row[name] = {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
                             "wilson95": [round(low, 4), round(high, 4)]}
            table[arm] = row
        return {"arm_key": "model|defence|attack", "harness_default_judgements_excluded": self.harness_default,
                "note": "AgentDojo format: utility_user_tasks = utility without the injection-task pre-passes; "
                        "attack_success = security on attacked runs that are not pre-passes (security of a benign run "
                        "is the runner's constant); the other names are the raw judgements of every run in the arm",
                "arms": table}


# ================================================================================================ redaction
class Redaction:
    def __init__(self) -> None:
        needles = personal_needles()
        self.needles = [(rule, n) for rule, items in needles.items() for n in items]
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.executions: dict[str, set[str]] = defaultdict(set)
        self.files = 0
        self.unparsed: Counter[str] = Counter()

    def _rules(self, data: bytes) -> list[tuple[str, int]]:
        found = [("account-path", len(ACCOUNT_PATH.findall(data)))]
        found += [(f"operator-{rule}", data.count(needle)) for rule, needle in self.needles]
        found += [(f"secret:{name}", len(p.findall(data))) for name, p in SECRET_PATTERNS.items()]
        return [(r, n) for r, n in found if n]

    def scan_file(self, kind: str, path: Path, ex: str | None) -> None:
        self.files += 1
        data = path.read_bytes() if path.stat().st_size <= _MAX_PARSE else None
        if data is None:
            self.unparsed[kind] += 1
            return
        if not self._rules(data):
            return
        if ex is not None:
            self.executions[kind].add(ex)
        values: list[tuple[str, Any]] = []
        if path.name.endswith(".jsonl"):
            for line in data.splitlines():
                if line.strip():
                    try:
                        value = json.loads(line)
                    except ValueError:
                        self.unparsed[kind] += 1
                        continue
                    prefix = str(value.get("k")) if kind == "aer" and isinstance(value, dict) else ""
                    values.append((prefix, value))
        else:
            try:
                values.append(("", json.loads(data)))
            except ValueError:
                for rule, n in self._rules(data):
                    self.counts[kind][f"{rule} <unparsed>"] += n
                return
        for prefix, value in values:
            for pointer, text, is_key in iter_strings(value):
                hits = self._rules(text.encode("utf-8", "surrogatepass"))
                for rule, n in hits:
                    where = (prefix + ":" if prefix else "") + pointer_text(pointer) + (" (key)" if is_key else "")
                    self.counts[kind][f"{rule} {where}"] += n

    def to_json(self) -> dict[str, Any]:
        return {"files_scanned": self.files, "files_too_large": dict(self.unparsed),
                "hits": {kind: dict(sorted(c.items())) for kind, c in sorted(self.counts.items())},
                "executions_hit": {kind: len(v) for kind, v in sorted(self.executions.items())},
                "note": "account-path matches benchmark fiction too (/home/user in sandboxes): read the pointer; "
                        "operator-* hits are the operator's own home path or host name and are always findings"}


def _object_kind(rel: str) -> str | None:
    if rel.startswith("raw/objects/") or rel.startswith(("logs/", "raw/tmp/")) or rel.endswith(".lock"):
        return None
    if rel.startswith(("aer/", "sem/", "prov/", "views/", "validation/")):
        return rel.split("/", 1)[0]
    return {"executions.jsonl": "index", "register.jsonl": "register", "corpus.json": "manifest",
            "derivation.json": "derivation", "raw/origins.jsonl": "raw-index", "raw/members.jsonl": "raw-index"}.get(rel, "other")


_EX_IN_PATH: Final = re.compile(r"(ex_[a-z2-7]{26})")


# ================================================================================================ withholding
def withholding(reader: Any, root: Path, profile_id: str, profile_version: int, rows: Sequence[Any]) -> dict[str, Any]:
    started = time.perf_counter()
    got = withholding_plan(reader, root, profile_id, profile_version, rows)
    if got is None:
        return {"policy": None}
    policy, plan = got
    by_basis: Counter[str] = Counter()
    if plan.document is not None:
        for obj in plan.document.entries:
            by_basis[f"{obj.basis}:{obj.reason}"] += 1
    return {"policy": {"ref": policy.ref, "rules": [{"id": r.id, "kind": r.kind, "scope": r.scope} for r in policy.rules],
                       "scan_rules": list(policy.scan_rules)},
            "objects_withheld": len(plan.objects), "executions_withheld": len(plan.executions),
            "executions_total": len(rows), "objects_by_basis": dict(sorted(by_basis.items())),
            "elapsed_s": round(time.perf_counter() - started, 1)}


def withholding_plan(reader: Any, root: Path, profile_id: str, profile_version: int, rows: Sequence[Any]) -> Any:
    """``(policy, plan)`` of the product's ``plan_withholding`` for the corpus under its profile, as ``package`` plans it
    (nothing written), or ``None`` without a policy."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.package import _profile_bytes
    from agentprov.corpus.layout import CorpusLayout, iter_tree
    from agentprov.corpus.package import _catalogue_versions, _object_hex
    from agentprov.corpus.withhold import derived_labels, load_policy, plan_withholding

    profile = load_profile(profile_id, profile_version)
    data = _profile_bytes(profile)
    policy = load_policy(data, profile_id=profile.id, profile_version=profile.version,
                         catalogues=_catalogue_versions(reader.derivation()))
    if policy is None:
        return None
    manifest = reader.manifest() or {}
    source = (manifest.get("sources") or [{}])[0]
    scan = iter_tree(root)
    layout = CorpusLayout(root)

    def stream(label: str) -> Iterable[bytes]:
        with reader.open_file(label, stored=True) as handle:
            while chunk := handle.read(1 << 20):
                yield chunk

    def artefacts(row: Any) -> Sequence[Mapping[str, Any]]:
        try:
            listed = reader.read_aer(row).header.get("artifacts")
        except Exception:  # noqa: BLE001 - an unreadable AER cites nothing (as package does)
            return ()
        return [a for a in listed if isinstance(a, Mapping)] if isinstance(listed, list) else ()

    snapshots = {str(s["snapshot_id"]): ("include", s.get("pin")) for s in source.get("snapshots", ())}
    plan = plan_withholding(
        rows=rows, register=reader.register(), members=reader.members() if reader.exists("raw/members.jsonl") else [],
        origins=reader.origins(), present={_object_hex(label): (label, size) for label, role, size in scan.files
                                           if role == "raw_object"},
        tombstones=[], snapshots=snapshots, stream=stream, derived=lambda row: derived_labels(layout, row, reader.exists),
        artefacts=artefacts, policy=policy, decided_on=None,
    )
    return policy, plan


# ================================================================================================ commands
def _cli(argv: Sequence[str], timeout: float) -> dict[str, Any]:
    """An ``agentprov`` command in a subprocess, with its ``--summary-json`` document."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="precheck-l2-") as tmp:
        summary = Path(tmp) / "summary.json"
        command = [sys.executable, "-m", "agentprov", *argv, "-q", "--summary-json", str(summary)]
        started = time.perf_counter()
        try:
            done = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"argv": [scrub(a) for a in argv], "exit_code": None, "error": "timeout"}
        doc = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    stdout = done.stdout.decode("utf-8", "replace")
    # the human lines (``package``'s "root digest ...") go to stderr (cli/main.py ``_print_messages``)
    digest = re.findall(r"root digest (sha256:[0-9a-f]{64})", stdout + "\n" + done.stderr.decode("utf-8", "replace"))
    return {"argv": [scrub(a) for a in argv], "exit_code": done.returncode,
            "elapsed_s": round(time.perf_counter() - started, 1), **_summary_view(doc),
            "root_digest": digest[-1] if digest else None,
            "stdout_tail": [scrub(line, 300) for line in stdout.splitlines()[-6:]],
            "stderr_tail": [scrub(line, 300) for line in done.stderr.decode("utf-8", "replace").splitlines()[-8:]]}


def _summary_view(doc: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(doc, Mapping):
        return {"summary": None}
    failures = doc.get("failures") or []
    return {"outcome": doc.get("outcome"), "counters": doc.get("counters"), "issues_by_code": doc.get("issues_by_code"),
            "notices": [scrub(str(n), 300) for n in (doc.get("notices") or [])][:20],
            "failures": [{k: scrub(str(v), 200) for k, v in f.items() if k in ("code", "stage", "detail")} for f in failures][:40],
            "refusal": scrub(json.dumps(doc.get("refusal")), 400) if doc.get("refusal") else None}


def recompute_in_process(root: Path, info: SampleInfo, jobs: int) -> dict[str, Any]:
    """``agentprov recompute --dry-run`` under the AnyOf shim when the import recorded the shim's marker."""
    import l2_import
    from agentprov.cli.main import main as cli_main

    manifest = json.loads((root / "corpus.json").read_text(encoding="utf-8"))
    include = ((manifest.get("selection") or {}).get("filters") or {}).get("include_paths") or []
    shimmed = bool(include) and str(include[0]).startswith("precheck:any-of:")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="precheck-l2-") as tmp:
        summary = Path(tmp) / "summary.json"
        argv = ["recompute", "--corpus", str(root), "--dry-run", "--jobs", str(jobs), "-q", "--summary-json", str(summary)]
        seen: dict[str, Any] = {}
        started = time.perf_counter()
        if include and not shimmed:
            note = ("the corpus records plain include_paths (a per-label import records only its last label): the "
                    "replay re-maps that selection only, so the comparison covers it alone")
        else:
            note = None
        if shimmed:
            if not info.labels:
                return {"exit_code": None, "error": "an any-glob import: pass --sample so the replay can be shimmed"}
            any_of = l2_import.AnyOf(sorted(info.labels))
            if str(any_of) != str(include[0]):
                return {"exit_code": None, "error": "the recorded any-of marker differs from the sample's (another sample?)"}
            with l2_import.any_of_matcher(any_of, seen, strict=False):
                code = cli_main(argv)
        else:
            code = cli_main(argv)
        doc = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    return {"argv": [scrub(a) for a in argv[:-2]], "exit_code": code, "shim": shimmed, "note": note,
            "discoveries": seen.get("discoveries"), "elapsed_s": round(time.perf_counter() - started, 1),
            **_summary_view(doc)}


def determinism(a: Path, b: Path) -> dict[str, Any]:
    trial = load_tool("agentdojo/phase10d_trial.py")
    result: dict[str, Any] = trial.compare_corpora(a, b)
    a_rows = (a / "executions.jsonl").read_bytes() if (a / "executions.jsonl").exists() else b""
    b_rows = (b / "executions.jsonl").read_bytes() if (b / "executions.jsonl").exists() else b""
    result["index_identical"] = a_rows == b_rows
    result["compared"] = [tilde(a), tilde(b)]
    return result


def seal_copy(root: Path, timeout: float) -> dict[str, Any]:
    """Seal a copy of the scratch corpus with a generated scratch spec, then ``verify --level chain --release``."""
    manifest = json.loads((root / "corpus.json").read_text(encoding="utf-8"))
    final = root.with_name(root.name.removesuffix(".partial") + "-sealcopy")
    partial = final.with_name(final.name + ".partial")
    for stale in (final, partial):
        if stale.exists():
            shutil.rmtree(stale)
    shutil.copytree(root, partial)
    source = (manifest.get("sources") or [{}])[0]
    profile = source.get("profile") or {}
    sem = sorted({str(p) for row in _index_rows(root) for p in (row.get("digests", {}).get("sem") or {})})
    spec_root = final.with_name(final.name + ".spec") / "corpora"
    spec_dir = spec_root / str(manifest["corpus_id"])
    spec_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "corpora" / "datasheet-statements.toml", spec_root / "datasheet-statements.toml")
    origins = pin_origins(root, manifest)
    snapshots = "\n".join(
        f'[[sources.snapshots]]\nsnapshot_id = "{s["snapshot_id"]}"\n'
        f"origin = {_toml_inline(origins.get(s['snapshot_id']) or _spec_origin(s))}\nalt_origins = []\n"
        'raw_policy = "include"\n'
        for s in source.get("snapshots", ()))
    mode = str(manifest.get("mode") or "import")
    spec = (f'# Scratch spec of a pre-check sealed copy (never a real corpus).\ncorpus_id = "{manifest["corpus_id"]}"\n'
            f'corpus_version = "0.1.0"\ntitle = "pre-check scratch copy"\nmode = "{mode}"\n\n[[sources]]\n'
            f'source_id = "{source["source_id"]}"\nprofile = "{profile.get("id")}@{profile.get("version")}"\n'
            f"parts = {json.dumps(source.get('parts', []))}\n\n{snapshots}\n[derive]\n"
            f"sem_profiles = {json.dumps(sem)}\nprov_specs = [\"agentprov-prov/0.1\"]\nviews = []\n"
            'options = { context_encoding = "members" }\n\n[licence]\nderived = "inherit"\n'
            'decided_by = "pre-check scratch copy"\nfiles = []\n\n[layout]\n'
            f"shard_depth = {_shard_depth(root)}\n")
    guard_output(spec_dir)
    (spec_dir / "corpus-spec.toml").write_text(spec, encoding="utf-8")
    (spec_dir / "CARD.md").write_text(scratch_card(mode), encoding="utf-8")
    (spec_dir / "CHANGES.toml").write_text('[[change]]\nversion = "0.1.0"\nbump = "initial"\nsummary = "scratch"\n',
                                           encoding="utf-8")
    package = _cli(["package", "--corpus", str(final), "--corpus-version", "0.1.0", "--spec",
                    str(spec_dir / "corpus-spec.toml"), "--release-date", "2026-10-14"], timeout)
    out: dict[str, Any] = {"package": package}
    root_digest = package.get("root_digest")
    if package.get("exit_code") == 0 and final.exists():
        args = ["verify", "--corpus", str(final), "--level", "chain"]
        out["verify_chain"] = _cli([*args, "--release", "--root-digest", root_digest] if root_digest else args, timeout)
    return out


def _index_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "executions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []


def _shard_depth(root: Path) -> int:
    rows = _index_rows(root)
    if not rows:
        return 1
    aer = str(rows[0].get("paths", {}).get("aer", "aer/xx/x"))
    return max(1, aer.count("/") - 1)


#: The scratch copy's card: the front matter ``package`` compares with ``corpus.json`` (H.9(5)) and one short paragraph per
#: datasheet section, with no literal number (H.9(3)); ``scratch_card`` fills in the mode.
SCRATCH_CARD: Final = """---
mode: {mode}
---

## Motivation

A pre-check scratch copy, sealed only to check sealing, withholding and the release chain. It is never released.

## Composition

A small stratified sample of one source part.

## Collection process

Imported from the pinned origin by the pre-check import tool.

## Preprocessing and labelling

Mapped, annotated and derived by the product pipeline.

## Uses

The pre-check only.

## Maintenance

Deleted with the scratch area.
"""


def scratch_card(mode: str) -> str:
    return SCRATCH_CARD.format(mode=mode)


def pin_origins(root: Path, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Per snapshot id, the sealed origin ``package`` derives from the recorded pin and the object origins of the
    snapshot's primaries (D-33), through the product's own helpers as ``seal`` calls them:
    ``package.snapshot_pin_object_origins`` (with PR-2's exclusion of the recorded pinned objects) and
    ``manifest.snapshot_origin_from_pin`` with the corpus format. A snapshot the product refuses is left out: the spec
    then falls back to :func:`_spec_origin` and ``package`` records the refusal."""
    from agentprov.corpus.manifest import ManifestError, format_for_aer, snapshot_origin_from_pin
    from agentprov.corpus.package import snapshot_pin_object_origins
    from agentprov.corpus.reader import CorpusReader

    reader = CorpusReader.open(root)
    by_sha: dict[str, list[dict[str, Any]]] = {}
    for row in reader.origins():
        by_sha.setdefault(row.sha256, []).append({"kind": row.origin.kind, **row.origin.data})
    aer = next((s for s in (reader.derivation() or {}).get("stages", ()) if isinstance(s, Mapping) and s.get("stage") == "aer"),
               {})
    corpus_format = format_for_aer(str(aer.get("format") or ""))
    rows = reader.index()
    snapshots = list((manifest.get("sources") or [{}])[0].get("snapshots", ()))
    out: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        sid = str(snapshot["snapshot_id"])
        primaries = {ref.sha256 for r in rows if sid in r.snapshot_ids for ref in r.raw if ref.role == "primary"}
        objects = snapshot_pin_object_origins(snapshot, primaries, by_sha, several=len(snapshots) > 1)
        try:
            out[sid] = dict(snapshot_origin_from_pin(snapshot.get("pin"), objects, corpus_format=corpus_format))
        except ManifestError:
            continue
    return out


def _spec_origin(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Fallback only (:func:`pin_origins` refused the snapshot): the recorded origin or pin, scalars only."""
    pin = snapshot.get("pin") or {}
    origin = snapshot.get("origin") or {}
    out = {k: v for k, v in (origin or pin).items() if isinstance(v, (str, int))}
    subtree = out.get("subtree")
    if out.get("kind") == "git" and isinstance(subtree, str) and ("," in subtree or subtree.endswith("/")):
        out["subtree"] = ""  # covering pathspecs of a partial clone: the spec names the commit root
    return out


def _toml_inline(value: Mapping[str, Any]) -> str:
    return "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in value.items()) + " }"


# ================================================================================================ main check
def check(root: Path, info: SampleInfo, keep: Callable[[str | None], bool] | None = None) -> dict[str, Any]:
    """The Level-2 census of ``root``. ``keep`` (the post-check's sample scope, ``tools/precheck/post_check.py``)
    restricts it to the executions whose primary raw object's label it accepts; the validation rows follow, the register
    stays corpus-wide. ``None``: every execution (the pre-check's scratch corpora hold only the sample)."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.corpus.reader import CorpusReader
    from agentprov.prov.specs import load_spec

    reader = CorpusReader.open(root)
    manifest = reader.manifest() or {}
    rows = reader.index()
    resolve = LabelResolver(reader.origins(), info)
    spec = load_spec()
    prov = ProvStats(set(spec.rules), RuleRegistry.default())
    outcomes = Outcomes()
    status: Counter[str] = Counter()
    issue_codes: Counter[str] = Counter()
    seal_codes: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    unreadable: Counter[str] = Counter()
    degenerate = adapter_defect = 0
    labels_seen: dict[str, int] = Counter()
    identities: list[tuple[str | None, dict[str, str]]] = []
    dialects: Counter[str] = Counter()
    kept_rows = []
    for row in rows:
        primary = next((r.sha256 for r in row.raw if r.role in ("primary", "capture_log")), None)
        label = resolve(primary) if primary is not None else None
        if keep is not None and not keep(label):
            continue
        kept_rows.append(row)
        status[f"status:{row.status}"] += 1
        status[f"completeness:{row.completeness}"] += 1
        status[f"unit:{row.unit}"] += 1
        status[f"observed:{row.execution_observed}"] += 1
        issue_codes.update(row.issues)
        for stage, state in row.stages.items():
            stages[f"{stage}:{state}"] += 1
        for name, out in (row.sem or {}).items():
            stages[f"sem:{name}:{out.state}"] += 1
        for name, out in (row.prov or {}).items():
            stages[f"prov:{name}:{out.state}"] += 1
        stages[f"validation:{row.validation.state if row.validation else 'absent'}"] += 1
        if primary is None:
            unreadable["index:no_primary_raw"] += 1
        if label is not None:
            labels_seen[label] += 1
        try:
            aer = reader.read_aer(row)
        except Exception as exc:  # noqa: BLE001 - counted, never raised (a corrupt row is a finding)
            unreadable[f"aer:{getattr(exc, 'code', type(exc).__name__)}"] += 1
            continue
        codes = [str(i.get("code")) for i in aer.seal.get("issues", ()) if isinstance(i, dict)]
        seal_codes.update(codes)
        degenerate += degenerate_of([*codes, *row.issues])
        adapter_defect += any(c.removeprefix("map.") == "adapter_defect" for c in [*codes, *row.issues])
        dialect = str((aer.header.get("dialect") or {}).get("id", ""))
        dialects[dialect] += 1
        identity = identity_of(aer)
        identities.append((label, identity))
        values, defaults = judgements_of(aer)
        outcomes.add(identity, dialect, values, defaults)
        for spec_id, prov_out in sorted((row.prov or {}).items()):
            if prov_out.state != "ok":
                continue
            try:
                prov.add(row.ex, label, reader.read_prov(row, spec_id), aer)
            except Exception as exc:  # noqa: BLE001
                unreadable[f"prov:{getattr(exc, 'code', type(exc).__name__)}"] += 1
    validation_failed: Counter[str] = Counter()
    kept_ex = {row.ex for row in kept_rows}
    for result in reader.validation_results():
        if keep is not None and result.get("ex") not in kept_ex:
            continue
        for check_id, verdict in (result.get("checks") or {}).items():
            if verdict == "fail":
                validation_failed[str(check_id)] += 1
    register = Counter(e.code for e in reader.register())
    sample_missing = sorted(info.labels - set(labels_seen)) if info.labels else []
    return {
        "manifest": {"corpus_id": manifest.get("corpus_id"), "partial": manifest.get("partial"),
                     "selection": manifest.get("selection"), "mode": manifest.get("mode"),
                     "sources": [{"source_id": s.get("source_id"), "profile": s.get("profile"),
                                  "snapshots": [{"snapshot_id": x.get("snapshot_id"), "verification": x.get("verification")}
                                                for x in s.get("snapshots", ())]} for s in manifest.get("sources", ())]},
        "executions": {"n": len(kept_rows), "counts": dict(sorted(status.items())), "degenerate": degenerate,
                       "adapter_defect": adapter_defect, "stages": dict(sorted(stages.items())),
                       "unreadable": dict(unreadable), "dialects": dict(dialects),
                       "validation_checks_failed": dict(sorted(validation_failed.items())),
                       "register_codes": dict(sorted(register.items()))},
        "sample_join": {"labels_sampled": len(info.labels), "labels_with_executions": len(labels_seen),
                        "executions_per_label": dict(Counter(labels_seen.values())),
                        "sampled_without_execution": [scrub(x) for x in sample_missing][:_MAX_LIST],
                        "n_sampled_without_execution": len(sample_missing)},
        "issues": {"index_issue_codes": dict(sorted(issue_codes.items())), "seal_issue_codes": dict(sorted(seal_codes.items()))},
        "prov": prov.to_json(),
        "identity": identity_census(identities, info),
        "outcomes": outcomes.to_json(),
        "_rows": kept_rows, "_reader": reader,
    }


def identity_census(identities: Sequence[tuple[str | None, Mapping[str, str]]], info: SampleInfo) -> dict[str, Any]:
    tuples: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    pairs: dict[str, Counter[str]] = defaultdict(Counter)
    mismatches: list[dict[str, str]] = []
    n_mismatch: Counter[str] = Counter()
    for label, ident in identities:
        tuples[f"{ident['model']}|{ident['defence']}|{ident['attack']}|{ident['suite']}"] += 1
        for name in ("model", "suite", "task"):
            if ident[name] == "none":
                unresolved[name] += 1
        row = info.rows.get(label or "")
        facets = row.get("facets") if isinstance(row, dict) and isinstance(row.get("facets"), dict) else None
        if not facets:
            continue
        for field_name, keys in FACETS.items():
            for key in keys:
                if key not in facets:
                    continue
                l1 = _norm(facets[key])
                pairs[f"{field_name}<-{key}"][f"{scrub(l1, 120)} -> {scrub(ident[field_name], 120)}"] += 1
                if field_name in DIRECT and key == next(k for k in keys if k in facets) and l1 != ident[field_name]:
                    n_mismatch[field_name] += 1
                    if len(mismatches) < _MAX_LIST:
                        mismatches.append({"label": scrub(label or "?", 300), "field": field_name, "l1_key": key,
                                           "l1": scrub(l1, 120), "aer": scrub(ident[field_name], 120)})
    non_functional: dict[str, dict[str, int]] = {}
    for key, table in pairs.items():
        targets: dict[str, set[str]] = defaultdict(set)
        for pair in table:
            left, _, right = pair.partition(" -> ")
            targets[left].add(right)
        bad = {left: len(right) for left, right in targets.items() if len(right) > 1}
        if bad:
            non_functional[key] = bad
    return {"tuples_model_defence_attack_suite": dict(tuples.most_common(200)), "unresolved": dict(unresolved),
            "pairs_l1_to_aer": {k: dict(v.most_common(60)) for k, v in sorted(pairs.items())},
            "l1_values_mapping_to_several_aer_values": non_functional,
            "direct_mismatches": {"counts": dict(n_mismatch), "rows": mismatches}}


def redaction_scan(root: Path, info: SampleInfo, only: set[str] | None = None) -> dict[str, Any]:
    """Counts and pointers of account and secret shapes in the corpus's records (raw objects are L1's). ``only`` (the
    post-check's sample scope): execution ids; a per-execution record of another execution and the corpus-wide files
    (index, register, manifest) are skipped."""
    red = Redaction()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        kind = _object_kind(rel)
        if kind is None:
            continue
        found = _EX_IN_PATH.search(path.name)
        if only is not None and (found is None or found.group(1) not in only):
            continue
        red.scan_file(kind, path, found.group(1) if found else None)
    out = red.to_json()
    flagged: Counter[str] = Counter()
    for row in info.rows.values():
        for flag in row.get("flags") or ():
            if re.search(r"account|secret|home|local_path", str(flag)):
                flagged[str(flag)] += 1
    out["l1_flags_of_sampled_labels"] = dict(sorted(flagged.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--corpus", required=True, type=Path, help="the scratch corpus (DIR.partial)")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--l1-units", type=Path)
    parser.add_argument("--compare-with", type=Path, help="a second scratch import (another --jobs) for determinism")
    parser.add_argument("--no-commands", action="store_true", help="skip validate, verify, recompute")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--tiers", default="aer,sem,prov,linkage,shacl,regression")
    parser.add_argument("--timeout", type=float, default=6 * 3600)
    parser.add_argument("--seal", action="store_true", help="try to seal a copy and verify --level chain --release")
    args = parser.parse_args(argv)
    root = guard_scratch(args.corpus)
    info = SampleInfo(args.sample, args.l1_units)
    started = time.perf_counter()
    result = check(root, info)
    reader, rows = result.pop("_reader"), result.pop("_rows")
    result["redaction"] = redaction_scan(root, info)
    source = (result["manifest"]["sources"] or [{}])[0]
    profile = source.get("profile") or {}
    try:
        result["withholding"] = withholding(reader, root, str(profile.get("id")), int(profile.get("version") or 0), rows)
    except Exception as exc:  # noqa: BLE001 - a refused policy or plan is a result, recorded
        result["withholding"] = {"error": f"{getattr(exc, 'code', type(exc).__name__)}: {scrub(str(exc), 300)}"}
    commands: dict[str, Any] = {}
    if not args.no_commands:
        commands["validate"] = _cli(["validate", "--corpus", str(root), "--tiers", args.tiers, "--jobs", str(args.jobs)],
                                    args.timeout)
        commands["verify_chain"] = _cli(["verify", "--corpus", str(root), "--level", "chain"], args.timeout)
        commands["recompute_dry_run"] = recompute_in_process(root, info, args.jobs)
    if args.compare_with is not None:
        commands["determinism"] = determinism(root, guard_scratch(args.compare_with))
    if args.seal:
        commands["seal_copy"] = seal_copy(root, args.timeout)
    result["commands"] = commands
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                           text=True, check=False)
    doc = {"format": CHECK_FORMAT, "corpus": tilde(root), "code": {"commit": head.stdout.strip(),
                                                                    "tracked_changes": bool(dirty.stdout.strip())},
           "sample": None if args.sample is None else {"file": tilde(args.sample), "sha256": sha256_file(args.sample),
                                                       "n": len(info.labels)},
           "l1_units": None if args.l1_units is None else tilde(args.l1_units),
           "elapsed_s": round(time.perf_counter() - started, 1), **result}
    write_json(args.out, doc)
    ex = doc["executions"]
    print(json.dumps({"executions": ex["n"], "degenerate": ex["degenerate"], "a3": {k: v["count"] for k, v in
                      doc["prov"]["a3"].items()}, "out": tilde(args.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("AGENTPROV_PROGRESS", "off")
    sys.exit(main())
