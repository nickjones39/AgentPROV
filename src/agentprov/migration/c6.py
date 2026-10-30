"""Gate C6, comparer half: old-versus-new live capture with a scripted client (docs/architecture J.3.4 row C6; K.9.2).

The producer (``backends/agentdojo/tests/test_c6_old_vs_new.py``, the backend project) leaves, per scenario,
``<work>/<scenario>/{scenario.json, new/session/, new/result.json, old/}``: the new side's sealed ``capture/0.1``
session and the frozen baseline generator's ``transcript.json``/``graph.json`` (when it wrote them), its wire requests
and ``probe.json``. This module (core, Python 3.14) maps and compares them; it never runs either package.

Per scenario:

* **new AER**: the staged session mapped with the ``agentdojo-live`` profile (:func:`agentprov.adapters.runner.live.
  map_session`) and sealed; **old AER**: the baseline transcript mapped with the ``adprov-v1`` profile (the importer
  of gates A/B);
* **wire** (both categories): the decoded request bodies, old ``requests/<n>.json`` versus the new ``llm.request``
  blobs, compared as JCS values per index: the ``gateway_compat`` port must build what ``_CompatLLM`` built;
* **C6(a)** (category ``a``): the v1 view of the new AER (:func:`agentprov.views.transcript_v1.render` +
  ``serialise``) against the old transcript, and the compat graph built from that view (``prov/compat/adprov_v2_3``)
  against the old graph, both **as bytes after the time mask** (:func:`mask_transcript`, :func:`mask_graph`);
* **C6(b)** (category ``b``): ``common_projection`` of the two AERs as JCS bytes, plus the deviation detectors, whose
  observations must be absorbed by exactly the scenario's expected XD entries (:mod:`agentprov.migration.xd`).

Every remaining difference becomes an :class:`~agentprov.migration.xd.Observation` keyed by its JSON Pointer (``v1:``,
``graph:``, ``projection:``, ``wire:``) or deviation (``deviation:<id>/...``); the register decides. Nothing here prints
or reports scenario text: pointers, ids, counts and digests only (MP-6).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.io.canonical import jcs_bytes
from agentprov.migration.xd import CheckResult, Observation, Register, check

__all__ = [
    "MASK",
    "C6Item",
    "C6Result",
    "compare_scenario",
    "compare_work",
    "json_differences",
    "listed_scenarios",
    "mask_graph",
    "mask_transcript",
]

MASK: Final = "<masked>"
#: J.3.4 C6(a): the run's times (always present in a v1 meta) and the per-tool times (optional tool-turn members).
META_TIME_KEYS: Final = ("started_at", "ended_at", "wall_clock_s")
TOOL_TIME_KEYS: Final = ("started_at", "ended_at")
#: The members the registered D.7.3 redefinition removes from the comparison (``XD-C6-D73-capture-verdict``): every
#: live transcript of ``579a908`` has them; the AER holds attempt scopes and the seal's accounting verdict instead.
D73_META_KEYS: Final = ("n_attempts", "capture")
#: The compat graph's carriers of those times (activity start/end; prov:time on generations, if any).
GRAPH_TIME_KEYS: Final = frozenset({"prov:startTime", "prov:endTime", "prov:time"})


# ------------------------------------------------------------------------------------------------ masks and diffs
def _mask_turns(turns: Any) -> None:
    for turn in turns if isinstance(turns, list) else ():
        if isinstance(turn, dict) and turn.get("role") == "tool":
            for key in TOOL_TIME_KEYS:
                turn.pop(key, None)


def mask_transcript(doc: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of a transcript/v1 document with the C6 time mask applied: ``meta.started_at``, ``ended_at`` and
    ``wall_clock_s`` replaced by ``"<masked>"`` where present (member order kept), and the tool turns' ``started_at``/
    ``ended_at`` removed (in ``turns`` and every ``discarded_attempts[].turns``)."""
    out = copy.deepcopy(dict(doc))
    meta = out.get("meta")
    if isinstance(meta, dict):
        for key in META_TIME_KEYS:
            if key in meta:
                meta[key] = MASK
    _mask_turns(out.get("turns"))
    for attempt in out.get("discarded_attempts") or ():
        if isinstance(attempt, dict):
            _mask_turns(attempt.get("turns"))
    return out


def mask_graph(doc: Any) -> Any:
    """A copy of a compat PROV-JSON graph without its time attributes (:data:`GRAPH_TIME_KEYS`, at any depth)."""
    if isinstance(doc, dict):
        return {k: mask_graph(v) for k, v in doc.items() if k not in GRAPH_TIME_KEYS}
    if isinstance(doc, list):
        return [mask_graph(v) for v in doc]
    return doc


