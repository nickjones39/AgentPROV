"""Quirk hooks: the extension point for source-specific TraceLogger behaviour (docs/architecture D.6.4, D.6.6, D.6.12).

A profile declares a quirk (``[[family.agentdojo.quirk]]``: ``id``, ``applies``, ``rules``, ``params``, ``observed``).
The generic mapper (:mod:`agentprov.adapters.agentdojo.mapper`) implements the quirks of the AgentDojo harness itself
(D.6.4 rows ``benign_security_constant`` … ``local_model_raw_completion``). A **source-specific** quirk (a ROPE guard
denial, a Mandate decline, a released recomputation, …) is added as a :class:`QuirkHook` in a module of the package
:mod:`agentprov.adapters.agentdojo.hooks`, without editing the generic code paths:

1. Write ``src/agentprov/adapters/agentdojo/hooks/<source>.py`` defining ``HOOKS: tuple[QuirkHook, ...]``. Modules are
   discovered by convention (sorted by name; :func:`hooks`); a quirk id registered twice is a build error.
2. Declare the rules the hook cites in the source's catalogue (``rules/<ns>.rules.toml``; ``rope``, ``agentdyn``,
   ``mandate``, ``survey``, ``drift`` and ``autodojo`` are homed in this family by ``agentprov.aer.rules``), and any new
   issue code in that catalogue's ``issue_codes``.
3. Declare the quirk in the profile with ``rules`` ⊇ ``QuirkHook.rules`` (checked by :func:`check_profile_hooks` when the
   profile is loaded) and the ``observed`` counts per part.
4. Give the hook ``census`` functions for every ``observed`` key; ``tools/agentdojo/profile_census.py`` and
   ``tests/full_corpus/test_profile_census.py`` check them against the full pinned snapshot wherever its bare fetch cache
   is present.

A hook runs only for a file whose facets its declared quirk's ``applies`` matches (D.6.4: a pattern from an undeclared
quirk is never applied). Hook points, all optional and all pure (they read the view, never the environment):

``defences(view) -> Sequence[str]``
    extra defence actors of the file (e.g. a guard active in a ROPE tree), besides the identity's; added as ``def<n>``
    actors sorted by name together with the identity's (rule: the hook's first rule, class I).
``tool_message(view, message) -> ToolDecision | None``
    called for each ``tool`` message before the generic D.6.6 rows (after the PI-detector sentinel row). A
    :class:`ToolDecision` turns the message into a defence decision: **no** ``tool_execution``, a ``decision`` record
    (``dc<n>``) whose subject is the linked ``tool_call`` part, and the tool message ``generated_by`` it (RF-3; the
    D.6.6 denial and decline rows).
``tool_execution(view, message, record) -> None``
    may add members to the ``tool_execution`` record under the hook's own ``ext.<ns>`` (e.g. a gate inferred to allow).
``judgements(view, recorded) -> Sequence[Mapping]``
    extra judgement records after the recorded ones, e.g. recomputations **released by the source** (``origin:
    "recomputed"``, ``revises`` the recorded one, attributed to the correcting party; C.3.10, D.6.7, D.6.13). Ids are
    assigned by the mapper.

Added with the AgentDyn source (D.6.14), same contract:

``user_message(view, message) -> ToolDecision | None``
    called for a ``user`` message that carries a key beyond ``{role, content}`` (so that it is not of a known ChatMessage
    shape), after the generic rows decided it is not first. A :class:`ToolDecision` turns it into a defence-authored
    message: a ``decision`` record whose subject is the rejected ``tool_call`` part of the previous assistant message (the
    only one, else that message), and the user message ``generated_by`` it, role kept (D.6.6 ``error``-key row; AgentDyn
    ``drift_integrated_user_error_key``). The decision's reason is the ``error`` value. Needs a previous assistant message;
    without one the message is kept verbatim as an unknown shape.
``orphan_tool_result(view, message) -> OrphanRequest | None``
    called for a ``tool`` message that no assistant call answers. An :class:`OrphanRequest` makes the execution
    ``requested_by`` a defence actor (an interpreter that executes calls the assistant never made; C.3.7 ``requested_by``,
    D.6.6 CaMeL row) instead of leaving its ``call`` ambiguous, and sets the severity of the ``orphan_tool_result`` issue.

Added with the ROPE source (D.6.13), same contract:

``execution(view, header) -> None``
    may add members to the ``execution`` header under the hook's own ``ext.<ns>`` (with their ``evf`` tags and scoped
    rules), or a scoped rule for a header field the generic mapper fills (e.g. ``/task/benchmark``).
``actors(view) -> Sequence[Mapping]``
    extra actor records after the ``def<n>`` actors (e.g. the correcting party of a released recomputation); their ids
    must not collide with the mapper's.
``fixture(view, vector, record) -> None``
    may add members to an ``injection_payload`` fixture under the hook's own ``ext.<ns>``.

Added with the detector-abort quirk (phase 10d routing R10, D-116), same contract:

``log_end(view, end) -> EndDecision | None``
    called once after every message is mapped, with :class:`LogEnd` (how the log ends: its last message's role and,
    when it ends with tool messages, their executions and the request they answer). An :class:`EndDecision` adds one
    ``decision`` record after the messages: by a defence actor, about the ``subject`` the hook names (one of the ids in
    the view), e.g. a ``terminate`` by an output detector that aborted the run after checking the last outputs. It never
    changes a record the mapper wrote.

Added with the CaMeL interpreter feedback (regeneration-batch item 2, B3; D-376), same contract:

``later_user_message(view, message) -> UserAuthor | None``
    called for a later ``user`` message of the plain ``{role, content}`` shape that no generic row attributes (not the
    first, not a tool-filter prompt or a repeated user prompt), before the unattributed fallback. A :class:`UserAuthor`
    makes a defence actor its author (``actor``, ``evf /actor`` at the class of ``rules[0]``, that rule scoped to
    ``/actor``), with no decision record: the defence wrote the message, it did not decide about a call; no
    ``unattributed_additional_user_message`` is raised.
``agent_input(view) -> InputNotLogged | None``
    called for each agent ``model_call``. An :class:`InputNotLogged` replaces the call's ``input`` (the logged prefix,
    ``agentdojo.context_is_prefix@1``) by ``unk {"/input": "not_recorded"}`` citing ``rules[0]`` scoped to ``/input``:
    the model was sent a list the log does not hold (e.g. CaMeL's privileged planner).

Added with the MELON defence messages (pre-check PC-melon-agentdojo-03/04, D-586), same contract:

``message_author(view, message) -> MessageAuthor | None``
    called with a :class:`TextMessage` for every ``system`` message (before the positional rule that gives the first one
    to the harness) and for every agent ``assistant`` message without tool calls. A :class:`MessageAuthor` names who wrote
    it, justified by ``rules[0]`` (``evf /actor`` at that rule's class):

    - for a system message, ``actor`` is a defence of the file (an insert, e.g. MELON-R's security warning) or
      ``"bench"`` (a harness prompt standing after an insert). A ``bench`` author keeps the prompt-variant label
      (D.6.6 system row);
    - for an assistant message, ``actor`` is a defence of the file and ``verdict`` is set: the defence replaced the
      model's reply. The model call is kept, a ``decision`` record by the defence (``subject`` the model call, the
      reply ``/original`` overwritten) generates the message, and nothing is generated by the model call.

Added with the SEAgent guard's dropped calls (pre-check PC-seagent-agentdojo-01, D-592), same contract:

``unexecuted_calls(view, batch) -> BatchIntervention | None``
    called for an agent assistant message whose calls have no tool message (:class:`CallBatch`), before the generic
    ``unexecuted_tool_call`` / ``missing_tool_result`` row. A :class:`BatchIntervention` says a defence dropped them: they
    become ``unexecuted_tool_call`` (warning) citing ``rules[0]``, wherever they stand in the batch, never a lost result.

``view.issue(code, ids, rule, severity=..., detail=...)`` raises a seal issue from any hook point (the code is a core
seal code or one the rule's catalogue declares).

A hook writes only under its own namespaces (``QuirkHook.namespaces``: prefix -> IRI, added to the header ``ns`` when the
hook is active for the profile) and cites only rules through ``view.rule`` (``RuleNotDeclared`` otherwise).
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Any, Literal

from agentprov.adapters.code_verification import reading_of
from agentprov.errors import ProfileError

if TYPE_CHECKING:
    from agentprov.adapters.agentdojo.profile import FamilyTable, Quirk

__all__ = ["BatchIntervention", "CallBatch", "CensusFile", "EndDecision", "HookView", "InputNotLogged", "LogEnd", "MessageAuthor", "OrphanRequest", "QuirkHook",
           "TextMessage", "ToolDecision", "ToolMessage", "UserAuthor", "UserMessage", "check_profile_hooks", "hooks"]


@dataclass(frozen=True, slots=True)
class CensusFile:
    """One sealed AER as the census sees it: its records (header first, seal excluded) and its seal issues."""

    records: Sequence[Mapping[str, Any]]
    issues: Sequence[Mapping[str, Any]]

    @property
    def header(self) -> Mapping[str, Any]:
        return self.records[0]

    def of_kind(self, kind: str) -> list[Mapping[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]

    def cites(self, rule: str) -> bool:
        """Whether any record cites ``rule`` (``<ns>.<name>@<n>``, with or without a pointer) or its ``_unverified`` twin
        (the same reading at class I, D.5.4)."""
        return any(reading_of(str(ref)) == rule for r in self.records for ref in r.get("rule", ()))

    def issue_ids(self, code: str) -> list[str]:
        return [str(i) for issue in self.issues if issue.get("code") == code for i in issue.get("ids", ())]

    def has_issue(self, code: str) -> bool:
        return any(issue.get("code") == code for issue in self.issues)


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """A ``tool`` message as a hook sees it (values as logged; the call it answers, when linked)."""

    index: int
    message: Mapping[str, Any]
    call: Mapping[str, Any] | None  # the linked FunctionCall of the assistant message, None when unlinked
    call_part: str | None  # its part id ``m<a>#<k>``

    @property
    def error(self) -> object:
        return self.message.get("error")

    @property
    def text(self) -> str | None:
        """The tool output text: a string ``content``, or the text of one text block (``v1.k14``)."""
        content = self.message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], Mapping) \
                and content[0].get("type") == "text" and isinstance(content[0].get("content"), str):
            return str(content[0]["content"])
        return None


@dataclass(frozen=True, slots=True)
class ToolDecision:
    """A tool message that records a defence decision instead of an execution (D.6.6 denial and decline rows; RF-3).

    ``defence`` names the defence actor (an identity defence or one from a ``defences`` hook). ``rules`` are cited on the
    decision record, unscoped; the first sets the record's class ``ev``. ``reason`` copies the logged ``error`` or the
    tool output text verbatim into ``decision.reason`` (O by source, with its locator); ``None`` declares
    ``unk {"/reason": "not_recorded"}``. ``ext`` holds the hook's own ``ext.<ns>`` members of the decision record;
    ``evf`` tags fields of the record (e.g. an ``/ext/<ns>/…`` member) and ``scoped`` cites ``(rule, pointer)`` pairs for
    them (D.6.13).
    """

    defence: str
    rules: tuple[str, ...]
    ev: Literal["D", "I"]
    verdict: Literal["deny"] = "deny"
    reason: Literal["error", "content"] | None = None
    ext: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    evf: Mapping[str, str] = field(default_factory=dict)
    scoped: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class UserMessage:
    """A ``user`` message as a hook sees it (values as logged): one of an unknown key set (``user_message``) or a later
    plain one (``later_user_message``)."""

    index: int
    message: Mapping[str, Any]

    @property
    def error(self) -> object:
        return self.message.get("error")

    @property
    def text(self) -> str | None:
        """The message text: a string ``content``, or the text of one text block (``v1.k14``)."""
        content = self.message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], Mapping) \
                and content[0].get("type") == "text" and isinstance(content[0].get("content"), str):
            return str(content[0]["content"])
        return None


@dataclass(frozen=True, slots=True)
class OrphanRequest:
    """A tool message with no call is an execution requested by the defence actor ``requester`` (class I, ``rules[0]``).

    ``severity`` is that of the ``orphan_tool_result`` issue (``info`` where the source's design produces such results,
    ``warning`` elsewhere)."""

    requester: str
    rules: tuple[str, ...]
    severity: Literal["info", "warning"] = "info"


@dataclass(frozen=True, slots=True)
class UserAuthor:
    """A later ``user`` message written by the defence actor ``defence`` (``rules[0]`` justifies the author)."""

    defence: str
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InputNotLogged:
    """An agent model call whose input the log does not hold (``rules[0]`` justifies the declaration)."""

    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LogEnd:
    """How a log ends, as a ``log_end`` hook sees it (ids of records the mapper wrote)."""

    index: int | None  # the last message's index, None for a log without messages
    role: str | None  # the last message's role as logged
    #: when the log ends with tool messages: their ``tool_execution`` ids in log order (a message that a hook turned
    #: into a decision has none), the tool message ids, and the agent assistant message whose calls they answer
    tool_executions: tuple[str, ...] = ()
    tool_messages: tuple[str, ...] = ()
    request: str | None = None


@dataclass(frozen=True, slots=True)
class EndDecision:
    """A decision a ``log_end`` hook adds after the messages: ``defence`` names the defence actor, ``subject`` one of
    the :class:`LogEnd` ids (a ``tool_execution`` means its output as produced, C.3.7). ``rules`` are cited unscoped;
    the first sets the record's class ``ev``. The reason is not logged (``unk``)."""

    defence: str
    subject: str
    rules: tuple[str, ...]
    ev: Literal["D", "I"]
    verdict: Literal["terminate"] = "terminate"


