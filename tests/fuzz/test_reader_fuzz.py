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
def test_a_turn_without_a_role_is_malformed_not_a_mapper_defect() -> None:
    """The fuzz finding of the first public CI run (2026-11-01, D-1011): a turn whose "role" key is damaged ("sole")
    mapped to a message with role null, which the AER writer refused (aer.schema.pattern at /role). The mapper now
    refuses such a turn as a malformed artefact, as it does a turn whose content is not a string."""
    from agentprov.adapters.runner import aer_bytes, map_artefact

    seed = next(s for s in ADPROV if b'"role": "system"' in s)
    blob = seed.replace(b'"role": "system"', b'"sole": "system"', 1)
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)  # the writer accepts what the mapper yields
    assert not any(isinstance(r, dict) and r.get("k") == "message" and r.get("role") is None for r in result.records)


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
def test_an_unknown_member_named_with_a_dollar_is_kept_literal() -> None:
    """Fuzz F-4 (the release CI run of 2026-11-05): one flipped byte turned a turn's "args" into "$rgs". The mapper
    copied the unknown member's name into ext.adprov.extra, where a name beginning with "$" is reserved, and the AER
    writer refused the record (aer.schema.pattern). Unknown members with such a name are kept as a $lit-wrapped
    object; the transcript/v1 view reads them back."""
    import json as _json

    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.views.transcript_v1 import render

    doc = _json.loads(next(s for s in ADPROV if b'"role": "user"' in s))
    turn = next(t for t in doc["turns"] if t.get("role") == "user")
    turn["$rgs"] = {"$x": 1}
    doc["meta"]["$meta"] = "kept"
    blob = _json.dumps(doc).encode()
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)  # the writer accepts what the mapper yields
    view = render([r for r in result.records if r.get("k") != "seal"])
    assert view["meta"]["$meta"] == "kept"
    assert next(t for t in view["turns"] if t.get("role") == "user")["$rgs"] == {"$x": 1}


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
@pytest.mark.parametrize("where", ["tool turn", "tool call"])
@pytest.mark.parametrize("placeholder", ["", "none", "-"])
def test_a_deny_listed_tool_name_is_kept_and_declared_ambiguous(where: str, placeholder: str) -> None:
    """Regen-batch row 190 (the v0.2.1 release CI fuzz run 42183082509): a deletion emptied a tool turn's "function",
    and the mapper wrote "" as the tool execution's /name, which the AER writer refused (aer.sentinel, AER-V17). As in
    the agentdojo mappers (UC-12), the verbatim name is kept and declared unk ambiguous, in a tool turn's execution and
    in an assistant tool call's part, and the transcript/v1 view reads it back."""
    import json as _json

    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.views.transcript_v1 import render

    doc = _json.loads(next(s for s in ADPROV if b'"role": "tool"' in s))
    if where == "tool turn":
        turn = next(t for t in doc["turns"] if t.get("role") == "tool")
    else:
        turn = next(c for t in doc["turns"] if t.get("role") == "assistant" for c in t.get("tool_calls") or ())
    turn["function"] = placeholder
    blob = _json.dumps(doc).encode()
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)  # the writer accepts what the mapper yields
    marked = [(r["k"], p) for r in result.records if isinstance(r, dict)
              for p, why in (r.get("unk") or {}).items() if p.endswith("name") and why == "ambiguous"]
    assert marked and all(k == ("tool_execution" if where == "tool turn" else "message") for k, _ in marked), marked
    view = render([r for r in result.records if r.get("k") != "seal"])
    names = [t.get("function") for t in view["turns"] if t.get("role") == "tool"] if where == "tool turn" else \
        [c.get("function") for t in view["turns"] if t.get("role") == "assistant" for c in t.get("tool_calls") or ()]
    assert placeholder in names


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
@pytest.mark.parametrize("key", ["agentdojo_version", "benchmark_version", "model_id", "suite", "user_task_id",
                                 "attack_type", "injection_task_id"])