def _esc(token: object) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def json_differences(old: Any, new: Any, at: str = "") -> Iterator[str]:
    """JSON Pointers where two decoded JSON documents differ, in document order: a member present on one side only,
    a different member order (``<pointer>#order``), a different type or value (compared as JCS bytes plus the
    int/float distinction, which JCS erases). Pointers are built from member names and indices only."""
    if isinstance(old, dict) and isinstance(new, dict):
        common = [k for k in old if k in new]
        if common != [k for k in new if k in old]:
            yield f"{at}#order"
        for key in old:
            if key not in new:
                yield f"{at}/{_esc(key)}"
        for key in new:
            if key not in old:
                yield f"{at}/{_esc(key)}"
        for key in common:
            yield from json_differences(old[key], new[key], f"{at}/{_esc(key)}")
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            if i >= len(old) or i >= len(new):
                yield f"{at}/{i}"
            else:
                yield from json_differences(old[i], new[i], f"{at}/{i}")
    elif type(old) is not type(new) or jcs_bytes(old) != jcs_bytes(new):
        yield at or "/"


def serialise_v1(doc: Mapping[str, Any]) -> bytes:
    """The baseline writer's form (``json.dumps(doc, indent=2)``; ``transcript.py:282-283``)."""
    return json.dumps(doc, indent=2).encode("utf-8")


# ------------------------------------------------------------------------------------------------ results
@dataclass
class C6Item:
    scenario: str
    category: str
    expect_xd: tuple[str, ...]
    status_new: str | None = None
    old_written: bool = False
    checks: dict[str, bool] = field(default_factory=dict)  # check name -> passed (before the register)
    observations: list[Observation] = field(default_factory=list)
    digests: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    benign_security: bool = False

    #: difference keys a confirmed deviation detector stands for: key -> its ``deviation:`` key (observed once)
    absorb: dict[str, str] = field(default_factory=dict)

    def observe(self, key: str) -> None:
        key = self.absorb.get(key, key)
        if key in self.absorb.values() and any(o.key == key for o in self.observations):
            return
        self.observations.append(Observation("C6", f"scenario:{self.scenario}", key))


@dataclass
class C6Result:
    items: list[C6Item]
    register: CheckResult
    #: the scenarios the producer's ``manifest.json`` lists; ``None`` when it is absent, unreadable or of another format
    scenarios: list[str] | None = None
    missing: list[str] = field(default_factory=list)  # listed, but no ``<scenario>/scenario.json`` was compared
    extra: list[str] = field(default_factory=list)  # compared, but not listed

    def verdict(self, item: C6Item) -> str:
        """``pass`` iff the scenario compared without error and the register absorbed every observation of it with
        exactly its declared entries (for C6(a) that is the D.7.3 entry alone: the views and graphs are otherwise
        byte-equal after the time mask)."""
        failing = {f["item"] for f in self.register.failures()}
        return "fail" if item.errors or f"scenario:{item.scenario}" in failing else "pass"

    @property
    def ok(self) -> bool:
        """Every scenario the manifest lists was compared, none other was, and each passed: a partial or empty work
        dir (a ``-k`` or killed producer run, a pruned dir) never passes C6."""
        return (self.scenarios is not None and not self.missing and not self.extra and self.register.ok
                and all(self.verdict(i) == "pass" for i in self.items))


# ------------------------------------------------------------------------------------------------ mapping
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def map_new_session(session_dir: Path) -> tuple[bytes, Any]:
    """The new side's sealed AER bytes and the loaded document (``agentdojo-live``)."""
    from agentprov.adapters.runner import aer_bytes
    from agentprov.adapters.runner.live import map_session
    from agentprov.aer.reader import load_aer_bytes

    outcome, _unit, register = map_session(session_dir, profile_id="agentdojo-live")
    if outcome is None:
        raise ValueError(f"the session yields no unit ({[r.get('code') for r in register]})")
    data, _info = aer_bytes(outcome)
    return data, load_aer_bytes(data)


def map_old_transcript(raw: bytes, scenario: str) -> tuple[bytes, Any]:
    """The old transcript's sealed AER bytes and document (``adprov-v1``, the importer of gates A and B)."""
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.raw.origins import Origin

    origin = Origin.corpus("AgentDojo-PROV-C6", "579a908", f"c6/{scenario}/old/transcript.json",
                           producer_commit="579a908354b93361efe0905ffb7623256aa96a06")
    outcome, _unit = map_artefact(raw, origin, profile_id="adprov-v1")
    data, _info = aer_bytes(outcome)
    return data, load_aer_bytes(data)


