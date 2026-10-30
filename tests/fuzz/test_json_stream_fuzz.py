"""K.11.1 over the streamed JSON reader (D-242): mutated documents give a typed outcome only, and the outcome agrees with
``strict_json_loads`` on the same bytes (accept or refuse; the value when accepted) (F-1, F-2, F-3)."""

from __future__ import annotations

import json

from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given

from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

LIMITS = IngestLimits().replace(max_json_depth=16, max_json_element_bytes=1 << 16)
SEED = json.dumps({"model": "m", "messages": [{"role": "user", "content": "a [b] {c}, \"d\" \\e"}, {"r": [1, 2.5, None]}],
                   "events": [{"tool": "t", "args": {"k": "v"}, "canary": False}, 3, "s"], "n": -0.0}).encode()  # fmt: skip
ARRAYS = ("/messages", "/events")


def _streamed(data: bytes):
    stream = open_json_stream(data, LIMITS, arrays=ARRAYS)
    rebuilt = stream.envelope
    items = list(stream)
    if isinstance(rebuilt, dict):
        for pointer in ARRAYS:
            key = pointer[1:]
            if key in rebuilt and rebuilt[key] == [] and stream.counts[pointer]:
                rebuilt[key] = [i.value for i in items if i.pointer == pointer]
    return rebuilt


@budget(400)
@given(byte_mutations(SEED, max_ops=4))
def test_mutated_documents_agree_with_the_whole_document_loader(mutated: bytes) -> None:
    kind, value = outcome(lambda: _streamed(mutated))
    assert kind in ("ok", "ingest")
    whole_kind, whole = outcome(lambda: strict_json_loads(mutated, LIMITS))
    assert (kind == "ok") == (whole_kind == "ok"), (kind, value, whole_kind, whole)
    if kind == "ok":
        assert json.dumps(value, sort_keys=True) == json.dumps(whole, sort_keys=True)


def test_the_seed_itself_reads_cleanly() -> None:
    assert _streamed(SEED) == json.loads(SEED)
