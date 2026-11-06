"""Real-model run policy: endpoint classes and the API call and cost caps (DECISIONS D-721, D-725, D-726; MN N.2.1b).

**Endpoint class** (D-721). A real-model run is ``local`` when its ``endpoints.toml`` entry says ``local = true`` *and*
the resolved base URL's host is loopback (``127.0.0.1``, ``::1``, ``localhost``); every other real-model run is ``api``
(a ``local = false`` entry, a custom endpoint, a base URL off loopback). A keyless model server on a private LAN
address (``--allow-lan-endpoint``, D-698) stays ``api`` although the egress proxy forwards to it: its prompts and
replies leave this machine, so the caps and API consent apply (D-1067, amending D-721). T0 decides it from the resolved
agent, before consent, the preflight probe or any spawn, for every source; the registry status gate (``planned`` admits
scripted runs only) runs first and is unchanged.

* ``local``: consent (interactive, ``--i-consent-to-local-run`` or ``--i-consent-to-api-costs``); caps are optional.
* ``api``: consent (interactive or ``--i-consent-to-api-costs``; ``--i-consent-to-local-run`` is refused) **and** both
  caps, ``--max-calls`` and ``--max-cost-usd`` with ``--price-in`` and ``--price-out`` (USD per million tokens); a
  missing cap is ``cli.refused.api_caps`` (exit 4). ``--preflight-only`` is a fixed one-call operation and needs no
  caps.

**Budget** (D-725). T0 counts the billed calls (every ``llm.response`` with an HTTP 2xx status: kept and discarded
replies alike) and their recorded ``usage`` in each attempt's capture log, plus each preflight probe at its call bound
(:attr:`Budget.step_calls`; counted in ``live.caps.probe_calls``, so a resumed campaign charges the earlier probes too;
no probe is sent unless it fits the caps). Before a
cell starts it checks that the spend so far plus the worst case of every in-flight cell and of the new one fits both
caps; otherwise no further cell starts (``cap_reached``). The worst case of a cell is its call bound
(``Budget.cell_calls``: :data:`CELL_CALL_BOUND` for an AgentDojo-family cell, each model step multiplied by the billed
replies its LLM element may take, :func:`step_attempts`, and raised by a defence's declared calls,
:func:`defence_cell_calls`; the bound T0 computes from the plan for an Inspect cell, D-740) billed calls, each at the per-call token bound: input :data:`CALL_INPUT_BOUND` or the largest input seen in the campaign,
output the transmitted ``max_tokens`` or :data:`CALL_OUTPUT_BOUND`, or the largest output seen. The spend is priced
conservatively: every input-side token (``input_tokens + cache_read_tokens + cache_write_tokens``, which counts an
OpenAI-convention cached part twice) at ``--price-in``, output at ``--price-out``; a billed reply without ``usage`` is
charged at the per-call bound, and an attempt the parent ended one extra call at the bound (a reply in flight at the
kill), and an attempt with no capture log a whole cell at the bound. A cell that spends more calls than its bound stops the campaign
(``cap_bound_exceeded``): the bound no longer holds, so no further cell is started. The provider-side key limit is the
backstop (U-10).

The budget counts the corpus's earlier attempts too (resume): the caps are per corpus, not per invocation. A cell is
counted in ``live.caps.unledgered_cells`` (written before it starts) until its attempt is ledgered, and a resumed
campaign charges each cell still counted there a whole cell at the bound: an aborting error, a second signal or a kill
leaves such a cell's spend outside the ledger (AU-LIVE-3).
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
    "CELL_PASSES",
    "PASS_STEPS",
    "STEP_ATTEMPTS_AUTODOJO_NATIVE",
    "STEP_ATTEMPTS_GATEWAY",
    "Budget",
    "Caps",
    "EndpointClass",
    "LogBilling",
    "defence_cell_calls",
    "api_reason",
    "endpoint_class",
    "is_lan_base_url",
    "log_billing",
    "step_attempts",
]

EndpointClass = Literal["local", "api"]
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})
#: Passes of one AgentDojo-family cell at most (``TaskSuite.run_task_with_pipeline`` re-runs on an empty final reply;
#: D.10.9 A1), and model steps of one pass: one LLM call plus ``ToolsExecutionLoop(max_iters=15)``.
CELL_PASSES: Final = 3
PASS_STEPS: Final = 1 + 15
#: Billed model calls of one AgentDojo-family cell at most, undefended, at one billed reply per model step.
CELL_CALL_BOUND: Final = CELL_PASSES * PASS_STEPS
#: Billed replies of one model step at most under ``gateway_compat`` (AU-LIVE-1): ``GatewayLLM`` asks again on a reply
#: whose tool call is not JSON and on an upstream failure answered 2xx, up to 8 attempts (the backend declares
#: ``agentdojo.retry_malformed_tool_json@1`` and ``agentdojo.retry_upstream_failure@1`` with ``max = 8``).
STEP_ATTEMPTS_GATEWAY: Final = 8
#: The same for the AutoDojo fork's native element, which re-requests on malformed tool-call JSON up to 3 attempts
#: (``autodojo.fork_malformed_json_retry@1``, ``max = 3``). The stock native element bills one reply per step: its SDK
#: and tenacity retries follow a failed request, not a billed reply.
STEP_ATTEMPTS_AUTODOJO_NATIVE: Final = 3
#: The assumed input tokens of one call until a larger one is seen (a request's whole context).
CALL_INPUT_BOUND: Final = 32_000
#: The assumed output tokens of one call when no ``max_tokens`` is transmitted, until a larger one is seen.
CALL_OUTPUT_BOUND: Final = 4_096
_PER_MTOK: Final = 1_000_000


def _host(base_url: str | None) -> str | None:
    if not base_url:
        return None
    try:
        return (urlsplit(base_url).hostname or "").lower()
    except ValueError:
        return None


def endpoint_class(*, local_entry: bool, base_url: str | None) -> EndpointClass:
    """``local`` only for a ``local = true`` entry whose resolved base URL is on a loopback host (D-721); a LAN model
    server is ``api`` (D-1067)."""
    if not local_entry:
        return "api"
    return "local" if _host(base_url) in LOOPBACK_HOSTS else "api"


def is_lan_base_url(base_url: str | None) -> bool:
    """Whether ``base_url``'s host is a literal private LAN address (D-698's set,
    ``agentprov_capture.endpoints.is_private_lan_host``)."""
    from agentprov_capture.endpoints import is_private_lan_host

    host = _host(base_url)
    return host is not None and host != "" and is_private_lan_host(host)


def api_reason(*, local_entry: bool, base_url: str | None) -> str:
    """Why a run is ``api``, as the refusals and notices say it (D-721, D-1067)."""
    if not local_entry:
        return "the endpoint entry is not local"
    if is_lan_base_url(base_url):
        return "a LAN model server is an API endpoint: prompts and replies leave this machine (D-1067)"
    return "the resolved base URL is not a local server on loopback"


def step_attempts(llm_element: Any, backend: str) -> int:
    """The billed replies one model step of an AgentDojo-family cell may take with this LLM element on this backend
    (AU-LIVE-1): :data:`STEP_ATTEMPTS_GATEWAY` for ``gateway_compat``, :data:`STEP_ATTEMPTS_AUTODOJO_NATIVE` for the
    AutoDojo fork's native element, else one."""
    if llm_element == "gateway_compat":
        return STEP_ATTEMPTS_GATEWAY
    if backend == "autodojo":
        return STEP_ATTEMPTS_AUTODOJO_NATIVE
    return 1