def _records(document: Any) -> list[Mapping[str, Any]]:
    return [r for r in getattr(document, "records", document) if isinstance(r, Mapping)]


# ------------------------------------------------------------------------------------------------ wire
def _new_request_bodies(session_dir: Path) -> list[bytes]:
    capture = next((session_dir / "raw" / "capture").glob("*.capture.jsonl"))
    bodies: list[bytes] = []
    for line in capture.read_bytes().splitlines():
        event = json.loads(line)
        if event.get("type") == "llm.request":
            ref = event["data"]["request"]["$blob"].split(":", 1)[1]
            bodies.append((session_dir / "raw" / "blobs" / "sha256" / ref[:2] / ref).read_bytes())
    return bodies


def compare_wire(item: C6Item, old_dir: Path, session_dir: Path) -> None:
    """Per wire request, the decoded bodies as JCS values (and the request count)."""
    old = [(old_dir / "requests" / f"{n}.json").read_bytes()
           for n in range(len(list((old_dir / "requests").glob("*.json"))))]
    new = _new_request_bodies(session_dir)
    item.counts["wire_requests_old"], item.counts["wire_requests_new"] = len(old), len(new)
    same = len(old) == len(new)
    if not same:
        item.observe("wire:/count")
    for n, (a, b) in enumerate(zip(old, new, strict=False)):
        for pointer in json_differences(json.loads(a), json.loads(b)):
            same = False
            item.observe(f"wire:/{n}{pointer}")
    item.checks["wire_requests_equal"] = same


# ------------------------------------------------------------------------------------------------ C6(a)
def compare_v1_and_graph(item: C6Item, old_dir: Path, new_doc: Any) -> None:
    from agentprov.prov.compat.adprov_v2_3 import SPEC
    from agentprov.views.transcript_v1 import render

    old_raw = (old_dir / "transcript.json").read_bytes()
    old_doc = json.loads(old_raw)
    if serialise_v1(old_doc) != old_raw:  # J-M1: the old writer's bytes re-serialise exactly
        item.errors.append("old transcript does not re-serialise byte-identically")
    view = render(new_doc)
    if generator_meta_absent(old_doc.get("meta"), view.get("meta"), new_doc):
        for key in GENERATOR_META_KEYS:
            item.absorb[f"v1:/meta/{key}"] = "deviation:C.15.3/generator-meta"
    old_masked, new_masked = mask_transcript(old_doc), mask_transcript(view)
    for doc in (old_masked, new_masked):  # the registered D.7.3 members (observed by detect_deviations)
        for key in D73_META_KEYS:
            doc.get("meta", {}).pop(key, None)
    a, b = serialise_v1(old_masked), serialise_v1(new_masked)
    item.digests.update({"v1_old_masked": _sha(a), "v1_new_masked": _sha(b)})
    item.checks["v1_bytes_after_mask"] = a == b
    if a != b:
        for pointer in json_differences(old_masked, new_masked):
            item.observe(f"v1:{pointer}")
        # the same bytes once the members the confirmed registered deviations stand for are left out
        absorbed = [k.removeprefix("v1:/meta/") for k in item.absorb if k.startswith("v1:/meta/")]
        for doc in (old_masked, new_masked):
            for key in absorbed:
                doc.get("meta", {}).pop(key, None)
        item.checks["v1_bytes_after_mask_and_registered"] = serialise_v1(old_masked) == serialise_v1(new_masked)
    old_graph = json.loads((old_dir / "graph.json").read_bytes())
    new_graph = json.loads(SPEC.serialise(SPEC.build(view)))
    ga, gb = serialise_v1(mask_graph(old_graph)), serialise_v1(mask_graph(new_graph))
    item.digests.update({"graph_old_masked": _sha(ga), "graph_new_masked": _sha(gb)})
    item.checks["graph_bytes_after_mask"] = ga == gb
    if ga != gb:
        for pointer in json_differences(mask_graph(old_graph), mask_graph(new_graph)):
            item.observe(f"graph:{pointer}")