@dataclass(frozen=True, slots=True)
class TextMessage:
    """A ``system`` message, or an agent ``assistant`` message without tool calls, as ``message_author`` sees it.

    ``text`` is a string content or the texts of text blocks joined by a newline (``get_text_content_as_str``), ``None``
    for any other shape; ``sha256`` is the digest of ``text`` (``None`` with it)."""

    index: int
    role: Literal["system", "assistant"]
    text: str | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class MessageAuthor:
    """Who wrote a :class:`TextMessage` (``rules[0]`` justifies it): a defence of the file, or ``"bench"`` for a system
    message. ``verdict`` (assistant messages only) is the defence's decision about the model's reply it replaced."""

    actor: str
    rules: tuple[str, ...]
    verdict: Literal["terminate"] | None = None


@dataclass(frozen=True, slots=True)
class CallBatch:
    """An agent assistant message (``message`` id) whose calls ``pending`` (part ids) have no tool message; ``calls``
    are all its logged FunctionCalls, in order."""

    message: str
    calls: tuple[Mapping[str, Any], ...]
    pending: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BatchIntervention:
    """The pending calls of a :class:`CallBatch` were dropped by a defence (``rules[0]`` justifies it)."""

    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HookView:
    """What a hook may read about the file being mapped. ``rule`` resolves a rule id (with an optional pointer) against
    the shipped catalogues, exactly like the mapping context.

    ``context`` lists the import's context artefacts (``[import] context_artefacts``, role ``supporting``) by label;
    ``open_context(label)`` returns one's bytes (untrusted: parse them only through :mod:`agentprov.ingest`), and
    ``cite_context(label)`` adds it to the AER header's ``artifacts`` (role ``supporting``) and returns its artefact id
    (``a<n>``) for locators. Live mappings and ``--input`` single files have no context."""

    quirk: Quirk
    facets: Mapping[str, str | None]
    variant: str
    doc: Mapping[str, Any]
    family: FamilyTable
    defence_ids: Mapping[str, str]  # defence name -> actor id (def<n>)
    rule: Callable[..., str]
    context: Mapping[str, Any] = field(default_factory=dict)  # label -> ArtefactRef
    open_context: Callable[[str], bytes] | None = None
    cite_context: Callable[[str], str] | None = None
    #: ``issue(code, ids, rule, *, severity="warning", detail=None)``: a seal issue citing ``rule`` (D.6.13).
    issue: Callable[..., None] | None = None
    #: The resolved model of the file's agent actor (``None``: unresolved; D.6.13).
    model: str | None = None

    @property
    def params(self) -> Mapping[str, Any]:
        return self.quirk.params


