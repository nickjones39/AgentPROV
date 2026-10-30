"""The ``credleak.cell`` reader (docs/architecture D.19.1, D.19.2): path grammar, sniff, one item per run."""

from __future__ import annotations

import hashlib
import json

import credleak_support as support
import pytest

from agentprov.adapters.credleak.dialect import CredleakCellReader, parse_path
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, Origin
from agentprov.errors import MalformedArtefact
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def test_path_grammar():
    roster = parse_path("p15b-run-data/01-injection-map/T1-file-document/gpt-5.5/run__T1__gpt-5.5__T1.1__2026.json")
    assert roster is not None and roster.to_json() == {
        "section": "01-injection-map", "channel": "T1-file-document", "model_dir": "gpt-5.5",
        "file": "run__T1__gpt-5.5__T1.1__2026.json", "layout_class": "roster", "prefix": "run"}
    excluded = parse_path("/x/p15b-run-data/04-hygiene/output-T-EMIT/excluded-models/glm-5/archive-p15b-a__T.json")
    assert excluded is not None and excluded.layout_class == "excluded-models" and excluded.prefix == "archive-p15b-a"
    probe = parse_path("01-injection-map/T-WEB-web-page/_fable-filter-probe-NOT-SCORABLE/addendum-2026-09-13__p.json")
    assert probe is not None and probe.layout_class == "underscore" and probe.model_dir is None
    assert probe.underscore_dir == "_fable-filter-probe-NOT-SCORABLE" and probe.prefix == "addendum-2026-09-13"
    assert "model_dir" not in probe.to_json()
    assert parse_path("p15b-run-data/T-WEB-web-page/_probe/x.json") is None  # no section
    assert parse_path("p15b-run-data/05-temit-precision-audit/x/y/sample.json") is None
    assert parse_path("p15b-run-data/01-injection-map/T1/m/README.md") is None
    other = parse_path("03-egress-axis/delayed-trigger/m/plain.json")
    assert other is not None and other.prefix == "other"


def test_every_fixture_cell_sniffs_and_parses_into_one_item_per_run():
    reader = CredleakCellReader()
    for entry in support.source_entries():
        data = support.cell_bytes(entry)
        assert reader.sniff(data, label=entry["label"], limits=LIMITS).match
        artefact = ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/json",
                               support.member_origin(entry["label"], data))
        items = list(reader.parse(data, artefact, limits=LIMITS))
        runs = json.loads(data)["runs"]
        assert [i.locator.p for i in items] == [f"/runs/{n}" for n in range(len(runs))]
        assert all(i.locator.key() == {"p": f"/runs/{n}"} for n, i in enumerate(items))
        assert all(i.value is items[0].value for i in items)  # the whole cell, parsed once


@pytest.mark.parametrize(("data", "reason"), [
    (b'{"runs": []}', "credleak.not_a_cell"),
    (b"[1, 2]", "credleak.not_a_cell"),
    (b'{"a": 1, "a": 2}', "ingest.json.duplicate_key"),
    (b"\xff\xfe", None),
])
def test_foreign_input_is_classified_never_raised(data, reason):
    sniff = CredleakCellReader().sniff(data, label="x.json", limits=LIMITS)
    assert not sniff.match
    if reason is not None:
        assert sniff.reasons == (reason,)
    else:
        assert sniff.reasons[0].startswith("ingest.")
    assert CredleakCellReader.register_detail(sniff.reasons) == (reason if reason == "credleak.not_a_cell" else None)


def test_a_cell_with_an_extra_key_is_not_a_cell_and_parse_refuses_it():
    value = json.loads(support.synthetic_cell())
    value["extra"] = 1
    data = json.dumps(value).encode()
    assert not CredleakCellReader().sniff(data, label="x.json", limits=LIMITS).match
    artefact = ArtefactRef("a0", "0" * 64, len(data), "application/json", Origin.local("/x.json"))
    with pytest.raises(MalformedArtefact):
        list(CredleakCellReader().parse(data, artefact, limits=LIMITS))


def test_a_cell_without_runs_yields_no_item():
    value = json.loads(support.synthetic_cell())
    value["runs"] = []
    data = json.dumps(value).encode()
    artefact = ArtefactRef("a0", "0" * 64, len(data), "application/json", Origin.local("/x.json"))
    assert list(CredleakCellReader().parse(data, artefact, limits=LIMITS)) == []


def test_discovery_follows_the_profile_selection():
    class Tree:
        def walk(self):
            for label in ("p15b-run-data/01-injection-map/T1/m/run__a.json", "p15b-run-data/README.md",
                          "p15b-run-data/05-temit-precision-audit/sample.json",
                          "p15b-run-data/03-egress-axis/external-canary-collector-log/log.json",
                          "p15b-run-data/04-hygiene/x/m/.DS_Store", "p15b-run-data/04-hygiene/x/m/run__b.json"):
                yield CandidateArtefact(label, 1, Origin.local("/" + label))

        def open(self, label, *, max_bytes):  # pragma: no cover - discovery reads nothing
            raise AssertionError(label)

    labels = [c.label for c in CredleakCellReader().iter_artefacts(Tree(), load_profile("credleak-p15b"))]
    assert labels == ["p15b-run-data/01-injection-map/T1/m/run__a.json", "p15b-run-data/04-hygiene/x/m/run__b.json"]
