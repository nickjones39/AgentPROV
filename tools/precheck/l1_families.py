"""Per-family hooks of the corpus pre-check's Level 1 scanner (docs/reports/precheck/README.md section 3).

Every hook reads **parsed** raw values (the scanner parsed them through ``agentprov.ingest``) and gives, per unit:

* ``facets``: the arm keys of the inventory (strings; a missing value is ``<none>``), from the label and from the JSON;
* ``steps``: the normalised message/step list the trajectory fingerprint is computed over (role + text/content + tool
  name + arguments; JCS-canonical, so key order never matters), or ``None`` when the unit has no step at all;
* ``outcomes``: the outcome fields as raw scalar values (the L2 outcome comparison reads them);
* ``flags``: family-level degenerate markers (``zero_messages``, ``error_only``, ``incomplete``, ``unterminated`` ...).

Independence (pre-registered rule): no hook imports a mapper (``agentprov.adapters.*.mapper``) or any family dialect
module. The path grammars below are written from the inventory and the profiles' ``[import]``/``layout`` **data**; the
variant of an AgentDojo log is classified from its key set here, not by ``agentdojo.dialect.classify``. The only family
code the scanner itself uses is the readers' ``iter_artefacts`` (selection = the importer's candidate labels), which reads
labels only and never parses content.

A stratum is the facets of :data:`STRATA` (per profile, else the family default) joined as ``k=v`` with ``|`` in that
fixed order. The L2 sampler may re-key from the recorded facets.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

NONE: Final = "<none>"
ACCOUNT_FACET: Final = "<account-path>"
LOCAL_MODEL_FACET: Final = "<local-path-model>"

#: Facet values are labels: one that carries a workstation path is masked before it is written anywhere.
_ACCOUNTISH: Final = re.compile(r"(/Users/|/home/|[A-Za-z]:[\\/]+Users[\\/])", re.IGNORECASE)
#: tools/inspect/phase10h_trial.py's local-checkpoint model id regex (a model id that embeds a workstation path).
LOCAL_PATH_MODEL: Final = re.compile(r"(^|/|:)/(workspace|Users|home|mnt|scratch|data|root|tmp)/")
SECRET_FACET: Final = "<secret-like>"
#: The key shapes of ``l1_scan.SECRET_PATTERNS`` in one expression: a facet value, outcome string or pointer segment
#: that holds one is masked before it is written anywhere (facets, outcomes and pointers are copied into reports).
SECRETISH: Final = re.compile(
    r"(?:AKIA|ASIA)[0-9A-Z]{16}|sk-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abposr]-[A-Za-z0-9\-]{10,}"
    r"|AIza[0-9A-Za-z_\-]{35}|[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|PRIVATE KEY-----|hf_[A-Za-z0-9]{34,}"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.eyJ")
_MAX_FACET: Final = 160


def fv(value: Any) -> str:
    """A facet value: a short string, ``<none>`` for missing/null, masked when it carries a workstation path or a
    secret-like shape."""
    if value is None or value == "":
        return NONE
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int | float | str):
        text = str(value)
    else:
        return "<" + type(value).__name__ + ">"
    if _ACCOUNTISH.search(text) or LOCAL_PATH_MODEL.search(text):
        return ACCOUNT_FACET
    if SECRETISH.search(text):
        return SECRET_FACET
    text = "".join(c if c.isprintable() else "?" for c in text)
    return text if len(text) <= _MAX_FACET else text[: _MAX_FACET - 1] + "~"


def model_fv(value: Any) -> str:
    """A model id facet: local-checkpoint ids with a workstation path become one bucket (counts only)."""
    if isinstance(value, str) and LOCAL_PATH_MODEL.search(value):
        return LOCAL_MODEL_FACET
    return fv(value)


def outcome_value(value: Any) -> Any:
    """An outcome as a small raw scalar (bool/int/float/short str); containers and long text are typed only."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        ok = len(value) <= 40 and value.isprintable() and not _ACCOUNTISH.search(value) and not SECRETISH.search(value)
        return value if ok else "<str>"
    return "<" + type(value).__name__ + ">"


def dict_outcomes(prefix: str, value: Any, limit: int = 8) -> dict[str, Any]:
    """Scalar members of a small outcome object (``scores.completion`` = ``{score, ...}``) as ``prefix.key``."""
    if not isinstance(value, Mapping):
        return {prefix: outcome_value(value)}
    out: dict[str, Any] = {}
    for key, item in list(value.items())[:limit]:
        if isinstance(key, str) and (item is None or isinstance(item, bool | int | float | str)):
            out[f"{prefix}.{fv(key)}"] = outcome_value(item)
    return out


def obj(value: Any, key: str) -> Mapping[str, Any]:
    """``value[key]`` when both are objects, else an empty mapping (raw data is untrusted: any shape may appear)."""
    if isinstance(value, Mapping):
        item = value.get(key)
        if isinstance(item, Mapping):
            return item
    return {}


def norm_content(content: Any) -> Any:
    """Message content for the fingerprint: a string as is; a block list as ``[type, text]`` pairs; else the raw value."""
    if isinstance(content, list):
        out: list[Any] = []
        for block in content:
            if isinstance(block, Mapping):
                kind = block.get("type")
                text = next((block[k] for k in ("text", "content", "reasoning", "refusal") if k in block), None)
                out.append([kind, text if text is not None else {k: v for k, v in block.items() if k != "type"}])
            else:
                out.append(block)
        return out
    return content


def empty_content(content: Any) -> bool:
    """E2 A03's empty turn on normalised content: nothing, or a block list whose blocks are all empty text blocks
    (v1.k14 local-model logs write ``[{"type": "text", "text": ""}]``; pre-check CC-08 / agentdojo-upstream PC-08)."""
    if content in (None, "", []):
        return True
    return isinstance(content, list) and all(
        isinstance(b, list) and len(b) == 2 and b[0] == "text" and b[1] in (None, "") for b in content)