@dataclass(frozen=True, slots=True)
class QuirkHook:
    """The mapper hooks of one source-specific quirk (module docstring)."""

    quirk_id: str
    rules: tuple[str, ...]
    namespaces: Mapping[str, str] = field(default_factory=dict)
    defences: Callable[[HookView], Sequence[str]] | None = None
    tool_message: Callable[[HookView, ToolMessage], ToolDecision | None] | None = None
    tool_execution: Callable[[HookView, ToolMessage, dict[str, Any]], None] | None = None
    judgements: Callable[[HookView, Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]] | None = None
    user_message: Callable[[HookView, UserMessage], ToolDecision | None] | None = None
    orphan_tool_result: Callable[[HookView, ToolMessage], OrphanRequest | None] | None = None
    #: ``observed`` key -> the count one AER contributes (summed over the snapshot; D.6.10 item 3).
    census: Mapping[str, Callable[[CensusFile], int]] = field(default_factory=dict)
    execution: Callable[[HookView, dict[str, Any]], None] | None = None
    actors: Callable[[HookView], Sequence[Mapping[str, Any]]] | None = None
    fixture: Callable[[HookView, str, dict[str, Any]], None] | None = None
    log_end: Callable[[HookView, LogEnd], EndDecision | None] | None = None
    later_user_message: Callable[[HookView, UserMessage], UserAuthor | None] | None = None
    agent_input: Callable[[HookView], InputNotLogged | None] | None = None
    message_author: Callable[[HookView, TextMessage], MessageAuthor | None] | None = None
    unexecuted_calls: Callable[[HookView, CallBatch], BatchIntervention | None] | None = None


