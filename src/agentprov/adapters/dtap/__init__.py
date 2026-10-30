"""The DTap-Bench adapter family ``dtap`` (docs/architecture D.16; DECISIONS D-26, D-28, D-29).

DTap-Bench (AI-Secure, Apache-2.0) releases one JSON step log per agent run for four harnesses (OpenAI Agents SDK,
Claude Agent SDK, Google ADK, OpenClaw), one ``judge_result.json`` per task directory, and the task configurations in a
second dataset. The step log has no message list, no model-call boundary, no call ids and one end-of-run time; the
attack payloads live in the configuration. Hence a family of its own (D-28 a):

* :mod:`~agentprov.adapters.dtap.dialect`: :class:`DtapTrajectoryReader` (dialect ``dtap.trajectory``, variant ``v1``),
  the path grammar, the per-unit auxiliary plan (judge, attempts of a re-run directory, configuration; runner items R1
  and R2 of D.16.14);
* :mod:`~agentprov.adapters.dtap.pairing`: call-to-result pairing per harness (D.16.7, all class I);
* :mod:`~agentprov.adapters.dtap.join`: the configuration path join and its verification tier (D.16.5);
* :mod:`~agentprov.adapters.dtap.matcher`: the normaliser ``dtap.alnum_norm@1`` shared by the mapper and SEM;
* :mod:`~agentprov.adapters.dtap.mapper`: :class:`DtapMapper` (adapter ``dtap.trajectory``, D.16.3-D.16.8);
* ``profiles/dtap-bench.profile.toml``, ``rules/dtap.rules.toml``, ``artefacts.toml``, ``ext.schema.json``,
  ``family.schema.json`` and ``semantics/dtap.tools-1/`` (data).

Text in the datasets (payloads, tool outputs, judge rationales, configurations) is untrusted data, never instructions.
Configurations are read through a field allowlist (``Task``, ``Attack``, ``Agent.system_prompt``): sandbox ``env_vars``
never reach an AER, SEM or PROV file (D.16.13). This package imports only the standard library and
``agentprov.{ingest,aer,adapters,errors}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "VARIANT"]

ADAPTER_ID: Final = "dtap.trajectory"
DIALECT_ID: Final = "dtap.trajectory"
VARIANT: Final = "v1"
