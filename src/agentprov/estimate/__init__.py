"""The live-run estimate and the model prices it reads (design §8.3 as amended by D-650, D-653, D-656; D-701 moved
them from the GUI into the core so that ``agentprov prices`` and ``agentprov estimate`` are the one implementation the
GUI calls).

* :mod:`.prices`: the shipped price table, refreshed OpenRouter snapshots and per-model overrides;
* :mod:`.cost`: the estimate itself (pure);
* :mod:`.usage`: counts from AER documents (no text kept);
* :mod:`.priors`: the shipped priors and the corpus → priors → defaults lookup;
* :mod:`.plan`: the strict reader of ``run --dry-run --plan-json`` (D-651).

Outside every stage closure (class 0): nothing here feeds AER, SEM, PROV or a corpus.
"""

from pathlib import Path as _Path
from typing import Final as _Final

#: The scripted stand-in a real-model estimate plans with when no key is given (an empty script: the dry run never
#: calls a model, so it is never read for a reply).
STAND_IN_SCRIPT: _Final = _Path(__file__).resolve().parent / "data" / "stand-in-script.json"