@dataclass
class UnitView:
    """What a hook says about one unit (see the module docstring)."""

    locator: str = ""
    facets: dict[str, str] = field(default_factory=dict)
    steps: list[Any] | None = None
    outcomes: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    variant: str | None = None


@dataclass(frozen=True)
class Ctx:
    """What a hook may know about the part: the source profile's id, part and parsed ``[import]``/family data."""

    profile_id: str
    part: str
    layout: str | None = None
    variant_labels: Mapping[str, str] = field(default_factory=dict)
    members: tuple[str, ...] = ()
    producer_band: tuple[str, ...] = ()


# ================================================================================================ path layouts
_SEG: Final = re.compile(r"^\{([a-z_]+)(\??)\}(.*)$")


def layout_facets(template: str | None, label: str) -> tuple[dict[str, str], list[str]]:
    """The named components of ``label`` under an AgentDojo-family ``layout`` template (written from the profile data's
    documented rule, not from ``agentdojo.layout``): literal segments must match, ``{x}`` captures one segment (a suffix
    such as ``.json`` is stripped), ``{x?}`` spans zero or more segments (joined by ``/``). Without an optional component
    the template is aligned from the right (leading directories become ``_prefix``); with one, the segments before it are
    aligned from the left and those after it from the right. Returns ``(facets, flags)``; ``layout_mismatch`` flags a
    label that does not fit."""
    segs = label.split("/")
    if not template:
        names = ("pipeline_dir", "suite", "task_dir", "attack_dir", "file")
        tail = segs[-5:] if len(segs) >= 5 else [NONE] * (5 - len(segs)) + segs
        plain = dict(zip(names, tail, strict=True))
        plain["file"] = re.sub(r"\.json$", "", plain["file"])
        plain["_prefix"] = "/".join(segs[:-5]) or NONE
        return {k: fv(v) for k, v in plain.items()}, ([] if len(segs) >= 5 else ["layout_mismatch"])
    tpl = template.split("/")
    opt = next((i for i, s in enumerate(tpl) if (m := _SEG.match(s)) and m.group(2) == "?"), None)
    out: dict[str, str] = {}
    flags: list[str] = []

    def bind(t: str, s: str) -> None:
        m = _SEG.match(t)
        if m is None:
            if t != s:
                flags.append("layout_mismatch")
            return
        name, _q, suffix = m.groups()
        if suffix and s.endswith(suffix):
            s = s[: -len(suffix)]
        elif suffix:
            flags.append("layout_mismatch")
        out[name] = s

    if opt is None:
        if len(segs) < len(tpl):
            return {}, ["layout_mismatch"]
        for t, s in zip(tpl, segs[len(segs) - len(tpl) :], strict=True):
            bind(t, s)
        out["_prefix"] = "/".join(segs[: len(segs) - len(tpl)]) or NONE
    else:
        left, right = tpl[:opt], tpl[opt + 1 :]
        if len(segs) < len(left) + len(right):
            return {}, ["layout_mismatch"]
        for t, s in zip(left, segs[: len(left)], strict=True):
            bind(t, s)
        for t, s in zip(right, segs[len(segs) - len(right) :], strict=True):
            bind(t, s)
        m = _SEG.match(tpl[opt])
        assert m is not None
        middle = segs[len(left) : len(segs) - len(right)]
        out[m.group(1)] = "/".join(middle) if middle else NONE
    return {k: fv(v) for k, v in out.items()}, sorted(set(flags))


# ================================================================================================ agentdojo
K11: Final = frozenset({"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type", "injections",
                        "messages", "error", "utility", "security", "duration"})  # fmt: skip
K14_EXTRA: Final = frozenset({"benchmark_version", "evaluation_timestamp", "agentdojo_package_version"})
KD18: Final = frozenset({"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type",
                         "build_constraints", "injection_isolation", "dynamic_validation", "adaptive_attack",
                         "tool_permission", "initial_trajectory", "initial_checklist", "benchmark_version", "utility",
                         "security", "total_tokens", "duration"})  # fmt: skip
_OUTCOME_KEYS: Final = ("utility", "security", "duration")


def agentdojo_variant(value: Any) -> str:
    """The TraceLogger generation from the key set (independent of ``agentdojo.dialect.classify``)."""
    if not isinstance(value, Mapping) or "suite_name" not in value or "user_task_id" not in value:
        return "not_tracelogger"
    msgs = "messages" if isinstance(value.get("messages"), list) else (
        "conversations" if isinstance(value.get("conversations"), list) else None)  # fmt: skip
    if msgs is None:
        return "not_tracelogger"
    if "build_constraints" in value:
        return f"drift.k18.{msgs}"
    if "pipeline_name" not in value:
        return "pre_v0"
    base = "v1.k14" if "agentdojo_package_version" in value else "v0.k11"
    return base + (".incomplete" if any(k not in value for k in _OUTCOME_KEYS) else "")


#: Extra path facets by segment index (from the inventory) for layouts whose optional component spans several segments.
_SEGMENT_FACETS: Final[Mapping[str, Mapping[str, int]]] = {
    "seagent-agentdojo": {"kind": 5, "arm": 6, "run_dir": 7},
}


