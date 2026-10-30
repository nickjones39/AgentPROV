"""K.11.1 reader fuzzing for the adapters that had none: AgentDojo-PROV ``transcript/v1`` (adprov) and Inspect ``.eval``
(container sniffing and sample-member parsing). The AgentDojo TraceLogger reader is fuzzed in
``tests/adapters/agentdojo/test_reader.py`` and FooBench in ``tests/adapters/foobench/test_fuzz.py``; ``dtap`` waits
for phase 10b (phase 12b).

F-1: ``sniff`` never raises; ``parse`` succeeds or raises ``MalformedArtefact`` / ``IngestError`` (a G.3.9 code).
F-4: a parsed adprov transcript maps to an AER that the core writer seals (a degenerate one at worst).
F-5: determinism. Seeds are the licence-cleared fixtures, read by the test (never printed: Hypothesis reports draw
indices, not fixture text).
"""

from __future__ import annotations

import hashlib
import io
import re

import pytest
from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.adapters.adprov.dialect import TranscriptV1Reader
from agentprov.adapters.inspect.dialect import InspectEvalReader
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.errors import MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden

LIMITS = IngestLimits()
SURROGATE = re.compile(rb"\\u[dD][89abAB][0-9a-fA-F]{2}|\\u[dD][c-fC-F][0-9a-fA-F]{2}")  # an escaped lone surrogate


def _ref(data: bytes, media: str = "application/json") -> ArtefactRef:
    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), media, Origin.capture(
        "019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8a"), "primary", "native")  # type: ignore[arg-type]


def _adprov_seeds() -> list[bytes]:
    if not golden.golden_available():
        return []
    return [e.transcript_bytes() for e in golden.v1_pairs() if e.tree == "release"][:3]


def _inspect_seeds() -> tuple[bytes | None, list[bytes]]:
    import import_support as support

    from agentprov.ingest.archives import iter_zip_members, open_archive

    if not support.INSPECT_FIXTURE.is_file():
        return None, []
    container = support.INSPECT_FIXTURE.read_bytes()
    samples: list[bytes] = []
    with open_archive(io.BytesIO(container), LIMITS, release=False, depth=1) as archive:
        wanted = lambda label: label.startswith("samples/") and label.endswith(".json")  # noqa: E731
        for member in iter_zip_members(archive, wanted, LIMITS):
            if member.disposition == "selected" and len(samples) < 2:
                samples.append(archive.read_member(member))
    return container, samples


ADPROV = _adprov_seeds()
CONTAINER, SAMPLES = _inspect_seeds()


def _pick(seeds: list[bytes]) -> st.SearchStrategy[bytes]:
    return st.integers(0, max(0, len(seeds) - 1)).flatmap(lambda i: byte_mutations(seeds[i], max_ops=4))


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
@budget(120, deadline=None)
@given(st.data())
def test_adprov_reader_is_total_and_its_items_map_to_a_sealed_aer(data: st.DataObject) -> None:
    from agentprov.adapters.runner import aer_bytes, map_artefact

    blob = data.draw(_pick(ADPROV))
    reader = TranscriptV1Reader()
    reader.sniff(blob, label="x.transcript.json", limits=LIMITS)
    first = outcome(lambda: len(list(reader.parse(blob, _ref(blob), limits=LIMITS))), MalformedArtefact)
    assert first == outcome(lambda: len(list(reader.parse(blob, _ref(blob), limits=LIMITS))), MalformedArtefact)
    if first[0] != "ok" or SURROGATE.search(blob):
        # an escaped lone surrogate ends in adapter_defect today (escaping audit F-01, DECISIONS D-23: the adapter-layer
        # replacement is decided and lands with the regeneration batch, because it changes a rule catalogue); F-1 and
        # F-5 above still hold for such input
        return
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    mapped = outcome(lambda: map_artefact(blob, origin, profile_id="adprov-v1"), MalformedArtefact)
    if mapped[0] == "ok":
        from agentprov.aer.writer import AerWriteError

        result, _unit = mapped[1]
        assert result.error_code != "adapter.defect", "the mapper raised an unexpected exception"
        try:
            aer_bytes(result)  # F-4: the core writer accepts what the mapper yields
        except AerWriteError as exc:
            # The one stated exception (AGENTS.md "Known follow-ups", now shown for adprov too): a degenerate header that
            # cannot name its task. aer/0.1 requires task.task_id with no unk escape, so the import pipeline registers the
            # artefact map.adapter_defect and keeps its bytes (importer._seal); any other refusal is a mapper bug.
            assert result.degenerate and {(f.code, f.pointer) for f in exc.findings} == {
                ("aer.schema.required", "/task/task_id")}, sorted({(f.code, f.pointer) for f in exc.findings})


@pytest.mark.skipif(not SAMPLES, reason="the committed Inspect .eval fixture is not present")
@budget(150)
@given(st.data())
def test_inspect_sample_reader_is_total_and_deterministic(data: st.DataObject) -> None:
    blob = data.draw(_pick(SAMPLES))
    reader = InspectEvalReader()
    reader.sniff(blob, label="samples/x.json", limits=LIMITS)
    first = outcome(lambda: [i.flags for i in reader.parse(blob, _ref(blob), limits=LIMITS)], MalformedArtefact)
    assert first == outcome(lambda: [i.flags for i in reader.parse(blob, _ref(blob), limits=LIMITS)], MalformedArtefact)


@pytest.mark.skipif(CONTAINER is None, reason="the committed Inspect .eval fixture is not present")
@budget(60)
@given(st.data())
def test_inspect_container_sniffing_is_total_on_mutated_archives(data: st.DataObject) -> None:
    assert CONTAINER is not None
    head = CONTAINER[: 64 * 1024]  # the sniff reads the magic only; mutate a bounded prefix
    blob = data.draw(byte_mutations(head, max_ops=4))
    reader = InspectEvalReader()
    first = reader.sniff(blob, label="x.eval", limits=LIMITS)
    assert first == reader.sniff(blob, label="x.eval", limits=LIMITS)
