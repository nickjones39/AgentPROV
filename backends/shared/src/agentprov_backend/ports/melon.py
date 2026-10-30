"""The MELON port (D-674; docs/reports/defence-backends/design.md §4.3): what the harness changes, and only that, to run
xwsdid/MELON's detector (``src/agentdojo/agent_pipeline/pi_detector.py`` at ``71d99dff``, provisioned by digest) on
stock agentdojo 0.1.35 and record it. The authors' decision logic is untouched: no line of their file is edited.

Changes, each declared in ``agentdojo.defence_port@1`` (kind ``harness_policy``):

1. **Embedding client.** ``MELON.__init__`` builds ``OpenAI(api_key=os.environ["OPENAI_API_KEY"], http_client=
   httpx.Client(proxy="http://127.0.0.1:7890"), max_retries=5)``. The port lets it construct (a placeholder key is
   provided only when none is set; nothing is sent then) and replaces ``detection_model`` with an SDK client on the
   recording transport for the defence endpoint (D-675), every ``embeddings.create`` bracketed as an auxiliary call of
   the defence actor.
2. **The two model calls of ``detect``.** ``MELON.detect`` queries its LLM twice, in this order: the agent's real next
   step, then the masked re-run. The port gives MELON an LLM proxy that brackets the first as the agent's call and the
   second as the defence's auxiliary call (the order is the pinned file's, guarded by its digest).
3. **Files.** The module writes ``runs/detection_stats.json`` (every 10 detections and at exit) and appends
   ``runs/defense_logs.jsonl`` relative to the working directory, the session's staging directory. The port turns both
   writes off and removes the exit handler; MELON's own defence log (``extra_args["defense_log"]`` and
   ``["melon_log"]``) is recorded as a capture note instead, so nothing it logged is lost.
4. **String content.** MELON's masked conversation (its few-shot turns and the tool-content summary) holds messages
   whose ``content`` is a plain string; its fork's OpenAI element turns such content into one text part
   (``_content_blocks_to_openai_content_blocks`` at the pin), stock 0.1.35's expects content blocks. The port passes
   copies of exactly those messages with the string as one text block, so the wire request is the fork's; MELON's own
   message dicts are not changed.
5. **MELON-AT state** (``melon_at`` only). Its adaptive threshold learns from the benign scores of earlier detections.
   The authors ran one detector per suite run; the harness builds one per cell (cells are independent sessions), so
   the threshold state lives for one cell and the adaptive branch needs five benign scores within it.
"""

from __future__ import annotations

import atexit
import contextlib
import os
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

__all__ = ["PORT_CHANGES", "apply_to_module", "build_detector", "port_item_params"]

PORT_CHANGES: tuple[str, ...] = (
    "embedding client: the recorded SDK client of the defence endpoint replaces OpenAI(api_key=OPENAI_API_KEY, "
    "proxy http://127.0.0.1:7890, max_retries=5); each embeddings.create is an auxiliary call of def0",
    "detect's two LLM calls: the first (the real next step) is bracketed as the agent's call, the second (the masked "
    "re-run) as def0's auxiliary call",
    "files: runs/detection_stats.json and runs/defense_logs.jsonl are not written and the atexit handler is removed; "
    "the defence log is recorded as the note agentdojo/defence_log",
    "string content: a message whose content is a plain string is passed to the stock OpenAI element as a copy with one "
    "text block, as the fork's element converts it (the wire request is the fork's)",
)
MELON_AT_CHANGE = ("melon_at: the adaptive-threshold state lives for one cell (one detector per cell), where the authors "
                   "kept one detector per suite run")


def port_item_params(entry_id: str) -> dict[str, Any]:
    changes = list(PORT_CHANGES) + ([MELON_AT_CHANGE] if entry_id == "melon_at" else [])
    return {"port": "melon", "changes": changes}


def apply_to_module(module: Any) -> None:
    """Change 3 on the freshly loaded module: no file writes, no exit handler."""
    handler = getattr(module, "_print_detection_stats_on_exit", None)
    if handler is not None:
        atexit.unregister(handler)
    stats = getattr(module, "_global_detection_stats", None)
    if stats is not None:
        stats.save_to_file = lambda *args, **kwargs: None
    module.append_defense_log = lambda *args, **kwargs: None


@contextlib.contextmanager
def _placeholder_key() -> Iterator[None]:
    """``MELON.__init__`` reads ``os.environ["OPENAI_API_KEY"]`` for a client the port replaces at once; a placeholder
    is set only when the variable is absent (scripted runs), and removed again."""
    present = "OPENAI_API_KEY" in os.environ
    if not present:
        os.environ["OPENAI_API_KEY"] = "agentprov-port-placeholder"
    try:
        yield
    finally:
        if not present:
            os.environ.pop("OPENAI_API_KEY", None)


class _SpannedEmbeddings:
    """``client.embeddings`` with each ``create`` in an auxiliary span of the defence actor (change 1)."""

    def __init__(self, embeddings: Any, session: Any, actor: str) -> None:
        self._embeddings = embeddings
        self._session = session
        self._actor = actor

    def create(self, *args: Any, **kwargs: Any) -> Any:
        with self._session.span("auxiliary", self._actor, ()):
            return self._embeddings.create(*args, **kwargs)


class _SpannedClient:
    def __init__(self, client: Any, session: Any, actor: str) -> None:
        self.embeddings = _SpannedEmbeddings(client.embeddings, session, actor)


class _DetectLLM:
    """The LLM MELON holds (change 2): calls alternate agent, masked, agent, masked ... within each ``detect``; the
    recorder resets the order before each detector query."""

    def __init__(self, llm: Any, session: Any, actor: str) -> None:
        from agentprov_backend._llm import SpannedLLM

        self.agent = SpannedLLM(llm, session)
        self.masked = SpannedLLM(llm, session, role="auxiliary", actor=actor, detached=True)
        self.name = getattr(llm, "name", None)
        self.calls = 0
        self.agent_outputs: list[Any] = []

    def reset(self) -> None:
        self.calls = 0
        self.agent_outputs = []

    def query(self, query: str, runtime: Any, env: Any, messages: Sequence[Any], extra_args: dict) -> Any:
        first = self.calls % 2 == 0
        self.calls += 1
        out = (self.agent if first else self.masked).query(query, runtime, env, _blocks(messages), extra_args)
        if first:
            self.agent_outputs.append(out[3][-1] if out[3] else None)
        return out


def _blocks(messages: Sequence[Any]) -> list[Any]:
    """Change 4: the messages, with a copy (string content as one text block) where the content is a string."""
    out = []
    for message in messages:
        if isinstance(message, Mapping) and isinstance(message.get("content"), str):
            message = {**message, "content": [{"type": "text", "content": message["content"]}]}
        out.append(message)
    return out


def build_detector(target: Any, kwargs: Mapping[str, Any], llm: Any, session: Any, actor: str,
                   embeddings_client: Any) -> tuple[Any, _DetectLLM]:
    """``target(proxy_llm, **kwargs)`` with the client replaced (changes 1 and 2)."""
    proxy = _DetectLLM(llm, session, actor)
    with _placeholder_key():
        detector = target(proxy, **dict(kwargs))
    if embeddings_client is None:
        raise ValueError("MELON needs a defence endpoint for its embeddings (--defence-endpoint, D-675)")
    detector.detection_model = _SpannedClient(embeddings_client, session, actor)
    return detector, proxy