def agentdojo_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    view = UnitView()
    # a member of a declared nested archive (D-382) has the chain label ``<container>!/<member>``: the layout is read from
    # the member's own label, as the mapper reads a member origin's label (D-156), and the containers above it are the
    # ``container`` facet (authority-caps' experiment tars, ipi-defenses' run tars). A label without ``!/`` is unchanged.
    chain = label.split("!/")
    own = chain[-1]
    facets, flags = layout_facets(ctx.layout, own)
    if len(chain) > 1:
        facets["container"] = fv("!/".join(chain[:-1]))
    for name, index in _SEGMENT_FACETS.get(ctx.profile_id, {}).items():
        segs = own.split("/")
        facets[name] = fv(segs[index]) if index < len(segs) else NONE
    variant = agentdojo_variant(value)
    view.variant = variant
    facets["variant"] = variant
    attack_dir = facets.get("attack_dir", NONE)
    facets["attack_class"] = "none" if attack_dir in ("none", NONE) else "attacked"
    task_dir = facets.get("task_dir", NONE)
    facets["task_kind"] = "prepass" if task_dir.startswith("injection_task") else "user"
    file = facets.get("file", NONE)
    facets["injection_variant"] = "memory" if file.endswith("_memory_injection") else "plain"
    facets["attack_family"] = re.sub(r"_injection_task_\d+$", "", attack_dir)
    run_set = facets.get("run_set")
    if run_set is not None:
        facets["run_set_family"] = re.sub(r"-\d+$", "", run_set)
    if variant == "not_tracelogger":
        view.facets, view.flags = facets, [*flags, "not_tracelogger"]
        return view
    assert isinstance(value, Mapping)
    facets["h_suite"] = fv(value.get("suite_name"))
    facets["h_attack"] = fv(value.get("attack_type") or "none")
    facets["h_pipeline"] = model_fv(value.get("pipeline_name"))
    # path_must_agree (suite_name, user_task_id, attack_type, injection_task_id), checked independently
    expect = {"suite": value.get("suite_name"), "task_dir": value.get("user_task_id"),
              "attack_dir": value.get("attack_type") or "none", "file": value.get("injection_task_id") or "none"}  # fmt: skip
    for key, header in expect.items():
        got = facets.get(key)
        if got is None or got == NONE:
            continue
        if key == "file" and ctx.profile_id == "craibench-agentdojo":
            continue  # D-107: CrAIBench's file stem carries the memory variant, injection_task_id is not compared
        if fv(header) != got:
            flags.append(f"path_disagrees:{key}")
    messages = value.get("messages") if isinstance(value.get("messages"), list) else value.get("conversations")
    steps: list[Any] = []
    assistants = 0
    for m in messages or ():
        if not isinstance(m, Mapping):
            steps.append(["<non-object>", m])
            continue
        role = m.get("role")
        assistants += role == "assistant"
        calls: list[Any] = []
        for c in m.get("tool_calls") or ():
            if isinstance(c, Mapping):
                calls.append([c.get("function"), c.get("args")])
        tc = m.get("tool_call")
        if role == "tool" and isinstance(tc, Mapping):
            calls.append([tc.get("function"), tc.get("args")])
        steps.append([role, norm_content(m.get("content")), calls, m.get("error")])
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    if value.get("error") not in (None, "") and assistants == 0:
        flags.append("error_only")
    if any(k not in value for k in _OUTCOME_KEYS):
        flags.append("incomplete")
    last_assistant = next((s for s in reversed(steps) if s and s[0] == "assistant"), None)
    if last_assistant is not None and empty_content(last_assistant[1]) and not last_assistant[2]:
        flags.append("null_final")
    if steps and isinstance(steps[-1], list) and steps[-1][0] == "assistant" and steps[-1][2]:
        flags.append("trailing_calls")  # the log ends on an assistant turn whose calls have no result (wave-2 PC-06)
    if variant.startswith(("v0", "v1")):
        extra = set(value) - K11 - K14_EXTRA
        if extra:
            flags.append("extra_keys")
    view.outcomes = {"utility": outcome_value(value.get("utility")), "security": outcome_value(value.get("security")),
                     "error_present": value.get("error") not in (None, "")}  # fmt: skip
    if ctx.variant_labels:
        part = ctx.variant_labels.get(variant.removesuffix(".incomplete"))
        facets["variant_part"] = part or NONE
    view.facets, view.flags = facets, sorted(set(flags))
    return view


# ================================================================================================ adprov transcript/v1
def adprov_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    segs = label.split("/")
    stem = re.sub(r"\.transcript\.json$", "", segs[-1])
    facets = {"model_folder": fv(segs[-4] if len(segs) >= 4 else None), "attack": fv(segs[-2] if len(segs) >= 2 else None),
              "suite": fv(stem.split("_user_task")[0] if "_user_task" in stem else None),
              "task_kind": "benign" if stem.endswith("_benign") else "attacked"}  # fmt: skip
    flags = [] if len(segs) >= 4 and segs[-3] == "prov" else ["layout_mismatch"]
    view = UnitView(facets=facets)
    if not isinstance(value, Mapping) or value.get("adprov_schema") != "transcript/v1":
        view.flags = [*flags, "not_transcript_v1"]
        return view
    meta = obj(value, "meta")
    facets["h_attack"] = fv(meta.get("attack_type"))
    facets["h_suite"] = fv(meta.get("suite"))
    facets["h_model"] = model_fv(meta.get("model"))
    if facets["h_attack"] != facets["attack"]:
        flags.append("path_disagrees:attack")
    steps: list[Any] = []
    for t in value.get("turns") or ():
        if not isinstance(t, Mapping):
            steps.append(["<non-object>", t])
            continue
        role = t.get("role")
        calls = [[c.get("function"), c.get("args")] for c in t.get("tool_calls") or () if isinstance(c, Mapping)]
        if role == "tool":
            calls.append([t.get("function"), t.get("args")])
        content = t.get("content") if "content" in t else t.get("text")
        steps.append([role, norm_content(content), calls, t.get("error")])
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    view.outcomes = {"utility": outcome_value(meta.get("utility")), "security": outcome_value(meta.get("security")),
                     "run_error_present": meta.get("run_error") not in (None, "")}  # fmt: skip
    view.flags = sorted(set(flags))
    return view