def defence_cell_calls(cost: Any, attempts: int = 1) -> int | None:
    """The billed-call bound of one AgentDojo-family cell under a defence, from its registry entry's ``cost`` table
    (``extra_calls_per_step``, ``embedding_calls_per_step``, ``extra_calls_per_pass``; every one is recorded as an
    ``llm.response``): every model step of every pass at ``attempts`` billed replies (:func:`step_attempts`; with one,
    :data:`CELL_CALL_BOUND`), plus each ``*_per_step`` count at every model step of every pass and each ``*_per_pass``
    count at every pass, rounded up. ``extra_calls_per_step`` are model calls through the agent's own LLM element (MELON's
    masked re-run: the port wraps the pipeline's element), so each is counted at ``attempts`` billed replies too
    (AU-FR-2); ``embedding_calls_per_step`` (the defence endpoint's client) and ``extra_calls_per_pass`` (``tool_filter``'s
    stock ``OpenAILLMToolFilter``, its own client) are counted once. ``None`` when the table holds a member the bound
    cannot use (a count that is not a finite non-negative number, or another key): the caps cannot bound such a cell."""
    base = CELL_CALL_BOUND * attempts
    if cost is None:
        return base
    if not isinstance(cost, Mapping):
        return None
    extra = 0.0
    for key, value in cost.items():
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
            return None
        if str(key) == "extra_calls_per_step":
            extra += value * attempts * CELL_PASSES * PASS_STEPS
        elif str(key).endswith("_per_step"):
            extra += value * CELL_PASSES * PASS_STEPS
        elif str(key).endswith("_per_pass"):
            extra += value * CELL_PASSES
        else:
            return None
    return base + math.ceil(extra - 1e-9)


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
    step_calls: int = 1  # the billed replies one model call may take (AU-LIVE-1): a probe is charged and admitted at it
    calls: int = 0
    cost_usd: float = 0.0
    max_call_input: int = 0
    max_call_output: int = 0
    exceeded_bound: list[str] = field(default_factory=list)
    probe_calls: int = 0  # preflight probe calls, this invocation's and (resume) the earlier ones recorded in live.caps
    unledgered_cells: int = 0  # cells an earlier invocation started and never ledgered (resume; AU-LIVE-3)
    started_cells: int = 0  # cells this invocation started that are not ledgered yet (recorded, so a resume charges them)
    #: ``run --tune-jobs`` (AU-RN-2): the sweep's own budget. The caps are per corpus, so each arm's corpus records only
    #: its own spend; every charge goes to the sweep's budget too, and a cell starts only while the sweep's total fits
    #: the caps as well, so the sweep as a whole stays within them
    sweep: Budget | None = field(default=None, repr=False, compare=False)

    def call_bound(self) -> tuple[int, int]:
        """The tokens one call is charged at when its usage is unknown: (input side, output)."""
        tokens_in = max(CALL_INPUT_BOUND, self.max_call_input)
        tokens_out = self.caps.max_tokens if self.caps.max_tokens is not None else CALL_OUTPUT_BOUND
        return tokens_in, max(tokens_out, self.max_call_output)

    def _price(self, tokens_in: int, tokens_out: int) -> float:
        p_in, p_out = self.caps.price_in or 0.0, self.caps.price_out or 0.0
        return (tokens_in * p_in + tokens_out * p_out) / _PER_MTOK

    def call_bound_usd(self) -> float:
        return self._price(*self.call_bound())

    def cell_bound(self) -> tuple[int, float]:
        """The worst case of one cell: billed calls and USD."""
        return self.cell_calls, self.cell_calls * self.call_bound_usd()

    def charge_probe(self, count: int = 1) -> None:
        """``count`` preflight probe calls at the per-call bound: a probe sent now is ``step_calls`` of them (its LLM
        element may ask again); a probe's session is never stored, so the earlier invocations' probe calls of a resumed
        campaign are charged from ``live.caps.probe_calls``."""
        self.calls += count
        self.cost_usd += count * self.call_bound_usd()
        self.probe_calls += count
        if self.sweep is not None:
            self.sweep.charge_probe(count)

    def probe_refusal(self) -> str | None:
        """Why no preflight probe may be sent now (``None``: it may): the probe is a paid call, so it must fit what is
        left of both caps at the per-call bound, and a campaign at its caps sends no probe either."""
        if self.caps.max_calls is not None and self.calls + self.step_calls > self.caps.max_calls:
            return (f"cap_reached: --max-calls {self.caps.max_calls}: {self.calls} billed call(s) so far, and a probe "
                    f"may need {self.step_calls}")
        probe_usd = self.step_calls * self.call_bound_usd()
        if self.caps.max_cost_usd is not None and self.cost_usd + probe_usd > self.caps.max_cost_usd + 1e-12:
            return (f"cap_reached: --max-cost-usd {_decimal(self.caps.max_cost_usd)}: about ${_usd(self.cost_usd)} "
                    f"spent so far, and a probe may cost up to ${_usd(probe_usd)}")
        return None

    def charge(self, billing: LogBilling, *, label: str = "") -> None:
        """One attempt's capture log (stored or quarantined alike: a quarantined session was still billed). Without a
        log the attempt is charged a whole cell at the bound, since nothing says what it spent."""
        if self.sweep is not None:
            self.sweep.charge(billing, label=label)
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

    def charge_unledgered(self, count: int) -> None:
        """``count`` cells an earlier invocation started and never ledgered (killed in flight by a campaign-aborting
        error, a second signal or a kill of the process): the corpus holds no capture log of theirs, so each is charged
        a whole cell at the bound, as an attempt without a log is, and they stay in ``live.caps.unledgered_cells``."""
        calls, usd = self.cell_bound()
        self.calls += count * calls
        self.cost_usd += count * usd
        self.unledgered_cells += count
        if self.sweep is not None:
            self.sweep.charge_unledgered(count)

    def charge_all(self, logs: Iterable[bytes | None], *, limits: Any = None) -> None:
        for log in logs:
            self.charge(log_billing(log, limits=limits))

    def refusal(self, in_flight: int) -> str | None:
        """Why no further cell may start now (``None``: it may). ``in_flight`` cells are reserved at their worst case."""
        if self.sweep is not None and (reason := self.sweep.refusal(in_flight)) is not None:
            return reason
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
        if self.probe_calls:  # kept across invocations (resume): a probe leaves no capture log to charge again
            out["probe_calls"] = self.probe_calls
        if self.unledgered_cells + self.started_cells:  # written before a cell starts: a resume charges what never
            out["unledgered_cells"] = self.unledgered_cells + self.started_cells  # reached the ledger (AU-LIVE-3)
        if self.caps.max_cost_usd is not None:
            out["spend_upper_bound_usd"] = _usd(self.cost_usd)
        return out


def _usd(value: float) -> str:
    """USD rounded up to a tenth of a cent, as a decimal string (an upper bound is never rounded down)."""
    return f"{math.ceil(value * 1000 - 1e-9) / 1000:.3f}"
