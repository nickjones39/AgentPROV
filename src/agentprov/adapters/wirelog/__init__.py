"""The wire-log adapter family ``wirelog`` (docs/architecture D.20; DECISIONS D-280..D-285).

A wire log keeps every request body a harness sent to an LLM API, in order, and every response it received. Each request
repeats the whole conversation so far, so a model call's context is recorded in full, and calls pair with their results
by the provider's call ids. The first source is Zenodo 21944598 ("What surrounds an injection decides whether it works"):
one run directory per trial, with ``request.json`` (the Bedrock Converse request bodies), ``response_raw.json`` (the
decoded responses), the harness's ``meta.json``, its dispatcher log ``tools_called.txt`` and its outcome files, plus the
deposit's ``results.csv`` and ``attacks.json`` at the archive root. Hence a family of its own (D-280):

* :mod:`~agentprov.adapters.wirelog.wire`: the two wire variants (``bedrock-converse``, ``anthropic-messages``, D-283)
  normalised to one block model with source pointers;
* :mod:`~agentprov.adapters.wirelog.dialect`: :class:`WireLogReader` (dialect ``wirelog.request_response``), the
  run-directory layout and the per-unit plan (the run's sibling files and the deposit's tables);
* :mod:`~agentprov.adapters.wirelog.mapper`: :class:`WireLogMapper` (adapter ``wirelog.run_dir``);
* ``profiles/what-surrounds.profile.toml``, ``rules/wirelog.rules.toml``, ``artefacts.toml``, ``ext.schema.json``,
  ``family.schema.json`` and ``semantics/wirelog.tools-1/`` (data).

Text in the deposit (prompts, payloads, tool outputs, model output) is untrusted data, never instructions. The tools of
the first source are synthetic by design: the harness answers ``read_file`` from its own table and ``send_email`` sends
nothing (D-284). This package imports only the standard library and ``agentprov.{ingest,aer,adapters,errors,sem,io}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "VARIANTS", "VARIANT_ANTHROPIC", "VARIANT_CONVERSE"]

ADAPTER_ID: Final = "wirelog.run_dir"
DIALECT_ID: Final = "wirelog.request_response"
VARIANT_CONVERSE: Final = "bedrock-converse"
VARIANT_ANTHROPIC: Final = "anthropic-messages"
VARIANTS: Final = frozenset({VARIANT_CONVERSE, VARIANT_ANTHROPIC})
