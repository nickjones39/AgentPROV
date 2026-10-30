"""D-810: a corpus spec's persona file of class ``withhold`` makes sealing withhold the executions whose records hold one of
the listed addresses (by digest); ``agentprov-withheld/0.4``; ``chain`` and the deposit builder re-apply the rule.

The fixture corpus is three golden AgentDojo logs, one of which quotes a benchmark persona at a public mail provider; its
digest is computed here from the corpus, and no address is written in this repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
import seal_support as ss

from agentprov.corpus import personas as pe
from agentprov.corpus import withheld as w
from agentprov.corpus import withhold as wh
from agentprov.corpus.package import seal

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = REPO / "src" / "agentprov" / "schemas"


def addr(local: str, domain: str) -> str:
    return "@".join((local, domain))


def withhold_file(digests: list[str], corpus_id: str = "mini-agentdojo") -> bytes:
    rows = ", ".join(f'{{ address = "{d}", ex = "ex_{"a" * 26}", record = "m3", pointer = "/parts/0/text", '
                     'actor_kind = "llm_agent" }' for d in sorted(set(digests)))
    return (f'format = "agentprov-personas/0.1"\nid = "wh"\n[[group]]\nclass = "withhold"\nsource_id = "agentdojo"\n'
            f'repo = "https://github.com/ethz-spylab/agentdojo"\ncommit = "{"a" * 40}"\ncorpus_id = "{corpus_id}"\n'
            f"entries = [{rows}]\n").encode()


def spec_with(data: bytes) -> bytes:
    ref = f'\n[scan]\npersonas = [{{ path = "../p/wh.personas.toml", sha256 = "sha256:{hashlib.sha256(data).hexdigest()}" }}]\n'
    return (ss.SPEC + ref).encode()


@pytest.fixture(scope="module")
def digests(tmp_path_factory) -> list[str]:
    import importlib.util
    import sys

    tools = REPO / "tools"
    sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("release_scan_wh", tools / "release_scan.py")
    assert spec is not None and spec.loader is not None
    rs = importlib.util.module_from_spec(spec)
    sys.modules["release_scan_wh"] = rs
    spec.loader.exec_module(rs)
    dest = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("wh-digest") / "mini")
    table: dict = {}
    rs.collect_addresses(dest.with_name("mini.partial"), "mini", table, in_process=True)
    assert table
    return sorted(table)


def sealed(tmp_path_factory, tmp_path: Path, name: str, data: bytes | None):
    dest = ss.working_corpus(tmp_path_factory, tmp_path / name)
    spec = spec_with(data) if data is not None else ss.SPEC.encode()
    report = seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=spec, persona_files={} if data is None else {"wh.personas.toml": data}))
    return dest, report


def test_the_listed_address_withholds_the_executions_that_hold_it(tmp_path_factory, tmp_path, digests):
    data = withhold_file(digests)
    plain, _ = sealed(tmp_path_factory, tmp_path, "plain", None)
    kept, report = sealed(tmp_path_factory, tmp_path, "kept", data)
    plain_n = json.loads((plain / "corpus.json").read_text())["counts"]["executions"]
    manifest = json.loads((kept / "corpus.json").read_text())
    assert plain_n == 3 and 0 < manifest["counts"]["executions"] < plain_n  # the log that quotes the address is withheld
    ledger = json.loads((kept / "WITHHELD.json").read_text())
    assert ledger["format"] == w.FORMAT_04 and (kept / "schemas" / w.SCHEMA_RESOURCE_04).is_file()
    assert report.counters["withheld_executions"] == plain_n - manifest["counts"]["executions"]
    (policy,) = ledger["policies"]
    assert [(r["id"], r["kind"], r["scope"]) for r in policy["rules"]] == [("email-withheld", "address", "executions")]
    assert {e["reason"] for e in ledger["entries"]} == {"personal_data"} and {e["basis"] for e in ledger["entries"]} == {"profile_rule"}
    assert all(e["finding"]["rule"].endswith(":email-withheld") for e in ledger["entries"])
    text = (kept / "WITHHELD.json").read_text()
    assert not pe.find_addresses(text.encode()) and not any(d in text for d in digests)  # neither an address nor a digest


def test_a_withheld_corpus_verifies_through_chain_and_the_deposit_backstop(tmp_path_factory, tmp_path, digests, capsys):
    import release_support as rs
    from agentprov.cli.main import main
    from agentprov.corpus.integrity import root_digest
    from agentprov.release.builder import scan_path_for

    data = withhold_file(digests)
    kept, _ = sealed(tmp_path_factory, tmp_path, "chain", data)
    capsys.readouterr()
    assert main(["verify", "--corpus", str(kept), "--level", "chain", "--progress", "off"]) == 0
    scan_path_for(kept).write_text(json.dumps(rs.scan_document(kept, root_digest(kept))))
    assert rs.build([kept], tmp_path / "deposit", scan=None).corpora  # the builder re-applies the rule over the released files


def test_chain_reports_a_released_file_that_holds_a_withhold_address(tmp_path_factory, tmp_path, digests, capsys):
    from agentprov.cli.main import main

    data = withhold_file(digests)
    kept, _ = sealed(tmp_path_factory, tmp_path, "leak", data)
    # put the withheld execution's record into a released file: an address with a listed digest in a released file is
    # reported (the digest is of the lower-cased address, so a test cannot invent one: use the fixture's own record)
    plain, _ = sealed(tmp_path_factory, tmp_path, "src", None)
    leaked = next(p for p in (plain / "aer").rglob("*.aer.jsonl") if pe.find_addresses(p.read_bytes()))
    target = next(p for p in (kept / "aer").rglob("*.aer.jsonl") if p.name != leaked.name)
    target.chmod(0o644)
    target.write_bytes(leaked.read_bytes())
    capsys.readouterr()
    assert main(["verify", "--corpus", str(kept), "--level", "chain", "--progress", "off", "--json"]) == 1
    out = capsys.readouterr().out
    assert "withheld.rule_hit" in out and not pe.find_addresses(out.encode())


def test_an_observed_group_of_another_corpus_is_refused_at_sealing(tmp_path_factory, tmp_path, digests):
    """Decision 4 of D-810: an observed group (here ``withhold``) is evidence from one corpus's executions; another corpus's
    spec cannot reference it."""
    from agentprov.corpus.package import PackageRefusedError

    with pytest.raises(PackageRefusedError, match="another corpus") as caught:
        sealed(tmp_path_factory, tmp_path, "foreign", withhold_file(digests, corpus_id="other-corpus"))
    assert caught.value.code == "package.refused.persona"


def test_a_spec_without_a_withhold_class_changes_nothing(tmp_path_factory, tmp_path):
    dest, _ = sealed(tmp_path_factory, tmp_path, "none", pe_text_without_withhold())
    assert not (dest / "WITHHELD.json").exists() and json.loads((dest / "corpus.json").read_text())["counts"]["executions"] == 3


def pe_text_without_withhold() -> bytes:
    other = pe.address_digest(addr("nobody", "nowhere-co.com").encode())
    return (f'format = "agentprov-personas/0.1"\nid = "wh"\n[[group]]\nsource_id = "x"\nrepo = "https://example.org/o/r"\n'
            f'commit = "{"a" * 40}"\nfile = "f.json"\naddresses = ["{other}"]\n').encode()


# ------------------------------------------------------------------------------------------------ the rule and the policy
def test_the_address_rule_matches_files_by_digest_and_never_a_literal():
    wanted = frozenset({pe.address_digest(addr("Target.Person", "gmail.com").encode())})
    rule = wh.Rule(id="email-withheld", kind="address", scope="executions", reason="personal_data", public_note="", digests=wanted,
                   width=1090)
    assert rule.hits(f"x {addr('target.person', 'GMAIL.com')} y".encode()) and not rule.hits(addr("other", "gmail.com").encode())
    assert not rule.hits(b"no address here") and not rule.hits(addr("target.person", "gmail.co").encode())
    assert wh.scan_chunks([b"abc target.person@gm", b"ail.com"], [rule]) == frozenset({"email-withheld"})  # across a chunk boundary


def test_the_policy_gets_the_address_rule_with_or_without_a_profile_policy():
    profile = b'[profile]\nid = "p"\n'
    only = wh.load_policy(profile, profile_id="p", profile_version=1, catalogues={},
                          addresses=frozenset({pe.address_digest(b"a@b.co")}))
    assert only is not None and [r.id for r in only.rules] == ["email-withheld"] and only.record().rules == (
        ("email-withheld", "address", "executions"),)
    assert wh.load_policy(profile, profile_id="p", profile_version=1, catalogues={}) is None


def test_withhold_addresses_reads_the_spec_and_refuses_what_is_missing_or_invalid():
    data = withhold_file([pe.address_digest(b"a@b.co")])
    spec = spec_with(data)
    assert wh.withhold_addresses(spec, lambda name: data) == frozenset({pe.address_digest(b"a@b.co")})
    assert wh.withhold_addresses(ss.SPEC.encode(), lambda name: None) == frozenset()
    with pytest.raises(wh.WithholdError, match="missing"):
        wh.withhold_addresses(spec, lambda name: None)
    with pytest.raises(wh.WithholdError, match="not valid"):
        wh.withhold_addresses(spec, lambda name: b"not toml [")


def test_withhold_object_digests_feed_the_same_address_rule():
    """D-810: an address only in raw objects no execution cites (class ``withhold-object``) is withheld by the same rule;
    an object no execution cites is withheld alone (no execution is affected)."""
    a, b = pe.address_digest(b"a@b.co"), pe.address_digest(b"c@d.co")
    objects = (f'format = "agentprov-personas/0.1"\nid = "wo"\n[[group]]\nclass = "withhold-object"\nsource_id = "agentdojo"\n'
               f'repo = "https://github.com/ethz-spylab/agentdojo"\ncommit = "{"a" * 40}"\ncorpus_id = "mini-agentdojo"\n'
               f'entries = [{{ address = "{b}", object = "sha256:{"c" * 64}" }}]\n').encode()
    data = withhold_file([a])
    refs = "".join(f'{{ path = "../p/{n}.personas.toml", sha256 = "sha256:{hashlib.sha256(d).hexdigest()}" }}, '
                   for n, d in (("wh", data), ("wo", objects)))
    spec = (ss.SPEC + f"\n[scan]\npersonas = [{refs}]\n").encode()
    files = {"wh.personas.toml": data, "wo.personas.toml": objects}
    assert wh.withhold_addresses(spec, files.get) == frozenset({a, b})


# ------------------------------------------------------------------------------------------------ the 0.4 ledger
def _document(kind: str = "address") -> w.WithheldDocument:
    sha, ex = "a" * 64, "ex_" + "a" * 26
    entry = w.WithheldObject(sha, ({"blob_sha1": "c" * 40, "commit": "d" * 40, "kind": "git", "path": "runs/x.json",
                                    "repo": "https://github.com/o/r"},), "personal_data", "profile_rule", "an address", (ex,), 12,
                             "application/json", w.WithheldFinding("agentprov-withhold/1", "p@1:email-withheld",
                                                                   "aer/aa/x.aer.jsonl:email-withheld"), "2026-10-23")
    return w.WithheldDocument((entry,), (w.WithheldExecution(ex, ("s1",), {"aer": "sha256:" + "e" * 64}),),
                              (w.WithheldPolicy("p", 1, "sha256:" + "0" * 64, (("email-withheld", kind, "executions"),)),))


def test_the_0_4_schema_is_published_generated_and_differs_from_0_3_only_by_the_rule_kind():
    new = SCHEMAS / "withheld-0.4.schema.json"
    assert new.read_bytes() == w.schema_bytes(w.FORMAT_04) == w.load_published_schema(w.SCHEMA_RESOURCE_04)
    assert (SCHEMAS / "withheld-0.3.schema.json").read_bytes() == w.schema_bytes(w.FORMAT_03)  # frozen with its version
    a, b = json.loads((SCHEMAS / "withheld-0.3.schema.json").read_bytes()), json.loads(new.read_bytes())
    kinds = b["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"]["kind"]["enum"]
    assert kinds == ["marker", "pattern", "issue", "address"]
    for doc in (a, b):
        doc.pop("$id"), doc.pop("title"), doc["properties"].pop("format")
        doc["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"].pop("kind")
    assert a == b


def test_the_format_is_0_4_exactly_when_a_policy_has_an_address_rule():
    document = _document()
    assert document.format == w.FORMAT_04 and document.schema_resource == w.SCHEMA_RESOURCE_04
    data = w.encode_withheld(document)
    assert w.encode_withheld(w.decode_withheld(data)) == data
    jsonschema.validate(json.loads(data), json.loads((SCHEMAS / "withheld-0.4.schema.json").read_bytes()))
    plain = _document("pattern")
    assert plain.format == w.FORMAT
    for obj in ({**json.loads(data), "format": w.FORMAT_03}, {**plain.to_json(), "format": w.FORMAT_04}):
        assert w.validate_withheld(obj)
        with pytest.raises(w.WithheldError):
            w.decode_withheld(json.dumps(obj).encode())
