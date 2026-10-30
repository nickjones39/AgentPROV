"""The setup-refusal stop (``agentprov.cli.live.campaign.setup_refusal``) and the pre-consent naming hint's attack list
(``agentprov.cli.run.MODEL_NAMING_ATTACKS``). Pure: synthetic capture lines; the backend module is read as source."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from agentprov.cli.live.campaign import SETUP_REFUSAL_MAX_CHARS, setup_refusal
from agentprov.cli.run import MODEL_NAMING_ATTACKS

ROOT = Path(__file__).resolve().parents[2]


def _log(*events: dict) -> bytes:
    return b"".join(json.dumps(e).encode() + b"\n" for e in events)


def _error(where: str = "setup", type_: str = "UnsupportedConfiguration", fatal: bool = True, message: object = "m") -> dict:
    return {"type": "error", "data": {"where": where, "fatal": fatal, "exception": {"type": type_, "message": message}}}


def test_only_a_fatal_setup_unsupported_configuration_counts() -> None:
    assert setup_refusal(_log({"type": "session.start", "data": {}}, _error(message="needs a name"))) == "needs a name"
    assert setup_refusal(_log(_error(where="cell"))) is None
    assert setup_refusal(_log(_error(type_="RuntimeError"))) is None
    assert setup_refusal(_log(_error(fatal=False))) is None
    assert setup_refusal(_log(_error(message=None))) == "UnsupportedConfiguration"
    assert setup_refusal(b"not json\n{\n") is None


def test_the_message_is_bounded() -> None:
    assert len(setup_refusal(_log(_error(message="x" * 5000))) or "") == SETUP_REFUSAL_MAX_CHARS


def test_the_naming_hint_lists_the_backend_s_name_taking_attacks() -> None:
    """Kept equal to agentprov_backend.attacks.PIPELINE_NAMED_ATTACKS, read as source (the core imports no backend)."""
    tree = ast.parse((ROOT / "backends/shared/src/agentprov_backend/attacks.py").read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "PIPELINE_NAMED_ATTACKS" for t in n.targets))
    assert isinstance(node.value, ast.Call)
    names = {elt.value for elt in node.value.args[0].elts}  # frozenset({...})
    assert MODEL_NAMING_ATTACKS == names
