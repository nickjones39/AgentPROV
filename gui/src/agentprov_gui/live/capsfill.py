"""Run Live's cap fields filled from the quote (D-1090): the words of their captions and tooltips.

``agentprov estimate`` suggests the D-725 caps in ``quote.caps`` (read by :func:`agentprov_gui.live.plan.parse_caps`):
the quote's p90 figure (the p90 model calls, or the upper cost, the sum of per-cell 90th percentiles) plus a margin
(the setting ``estimate.caps_margin_pct``, 20 % when unset), plus room for what the run reserves before it starts a
cell (the cells that run at once, each at its worst case, and one preflight probe). The GUI shows those figures and
fills the fields with them; it computes none. This module only words them: which figure, the margin, whether the
priors are local or shipped (``agentprov priors show``), and where the prices come from.

A field is in one of three states: **from the quote** (it follows every new quote), **yours** (typed; it stays until
"Use the quote's figure"), or **manual** (no suggestion: the caption says why and the field must be typed, as before).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from agentprov_gui import text as T
from agentprov_gui.live.plan import QuoteBasis, SuggestedCaps

__all__ = ["CALLS", "COST", "CapText", "cap_text", "prices_words", "priors_words", "usd"]

Which = str  # CALLS or COST
CALLS: Final = "calls"
COST: Final = "cost"

#: the base tooltips (what the cap is), kept from the earlier rows (D-1060 rule 2: no tooltip information is lost)
BASE_TIP: Final[dict[str, str]] = {
    COST: "Spend of the corpus at most, in USD (--max-cost-usd), priced at the prices below.",
    CALLS: "Billed model calls of the corpus at most, preflight probes included (--max-calls).",
}


@dataclass(frozen=True, slots=True)
class CapText:
    caption: str
    tooltip: str


def usd(value: Decimal | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def priors_words(basis: QuoteBasis | None) -> str:
    """Whose recorded figures the quote rests on, in a few words (``quote.basis.priors``)."""
    if basis is None:
        return "figures of unknown origin"
    if basis.executions == 0:
        return "your default assumptions"
    own = "" if basis.family_specific is not False else ", all-model figures"
    return {"local": "your priors", "shipped": "shipped priors",
            "mixed": "your and the shipped priors"}.get(basis.priors or "", "the opened corpora") + own


def prices_words(basis: QuoteBasis | None) -> str:
    """Where the prices come from and their date (``quote.basis.price_source`` and ``price_as_of``)."""
    if basis is None or not basis.price_source:
        return "prices of unknown source"
    source = {"direct": "provider list prices", "openrouter": "OpenRouter prices", "override": "your price override",
              "local": "no per-token price"}.get(basis.price_source, f"{T.line(basis.price_source, 40)} prices")
    return source + (f" of {T.line(basis.price_as_of, 10)}" if basis.price_as_of else "")


def _value(which: Which, caps: SuggestedCaps) -> str:
    return f"{caps.max_calls:,} calls" if which == CALLS else usd(caps.max_cost_usd)


def _reason(caps: SuggestedCaps | None) -> str:
    if caps is None:
        return "this agentprov suggests no caps"
    reason = T.line(caps.reason or "no reason given", 300)
    return reason.split(";")[0].split(" (")[0]


def cap_text(which: Which, caps: SuggestedCaps | None, basis: QuoteBasis | None, *, typed: bool,
             pending: bool) -> CapText:
    """The caption and tooltip of one cap field. ``typed``: the user's own value; ``pending``: the quote of this
    selection is not in yet."""
    base = BASE_TIP[which]
    if pending:
        return CapText("Filled from the quote once it is in" if not typed else "Your value",
                       f"{base} Filled from the quote's suggestion once the estimate of this selection is in; a value "
                       "you type stays until Use the quote's figure.")
    if caps is None or not caps.available:
        why = _reason(caps)
        return CapText(f"Enter it yourself: {why}" if not typed else f"Your value (no suggestion: {why})",
                       f"{base} The quote suggests no cap here ({T.line(caps.reason if caps else why, 260)}), so "
                       "type one, as without a quote.")
    margin = f"{caps.margin_pct:g} %" if caps.margin_pct is not None else "the margin"
    figure = "p90 calls" if which == CALLS else "upper cost (p90)"
    where = priors_words(basis) + ("" if which == CALLS else f" · {prices_words(basis)}")
    cells = caps.reserved_cells or 1
    room = f"{cells} cell{'s' if cells != 1 else ''}"
    if typed:
        caption = f"Your value; the quote suggests {_value(which, caps)}"
    else:
        caption = f"Quote: {figure} + {margin} + room for {room} · {where}"
    worst = (f"{caps.cell_calls:,} billed calls" if caps.cell_calls is not None else "its worst case") + (
        f", {usd(caps.cell_usd)}" if which == COST and caps.cell_usd is not None else "")
    margin_from = " (Settings › Estimate)" if caps.margin_from == "setting" else " (default, Settings › Estimate)"
    tip = (f"{base} Suggested {_value(which, caps)}: the quote's {figure if which == CALLS else 'upper figure'} "
           f"{'(sum of per-cell 90th percentiles) ' if which == COST else ''}+ {margin}{margin_from}, plus room for "
           f"{room} at the worst case ({worst} each) and a probe, which the run reserves "
           f"(D-725). From {where}. "
           + ("Typed: kept until Use the quote's figure." if typed else "Follows the quote until typed."))
    if caps.resumed_units:
        tip += " Add the spend of the units the corpus holds."
    return CapText(caption, tip)
