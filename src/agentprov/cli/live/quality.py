"""Canary conditions and the capture-quality report, computed from sealed evidence (D.10.9; MN N.1.14).

Everything here reads stored capture logs and their blobs (the raw objects of the working corpus, parsed with the strict
loader) and nothing else: the report is a pure function of the corpus, so ``agentprov stats`` can reproduce it, and no
pipeline decision reads the feedback level (F4). The controls of D.10.9 that can be observed per session:

* **A3** ``param_not_transmitted``: a configured ``temperature``, ``reasoning_effort``, ``top_p``, ``seed`` or
  ``max_tokens`` that a request did not transmit;
* **A4** ``text_tool_call_suspect``: a kept reply with no structured tool call whose text names a tool of the request or
  carries ``<function=``, ``<|python_tag|>`` or ``<tool_call>``;
* **A6** ``abnormal_finish``: a kept reply whose ``finish_reason`` is not a normal end for its provider (``stop`` or
  ``tool_calls``; for provider ``anthropic``, the Messages API's ``end_turn``, ``tool_use`` or ``stop_sequence``,
  D-656), as the identity's ``agent.provider`` records it (the canary fires above 20 % of kept calls);
* **A11** attempts per cell, and **errored or aborted** sessions (the canary fires on any);
* **A12** ``served_model``: a reply (kept or discarded) whose ``served_model`` is absent or differs from the model its
  request named (the identity's ``model_requested`` when the request body names none), unless the operator accepted
  that served id (``--accept-served-model``, recorded); the canary fires on any (D-694: never silently accepted);
* **A14** ``local_model_drift``: a session whose ``agentdojo/local_model`` note (T0's observation of a local model just
  before the cell) says it does not match the plan's identity; the canary fires on any (D-695);
* passes per session, retries (wire attempts after the first), HTTP status classes, the instrumentation in force.

A9 (stock roles rejected) is a preflight condition (the ``probe`` op), not a canary one: an HTTP 400 inside a cell has
many causes (``context_length_exceeded`` among them) and is reported by class only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "CANARY_ABNORMAL_SHARE", "SessionQuality", "canary_conditions", "quality_report", "served_mismatches",
    "session_quality",
]

TRACKED_PARAMS: Final = ("temperature", "reasoning_effort", "top_p", "seed", "max_tokens")
TEXT_CALL_MARKS: Final = ("<function=", "<|python_tag|>", "<tool_call>")
NORMAL_FINISH: Final = frozenset({"stop", "tool_calls"})
#: Normal ends by provider (``identity.agent.provider``); any other provider uses :data:`NORMAL_FINISH`. The Messages
#: API's ``max_tokens``, ``refusal`` and ``pause_turn`` stay abnormal, as ``length`` and ``content_filter`` are (D-656).
NORMAL_FINISH_BY_PROVIDER: Final[Mapping[str, frozenset[str]]] = {
    "anthropic": frozenset({"end_turn", "tool_use", "stop_sequence"}),
}
CANARY_ABNORMAL_SHARE: Final = 0.2


@dataclass
class SessionQuality:
    session: str
    cell_key: str | None = None
    model: str | None = None
    status: str | None = None  # session.end status (None: unsealed)
    appended_by: str | None = None
    passes: int = 0
    kept: int = 0
    discarded: int = 0
    errors: int = 0
    retries: int = 0
    http: Counter[str] = field(default_factory=Counter)
    not_transmitted: set[str] = field(default_factory=set)
    abnormal_finish: int = 0
    finish_reasons: Counter[str] = field(default_factory=Counter)
    text_tool_call_suspect: int = 0
    instrumentation: tuple[str, ...] = ()
    unparsed_lines: int = 0
    #: (requested, served) per reply with a body; served ``None`` when the reply named no model (A12)
    served: Counter[tuple[str, str | None]] = field(default_factory=Counter)
    local_model_drift: int = 0  # A14


def _blob_json(ref: Any, read_blob: Callable[[str], bytes | None], limits: Any) -> Any:
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    if not isinstance(ref, Mapping) or not isinstance(ref.get("$blob"), str):
        return None
    digest = ref["$blob"].removeprefix("sha256:")
    data = read_blob(digest)
    if data is None:
        return None
    try:
        return strict_json_loads(data, limits)
    except IngestError:
        return None


def _tool_names(request: Any) -> set[str]:
    names: set[str] = set()
    tools = request.get("tools") if isinstance(request, Mapping) else None
    for tool in tools if isinstance(tools, list) else ():
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if isinstance(function, Mapping) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return names


def _reply_is_text_call(response: Any, names: set[str]) -> bool:
    choices = response.get("choices") if isinstance(response, Mapping) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return False
    message = choices[0].get("message")
    if not isinstance(message, Mapping) or message.get("tool_calls"):
        return False
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    return any(mark in text for mark in TEXT_CALL_MARKS) or any(name in text for name in names)


def session_quality(session: str, log: bytes, read_blob: Callable[[str], bytes | None], *, limits: Any = None) -> SessionQuality:
    """The quality facts of one stored capture log (strict, bounded parsing; the log is untrusted evidence)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    limits = limits or IngestLimits()
    q = SessionQuality(session=session)
    requests: dict[str, Any] = {}
    normal: frozenset[str] = NORMAL_FINISH
    for line in log.split(b"\n"):
        if not line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            q.unparsed_lines += 1
            continue
        if not isinstance(event, Mapping) or not isinstance(event.get("data"), Mapping):
            q.unparsed_lines += 1
            continue
        kind, data = event.get("type"), event["data"]
        if kind == "instrumentation":
            items = data.get("items")
            q.instrumentation = tuple(sorted(str(i.get("id")) for i in items if isinstance(i, Mapping))) if isinstance(items, list) else ()
        elif kind == "identity":
            agent = data.get("agent")
            if isinstance(agent, Mapping) and isinstance(agent.get("model_requested"), str):
                q.model = agent["model_requested"]
            if isinstance(agent, Mapping) and isinstance(agent.get("provider"), str):
                normal = NORMAL_FINISH_BY_PROVIDER.get(agent["provider"], NORMAL_FINISH)
        elif kind == "note" and data.get("ns") == "agentdojo" and data.get("kind") == "cell":
            payload = data.get("payload")
            if isinstance(payload, Mapping) and isinstance(payload.get("cell_key"), str):
                q.cell_key = payload["cell_key"]
        elif kind == "pass.start":
            q.passes += 1
        elif kind == "llm.request":
            call = data.get("call")
            if isinstance(data.get("attempt"), int) and not isinstance(data.get("attempt"), bool) and data["attempt"] > 0:
                q.retries += 1
            params = data.get("params")
            if isinstance(params, Mapping):
                c_raw, t_raw = params.get("configured"), params.get("transmitted")
                configured: Mapping[str, Any] = c_raw if isinstance(c_raw, Mapping) else {}
                transmitted: Mapping[str, Any] = t_raw if isinstance(t_raw, Mapping) else {}
                for name in TRACKED_PARAMS:
                    if name in configured and name not in transmitted:
                        q.not_transmitted.add(name)
            if isinstance(call, str):
                requests[call] = data.get("request")
        elif kind == "note" and data.get("kind") == "local_model":
            payload = data.get("payload")
            if isinstance(payload, Mapping) and payload.get("matches_plan") is not True:
                q.local_model_drift += 1
        elif kind == "llm.response":
            status = data.get("status")
            http = data.get("http_status")
            q.http[f"{http // 100}xx" if isinstance(http, int) and not isinstance(http, bool) else "none"] += 1
            if status in ("kept", "discarded"):
                request_doc = _blob_json(requests.get(str(data.get("call"))), read_blob, limits)
                asked = request_doc.get("model") if isinstance(request_doc, Mapping) else None
                asked = asked if isinstance(asked, str) else (q.model or "unrecorded")
                served = data.get("served_model")
                q.served[(asked, served if isinstance(served, str) else None)] += 1
            if status == "kept":
                q.kept += 1
                finish = data.get("finish_reason")
                q.finish_reasons[str(finish) if isinstance(finish, str) else "unrecorded"] += 1
                if isinstance(finish, str) and finish not in normal:
                    q.abnormal_finish += 1
                response = _blob_json(data.get("response"), read_blob, limits)
                request = _blob_json(requests.get(str(data.get("call"))), read_blob, limits)
                if response is not None and _reply_is_text_call(response, _tool_names(request)):
                    q.text_tool_call_suspect += 1
            elif status == "discarded":
                q.discarded += 1
            else:
                q.errors += 1
        elif kind == "session.end":
            q.status = data.get("status") if isinstance(data.get("status"), str) else None
            q.appended_by = data.get("appended_by") if isinstance(data.get("appended_by"), str) else None
    return q


