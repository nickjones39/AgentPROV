"""Real-model run policy: endpoint classes and the API call and cost caps (DECISIONS D-721, D-725, D-726; MN N.2.1b).

**Endpoint class** (D-721). A real-model run is ``local`` when its ``endpoints.toml`` entry says ``local = true`` *and*
the resolved base URL's host is loopback (``127.0.0.1``, ``::1``, ``localhost``); every other real-model run is ``api``
(a ``local = false`` entry, a custom endpoint, a base URL off loopback). T0 decides it from the resolved agent, before
consent, the preflight probe or any spawn, for every source; the registry status gate (``planned`` admits scripted runs
only) runs first and is unchanged.

* ``local``: consent (interactive, ``--i-consent-to-local-run`` or ``--i-consent-to-api-costs``); caps are optional.
* ``api``: consent (interactive or ``--i-consent-to-api-costs``; ``--i-consent-to-local-run`` is refused) **and** both
  caps, ``--max-calls`` and ``--max-cost-usd`` with ``--price-in`` and ``--price-out`` (USD per million tokens); a
  missing cap is ``cli.refused.api_caps`` (exit 4). ``--preflight-only`` is a fixed one-call operation and needs no
  caps.

**Budget** (D-725). T0 counts the billed calls (every ``llm.response`` with an HTTP 2xx status: kept and discarded
replies alike) and their recorded ``usage`` in each attempt's capture log, plus one call per preflight probe. Before a
cell starts it checks that the spend so far plus the worst case of every in-flight cell and of the new one fits both
caps; otherwise no further cell starts (``cap_reached``). The worst case of a cell is its call bound
(``Budget.cell_calls``: :data:`CELL_CALL_BOUND` for an AgentDojo-family cell, the bound T0 computes from the plan for an
Inspect cell, D-740) billed calls, each at the per-call token bound: input :data:`CALL_INPUT_BOUND` or the largest input seen in the campaign,
output the transmitted ``max_tokens`` or :data:`CALL_OUTPUT_BOUND`, or the largest output seen. The spend is priced
conservatively: every input-side token (``input_tokens + cache_read_tokens + cache_write_tokens``, which counts an
OpenAI-convention cached part twice) at ``--price-in``, output at ``--price-out``; a billed reply without ``usage`` is
charged at the per-call bound, and an attempt the parent ended one extra call at the bound (a reply in flight at the
kill), and an attempt with no capture log a whole cell at the bound. A cell that spends more calls than its bound stops the campaign
(``cap_bound_exceeded``): the bound no longer holds, so no further cell is started. The provider-side key limit is the
backstop (U-10).

The budget counts the corpus's earlier attempts too (resume): the caps are per corpus, not per invocation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from urllib.parse import urlsplit

__all__ = [
    "CALL_INPUT_BOUND",
    "CALL_OUTPUT_BOUND",
    "CELL_CALL_BOUND",
    "Budget",
    "Caps",
    "EndpointClass",
    "LogBilling",
    "endpoint_class",
    "log_billing",
]

EndpointClass = Literal["local", "api"]
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})
#: Billed model calls of one AgentDojo-family cell at most: up to 3 passes (``TaskSuite.run_task_with_pipeline``
#: re-runs on an empty final reply; D.10.9 A1), each one LLM call plus ``ToolsExecutionLoop(max_iters=15)``.
CELL_CALL_BOUND: Final = 3 * (1 + 15)
#: The assumed input tokens of one call until a larger one is seen (a request's whole context).
CALL_INPUT_BOUND: Final = 32_000
#: The assumed output tokens of one call when no ``max_tokens`` is transmitted, until a larger one is seen.
CALL_OUTPUT_BOUND: Final = 4_096
_PER_MTOK: Final = 1_000_000


def endpoint_class(*, local_entry: bool, base_url: str | None) -> EndpointClass:
    """``local`` only for a ``local = true`` entry whose resolved base URL is on a loopback host (D-721)."""
    if not local_entry or not base_url:
        return "api"
    try:
        host = (urlsplit(base_url).hostname or "").lower()
    except ValueError:
        return "api"
    return "local" if host in LOOPBACK_HOSTS else "api"


@dataclass(frozen=True)
class Caps:
    """The run's caps (``None``: not given). ``price_in`` and ``price_out`` are USD per million tokens."""

    max_calls: int | None = None
    max_cost_usd: float | None = None
    price_in: float | None = None
    price_out: float | None = None
    max_tokens: int | None = None  # the transmitted output cap, when the agent configures one

    @property
    def active(self) -> bool:
        return self.max_calls is not None or self.max_cost_usd is not None

    def missing_for_api(self) -> list[str]:
        """The cap options an ``api`` run lacks (D-725)."""
        missing = []
        if self.max_calls is None:
            missing.append("--max-calls")
        if self.max_cost_usd is None:
            missing.append("--max-cost-usd")
        if self.max_cost_usd is not None and (self.price_in is None or self.price_out is None):
            missing.extend(n for n, v in (("--price-in", self.price_in), ("--price-out", self.price_out)) if v is None)
        return missing

    def record(self) -> dict[str, Any]:
        out: dict[str, Any] = {"max_calls": self.max_calls, "cell_call_bound": CELL_CALL_BOUND}
        if self.max_cost_usd is not None:
            out["max_cost_usd"] = _decimal(self.max_cost_usd)
            out["price_in_usd_per_mtok"] = _decimal(self.price_in)
            out["price_out_usd_per_mtok"] = _decimal(self.price_out)
        return out