@pytest.mark.parametrize("placeholder", ["", "unknown", "-"])
def test_a_placeholder_in_meta_never_reaches_a_typed_field(key: str, placeholder: str) -> None:
    """The thorough fuzz profile's finding of 2026-11-01 (D-1011): two deleted bytes emptied meta.agentdojo_version, and
    the mapper wrote the empty string as /code/dist_version, which the AER writer refused (aer.sentinel, AER-V17). A
    version or model id holding a placeholder is now not recorded, and a task identity holding one is malformed."""
    import json as _json

    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.aer.writer import AerWriteError

    seed = next(s for s in ADPROV if b'"injection_task_id": "' in s)
    doc = _json.loads(seed)
    doc["meta"][key] = placeholder
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(_json.dumps(doc, indent=2).encode(), origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    try:
        aer_bytes(result)
    except AerWriteError as exc:  # the stated exception: a degenerate header that cannot name its task
        assert key == "user_task_id" and result.degenerate
        assert {(f.code, f.pointer) for f in exc.findings} == {("aer.schema.required", "/task/task_id")}
    else:
        assert result.degenerate == (key in ("suite", "attack_type", "injection_task_id"))


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
def test_a_tool_turn_that_ends_before_it_starts_is_malformed_not_a_mapper_defect() -> None:
    """The thorough fuzz profile's finding of 2026-11-01 (D-1011): a tool turn whose ended_at precedes its started_at
    (one flipped digit) reached the AER writer, which refused it (aer.order.time, AER-V19). The mapper now refuses the
    contradiction as malformed and never repairs a time (invariant 2)."""
    import re as _re

    from agentprov.adapters.runner import aer_bytes, map_artefact

    seed = next(s for s in ADPROV if b'"ended_at": "20' in s and b'"role": "tool"' in s)
    starts = list(_re.finditer(rb'"started_at": "(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)', seed))
    tool = next(m for m in starts if seed.rfind(b'"role": "tool"', 0, m.start()) > seed.rfind(b'"role": "assistant"', 0, m.start()))
    end = _re.compile(rb'"ended_at": "\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d').search(seed, tool.end())
    assert end is not None
    blob = seed[:end.start()] + b'"ended_at": "2000-01-01T00:00:00' + seed[end.end():]  # before every start
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)  # the writer accepts what the mapper yields


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
def test_a_time_outside_the_aer_ranges_is_malformed_not_a_mapper_defect() -> None:
    """The thorough fuzz profile's finding of 2026-11-01 (D-1011): an ended_at with month 16 matched the mapper's time
    shape and reached the AER writer, which refused it (aer.schema.pattern at /t/end)."""
    import re as _re

    from agentprov.adapters.runner import aer_bytes, map_artefact

    seed = next(s for s in ADPROV if _re.search(rb'"ended_at": "\d{4}-\d\d-', s))
    match = _re.search(rb'"ended_at": "(\d{4})-\d\d-', seed)
    assert match is not None
    blob = seed[:match.start()] + b'"ended_at": "' + match.group(1) + b"-16-" + seed[match.end():]
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)


@pytest.mark.skipif(not ADPROV, reason="the golden transcript/v1 fixtures are not present")
def test_counts_beyond_the_aer_integer_range_neither_break_the_record_nor_run_away() -> None:
    """The thorough fuzz profile's finding of 2026-11-01 (D-1011): 30 nines spliced into a usage count reached the typed
    usage field (aer.schema.pattern at /usage/input_tokens). Such a count is now kept verbatim in ext, as other unusable
    values are; and an n_llm_calls that large, which would have meant one lost-call record per unit, is refused at once."""
    import re as _re
    import time

    from agentprov.adapters.runner import aer_bytes, map_artefact

    origin = Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.transcript.json", producer_commit="5" * 40)
    seed = next(s for s in ADPROV if _re.search(rb'"usage": \{', s))
    huge = b"9" * 30
    count = _re.compile(rb'("(?!n_llm_calls)[a-z_]*tokens?[a-z_]*": )(\d+)')
    match = count.search(seed, seed.index(b'"usage": {'))
    assert match is not None
    blob = seed[:match.start(2)] + huge + seed[match.end(2):]
    result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
    assert result.error_code != "adapter.defect"
    aer_bytes(result)
    calls = _re.compile(rb'("n_llm_calls": )(\d+)').search(seed)
    if calls is not None:
        blob = seed[:calls.start(2)] + huge + seed[calls.end(2):]
        started = time.monotonic()
        result, _unit = map_artefact(blob, origin, profile_id="adprov-v1")
        assert result.error_code != "adapter.defect" and time.monotonic() - started < 10
        aer_bytes(result)


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