def served_mismatches(q: SessionQuality, accepted: Iterable[str] = ()) -> int:
    """Replies whose served model is absent or differs from the requested one and is not an accepted served id (A12)."""
    ok = set(accepted)
    return sum(n for (asked, served), n in q.served.items() if served is None or (served != asked and served not in ok))


def canary_conditions(sessions: Iterable[SessionQuality], *, accepted_served: Iterable[str] = ()) -> list[str]:
    """The D.10.9 canary conditions present in ``sessions`` (empty: the campaign may continue)."""
    found: list[str] = []
    items = list(sessions)
    accepted = tuple(accepted_served)
    if any(q.not_transmitted for q in items):
        found.append("A3 configured parameter not transmitted: " + ", ".join(sorted(set().union(*(q.not_transmitted for q in items)))))
    if any(q.text_tool_call_suspect for q in items):
        found.append("A4 text-encoded tool call suspected")
    kept = sum(q.kept for q in items)
    abnormal = sum(q.abnormal_finish for q in items)
    if kept and abnormal / kept > CANARY_ABNORMAL_SHARE:
        found.append(f"A6 abnormal finish reasons in {abnormal} of {kept} kept calls (> 20 %)")
    mismatched = sum(served_mismatches(q, accepted) for q in items)
    if mismatched:
        pairs = sorted({f"{a} -> {s or 'none'}" for q in items for (a, s) in q.served
                        if s is None or (s != a and s not in accepted)})
        found.append(f"A12 served model differs from the requested one in {mismatched} repl(ies): "
                     + ", ".join(pairs[:5]) + " (accept a served id with --accept-served-model)")
    drift = sum(q.local_model_drift for q in items)
    if drift:
        found.append(f"A14 the local model changed since the plan was made in {drift} session(s)")
    bad = [q for q in items if q.status in ("errored", "aborted") or q.status is None]
    if bad:
        found.append(f"{len(bad)} attempt(s) errored, aborted or unsealed")
    return found