# ================================================================================================ inspect .eval
_SAMPLE_MEMBER: Final = re.compile(r"^samples/[^/]+_epoch_\d+\.json$")
#: Sample-level facets by profile (sample ``/metadata`` keys); the log-level facets come from the header and the label.
_INSPECT_SAMPLE_FACETS: Final[Mapping[str, tuple[str, ...]]] = {
    "controlarena-persistent": ("eval_mode", "setting_name", "side_task_name"),
    "atia-benchmark": ("attack_type",),
    "survey-agentharm": ("category",),
    "kexin-xu-01-agentharm": ("category",),
    "fragfuse-agentharm": ("category",),
}


def is_sample_member(label: str) -> bool:
    return _SAMPLE_MEMBER.match(label) is not None


def inspect_log_facets(header: Any, label: str, ctx: Ctx) -> tuple[dict[str, str], list[str]]:
    """Log-level facets of one ``.eval`` from its label and ``header.json`` (``None`` header: label facets only)."""
    chain = label.split("!/")
    path = chain[-1]
    segs = path.split("/")
    directory = "/".join(segs[:-1])
    facets: dict[str, str] = {"dir": fv(directory or None)}
    flags: list[str] = []
    pid = ctx.profile_id
    if pid == "survey-agentharm":
        facets["results_dir"] = fv(segs[-2] if len(segs) >= 2 else None)
    elif pid == "whistlebench":
        facets["experiment"] = fv(directory.removeprefix("final_runs/") or None)
    elif pid == "kexin-xu-01-agentharm":
        facets["judge_variant"] = fv(segs[1] if len(segs) > 2 else "base")
    elif pid == "fragfuse-agentharm":
        facets["experiment"] = ("carrier" if "carrier_inject_eval" in path else "retrieve"
                                if "retrieve_test_logs_memory" in path else "logs_archive")  # fmt: skip
    elif pid == "controlarena-persistent":
        top = chain[0] if len(chain) > 1 else (segs[1] if len(segs) > 2 and segs[0] == "logs" else segs[0])
        facets["experiment"] = fv(top)
    elif pid == "atia-benchmark":
        facets["log"] = fv(re.sub(r"\.eval$", "", segs[-1]))
    if not isinstance(header, Mapping):
        flags.append("no_header")
        return facets, flags
    ev = obj(header, "eval")
    facets["model"] = model_fv(ev.get("model"))
    facets["task"] = fv(ev.get("task"))
    roles = obj(ev, "model_roles")
    for role in ("untrusted", "trusted"):
        entry = roles.get(role)
        if isinstance(entry, Mapping):
            facets[role] = model_fv(entry.get("model"))
    meta = obj(ev, "metadata")
    if "mode" in meta:
        facets["mode"] = fv(meta.get("mode"))
    facets["status"] = fv(header.get("status"))
    packages = obj(ev, "packages")
    producer = packages.get("inspect_ai")
    facets["producer"] = fv(producer)
    if ctx.producer_band and producer not in ctx.producer_band:
        flags.append("producer_out_of_band")
    if header.get("version") != 2:
        flags.append("log_version_not_2")
    if pid == "whistlebench":
        args = obj(ev, "task_args")
        params = args.get("params") if isinstance(args.get("params"), Mapping) else args
        grader = params.get("grader_model") if isinstance(params, Mapping) else None
        facets["grader"] = model_fv(grader)
    if pid == "kexin-xu-01-agentharm" or pid == "fragfuse-agentharm" or pid == "survey-agentharm":
        facets["split"] = "benign" if "benign" in str(ev.get("task", "")) else "harmful"
    return facets, flags


def inspect_sample_unit(value: Any, member: str, ctx: Ctx) -> UnitView:
    view = UnitView(locator=member)
    if not isinstance(value, Mapping):
        view.flags = ["not_a_sample"]
        return view
    meta = obj(value, "metadata")
    for key in _INSPECT_SAMPLE_FACETS.get(ctx.profile_id, ()):
        view.facets[key] = fv(meta.get(key))
    if ctx.profile_id == "atia-benchmark":
        kinds = set()
        for m in value.get("messages") or ():
            if isinstance(m, Mapping) and m.get("role") == "user" and isinstance(m.get("content"), list):
                kinds |= {str(p.get("type")) for p in m["content"] if isinstance(p, Mapping) and p.get("type") != "text"}
        view.facets["media_kind"] = "+".join(sorted(kinds)) or "none"
    steps: list[Any] = []
    for m in value.get("messages") or ():
        if not isinstance(m, Mapping):
            steps.append(["<non-object>", m])
            continue
        calls = [[c.get("function"), c.get("arguments")] for c in m.get("tool_calls") or () if isinstance(c, Mapping)]
        if m.get("role") == "tool":
            calls.append([m.get("function"), None])
        steps.append([m.get("role"), norm_content(m.get("content")), calls, m.get("error")])
    view.steps = steps or None
    flags = []
    if not steps:
        flags.append("zero_messages")
    if value.get("error") not in (None, ""):
        flags.append("sample_error")
    if value.get("limit") not in (None, ""):
        flags.append("sample_limit")
    if not value.get("events"):
        flags.append("zero_events")
    view.flags = flags
    scores = obj(value, "scores")
    for name, score in scores.items():
        if isinstance(score, Mapping):
            view.outcomes.update(dict_outcomes(f"score.{fv(name)}", score.get("value")))
    return view


