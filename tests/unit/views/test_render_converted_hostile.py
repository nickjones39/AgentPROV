"""Regen item 71 (CA-13): an ``agentdojo.unknown_message`` value the converter rules cannot render is a ``ViewError``.

The importer keeps a message whose shape it does not know verbatim as an ``agentdojo.unknown_message`` part, so its
value is untrusted source JSON. A release-valid AER holding ``content: 5``, ``args: "xy"`` or a lone surrogate made
``render_converted`` raise ``TypeError``/``ValueError``/``UnicodeEncodeError``; derive catches only ``AgentProvError``,
so one log aborted the derive instead of recording ``view.transcript_v1`` for that execution. Synthetic logs only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov.corpus.derive import VIEW_RENDERERS
from agentprov.errors import AgentProvError
from agentprov.views.transcript_v1 import ViewError, render_converted, serialise

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "agentdojo"))
from agentdojo_support import map_log, new_log  # noqa: E402


def _content_int(log: dict[str, Any]) -> None:
    log["messages"][4]["content"] = 5  # final assistant reply: content neither str, list nor None


def _args_str(log: dict[str, Any]) -> None:
    log["messages"][3]["tool_call"]["args"] = "xy"  # tool message echo: args not a mapping


def _lone_surrogate(log: dict[str, Any]) -> None:
    log["messages"][3]["error"] = 5
    log["messages"][3]["content"] = "a\udc00"  # stored as $utf16 by the importer


@pytest.mark.parametrize("mutate", [_content_int, _args_str, _lone_surrogate],
                         ids=["content-int", "args-str", "surrogate"])
def test_a_hostile_unknown_message_raises_view_error(mutate: Any) -> None:
    log = new_log()
    mutate(log)
    mapped = map_log(log)
    assert mapped.validate().ok, "the AER is release-valid"
    assert "agentdojo.unknown_message_shape" in mapped.codes
    with pytest.raises(ViewError) as caught:
        serialise(render_converted(mapped.records))
    # derive records the per-execution failure under this code because the error is an AgentProvError
    assert isinstance(caught.value, AgentProvError) and caught.value.code == "view.transcript_v1"
    assert "/parts/0/value" in str(caught.value) and "a\udc00" not in str(caught.value)


def test_derive_renders_this_adapter_with_render_converted() -> None:
    assert VIEW_RENDERERS["agentdojo.tracelogger"] == "render_converted"


def test_the_unmutated_log_still_renders() -> None:
    doc = render_converted(map_log(new_log()).records)
    assert [t["role"] for t in doc["turns"]] == ["system", "user", "assistant", "tool", "assistant"]