# ------------------------------------------------------------------------------------------------ C6(b)
def compare_projection(item: C6Item, old_doc: Any, new_doc: Any) -> None:
    from agentprov.adapters.projection import common_projection, projection_bytes

    pa, pb = common_projection(_records(old_doc)), common_projection(_records(new_doc))
    if item.benign_security:
        for k, judgement in enumerate(pa.get("judgements", ())):
            if judgement.get("name") == '"security"':
                item.absorb[f"projection:/judgements/{k}/value"] = BENIGN_SECURITY
    ba, bb = projection_bytes(pa), projection_bytes(pb)
    item.digests.update({"projection_old": _sha(ba), "projection_new": _sha(bb)})
    item.checks["projection_equal"] = ba == bb
    if ba != bb:
        for pointer in json_differences(pa, pb):
            item.observe(f"projection:{pointer}")
        if item.benign_security:  # the same bytes without the security judgement the D.10.5 entry stands for
            qa, qb = ({**q, "judgements": [j for j in q["judgements"] if j.get("name") != '"security"']} for q in (pa, pb))
            item.checks["projection_equal_but_registered"] = projection_bytes(qa) == projection_bytes(qb)


def detect_deviations(item: C6Item, scenario: Mapping[str, Any], probe: Mapping[str, Any], new_doc: Any,
                      old_written: bool, old_meta: Mapping[str, Any] | None) -> None:
    """The registered D5 deviations (F-02, F-05, F-13) and the D.7.3 redefinition, as observed in the outputs."""
    records = _records(new_doc)
    header = records[0] if records else {}
    # F-02: every reply the port did not keep is a discarded model_call (the baseline kept only counters of them)
    for r in records:
        if r.get("k") == "model_call" and r.get("status") in ("discarded", "error"):
            item.observe(f"deviation:F-02/{r.get('id')}")
    # F-05: the baseline discarded a failed cell (no transcript, an error row); the new side sealed and kept it
    run = next((r for r in records if r.get("k") == "scope" and r.get("id") == "run"), {})
    if not old_written and probe.get("row", {}).get("error") is not None:
        kept = item.status_new == "errored" and run.get("status") == "error"
        item.observe("deviation:F-05/failed-cell" if kept else "deviation:F-05/failed-cell-not-kept")
    # F-13: the baseline mutated MODEL_NAMES for the attack; the new side declared the preset
    items = [i for i in header.get("instrumentation", ()) if isinstance(i, Mapping)]
    preset = [i for i in items if i.get("id") == "agentdojo.attack_model_display_name@1"
              and isinstance(i.get("params"), Mapping) and i["params"].get("preset") is not None]
    if scenario.get("old", {}).get("kind") == "injection" and probe.get("model_names_added") and preset:
        same = preset[0]["params"].get("display_name") in probe["model_names_added"].values()
        item.observe("deviation:F-13/display-name" if same else "deviation:F-13/display-name-differs")
    # D.7.3: the baseline's meta.n_attempts/meta.capture versus the AER's attempt scopes and accounting verdict; they
    # must agree (complete true <-> consistent, the pass count <-> the attempt scopes)
    capture = (old_meta or {}).get("capture")
    if isinstance(capture, Mapping):
        n_scopes = sum(1 for r in records if r.get("k") == "scope" and r.get("kind") == "attempt")
        status = (getattr(new_doc, "seal", {}) or {}).get("accounting", {}).get("status")
        verdicts = {True: "consistent", False: "inconsistent", None: "unverifiable"}
        agree = (verdicts.get(capture.get("complete")) == status
                 and capture.get("n_attempts") == n_scopes == (old_meta or {}).get("n_attempts"))
        item.observe("deviation:D.7.3/capture-block" if agree else "deviation:D.7.3/verdict-disagrees")


# ------------------------------------------------------------------------------------------------ narrow detectors
BENIGN_SECURITY: Final = "deviation:D.10.5/benign-security"
#: v1 meta members the baseline generator wrote from its own bookkeeping (``_trace_meta``/``_model_config_from_llm``)
GENERATOR_META_KEYS: Final = ("model", "model_config")


def benign_security_constant(old_meta: Mapping[str, Any] | None, new_doc: Any, scenario: Mapping[str, Any]) -> bool:
    """The D.10.5 deviation, narrowly: a benign cell, the baseline's ``meta.security`` null (its generator called
    ``suite.run_task_with_pipeline`` and wrote ``None``), the new AER's ``security`` judgement ``true`` with origin
    ``harness_default`` (the stock ``run_task_without_injection_tasks`` returns a constant ``True``; D.6.7)."""
    if scenario.get("old", {}).get("kind") != "benign" or not isinstance(old_meta, Mapping):
        return False
    if old_meta.get("attack_type") != "benign" or "security" not in old_meta or old_meta["security"] is not None:
        return False
    security = [r for r in _records(new_doc) if r.get("k") == "judgement" and r.get("name") == "security"
                and "revises" not in r]
    return len(security) == 1 and security[0].get("value") is True and security[0].get("origin") == "harness_default"


