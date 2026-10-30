"""D-964: a corpus spec's ``[withhold]`` table lists stored raw objects (each withheld alone) and executions (each withheld
with its primary object), reason ``secret``; ``agentprov-withheld/0.5``; ``chain`` and the deposit builder check that
nothing listed is released. The fixture corpus is the three golden AgentDojo logs of ``seal_support``.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import seal_support as ss

from agentprov.corpus import withheld as w
from agentprov.corpus.package import seal

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = REPO / "src" / "agentprov" / "schemas"


def rows_of(dest: Path) -> list[dict]:
    lines = (dest.with_name(dest.name + ".partial") / "executions.jsonl").read_text().splitlines()
    return sorted((json.loads(line) for line in lines if line.strip()), key=lambda r: r["ex"])


def primary(row: dict) -> str:
    return next(ref["sha256"] for ref in row["raw"] if ref["role"] == "primary").removeprefix("sha256:")


def spec_listing(objects: list[str] = (), executions: list[str] = ()) -> bytes:  # type: ignore[assignment]
    table = '\n[withhold]\ndecided_by = "a release-scan review (test)"\n'
    if objects:
        table += "objects = [" + ", ".join(f'"sha256:{o}"' for o in objects) + "]\n"
    if executions:
        table += "executions = [" + ", ".join(f'"{e}"' for e in executions) + "]\n"
    return (ss.SPEC + table).encode()


def test_a_listed_object_goes_alone_and_a_listed_execution_with_its_primary(tmp_path_factory, tmp_path):
    dest = ss.working_corpus(tmp_path_factory, tmp_path / "listed")
    first, second, third = rows_of(dest)
    report = seal(dest, corpus_version="0.1.0",
                  inputs=ss.inputs(spec=spec_listing([primary(first)], [second["ex"]])))
    manifest = json.loads((dest / "corpus.json").read_text())
    assert manifest["counts"]["executions"] == 2 and report.counters["withheld_executions"] == 1  # only the listed one
    ledger = json.loads((dest / "WITHHELD.json").read_text())
    assert ledger["format"] == w.FORMAT_05 and (dest / "schemas" / w.SCHEMA_RESOURCE_05).is_file()
    assert {e["sha256"].removeprefix("sha256:") for e in ledger["entries"]} == {primary(first), primary(second)}
    assert [x["ex"] for x in ledger["executions"]] == [second["ex"]]
    assert {(e["reason"], e["basis"]) for e in ledger["entries"]} == {("secret", "profile_rule")}
    (policy,) = ledger["policies"]
    assert [(r["id"], r["kind"], r["scope"]) for r in policy["rules"]] == [("secret-withheld", "object", "object")]
    index = (dest / "executions.jsonl").read_text()
    assert first["ex"] in index and second["ex"] not in index and third["ex"] in index  # the first keeps its record


def test_a_listed_corpus_verifies_through_chain_and_the_deposit_backstop(tmp_path_factory, tmp_path, capsys):
    import release_support as rs
    from agentprov.cli.main import main
    from agentprov.corpus.integrity import root_digest
    from agentprov.release.builder import scan_path_for

    dest = ss.working_corpus(tmp_path_factory, tmp_path / "chain")
    first, second, _ = rows_of(dest)
    seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=spec_listing([primary(first)], [second["ex"]])))
    capsys.readouterr()
    assert main(["verify", "--corpus", str(dest), "--level", "chain", "--progress", "off"]) == 0
    scan_path_for(dest).write_text(json.dumps(rs.scan_document(dest, root_digest(dest))))
    assert rs.build([dest], tmp_path / "deposit", scan=None).corpora


def test_a_listed_object_the_corpus_does_not_store_refuses_the_seal(tmp_path_factory, tmp_path):
    from agentprov.corpus.package import PackageRefusedError

    dest = ss.working_corpus(tmp_path_factory, tmp_path / "unknown")
    with pytest.raises(PackageRefusedError) as caught:
        seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=spec_listing(["f" * 64])))
    assert caught.value.code == "package.refused.policy"


def test_a_spec_without_a_withhold_table_seals_as_before(tmp_path_factory, tmp_path):
    dest = ss.working_corpus(tmp_path_factory, tmp_path / "none")
    seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=ss.SPEC.encode()))
    assert not (dest / "WITHHELD.json").exists() and json.loads((dest / "corpus.json").read_text())["counts"]["executions"] == 3


# ------------------------------------------------------------------------------------------------ the ledger version
def _document(kind: str = "object") -> w.WithheldDocument:
    ex = "ex_" + "a" * 26
    entry = w.WithheldObject("e" * 64, ({"blob_sha1": "c" * 40, "commit": "1" * 40, "kind": "git", "path": "x.json",
                                         "repo": "https://github.com/o/r"},), "secret", "profile_rule", "a value", (ex,), 12,
                             "application/json", w.WithheldFinding("agentprov-withhold/1", "p@1:secret-withheld",
                                                                   "aer/aa/x.aer.jsonl:secret-withheld"), "2026-10-29")
    return w.WithheldDocument((entry,), (w.WithheldExecution(ex, ("s1",), {"aer": "sha256:" + "e" * 64}),),
                              (w.WithheldPolicy("p", 1, "sha256:" + "0" * 64, (("secret-withheld", kind, "object"),)),))


def test_the_0_5_schema_is_published_generated_and_differs_from_0_4_only_by_the_rule_kind():
    new = SCHEMAS / "withheld-0.5.schema.json"
    assert new.read_bytes() == w.schema_bytes(w.FORMAT_05) == w.load_published_schema(w.SCHEMA_RESOURCE_05)
    assert (SCHEMAS / "withheld-0.4.schema.json").read_bytes() == w.schema_bytes(w.FORMAT_04)  # frozen with its version
    a, b = json.loads((SCHEMAS / "withheld-0.4.schema.json").read_bytes()), json.loads(new.read_bytes())
    kinds = b["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"]["kind"]["enum"]
    assert kinds == ["marker", "pattern", "issue", "address", "object"]
    for doc in (a, b):
        doc.pop("$id"), doc.pop("title"), doc["properties"].pop("format")
        doc["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"].pop("kind")
    assert a == b


def test_the_format_is_0_5_exactly_when_a_policy_has_an_object_rule():
    document = _document()
    assert document.format == w.FORMAT_05 and document.schema_resource == w.SCHEMA_RESOURCE_05
    data = w.encode_withheld(document)
    assert w.encode_withheld(w.decode_withheld(data)) == data
    jsonschema.validate(json.loads(data), json.loads((SCHEMAS / "withheld-0.5.schema.json").read_bytes()))
    plain = _document("pattern")
    assert plain.format == w.FORMAT
    for obj in ({**json.loads(data), "format": w.FORMAT_04}, {**plain.to_json(), "format": w.FORMAT_05}):
        assert w.validate_withheld(obj)
        with pytest.raises(w.WithheldError):
            w.decode_withheld(json.dumps(obj).encode())


# ------------------------------------------------------------------------------------------------ the spec table
@pytest.mark.parametrize("table, message", [
    ('decided_by = "x"\n', "objects or executions"),
    ('decided_by = "x"\nobjects = []\n', "at least one"),
    ('decided_by = "x"\nexecutions = ["ex_1"]\n', "malformed"),
    ('decided_by = "x"\nobjects = ["sha256:' + "a" * 63 + '"]\n', "malformed"),
    ('decided_by = "x"\nobjects = ["sha256:' + "a" * 64 + '", "sha256:' + "a" * 64 + '"]\n', "duplicate"),
    ('objects = ["sha256:' + "a" * 64 + '"]\n', "missing decided_by"),
    ('decided_by = "x"\nobjects = ["sha256:' + "a" * 64 + '"]\nreason = "secret"\n', "unknown key"),
])
def test_a_malformed_withhold_table_is_refused(table, message):
    from agentprov.corpus.spec import CorpusSpecError, parse_spec

    with pytest.raises(CorpusSpecError, match=message):
        parse_spec((ss.SPEC + "\n[withhold]\n" + table).encode())


def test_the_withhold_table_parses_into_the_spec():
    from agentprov.corpus.spec import parse_spec

    spec = parse_spec(spec_listing(["a" * 64], ["ex_" + "b" * 26]))
    assert spec.withhold_objects == ("sha256:" + "a" * 64,) and spec.withhold_executions == ("ex_" + "b" * 26,)
    assert spec.withhold_decided_by == "a release-scan review (test)"
    plain = parse_spec(ss.SPEC.encode())
    assert (plain.withhold_objects, plain.withhold_executions, plain.withhold_decided_by) == ((), (), None)