@cache
def hooks() -> Mapping[str, QuirkHook]:
    """Every registered hook by quirk id, from the modules of :mod:`agentprov.adapters.agentdojo.hooks` (sorted)."""
    package = importlib.import_module("agentprov.adapters.agentdojo.hooks")
    found: dict[str, QuirkHook] = {}
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for hook in getattr(module, "HOOKS", ()):
            if not isinstance(hook, QuirkHook):
                raise ProfileError(f"hooks module {info.name!r}: HOOKS holds a non-QuirkHook")
            if not hook.quirk_id.startswith("agentdojo."):
                raise ProfileError(f"hook {hook.quirk_id!r}: quirk ids are agentdojo.<quirk> (D.6.4)")
            if hook.quirk_id in found:
                raise ProfileError(f"quirk {hook.quirk_id!r} has more than one hook")
            found[hook.quirk_id] = hook
    return found


def check_profile_hooks(profile_id: str, table: FamilyTable) -> None:
    """A declared quirk with a hook lists every rule the hook cites (D.6.12 item 7)."""
    registered = hooks()
    for quirk in table.quirks:
        hook = registered.get(quirk.id)
        if hook is not None and not set(hook.rules) <= set(quirk.rules):
            missing = sorted(set(hook.rules) - set(quirk.rules))
            raise ProfileError(f"profile {profile_id!r}: quirk {quirk.id} does not list its hook's rules {missing}")