# ================================================================================================ dtap
_DTAP_TS: Final = re.compile(r"^\d{8}_\d{6}(?:_\d+|\(1\))?\.json$")


def dtap_file_class(name: str) -> str:
    if name in ("judge_result.json", "judge_result(1).json"):
        return "judge"
    if name == "trajectory.json":
        return "trajectory"
    if name == "partial_trajectory.json":
        return "partial"
    if name.startswith("red_teaming_agent_"):
        return "red_teaming"
    if _DTAP_TS.match(name):
        return "copy" if name.endswith("(1).json") else ("rerun" if name[15:].startswith("_") else "timestamp")
    return "other"


def dtap_path_facets(label: str) -> tuple[dict[str, str], list[str]]:
    segs = label.split("/")
    facets = {k: NONE for k in ("framework", "model", "domain", "split", "threat", "risk_category", "subcategory")}
    flags: list[str] = []
    if len(segs) < 6 or segs[3] not in ("benign", "malicious"):
        return facets | {"split_label": NONE, "file_class": dtap_file_class(segs[-1])}, ["layout_mismatch"]
    facets.update(framework=fv(segs[0]), model=fv(segs[1]), domain=fv(segs[2]), split=segs[3])
    if segs[3] == "malicious":
        if len(segs) < 8:
            flags.append("layout_mismatch")
        else:
            facets.update(threat=fv(segs[4]), risk_category=fv(segs[5]))
    elif len(segs) == 7:
        facets["subcategory"] = fv(segs[4])
    facets["split_label"] = facets["threat"] if segs[3] == "malicious" else "benign"
    facets["file_class"] = dtap_file_class(segs[-1])
    return facets, flags


def dtap_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    facets, flags = dtap_path_facets(label)
    view = UnitView(facets=facets)
    if facets["file_class"] == "judge":
        view.outcomes = judge_outcomes(value)
        view.flags = [*flags, "judge_only_unit"]
        return view
    if not isinstance(value, Mapping):
        view.flags = [*flags, "not_a_trajectory"]
        return view
    traj = value.get("trajectory")
    steps: list[Any] = []
    harness_error = False
    for s in traj if isinstance(traj, list) else ():
        if not isinstance(s, Mapping):
            steps.append(["<non-object>", s])
            continue
        md = obj(s, "metadata")
        if s.get("action") == "error":
            harness_error = True
        steps.append([s.get("role"), s.get("action"), md.get("tool_name"), md.get("tool_params"), md.get("message"),
                      s.get("state")])  # fmt: skip
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    if harness_error:
        flags.append("harness_error")
    ti = obj(value, "task_info")
    tr = obj(value, "traj_info")
    md = obj(tr, "metadata")
    if ti.get("synthetic") or md.get("synthetic"):
        flags.append("synthetic")
    view.outcomes = {"traj_success": outcome_value(tr.get("success"))}
    view.flags = sorted(set(flags))
    return view


