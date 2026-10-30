"""A small Hypothesis fuzz of the ``dtap.trajectory`` reader and mapper (D.12.1 row 9). The full fuzz campaign of the
reader is phase 12b's (AGENTS.md §0); this one pins the two contracts the family adds:

* the reader's ``sniff`` never raises, and ``parse`` either yields one item or raises ``MalformedArtefact`` or an
  ``IngestError`` with a G.3.9 code;
* any reordering, deletion or role change of a real run's steps still ends in a sealed AER that validates, a degenerate
  one at worst (D.2.8 case 3), never an exception.
"""

from __future__ import annotations

import hashlib
import json

import dtap_support as support
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.adapters.dtap.dialect import DtapTrajectoryReader
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.errors import INGEST_CODES, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()
FUZZ = settings(max_examples=150, deadline=2000, suppress_health_check=[HealthCheck.too_slow])
MAPFUZZ = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@FUZZ
@given(st.binary(max_size=512))
def test_reader_is_total_on_arbitrary_bytes(data):
    reader = DtapTrajectoryReader()
    sniff = reader.sniff(data, label="", limits=LIMITS)
    ref = ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/json", Origin.local("fuzz"))
    try:
        items = list(reader.parse(data, ref, limits=LIMITS))
    except IngestError as exc:
        assert exc.code in INGEST_CODES and not sniff.match
    except MalformedArtefact:
        assert not sniff.match
    else:
        assert sniff.match and len(items) == 1


@MAPFUZZ
@given(st.lists(st.tuples(st.sampled_from(["drop", "swap", "role", "state", "meta"]), st.integers(0, 40), st.integers(0, 40)),
                max_size=6))
def test_mapper_survives_step_mutations(ops):
    label = support.F["F05"]
    runs = support.runs_files()
    value = json.loads(runs[label])
    steps = value["trajectory"]
    for op, a, b in ops:
        if not steps:
            break
        i, j = a % len(steps), b % len(steps)
        if op == "drop":
            del steps[i]
        elif op == "swap":
            steps[i], steps[j] = steps[j], steps[i]
        elif op == "role":
            steps[i]["role"] = ["user", "agent", "tool", "system"][j % 4]
        elif op == "state":
            steps[i]["state"] = [None, 7, "{'a': 1}", {"x": [1, 2]}, "text"][j % 5]
        elif op == "meta":
            steps[i]["metadata"] = [{}, {"tool_name": "unknown"}, {"tool_name": "List MCP Tools", "server": "s"}, None][j % 4]
    runs[label] = json.dumps(value).encode()
    m = support.map_label(label, runs=runs)
    assert m.doc.seal["n_records"] >= 2
    assert m.outcome.error_code != "adapter.defect", "an unexpected exception: the mapper must refuse bad shapes explicitly"
    if not m.outcome.degenerate:
        assert m.header["unit"] in ("agent_execution", "outcome_only")