def generator_meta_absent(old_meta: Any, view_meta: Any, new_doc: Any) -> bool:
    """The C.15.3 limit, narrowly: the baseline wrote ``meta.model`` (a string) and ``meta.model_config`` (an object);
    the live AER carries no ``ext.adprov`` (the only source the field table names for ``model`` and the
    ``model_config`` key list), so the view renders ``model`` null and no ``model_config``."""
    records = _records(new_doc)
    header = records[0] if records else {}
    ext = header.get("ext")
    return (isinstance(old_meta, Mapping) and isinstance(old_meta.get("model"), str)
            and isinstance(old_meta.get("model_config"), Mapping) and isinstance(view_meta, Mapping)
            and view_meta.get("model") is None and "model_config" not in view_meta
            and not (isinstance(ext, Mapping) and "adprov" in ext))


# ------------------------------------------------------------------------------------------------ driver
def compare_scenario(directory: Path) -> C6Item:
    scenario = json.loads((directory / "scenario.json").read_text(encoding="utf-8"))
    item = C6Item(scenario["name"], scenario["category"], tuple(scenario.get("expect_xd", ())))
    old_dir, session_dir = directory / "old", directory / "new" / "session"
    probe = json.loads((old_dir / "probe.json").read_text(encoding="utf-8"))
    result = json.loads((directory / "new" / "result.json").read_text(encoding="utf-8"))
    item.status_new = result.get("status")
    item.old_written = (old_dir / "transcript.json").is_file()
    try:
        new_data, new_doc = map_new_session(session_dir)
        item.digests["aer_new"] = _sha(new_data)
        compare_wire(item, old_dir, session_dir)
        old_doc = None
        old_meta = json.loads((old_dir / "transcript.json").read_bytes()).get("meta") if item.old_written else None
        if benign_security_constant(old_meta, new_doc, scenario):
            item.benign_security = True
            item.absorb["v1:/meta/security"] = BENIGN_SECURITY
        if item.old_written:
            old_data, old_doc = map_old_transcript((old_dir / "transcript.json").read_bytes(), item.scenario)
            item.digests["aer_old"] = _sha(old_data)
        if item.category == "a":
            compare_v1_and_graph(item, old_dir, new_doc)
        elif old_doc is not None:
            compare_projection(item, old_doc, new_doc)
        detect_deviations(item, scenario, probe, new_doc, item.old_written, old_meta)
    except Exception as exc:  # noqa: BLE001 - a scenario that cannot be compared fails, with the exception type only
        item.errors.append(f"{type(exc).__name__}")
    return item


WORK_FORMAT: Final = "agentprov-c6-work/1"


def listed_scenarios(work: Path) -> list[str] | None:
    """The scenario names the producer's ``<work>/manifest.json`` lists (``test_c6_manifest``), or ``None`` when the
    manifest is absent, unreadable or not ``agentprov-c6-work/1``."""
    try:
        manifest = json.loads((Path(work) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("format") != WORK_FORMAT:
        return None
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not all(isinstance(s, str) for s in scenarios):
        return None
    return sorted(scenarios)


def compare_work(work: Path, register: Register) -> C6Result:
    directories = sorted(p.parent for p in Path(work).glob("*/scenario.json"))
    items = [compare_scenario(d) for d in directories]
    observations = [o for i in items for o in i.observations]
    expected = {f"scenario:{i.scenario}": list(i.expect_xd) for i in items}
    scenarios = listed_scenarios(work)
    found = {i.scenario for i in items}
    listed = set(scenarios or ())
    return C6Result(items, check(observations, register, expected=expected), scenarios,
                    missing=sorted(listed - found), extra=sorted(found - listed) if scenarios is not None else [])


def summary(result: C6Result) -> list[dict[str, Any]]:
    """One row per scenario: verdict, checks, counts, XD hits (ids and numbers only)."""
    rows = []
    for item in result.items:
        hits = {eid: n for (eid, it), n in result.register.hits.items() if it == f"scenario:{item.scenario}"}
        rows.append({"scenario": item.scenario, "category": item.category, "verdict": result.verdict(item),
                     "status_new": item.status_new, "old_written": item.old_written, "checks": item.checks,
                     "counts": item.counts, "xd_hits": hits, "errors": item.errors,
                     "observations": sorted({o.key for o in item.observations})[:50]})
    return rows