def _decimal(value: float | None) -> str | None:
    """A price or amount as a decimal string (the manifest holds no floats; H.1.4(3))."""
    return None if value is None else format(value, "f").rstrip("0").rstrip(".") or "0"


@dataclass
class LogBilling:
    """What one capture log says was billed."""

    billed_calls: int = 0
    input_tokens: int = 0  # input + cache read + cache write, as recorded (conservative across conventions)
    output_tokens: int = 0
    without_usage: int = 0  # billed replies with no recorded usage (charged at the per-call bound)
    max_call_input: int = 0
    max_call_output: int = 0
    parent_ended: bool = False  # session.end appended by the parent, or no session.end
    missing: bool = False  # no capture log at all: what was billed is unknown


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def log_billing(log: bytes | None, *, limits: Any = None) -> LogBilling:
    """The billed calls and recorded usage of one capture log (strict, bounded parsing; the log is untrusted)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    billing = LogBilling(parent_ended=True)
    if log is None:
        billing.missing = True
        return billing
    limits = limits or IngestLimits()
    for line in log.split(b"\n"):
        if not line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            continue
        if not isinstance(event, Mapping) or not isinstance(event.get("data"), Mapping):
            continue
        kind, data = event.get("type"), event["data"]
        if kind == "llm.response":
            http = data.get("http_status")
            if not (isinstance(http, int) and not isinstance(http, bool) and 200 <= http < 300):
                continue
            billing.billed_calls += 1
            usage = data.get("usage")
            if not isinstance(usage, Mapping) or not usage:
                billing.without_usage += 1
                continue
            tokens_in = _int(usage.get("input_tokens")) + _int(usage.get("cache_read_tokens")) + \
                _int(usage.get("cache_write_tokens"))
            tokens_out = _int(usage.get("output_tokens"))
            billing.input_tokens += tokens_in
            billing.output_tokens += tokens_out
            billing.max_call_input = max(billing.max_call_input, tokens_in)
            billing.max_call_output = max(billing.max_call_output, tokens_out)
        elif kind == "session.end":
            billing.parent_ended = data.get("appended_by") == "parent"
    return billing


@dataclass
class Budget:
    """The campaign's spend against :class:`Caps` (D-725); only T0 updates it, in the campaign's main thread."""

    caps: Caps
    cell_calls: int = CELL_CALL_BOUND  # the per-cell call bound: AgentDojo's constant, or an Inspect cell's (D-740)
    calls: int = 0
    cost_usd: float = 0.0
    max_call_input: int = 0
    max_call_output: int = 0
    exceeded_bound: list[str] = field(default_factory=list)

    def _call_bound(self) -> tuple[int, int]:
        tokens_in = max(CALL_INPUT_BOUND, self.max_call_input)
        tokens_out = self.caps.max_tokens if self.caps.max_tokens is not None else CALL_OUTPUT_BOUND
        return tokens_in, max(tokens_out, self.max_call_output)

    def _price(self, tokens_in: int, tokens_out: int) -> float:
        p_in, p_out = self.caps.price_in or 0.0, self.caps.price_out or 0.0
        return (tokens_in * p_in + tokens_out * p_out) / _PER_MTOK

    def call_bound_usd(self) -> float:
        return self._price(*self._call_bound())

    def cell_bound(self) -> tuple[int, float]:
        """The worst case of one cell: billed calls and USD."""
        return self.cell_calls, self.cell_calls * self.call_bound_usd()

    def charge_probe(self) -> None:
        """One preflight probe: one call at the per-call bound (its session is never stored)."""
        self.calls += 1
        self.cost_usd += self.call_bound_usd()

    def charge(self, billing: LogBilling, *, label: str = "") -> None:
        """One attempt's capture log (stored or quarantined alike: a quarantined session was still billed). Without a
        log the attempt is charged a whole cell at the bound, since nothing says what it spent."""
        if billing.missing:
            calls, usd = self.cell_bound()
            self.calls += calls
            self.cost_usd += usd
            return
        self.max_call_input = max(self.max_call_input, billing.max_call_input)
        self.max_call_output = max(self.max_call_output, billing.max_call_output)
        self.calls += billing.billed_calls
        self.cost_usd += self._price(billing.input_tokens, billing.output_tokens)
        self.cost_usd += billing.without_usage * self.call_bound_usd()
        if billing.parent_ended:
            self.calls += 1
            self.cost_usd += self.call_bound_usd()
        if billing.billed_calls > self.cell_calls:
            self.exceeded_bound.append(label or "an attempt")

    def charge_all(self, logs: Iterable[bytes | None], *, limits: Any = None) -> None:
        for log in logs:
            self.charge(log_billing(log, limits=limits))

    def refusal(self, in_flight: int) -> str | None:
        """Why no further cell may start now (``None``: it may). ``in_flight`` cells are reserved at their worst case."""
        if self.exceeded_bound:
            return (f"cap_bound_exceeded: {self.exceeded_bound[0]} spent more than {self.cell_calls} billed calls, so "
                    "the per-cell bound does not hold; no further cell is started")
        calls_bound, usd_bound = self.cell_bound()
        reserve = in_flight + 1
        if self.caps.max_calls is not None and self.calls + reserve * calls_bound > self.caps.max_calls:
            return (f"cap_reached: --max-calls {self.caps.max_calls}: {self.calls} billed call(s) so far, and a cell "
                    f"may need {calls_bound} (with {in_flight} in flight)")
        if self.caps.max_cost_usd is not None and \
                self.cost_usd + reserve * usd_bound > self.caps.max_cost_usd + 1e-12:
            return (f"cap_reached: --max-cost-usd {_decimal(self.caps.max_cost_usd)}: about ${_usd(self.cost_usd)} "
                    f"spent so far, and a cell may cost up to ${_usd(usd_bound)} (with {in_flight} in flight)")
        return None

    def record(self) -> dict[str, Any]:
        """``live.caps`` of the campaign record: the caps, the bounds used and the spend (decimal strings, no floats)."""
        out = self.caps.record()
        out["cell_call_bound"] = self.cell_calls  # the bound this campaign reserved (D-740: an Inspect cell's own)
        out["billed_calls"] = self.calls
        if self.caps.max_cost_usd is not None:
            out["spend_upper_bound_usd"] = _usd(self.cost_usd)
        return out


def _usd(value: float) -> str:
    """USD rounded up to a tenth of a cent, as a decimal string (an upper bound is never rounded down)."""
    return f"{math.ceil(value * 1000 - 1e-9) / 1000:.3f}"
