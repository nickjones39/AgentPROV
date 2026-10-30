"""Backend test support (AD-01(e); K.3.2): ``ScriptedTransport`` and the network guard.

Importing this package never imports a benchmark package (``test_import.py``)."""

from agentprov_backend.testing import netguard
from agentprov_backend.testing.messages import MessagesFail, MessagesReply, messages_step_from_dict
from agentprov_backend.testing.transport import (
    DEFAULT_USAGE,
    Fail,
    Reply,
    Script,
    ScriptedTransport,
    ScriptError,
    ScriptExhausted,
    ScriptExpectationFailed,
    Step,
    load_script,
    step_from_dict,
)

__all__ = [
    "DEFAULT_USAGE",
    "Fail",
    "MessagesFail",
    "MessagesReply",
    "Reply",
    "Script",
    "ScriptError",
    "ScriptExhausted",
    "ScriptExpectationFailed",
    "ScriptedTransport",
    "Step",
    "load_script",
    "messages_step_from_dict",
    "netguard",
    "step_from_dict",
]