def judge_outcomes(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    out = {"task_success": outcome_value(value.get("task_success")),
           "attack_success": outcome_value(value.get("attack_success"))}  # fmt: skip
    if "audit_correction" in value:
        out["audit_corrected"] = True
    return out


# ================================================================================================ openhands
_OAS: Final = re.compile(r"(?:^|/)evaluation/([^/]+)/traj_([^/]+)\.json$")
_RC: Final = re.compile(r"(?:^|/)results/OH/([^/]+)/(S\d)/([^/]+)/trajectory/oh_(.+?)_(\d+)_(py|sh)_(S\d)-([^/]+)\.json$")


def openhands_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    view = UnitView()
    flags: list[str] = []
    if (m := _OAS.search(label)) is not None:
        view.facets = {"source_kind": "oas", "model": fv(m.group(1)), "task": fv(m.group(2))}
    elif (m := _RC.search(label)) is not None:
        view.facets = {"source_kind": "redcode", "model": fv(m.group(1)), "target": m.group(2), "language": fv(m.group(3)),
                       "scenario": fv(m.group(4)), "payload": fv(m.group(5))}  # fmt: skip
        if m.group(2) != m.group(7):
            flags.append("path_disagrees:target")
    else:
        flags.append("layout_mismatch")
    if not isinstance(value, list):
        view.flags = [*flags, "not_an_event_list"]
        return view
    steps: list[Any] = []
    variant = "oas-0.28"
    last_id: Any = None
    for e in value:
        if not isinstance(e, Mapping):
            steps.append(["<non-object>", e])
            continue
        if e.get("action") == "system" and isinstance(e.get("args"), Mapping) and "openhands_version" in e["args"]:
            variant = "oh-1.5"
        tcm = obj(e, "tool_call_metadata")
        kind = ["action", e.get("action")] if "action" in e else ["observation", e.get("observation")]
        args = e.get("args") if "action" in e else None
        content = e.get("content") if "observation" in e else None
        steps.append([e.get("source"), kind, e.get("message"), tcm.get("function_name"), args, content])
        if isinstance(e.get("id"), int) and isinstance(last_id, int) and e["id"] <= last_id:
            flags.append("ids_not_increasing")
        last_id = e.get("id", last_id)
    view.variant = variant
    view.facets["variant"] = variant
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    view.flags = sorted(set(flags))
    return view


# ================================================================================================ agentops
_AGENTOPS: Final = re.compile(r"(?:^|/)pilot_v1_seeded/([^/]+)/([^/]+)/([^/]+)/(.+)_(\d{3})_run(\d+)\.json$")


def agentops_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    view = UnitView()
    flags: list[str] = []
    if (m := _AGENTOPS.search(label)) is not None:
        view.facets = {"agent_dir": fv(m.group(1)), "provider_model": fv(m.group(2)), "condition": fv(m.group(3)),
                       "domain": fv(m.group(4)), "run": m.group(6)}  # fmt: skip
    else:
        flags.append("layout_mismatch")
    if not isinstance(value, Mapping):
        view.flags = [*flags, "not_a_run"]
        return view
    if fv(value.get("condition")) != view.facets.get("condition", fv(value.get("condition"))):
        flags.append("path_disagrees:condition")
    trace = obj(value, "trace")
    steps: list[Any] = []
    for s in trace.get("steps") or ():
        if not isinstance(s, Mapping):
            steps.append(["<non-object>", s])
            continue
        calls = [[c.get("tool_name"), c.get("arguments")] for c in s.get("tool_calls") or () if isinstance(c, Mapping)]
        results = [[r.get("tool_name"), r.get("result")] for r in s.get("tool_results") or () if isinstance(r, Mapping)]
        steps.append([s.get("reasoning"), calls, results])
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
        if trace.get("error"):
            flags.append("error_only")
    scores = obj(value, "scores")
    view.outcomes = {"completed": outcome_value(trace.get("completed")), "error_present": bool(trace.get("error")),
                     **dict_outcomes("completion", scores.get("completion")), **dict_outcomes("safety", scores.get("safety"))}  # fmt: skip
    view.flags = sorted(set(flags))
    return view


# ================================================================================================ credleak
def credleak_cell_facets(value: Any, label: str) -> tuple[dict[str, str], list[str]]:
    segs = label.split("/")
    facets: dict[str, str] = {"section": fv(segs[1] if len(segs) > 1 else None), "channel": fv(segs[2] if len(segs) > 2 else None)}
    flags: list[str] = []
    if len(segs) >= 5 and segs[3] == "excluded-models":
        facets.update(layout_class="excluded-models", model_dir=fv(segs[4]))
    elif len(segs) >= 4 and segs[3].startswith("_"):
        facets.update(layout_class="underscore", model_dir=NONE)
    elif len(segs) >= 5:
        facets.update(layout_class="roster", model_dir=fv(segs[3]))
    else:
        facets.update(layout_class=NONE, model_dir=NONE)
        flags.append("layout_mismatch")
    name = segs[-1]
    prefix = name.split("__", 1)[0] if "__" in name else NONE
    facets["batch"] = "archive" if prefix.startswith("archive-") else "addendum" if prefix.startswith("addendum-") else fv(prefix)
    if isinstance(value, Mapping):
        facets.update(model=model_fv(value.get("model")), technique=fv(value.get("technique")),
                      scenario=fv(value.get("scenario")), defence=fv(value.get("defence")))  # fmt: skip
    return facets, flags


def credleak_run_unit(run: Any, index: int) -> UnitView:
    view = UnitView(locator=f"/runs/{index}")
    if not isinstance(run, Mapping):
        view.flags = ["not_a_run"]
        return view
    steps: list[Any] = []
    for t in run.get("turns") or ():
        if not isinstance(t, Mapping):
            steps.append(["<non-object>", t])
            continue
        calls = [[c.get("tool"), c.get("input"), c.get("output")] for c in t.get("toolCalls") or () if isinstance(c, Mapping)]
        steps.append([t.get("userMessage"), t.get("assistantResponse"), calls])
    view.steps = steps or None
    view.flags = [] if steps else ["zero_messages"]
    if run.get("invocationError"):
        view.flags.append("invocation_error")
    view.outcomes = {k: outcome_value(run.get(k)) for k in ("hijackSucceeded", "exfiltrationDetected", "agentDetected")}
    if run.get("repetition") != index + 1:
        view.flags.append("repetition_not_index")
    return view


# ================================================================================================ autogen
_AUTOGEN: Final = re.compile(r"(?:^|/)results/phase(\d+)(?:/([^/]+))?/runs\.jsonl$")


def autogen_file_facets(label: str) -> tuple[dict[str, str], list[str]]:
    m = _AUTOGEN.search(label)
    if m is None:
        return {"phase": NONE, "arm": NONE}, ["layout_mismatch"]
    return {"phase": m.group(1), "arm": fv(m.group(2))}, []


def autogen_row_unit(value: Any, line: int) -> UnitView | None:
    """One run row (``None``: a non-run row, which the scanner counts as such)."""
    if not isinstance(value, Mapping) or "run_id" not in value or "messages" not in value:
        return None
    view = UnitView(locator=f"line:{line}")
    for key in ("entry", "defense", "condition", "block_guard", "block_at"):
        view.facets[key] = fv(value.get(key))
    modes = value.get("modes")
    if isinstance(modes, Mapping):
        view.facets["modes"] = ",".join(f"{k}:{fv(modes[k])}" for k in sorted(modes))
    steps: list[Any] = []
    for m in value.get("messages") or ():
        if not isinstance(m, Mapping):
            steps.append(["<non-object>", m])
            continue
        raw = obj(m, "raw")
        steps.append([m.get("type"), m.get("source"), m.get("text"), raw.get("content")])
    view.steps = steps or None
    view.flags = [] if steps else ["zero_messages"]
    view.outcomes = {"stop_reason": outcome_value(value.get("stop_reason")), "error_present": value.get("error") not in (None, "")}
    return view


# ================================================================================================ wirelog
_WIRELOG: Final = re.compile(r"(?:^|/)runs_named/([A-Za-z0-9][A-Za-z0-9._:-]*)__([a-z0-9_]+)__(\d{4,})/[^/]+$")


def wirelog_unit(value: Any, label: str, ctx: Ctx) -> UnitView:
    view = UnitView()
    flags: list[str] = []
    if (m := _WIRELOG.search(label)) is not None:
        view.facets = {"model_dir": fv(m.group(1)), "arm": fv(m.group(2)), "attacked": "no" if m.group(2) == "clean" else "yes"}
    else:
        flags.append("layout_mismatch")
    if not isinstance(value, list):
        view.flags = [*flags, "not_a_response_list"]
        return view
    steps: list[Any] = []
    for r in value:
        if not isinstance(r, Mapping):
            steps.append(["<non-object>", r])
            continue
        if "output" in r:  # Bedrock Converse
            msg = obj(obj(r, "output"), "message")
            items = msg.get("content") if isinstance(msg, Mapping) else None
            steps.append(["converse", r.get("stopReason"), norm_wire(items)])
        else:  # Anthropic Messages (run 0001)
            steps.append(["messages", r.get("stop_reason"), norm_wire(r.get("content"))])
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    view.variant = "anthropic-messages" if value and isinstance(value[0], Mapping) and "output" not in value[0] else "bedrock-converse"
    view.facets["variant"] = view.variant
    view.flags = flags
    return view


def norm_wire(items: Any) -> Any:
    if not isinstance(items, list):
        return items
    out: list[Any] = []
    for it in items:
        if isinstance(it, Mapping) and "toolUse" in it and isinstance(it["toolUse"], Mapping):
            out.append(["toolUse", it["toolUse"].get("name"), it["toolUse"].get("input")])
        elif isinstance(it, Mapping) and it.get("type") == "tool_use":
            out.append(["toolUse", it.get("name"), it.get("input")])
        elif isinstance(it, Mapping):
            out.append(["text", it.get("text")])
        else:
            out.append(it)
    return out


# ================================================================================================ mcphunt
def mcphunt_trace_unit(value: Any, index: int) -> UnitView:
    view = UnitView(locator=f"/traces/{index}")
    if not isinstance(value, Mapping):
        view.flags = ["not_a_trace"]
        return view
    for key in ("model", "defense", "mitigation_level", "env_type", "risk_mechanism"):
        view.facets[key] = model_fv(value.get(key)) if key == "model" else fv(value.get(key))
    steps: list[Any] = []
    for m in value.get("messages") or ():
        if not isinstance(m, Mapping):
            steps.append(["<non-object>", m])
            continue
        calls = []
        for c in m.get("tool_calls") or ():
            if isinstance(c, Mapping):
                fn = obj(c, "function")
                calls.append([fn.get("name"), fn.get("arguments")])
        steps.append([m.get("role"), m.get("content"), calls])
    view.steps = steps or None
    view.flags = [] if steps else ["zero_messages"]
    canary = sum(1 for e in value.get("events") or () if isinstance(e, Mapping)
                 and (e.get("canary_in_result") or e.get("canary_in_args")))  # fmt: skip
    if canary:
        view.flags.append("canary_flagged")
    labeling = obj(value, "labeling")
    view.outcomes = {"outcome": outcome_value(value.get("outcome")), "any_risk": outcome_value(labeling.get("any_risk")),
                     "task_completed": outcome_value(value.get("task_completed"))}  # fmt: skip
    return view


# ================================================================================================ geminicli
_GEMINI: Final = re.compile(r"(?:^|/)cells/([a-z][a-z_]*)__([A-Za-z0-9][A-Za-z0-9._-]*)/(SK-[A-Z0-9]+)__(m\d{2})/([^/]+)$")


def geminicli_path_facets(label: str) -> tuple[dict[str, str], list[str]]:
    m = _GEMINI.search(label)
    if m is None:
        return {"scaffold": NONE, "model": NONE, "skeleton": NONE, "mutation": NONE}, ["layout_mismatch"]
    return {"scaffold": m.group(1), "model": fv(m.group(2)), "skeleton": m.group(3), "mutation": m.group(4)}, []


def geminicli_stream_unit(lines: Sequence[Any], label: str) -> UnitView:
    facets, flags = geminicli_path_facets(label)
    view = UnitView(facets=facets)
    steps: list[Any] = []
    has_result = False
    for e in lines:
        if not isinstance(e, Mapping):
            steps.append(["<non-object>", e])
            continue
        kind = e.get("type")
        has_result |= kind == "result"
        if kind == "message":
            steps.append(["message", e.get("role"), e.get("content")])
        elif kind == "tool_use":
            steps.append(["tool_use", e.get("tool_name"), e.get("parameters")])
        elif kind == "tool_result":
            err = obj(e, "error")
            steps.append(["tool_result", e.get("status"), e.get("output"), err.get("type")])
        elif kind == "result":
            steps.append(["result", e.get("status")])
    view.steps = steps or None
    if not steps:
        flags.append("zero_messages")
    if lines and not has_result:
        flags.append("unterminated")
    view.flags = flags
    return view


def geminicli_verdict_outcomes(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {"elicited": outcome_value(value.get("elicited")), "n_misaligned": outcome_value(value.get("n_misaligned")),
            "timed_out": outcome_value(value.get("timed_out"))}  # fmt: skip


# ================================================================================================ registry of hooks
@dataclass(frozen=True)
class Hook:
    """A family hook: ``kind`` is the artefact shape the scanner parses (``json``, ``jsonl``, ``eval``, ``jsonstream``);
    the callables give the unit views (see each family above)."""

    dialect: str
    kind: str
    unit: Callable[[Any, str, Ctx], UnitView] | None = None
    #: ``jsonl`` only: ``"rows"`` (every line a unit, autogen) or ``"file"`` (the file is one unit, geminicli)
    jsonl_mode: str = "file"
    #: auxiliary file name -> outcome reader, joined into the unit rows of the same directory (judge, verdict)
    aux_outcomes: Mapping[str, Callable[[Any], dict[str, Any]]] = field(default_factory=dict)
    default_strata: tuple[str, ...] = ()


HOOKS: Final[Mapping[str, Hook]] = {
    "agentdojo.tracelogger": Hook("agentdojo.tracelogger", "json", agentdojo_unit,
                                  default_strata=("_prefix", "pipeline_dir", "suite", "attack_dir")),
    "adprov.transcript_v1": Hook("adprov.transcript_v1", "json", adprov_unit, default_strata=("model_folder", "attack", "suite")),
    "inspect.eval": Hook("inspect.eval", "eval", default_strata=("dir", "model", "task")),
    "dtap.trajectory": Hook("dtap.trajectory", "json", dtap_unit,
                            aux_outcomes={"judge_result.json": judge_outcomes},
                            default_strata=("framework", "model", "split_label")),
    "openhands.events": Hook("openhands.events", "json", openhands_unit, default_strata=("model",)),
    "agentops.trace": Hook("agentops.trace", "json", agentops_unit, default_strata=("provider_model", "condition", "domain")),
    "credleak.cell": Hook("credleak.cell", "json", default_strata=("model", "technique", "layout_class")),
    "autogen.runs": Hook("autogen.runs", "jsonl", jsonl_mode="rows", default_strata=("phase", "arm")),
    "wirelog.request_response": Hook("wirelog.request_response", "json", wirelog_unit, default_strata=("model_dir", "arm")),
    "mcphunt.traces": Hook("mcphunt.traces", "jsonstream", default_strata=("split", "document")),
    "geminicli.stream_json": Hook("geminicli.stream_json", "jsonl", jsonl_mode="file",
                                  aux_outcomes={"verdict.json": geminicli_verdict_outcomes},
                                  default_strata=("model", "skeleton")),
}  # fmt: skip

#: Stratum keys per source profile (the inventory's suggested arm keys); every other profile takes its family default.
STRATA: Final[Mapping[str, tuple[str, ...]]] = {
    "agentdojo-upstream": ("pipeline_dir", "attack_dir", "suite", "variant"),
    "agentdyn": ("pipeline_dir", "attack_dir", "suite"),
    "rope": ("model_dir", "attack_dir", "suite"),
    "survey-runs": ("results_dir", "attack_dir", "suite"),
    "mandate-agentdojo-eval": ("pipeline_dir", "attack_dir"),
    "interbolt-agentdojo": ("experiment", "suite", "pipeline_dir", "attack_dir"),
    "melon-agentdojo": ("pipeline_dir", "attack_dir", "suite"),
    "glitch-agentdojo": ("pipeline_dir", "suite", "attack_dir"),
    "mohameduk-agentdojo": ("pipeline_dir", "suite", "attack_dir"),
    "tacit-agentdojo": ("model_dir", "suite", "attack_dir"),
    "geryon-agentdojo": ("model_dir", "attack_dir"),
    "hilarytorn-trajectory-poisoning": ("arm", "attack_family"),
    "yockcheng-prompt-injection-harness": ("tree", "pipeline_dir", "attack_dir"),
    "shreeyavarma-llm-safety": ("results_dir", "pipeline_dir", "attack_dir"),
    "gate-agentdojo": ("pipeline_dir", "attack_dir", "suite"),
    "sentry-agentdojo": ("pipeline_dir", "attack_dir", "suite"),
    "bookkeeper-agentdojo": ("pipeline_dir", "attack_dir"),
    "aiauthz-agentdojo": ("model_dir", "attack_dir"),
    "kongminos-agentdojo": ("run_set", "attack_dir", "suite"),
    "ceferisbarov-agentdojo": ("arm", "pipeline_dir"),
    "linyxus-agentdojo": ("pipeline_dir", "run_set_family", "suite"),
    "craibench-agentdojo": ("pipeline_dir", "suite", "attack_dir", "injection_variant"),
    "menelaus29-ipi-multidomain": ("model_dir", "attack_class"),
    "llm-lock-agentdojo": ("model_dir", "attack_dir", "suite"),
    "seagent-agentdojo": ("kind", "arm", "suite"),
    "drift": ("suite", "attack_dir"),
    "survey-agentharm": ("results_dir",),
    "whistlebench": ("experiment", "model"),
    "kexin-xu-01-agentharm": ("judge_variant", "model", "task"),
    "fragfuse-agentharm": ("experiment", "model", "task"),
    "controlarena-persistent": ("experiment", "untrusted", "mode"),
    "atia-benchmark": ("task",),
    "openagentsafety": ("model",),
    "redcode-exec-openhands": ("model", "target", "language"),
    "credleak-p15b": ("model", "technique", "layout_class"),
    # wave 7 (phase 10j, merged 2026-10-15; proposed from the profiles' layouts and census.md, to be confirmed by the
    # pre-registration before the wave runs). environmentoptim-agentdojo takes the family default (one model directory,
    # benign runs only, 104 selected logs).
    "authority-caps-agentdojo": ("container", "model_dir", "pipeline_dir", "attack_dir"),  # experiment x arm x attack
    "ipi-defenses-agentdojo": ("container", "model_dir", "attack_dir"),  # run tar x model/defence x attack (banking)
    "dca-agentdojo": ("model_dir", "suite", "attack_dir"),  # arm directory (runner, model, defence) x suite x attack
    "kavach-agentdojo": ("model_dir", "suite", "attack_dir"),  # run directory + pipeline (local / local-kavach)
    "drift1-agentdojo": ("model_dir", "suite", "attack_dir"),  # gpt-4o-mini and the PACT-DRIFT directory
}


def strata_keys(profile_id: str, dialect: str) -> tuple[str, ...]:
    return STRATA.get(profile_id) or HOOKS[dialect].default_strata


def stratum_of(facets: Mapping[str, str], keys: Iterable[str]) -> str:
    return "|".join(f"{k}={facets.get(k, NONE)}" for k in keys)