def quality_report(sessions: Iterable[SessionQuality], attempts_per_cell: Mapping[str, int]) -> dict[str, Any]:
    """The capture-quality report (D.10.9): per model, the controls' counts; integers only (H.1.4(3))."""
    by_model: dict[str, dict[str, Any]] = {}
    for q in sessions:
        m = by_model.setdefault(q.model or "unrecorded", {
            "sessions": 0, "statuses": Counter(), "passes": Counter(), "kept_calls": 0, "discarded_calls": 0,
            "error_calls": 0, "retries": 0, "http": Counter(), "param_not_transmitted": 0, "text_tool_call_suspect": 0,
            "abnormal_finish": 0, "finish_reasons": Counter(), "instrumentation": set(), "parent_appended": 0,
            "served_models": Counter(), "served_model_mismatch": 0, "local_model_drift": 0,
        })  # fmt: skip
        m["sessions"] += 1
        m["statuses"][q.status or "unsealed"] += 1
        m["passes"][str(q.passes)] += 1
        m["kept_calls"] += q.kept
        m["discarded_calls"] += q.discarded
        m["error_calls"] += q.errors
        m["retries"] += q.retries
        m["http"].update(q.http)
        m["param_not_transmitted"] += int(bool(q.not_transmitted))
        m["text_tool_call_suspect"] += q.text_tool_call_suspect
        m["abnormal_finish"] += q.abnormal_finish
        m["finish_reasons"].update(q.finish_reasons)
        m["instrumentation"].update(q.instrumentation)
        m["parent_appended"] += int(q.appended_by == "parent")
        for (_asked, served), n in q.served.items():
            m["served_models"][served if served is not None else "none"] += n
        m["served_model_mismatch"] += served_mismatches(q)  # before acceptance: the accepted ids are in the live block
        m["local_model_drift"] += q.local_model_drift
    models = {}
    for name, m in sorted(by_model.items()):
        models[name] = {k: (dict(sorted(v.items())) if isinstance(v, Counter) else sorted(v) if isinstance(v, set) else v)
                        for k, v in sorted(m.items())}
    attempts = Counter(str(n) for n in attempts_per_cell.values())
    return {"format": "agentprov-capture-quality/0.1", "models": models, "attempts_per_cell": dict(sorted(attempts.items()))}
