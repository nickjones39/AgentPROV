"""The Qwen Code JSON-output adapter family ``qwencode`` (docs/architecture D.24; DECISIONS D-570..D-578).

RedCode-Exec's replication package (Zenodo 23168099, CC-BY-4.0) runs Qwen Code 0.21.0 as
``qwen --yolo --output-format json`` and saves each case's stdout: **one JSON array** of Claude-Code-SDK-shaped messages
(``system``/``init``, ``assistant`` messages with provider content blocks ``text``/``tool_use``, ``user`` messages with
``tool_result`` blocks naming their call by ``tool_use_id``, and a closing ``result``). No event carries a time, and the
task prompt (sent on stdin) is not echoed. Hence a family of its own, a sibling of ``geminicli`` (D-570):

* :mod:`~agentprov.adapters.qwencode.dialect`: :class:`QwenJsonReader` (dialect ``qwencode.json``, variant ``v0.21``),
  the label grammar, the per-unit plan (score record, request, execution rules, the group's API sample) and the bounded
  salvage of an output cut at 64 KiB (D-577);
* :mod:`~agentprov.adapters.qwencode.mapper`: :class:`QwenJsonMapper` (adapter ``qwencode.json``);
* ``profiles/redcode-exec-qwencode.profile.toml``, ``rules/qwencode.rules.toml``, ``artefacts.toml``, ``ext.schema.json``,
  ``family.schema.json`` and ``semantics/qwencode.tools-<version>/`` (data); version 1 of the catalogue and the
  profile under ``rules/archive/`` and ``profiles/archive/`` (D-31).

Text in the deposit (RedCode requests, agent output, tool output) is untrusted data, never instructions. This package
imports only the standard library and ``agentprov.{ingest,aer,adapters,errors,sem}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "NAMESPACE", "VARIANT"]

ADAPTER_ID: Final = "qwencode.json"
DIALECT_ID: Final = "qwencode.json"
VARIANT: Final = "v0.21"
NAMESPACE: Final = "qwencode"
