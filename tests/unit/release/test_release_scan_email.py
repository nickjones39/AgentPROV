"""The release scan's e-mail rule, its persona and reserved-domain triage and the helpers (D-810; G.9.4).

No address is written in this repository: the canary and the fixture personas are assembled at run time. The fixture
corpus quotes AgentDojo benchmark personas (three golden logs); their digests are computed here from the corpus itself.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import release_support as rs
import seal_support as ss

from agentprov.corpus import personas as pe
from agentprov.corpus.integrity import root_digest
from agentprov.corpus.package import PackageRefusedError, seal
from agentprov.release.builder import scan_path_for

TOOLS = Path(__file__).resolve().parents[3] / "tools"


def load(name: str, module: str):
    spec = importlib.util.spec_from_file_location(module, TOOLS / name)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module] = mod
    sys.path.insert(0, str(TOOLS))
    spec.loader.exec_module(mod)
    return mod


release_scan = load("release_scan.py", "release_scan_email")
scan_personas = load("scan_personas.py", "scan_personas_email")


def addr(local: str, domain: str) -> str:
    return "@".join((local, domain))


CANARY = addr("canary.person9", "persona-canary-d810.com")
CANARY_PARTS = ("canary.person9", "persona-canary-d810", CANARY)


class FakeGitleaks:
    def __call__(self, argv, env, timeout):
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, b"8.30.1\n", b"")
        Path(argv[argv.index("--report-path") + 1]).write_text("[]")
        return subprocess.CompletedProcess(argv, 0, b"", b"")


def persona_file(digests: list[str], pid: str = "bench-one", file_names: list[str] = (), *,
                 benchmark_input: list[str] = (), model_generated: list[str] = ()) -> bytes:
    """A persona file: ``digests`` are ``upstream-data``; the other classes have their own groups (an observed class holds
    entries with synthetic AER evidence)."""

    def group(klass: str, items: list[str], file: str) -> str:
        listing = ", ".join(f'"{d}"' for d in sorted(set(items)))
        return (f'[[group]]\nclass = "{klass}"\nsource_id = "agentdojo"\nrepo = "https://github.com/ethz-spylab/agentdojo"\n'
                f'commit = "{"a" * 40}"\nfile = "{file}"\naddresses = [{listing}]\n')

    def observed(klass: str, items: list[str], actor: str) -> str:
        rows = ", ".join(f'{{ address = "{d}", ex = "ex_{"a" * 26}", record = "m3", pointer = "/parts/0/text", '
                         f'actor_kind = "{actor}" }}' for d in sorted(set(items)))
        return (f'[[group]]\nclass = "{klass}"\nsource_id = "agentdojo"\nrepo = "https://github.com/ethz-spylab/agentdojo"\n'
                f'commit = "{"a" * 40}"\ncorpus_id = "mini-agentdojo"\nentries = [{rows}]\n')

    body = group("upstream-data", digests, "src/data.py") if digests else ""
    body += group("file-name", list(file_names), "runs/x.json") if file_names else ""
    body += observed("benchmark-input", list(benchmark_input), "simulated_user") if benchmark_input else ""
    body += observed("model-generated", list(model_generated), "llm_agent") if model_generated else ""
    return f'format = "agentprov-personas/0.1"\nid = "{pid}"\n{body}'.encode()


@pytest.fixture(scope="module")
def working(tmp_path_factory) -> Path:
    """``(working corpus)``: three golden AgentDojo logs, whose raw objects and AER quote benchmark personas."""
    dest = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("email") / "mini")
    return dest


@pytest.fixture(scope="module")
def table(working: Path) -> dict:
    out: dict = {}
    assert release_scan.collect_addresses(working.with_name(working.name + ".partial"), "mini", out, in_process=True) == 0
    return out


def classes(table: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for digest, stat in table.items():
        out.setdefault(stat.klass, []).append(digest)
    return out


def sealed(tmp_path_factory, tmp_path, name: str, personas: dict[str, bytes] | None) -> Path:
    dest = ss.working_corpus(tmp_path_factory, tmp_path / name)
    scan = ""
    if personas:
        refs = ", ".join(f'{{ path = "../p/{n}", sha256 = "sha256:{hashlib.sha256(b).hexdigest()}" }}'
                         for n, b in sorted(personas.items()))
        scan = f"\n[scan]\npersonas = [{refs}]\n"
    seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=(ss.SPEC + scan).encode(), persona_files=personas or {}))
    return dest


def run_scan(root: Path):
    return release_scan.scan(root, gitleaks="/g", run=FakeGitleaks(), needles={}, accounts=False)


def email_rows(doc: dict) -> list[dict]:
    return [f for f in doc["findings"] if f["rule"] == "email-address"]


# ------------------------------------------------------------------------------------------------ the fixture
def test_the_fixture_corpus_quotes_a_freemail_persona_in_raw_and_aer(table):
    assert classes(table) == {"public-freemail": list(table)} and len(table) >= 1
    assert all(len(d) == 71 and d.startswith("sha256:") for d in table)
    assert {s for st in table.values() for s in st.stages} >= {"raw", "aer"}


# ------------------------------------------------------------------------------------------------ the rule in files
def scan_file(tmp_path: Path, data: bytes, personas: frozenset[str] = frozenset(), chunk: int | None = None, monkeypatch=None):
    if chunk is not None:
        monkeypatch.setattr(release_scan, "_CHUNK", chunk)
    root = tmp_path / "t"
    root.mkdir(parents=True, exist_ok=True)
    (root / "f.txt").write_bytes(data)
    seen: list[tuple[str, str, int]] = []
    emails = release_scan.Emails({"upstream-data": personas}, lambda digest, klass, where, line: seen.append((digest, klass, line)))
    found = release_scan.path_scan(root, {}, accounts=False, secrets=False, decode=False, emails=emails)
    return found, seen


def test_an_address_is_a_finding_on_its_line_and_records_no_value(tmp_path):
    found, seen = scan_file(tmp_path, f"one\ntwo {CANARY}\nthree\n".encode())
    assert [(f.path, f.rule, f.line, f.basis) for f in found] == [("f.txt", "email-address", 2, None)]
    assert seen == [(pe.address_digest(CANARY.encode()), "other", 2)]
    assert CANARY not in json.dumps([vars(f) for f in found])


def test_every_address_of_a_line_must_be_cleared_for_the_line_to_be(tmp_path):
    reserved = addr("a", "example.com")
    persona = addr("b", "persona-one.com")
    keep = frozenset({pe.address_digest(persona.encode())})
    only, _ = scan_file(tmp_path, f"{reserved} {persona}\n".encode(), keep)
    assert [(f.line, f.basis) for f in only] == [(1, "upstream-data")]
    mixed, _ = scan_file(tmp_path, f"{reserved} {persona} {CANARY}\n".encode(), keep)
    assert [(f.line, f.basis) for f in mixed] == [(1, None)]  # one unlisted address leaves the whole line untriaged
    just_reserved, _ = scan_file(tmp_path, f"{reserved}\n".encode(), keep)
    assert [(f.line, f.basis) for f in just_reserved] == [(1, "reserved")]


def test_reserved_domains_are_cleared_and_test_com_is_not(tmp_path):
    cleared, _ = scan_file(tmp_path, "\n".join(addr("u", d) for d in ("example.com", "x.example", "y.test", "z.invalid")).encode())
    assert [(f.line, f.basis) for f in cleared] == [(n, "reserved") for n in (1, 2, 3, 4)]
    real, _ = scan_file(tmp_path, addr("u", "test.com").encode())
    assert [f.basis for f in real] == [None]


def test_a_public_freemail_address_is_cleared_only_by_its_own_entry(tmp_path):
    freemail = addr("someone.real", "gmail.com")
    none, _ = scan_file(tmp_path, freemail.encode())
    other, _ = scan_file(tmp_path, freemail.encode(), frozenset({pe.address_digest(addr("else", "gmail.com").encode())}))
    exact, _ = scan_file(tmp_path, freemail.encode(), frozenset({pe.address_digest(freemail.upper().encode())}))
    assert [f.basis for f in none] == [None] and [f.basis for f in other] == [None]
    assert [f.basis for f in exact] == ["upstream-data"]  # an exact entry (case is normalised) is the only way


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 64, 1500, 4096])
def test_an_address_is_found_once_with_one_digest_across_any_chunking(tmp_path, monkeypatch, chunk):
    filler = "x" * 17
    data = (f"{filler}\n{CANARY}\n{filler} " * 3 + addr("tail.person", "end-of-file.org")).encode()
    found, seen = scan_file(tmp_path, data, chunk=chunk, monkeypatch=monkeypatch)
    expected = {pe.address_digest(CANARY.encode()), pe.address_digest(addr("tail.person", "end-of-file.org").encode())}
    assert {d for d, _k, _l in seen} == expected
    assert sorted(f.line for f in found) == [2, 4, 6, 7]  # one finding per line, whatever the chunking


def test_the_chunk_boundary_cannot_split_the_digest_or_the_line(tmp_path, monkeypatch):
    big = release_scan._EMAIL_REACH * 3
    data = b"\n" * 5 + b"." * big + CANARY.encode() + b"\n" + b"y" * big + CANARY.encode()
    whole, seen_whole = scan_file(tmp_path / "w", data)
    for chunk in (1000, 1024, 1025, 3000, big + 3, big - 1):
        parts, seen = scan_file(tmp_path / f"c{chunk}", data, chunk=chunk, monkeypatch=monkeypatch)
        assert sorted((f.line, f.rule) for f in parts) == sorted((f.line, f.rule) for f in whole), chunk
        assert {d for d, _k, _l in seen} == {d for d, _k, _l in seen_whole}, chunk


def test_hostile_input_does_not_stall_the_scan(tmp_path):
    import time

    start = time.perf_counter()
    scan_file(tmp_path, b"a@" + b"a." * 300_000 + b"\n" + b"@" * 300_000 + b"\n" + b"x" * 300_000 + b"@a.bc")
    assert time.perf_counter() - start < 10


def test_an_address_in_an_archive_member_is_a_finding(tmp_path):
    import zipfile

    root = tmp_path / "z"
    root.mkdir()
    with zipfile.ZipFile(root / "a.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("m.txt", f"x\n{CANARY}\n")
    found = release_scan.path_scan(root, {}, accounts=False, secrets=False, emails=release_scan.Emails(), in_process=True,
                                   release=False)
    assert [(f.path.startswith("a.zip#"), f.rule, f.line) for f in found] == [(True, "email-address", 2)]


def test_an_archive_read_decoded_is_not_judged_by_its_stored_bytes(tmp_path):
    """D-810 (path-scan 6): compressed bytes match the address shape by chance; an archive the decoded scan read is judged
    by its members only. A stored (uncompressed) member is still found, through the decoded scan."""
    import zipfile

    root = tmp_path / "z"
    root.mkdir()
    with zipfile.ZipFile(root / "a.zip", "w", zipfile.ZIP_STORED) as zf:  # the address is in the archive's stored bytes
        zf.writestr("m.txt", f"x\n{CANARY}\n")
    sunk: list[tuple] = []
    found = release_scan.path_scan(root, {}, accounts=False, secrets=False, in_process=True, release=False,
                                   emails=release_scan.Emails(None, lambda *call: sunk.append(call)))
    assert CANARY.encode() in (root / "a.zip").read_bytes()
    assert [(f.path.startswith("a.zip#"), f.rule) for f in found] == [(True, "email-address")]
    assert {where.startswith("a.zip#") for _d, _k, where, _l in sunk} == {True}
    plain = release_scan.path_scan(root, {}, accounts=False, secrets=False, decode=False,
                                   emails=release_scan.Emails())  # no decoded scan: the stored bytes are judged
    assert [(f.path, f.rule) for f in plain] == [("a.zip", "email-address")]


def test_an_escaped_address_has_the_digest_of_the_decoded_one(tmp_path):
    """A persona quoted after a JSON newline escape is the same persona (D-810, path-scan 6)."""
    data = json.dumps({"text": "Hi\n" + CANARY}).encode()
    assert b"\\n" + CANARY.encode() in data
    table: dict = {}
    root = tmp_path / "e"
    root.mkdir()
    (root / "x.json").write_bytes(data)
    release_scan.collect_addresses(root, "e", table, in_process=True)
    assert set(table) == {pe.address_digest(CANARY.encode())}


# ------------------------------------------------------------------------------------------------ the scan document
def test_the_scan_documents_every_persona_address_untriaged_without_a_list(tmp_path_factory, tmp_path):
    root = sealed(tmp_path_factory, tmp_path, "plain", None)
    doc = run_scan(root)
    rows = email_rows(doc)
    assert rows and all(r["triage"] is None and r["basis"] is None for r in rows)
    assert doc["personas"]["files"] == [] and sum(doc["personas"]["classes"].values()) == 0
    assert doc["tools"][1]["version"] == "6" and "e-mail" in doc["tools"][1]["mode"]
    assert {r["detector"] for r in rows} == {"agentprov-path-scan"}


PERSONA = addr("persona.one", "bench-co.com")  # a benchmark persona at a domain the benchmark invented
PROBE = "raw/persona-probe.txt"


def with_probe(root: Path, extra: str = "") -> Path:
    """Add a probe file to a sealed tree (the scan does not check closed-world): line 1 holds the persona."""
    probe = root / PROBE
    probe.write_text(f"{PERSONA}\n{extra}")
    return probe


def probe_rows(doc: dict) -> list[dict]:
    return [r for r in email_rows(doc) if r["path"] == PROBE]


def test_a_persona_list_clears_its_own_corpus_only(tmp_path_factory, tmp_path, table):
    listed = [pe.address_digest(PERSONA.encode())]
    mine = sealed(tmp_path_factory, tmp_path, "mine", {"bench-one.personas.toml": persona_file(listed)})
    theirs = sealed(tmp_path_factory, tmp_path, "theirs", None)  # the same persona under a spec that lists nothing
    with_probe(mine), with_probe(theirs)
    doc = run_scan(mine)
    (row,) = probe_rows(doc)
    assert row["basis"] == "upstream-data" and row["triage"] == "synthetic-benchmark"
    assert "upstream-data entry of this corpus" in row["reason"] and "1 digests" in row["reason"]
    assert doc["personas"]["classes"] == {"model-generated": 0, "benchmark-input": 0, "upstream-data": 1, "file-name": 0}
    assert doc["personas"]["spec_sha256"] == json.loads((mine / "corpus.json").read_text())["files"]["spec"]["sha256"]
    (other,) = probe_rows(run_scan(theirs))
    assert other["basis"] is None and other["triage"] is None


def test_a_freemail_persona_stays_untriaged_unless_its_digest_is_listed(tmp_path_factory, tmp_path, table):
    freemail = list(table)
    listed = [pe.address_digest(PERSONA.encode())]
    root = sealed(tmp_path_factory, tmp_path, "free", {"bench-one.personas.toml": persona_file(listed)})
    doc = run_scan(root)
    assert email_rows(doc) and all(r["triage"] is None for r in email_rows(doc))  # a public-freemail address, no entry
    full = sealed(tmp_path_factory, tmp_path, "full", {"bench-one.personas.toml": persona_file(listed + freemail)})
    assert all(r["triage"] == "synthetic-benchmark" for r in email_rows(run_scan(full)))  # the exact entries clear them


MODEL_MADE = addr("model.made.up", "invented-co.com")
BENCH_INPUT = addr("supplied", "bench-input-co.com")


def three_class_corpus(tmp_path_factory, tmp_path, name="three"):
    digest = lambda a: pe.address_digest(a.encode())  # noqa: E731
    return sealed(tmp_path_factory, tmp_path, name, {"all.personas.toml": persona_file(
        [digest(PERSONA)], "all", model_generated=[digest(MODEL_MADE)], benchmark_input=[digest(BENCH_INPUT)])})


def test_each_class_has_its_own_basis_and_triage_and_model_generated_is_never_synthetic(tmp_path_factory, tmp_path):
    root = three_class_corpus(tmp_path_factory, tmp_path)
    (root / PROBE).write_text(f"{PERSONA}\n{BENCH_INPUT}\n{MODEL_MADE}\n")
    doc = run_scan(root)
    rows = {r["line"]: r for r in probe_rows(doc)}
    assert (rows[1]["basis"], rows[1]["triage"]) == ("upstream-data", "synthetic-benchmark")
    assert (rows[2]["basis"], rows[2]["triage"]) == ("benchmark-input", "synthetic-benchmark")
    assert (rows[3]["basis"], rows[3]["triage"]) == ("model-generated", "model-generated")
    assert "appears only in model output" in rows[3]["reason"] and "not a benchmark persona" in rows[3]["reason"]
    assert doc["personas"]["classes"] == {"model-generated": 1, "benchmark-input": 1, "upstream-data": 1, "file-name": 0}


def test_a_line_of_mixed_cleared_bases_takes_the_strongest_disclosure(tmp_path):
    digest = lambda a: pe.address_digest(a.encode())  # noqa: E731
    classes = {"upstream-data": frozenset({digest(PERSONA)}), "benchmark-input": frozenset({digest(BENCH_INPUT)}),
               "model-generated": frozenset({digest(MODEL_MADE)}), "file-name": frozenset({digest(addr("i", "2x.png"))})}

    def basis(*addresses: str):
        root = tmp_path / str(abs(hash(addresses)))
        root.mkdir()
        (root / "f.txt").write_text(" ".join(addresses))
        found = release_scan.path_scan(root, {}, accounts=False, secrets=False, decode=False, emails=release_scan.Emails(classes))
        return [f.basis for f in found]

    assert basis(PERSONA, MODEL_MADE) == ["model-generated"]  # never reported as a synthetic benchmark line
    assert basis(PERSONA, BENCH_INPUT) == ["benchmark-input"]
    assert basis(PERSONA, addr("i", "2x.png")) == ["upstream-data"]
    assert basis(addr("i", "2x.png"), addr("x", "example.com")) == ["file-name"]
    assert basis(MODEL_MADE, CANARY) == [None]


def test_the_builder_accepts_all_classes_and_keeps_the_bases_apart(tmp_path_factory, tmp_path, table):
    digests = list(table)  # the fixture's one address stands in for each class in turn
    for klass, kwargs, triage in (("upstream-data", {}, "synthetic-benchmark"), ("benchmark-input", {"benchmark_input": digests},
                                  "synthetic-benchmark"), ("model-generated", {"model_generated": digests}, "model-generated")):
        root = sealed(tmp_path_factory, tmp_path / klass, klass, {"x.personas.toml": persona_file(
            digests if klass == "upstream-data" else [], "x", **kwargs)})
        doc = run_scan(root)
        assert all(r["basis"] == klass and r["triage"] == triage for r in email_rows(doc))
        report = build_with(root, doc, tmp_path / klass)
        row = report.corpora[0]["release_scan"]
        assert row["by_triage"] == {triage: len(email_rows(doc))} and row["by_basis"] == {klass: len(email_rows(doc))}


FILE_NAME = addr("icon", "2x.png")  # a file name with the shape of an address


def test_a_file_name_entry_is_a_false_positive_for_its_own_corpus_only(tmp_path_factory, tmp_path):
    entry = [pe.address_digest(FILE_NAME.encode())]
    mine = sealed(tmp_path_factory, tmp_path, "fn-mine", {"names.personas.toml": persona_file([], "names", entry)})
    theirs = sealed(tmp_path_factory, tmp_path, "fn-theirs", {"names.personas.toml": persona_file([], "names", [
        pe.address_digest(addr("other", "2x.png").encode())])})
    plain = sealed(tmp_path_factory, tmp_path, "fn-plain", None)
    for root in (mine, theirs, plain):
        (root / PROBE).write_text(f"{FILE_NAME}\n")
    doc = run_scan(mine)
    (row,) = probe_rows(doc)
    assert (row["basis"], row["triage"], row["rule"]) == ("file-name", "false-positive", "email-address")
    assert "file-name entry of this corpus" in row["reason"] and doc["personas"]["classes"]["file-name"] == 1
    assert doc["personas"]["classes"]["upstream-data"] == 0
    for root in (theirs, plain):  # another corpus's entry, or none: the same string is a finding to triage
        (other,) = probe_rows(run_scan(root))
        assert other["basis"] is None and other["triage"] is None


def test_no_extension_is_cleared_without_an_entry(tmp_path):
    for domain in ("2x.png", "host.json", "x.py", "files.md", "a.zip"):
        found, _ = scan_file(tmp_path / domain, addr("name", domain).encode())
        assert [f.basis for f in found] == [None], domain  # there is no denylist of extensions


def test_a_line_with_a_listed_persona_and_an_unlisted_address_stays_untriaged(tmp_path_factory, tmp_path):
    root = sealed(tmp_path_factory, tmp_path, "mixed", {"bench-one.personas.toml": persona_file(
        [pe.address_digest(PERSONA.encode())])})
    with_probe(root, f"{PERSONA} {CANARY}\n")
    rows = {r["line"]: r for r in probe_rows(run_scan(root))}
    assert rows[1]["basis"] == "upstream-data" and rows[2]["basis"] is None and rows[2]["triage"] is None


def test_a_human_triage_entry_decides_its_fingerprint_over_a_rule(tmp_path_factory, tmp_path):
    root = sealed(tmp_path_factory, tmp_path, "human", {"bench-one.personas.toml": persona_file(
        [pe.address_digest(PERSONA.encode())])})
    with_probe(root)
    first = probe_rows(run_scan(root))[0]
    text = (f'root_digest = "{root_digest(root)}"\n[[triage]]\nfingerprint = "{first["fingerprint"]}"\n'
            'triage = "real"\nreason = "reviewed: a real person"\n').encode()
    doc = release_scan.scan(root, gitleaks="/g", run=FakeGitleaks(), needles={}, accounts=False,
                            triage=release_scan.load_triage(text))
    (row,) = probe_rows(doc)
    assert row["triage"] == "real" and row["basis"] is None


def test_no_value_is_in_the_scan_document(tmp_path_factory, tmp_path, table):
    root = sealed(tmp_path_factory, tmp_path, "novalue", None)
    probe = root / "raw" / "canary-probe.txt"
    probe.write_text(f"x\n{CANARY}\n")
    try:
        doc = run_scan(root)
    finally:
        probe.unlink()
    text = json.dumps(doc)
    assert any(r["path"] == "raw/canary-probe.txt" and r["line"] == 2 for r in email_rows(doc))
    assert not any(part in text for part in CANARY_PARTS)


def test_a_spec_that_does_not_match_the_manifest_is_refused(tmp_path_factory, tmp_path):
    root = sealed(tmp_path_factory, tmp_path, "tampered", None)
    spec = root / "rules" / "corpus-spec.toml"
    spec.write_bytes(spec.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="files.spec"):
        run_scan(root)


# ------------------------------------------------------------------------------------------------ sealing the lists
def test_sealing_refuses_a_missing_wrong_or_unreferenced_persona_file(tmp_path_factory, tmp_path):
    good = persona_file([pe.address_digest(addr("a", "x.com").encode())])
    ref = f'\n[scan]\npersonas = [{{ path = "../p/bench-one.personas.toml", sha256 = "sha256:{hashlib.sha256(good).hexdigest()}" }}]\n'
    cases = {
        "missing": ({}, ref),
        "wrong digest": ({"bench-one.personas.toml": good + b"# changed\n"}, ref),
        "unreferenced": ({"bench-one.personas.toml": good}, ""),
        "unparsable": ({"bench-one.personas.toml": b"not toml ["},
                       f'\n[scan]\npersonas = [{{ path = "../p/bench-one.personas.toml", sha256 = "sha256:{hashlib.sha256(b"not toml [").hexdigest()}" }}]\n'),
    }
    for label, (supplied, scan) in cases.items():
        dest = ss.working_corpus(tmp_path_factory, tmp_path / label.replace(" ", "-"))
        with pytest.raises(PackageRefusedError) as caught:
            seal(dest, corpus_version="0.1.0", inputs=ss.inputs(spec=(ss.SPEC + scan).encode(), persona_files=supplied))
        assert caught.value.code == "package.refused.persona", label
        assert Path(str(dest) + ".partial").is_dir() and not dest.exists()  # nothing was written


def test_the_sealed_corpus_carries_the_persona_file_and_verifies(tmp_path_factory, tmp_path, capsys, table):
    from agentprov.cli.main import main

    data = persona_file(list(table))
    root = sealed(tmp_path_factory, tmp_path, "carry", {"bench-one.personas.toml": data})
    assert (root / "rules" / "personas" / "bench-one.personas.toml").read_bytes() == data
    assert "rules/personas/bench-one.personas.toml" in (root / "checksums.sha256").read_text()
    capsys.readouterr()
    assert main(["verify", "--corpus", str(root), "--level", "chain", "--progress", "off"]) == 0
    assert not any(part in (root / "rules" / "personas" / "bench-one.personas.toml").read_text() for part in ("@",))


# ------------------------------------------------------------------------------------------------ the builder
def build_with(corpus: Path, doc: dict, tmp_path: Path):
    scan_path_for(corpus).write_text(json.dumps(doc))
    return rs.build([corpus], tmp_path / "deposit", scan=None)


def test_the_builder_refuses_an_untriaged_email_finding(tmp_path_factory, tmp_path):
    root = sealed(tmp_path_factory, tmp_path, "untriaged", None)
    with pytest.raises(Exception) as caught:
        build_with(root, run_scan(root), tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_untriaged"


def cleared_corpus(tmp_path_factory, tmp_path, table) -> tuple[Path, dict]:
    root = sealed(tmp_path_factory, tmp_path, "cleared", {"bench-one.personas.toml": persona_file(list(table))})
    return root, run_scan(root)


def test_the_builder_accepts_a_persona_cleared_scan_and_the_deposit_verifies(tmp_path_factory, tmp_path, table):
    from agentprov.release.verify import verify_deposit

    root, doc = cleared_corpus(tmp_path_factory, tmp_path, table)
    assert all(r["triage"] == "synthetic-benchmark" for r in email_rows(doc))
    report = build_with(root, doc, tmp_path)
    assert report.corpora[0]["release_scan"]["by_triage"] == {"synthetic-benchmark": len(email_rows(doc))}
    assert verify_deposit(tmp_path / "deposit", level="chain", release=False).passed()


def test_the_builder_refuses_a_persona_basis_from_another_spec(tmp_path_factory, tmp_path, table):
    root, doc = cleared_corpus(tmp_path_factory, tmp_path, table)
    doc["personas"]["spec_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_personas"
    doc["personas"] = None
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_personas"


@pytest.mark.parametrize(("basis", "triage"), [("upstream-data", "false-positive"), ("reserved", "synthetic-benchmark"),
                                               ("upstream-data", "real"), ("whatever", "false-positive"),
                                               ("file-name", "synthetic-benchmark"), ("file-name", "real"),
                                               ("model-generated", "synthetic-benchmark"),
                                               ("benchmark-input", "model-generated"),
                                               ("benchmark-input", "false-positive")])
def test_the_builder_refuses_a_basis_that_does_not_fit_its_triage(tmp_path_factory, tmp_path, table, basis, triage):
    root, doc = cleared_corpus(tmp_path_factory, tmp_path, table)
    row = email_rows(doc)[0]
    row["basis"], row["triage"] = basis, triage
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_basis"


def test_the_builder_accepts_a_file_name_basis_of_this_corpus_and_refuses_another_spec(tmp_path_factory, tmp_path, table):
    root = sealed(tmp_path_factory, tmp_path, "fn-build", {"names.personas.toml": persona_file(
        [], "names", list(table))})  # (the fixture's one address stands in for a file name)
    doc = run_scan(root)
    assert all(r["basis"] == "file-name" and r["triage"] == "false-positive" for r in email_rows(doc))
    doc["personas"]["spec_sha256"] = "sha256:" + "1" * 64
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_personas"
    doc["personas"]["spec_sha256"] = json.loads((root / "corpus.json").read_text())["files"]["spec"]["sha256"]
    assert build_with(root, doc, tmp_path).corpora[0]["release_scan"]["by_triage"] == {"false-positive": len(email_rows(doc))}


def test_a_basis_on_a_rule_that_is_not_email_is_refused(tmp_path_factory, tmp_path, table):
    root, doc = cleared_corpus(tmp_path_factory, tmp_path, table)
    row = email_rows(doc)[0]
    row["rule"] = "account-path"
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_basis"


def test_an_older_path_scan_version_is_refused(tmp_path_factory, tmp_path, table):
    root, doc = cleared_corpus(tmp_path_factory, tmp_path, table)
    doc["tools"][1]["version"] = "4"
    with pytest.raises(Exception) as caught:
        build_with(root, doc, tmp_path)
    assert getattr(caught.value, "code", "") == "release.refused.scan_tools"


# ------------------------------------------------------------------------------------------------ --list-addresses
def test_list_addresses_prints_digests_classes_counts_corpora_and_layers_never_an_address(tmp_path, capsys):
    a, b = tmp_path / "corpus-a.partial", tmp_path / "corpus-b"
    for root in (a, b):
        (root / "raw").mkdir(parents=True)
        (root / "aer").mkdir()
    (a / "raw" / "x.txt").write_text(f"{CANARY}\n{addr('r', 'example.org')}\n{CANARY}\n")
    (a / "aer" / "y.jsonl").write_text(CANARY + "\n")
    (b / "raw" / "z.txt").write_text(f"x {CANARY}\n{addr('p', 'gmail.com')}\n")
    capsys.readouterr()
    assert release_scan.list_addresses([a, b]) == 0
    out, err = capsys.readouterr()
    lines = {line.split()[0]: line.split() for line in out.splitlines()}
    canary = lines[pe.address_digest(CANARY.encode())]
    assert canary[1:] == ["other", "findings=4", "corpora=corpus-a,corpus-b", "stages=aer,raw"]  # lines 1+3 of x are 2
    assert lines[pe.address_digest(addr("r", "example.org").encode())][1:3] == ["reserved", "findings=1"]
    assert lines[pe.address_digest(addr("p", "gmail.com").encode())][1] == "public-freemail"
    assert len(lines) == 3 and "3 distinct address(es)" in err
    assert not any(part in out + err for part in (*CANARY_PARTS, "gmail", "example.org"))


def test_main_list_addresses_needs_no_gitleaks_and_writes_no_file(tmp_path, capsys, monkeypatch):
    root = tmp_path / "c"
    root.mkdir()
    (root / "f.txt").write_text(CANARY)
    monkeypatch.setattr(release_scan.shutil, "which", lambda name: None)
    assert release_scan.main(["--list-addresses", str(root)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c"]
    assert not any(part in capsys.readouterr().out for part in CANARY_PARTS)


def test_scanning_two_corpora_at_once_is_a_usage_error(tmp_path, capsys):
    assert release_scan.main([str(tmp_path), str(tmp_path)]) == 2


# ------------------------------------------------------------------------------------------------ scan_personas
def git(repo: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo)}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args], capture_output=True, text=True,
                          env=env, check=True).stdout.strip()


@pytest.fixture
def upstream(tmp_path) -> tuple[Path, str]:
    repo = tmp_path / "upstream"
    (repo / "src").mkdir(parents=True)
    (repo / "runs").mkdir()
    (repo / "src" / "suite.py").write_text(f'RECIPIENT = "{addr("suite.persona", "bench-co.com")}"\n')
    (repo / "src" / "b.py").write_text(f'X = "{addr("suite.persona", "bench-co.com")}"\nY = "{addr("second", "bench-co.com")}"\n')
    (repo / "runs" / "log.json").write_text(f'"{addr("only.in.a.log", "bench-co.com")}"')
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "one")
    return repo, git(repo, "rev-parse", "HEAD")


def corpus_tree(tmp_path: Path) -> Path:
    root = tmp_path / "corp.partial"
    (root / "raw").mkdir(parents=True)
    (root / "aer").mkdir()
    (root / "raw" / "a.txt").write_text("\n".join(addr(n, "bench-co.com") for n in ("suite.persona", "only.in.a.log", "model.invented")) + "\n")
    (root / "aer" / "b.jsonl").write_text(addr("suite.persona", "bench-co.com") + "\n" + addr("x", "example.com") + "\n"
                                          + addr("someone", "gmail.com") + "\n")
    return root


def test_scan_personas_splits_found_reserved_and_not_found_by_digest(upstream, tmp_path, capsys):
    repo, commit = upstream
    root = corpus_tree(tmp_path)
    capsys.readouterr()
    code = scan_personas.main(["--corpus", str(root), "--upstream", str(repo), commit, "https://github.com/o/r",
                               "--exclude", "runs/"])
    out, err = capsys.readouterr()
    assert code == 0
    first, second = (json.loads(line) for line in out.splitlines())
    assert first["distinct_addresses"] == 2 and first["blobs_read"] == 2  # runs/ is excluded
    assert second["corpus"] == "corp" and second["distinct_addresses"] == 5
    assert (second["reserved"], second["found_in_upstream"], second["not_found"]) == (1, 1, 3)
    assert second["not_found_by_class"] == {"other": 2, "public-freemail": 1}
    assert second["not_found_addresses_by_stage"] == {"aer": 1, "raw": 2}
    assert second["not_found_findings_by_stage"] == {"aer": 1, "raw": 2}
    assert not any(part in out + err for part in ("persona", "bench-co", "gmail", "example.com"))


def test_scan_personas_writes_a_digest_only_persona_file_with_evidence(upstream, tmp_path, capsys):
    repo, commit = upstream
    root = corpus_tree(tmp_path)
    out = tmp_path / "bench.personas.toml"
    assert scan_personas.main(["--corpus", str(root), "--upstream", str(repo), commit, "https://github.com/o/r",
                               "--exclude", "runs/", "--source-id", "bench", "--out", str(out), "--id", "bench-one"]) == 0
    text = out.read_text()
    assert "@" not in text and "bench-co" not in text and "persona" not in text.replace("agentprov-personas", "")
    doc = pe.parse_persona_file(text.encode())
    assert doc.digests == {pe.address_digest(addr("suite.persona", "bench-co.com").encode())}  # not the log-only address
    (group,) = doc.groups
    assert (group["source_id"], group["repo"], group["commit"], group["file"]) == (
        "bench", "https://github.com/o/r", commit, "src/b.py") or group["file"] == "src/suite.py"
    assert group["file"] == "src/b.py"  # in path order, b.py comes first of the two files holding the address


def test_scan_personas_counts_an_absent_blob_and_never_fetches_it(upstream, tmp_path, capsys):
    repo, commit = upstream
    blob = git(repo, "rev-parse", f"{commit}:src/suite.py")
    path = repo / ".git" / "objects" / blob[:2] / blob[2:]
    path.chmod(0o644)
    path.unlink()  # a blob a partial clone does not hold (git ls-tree -l prints BAD for its size)
    root = corpus_tree(tmp_path)
    assert scan_personas.main(["--corpus", str(root), "--upstream", str(repo), commit, "https://github.com/o/r",
                               "--exclude", "runs/"]) == 0
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert (first["blobs_absent"], first["blobs_read"]) == (1, 1)
    assert second["found_in_upstream"] == 1  # the address is still in the other file


def test_scan_personas_reads_a_plain_directory_upstream_such_as_a_dataset_snapshot(tmp_path, capsys):
    snapshot = tmp_path / "snapshot"
    (snapshot / "benchmark").mkdir(parents=True)
    (snapshot / "benchmark" / "data.json").write_text(f'["{addr("dataset.person", "bench-co.com")}"]')
    (snapshot / "README.md").write_text(f"{addr('dataset.person', 'bench-co.com')} {addr('also', 'bench-co.com')}")
    (snapshot / "outside.txt").symlink_to(tmp_path / "elsewhere")  # a link is never followed
    root = tmp_path / "corp.partial"
    (root / "raw").mkdir(parents=True)
    (root / "raw" / "a.txt").write_text(f"{addr('dataset.person', 'bench-co.com')}\n{addr('model.made.up', 'bench-co.com')}\n")
    out = tmp_path / "ds.personas.toml"
    assert scan_personas.main(["--corpus", str(root), "--upstream-dir", str(snapshot), "e23b3fe6" + "0" * 32,
                               "https://huggingface.co/datasets/o/n", "--source-id", "ds", "--out", str(out), "--id", "ds-one"]) == 0
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert first["blobs_read"] == 2 and (second["found_in_upstream"], second["not_found"]) == (1, 1)
    parsed = pe.parse_persona_file(out.read_bytes())
    assert parsed.digests == {pe.address_digest(addr("dataset.person", "bench-co.com").encode())}
    assert parsed.groups[0]["file"] == "README.md" and parsed.groups[0]["repo"] == "https://huggingface.co/datasets/o/n"
    assert "@" not in out.read_text() and "bench-co" not in out.read_text()


def test_scan_personas_needs_an_upstream(tmp_path, capsys):
    assert scan_personas.main(["--corpus", str(tmp_path)]) == 2


def test_scan_personas_sets_no_lazy_fetch_on_every_git_call():
    assert scan_personas._ENV["GIT_NO_LAZY_FETCH"] == "1"
    assert not any(k.startswith("GIT_") and k not in ("GIT_NO_LAZY_FETCH", "GIT_TERMINAL_PROMPT") for k in scan_personas._ENV)


def test_scan_personas_out_without_id_is_a_usage_error(upstream, tmp_path, capsys):
    repo, commit = upstream
    assert scan_personas.main(["--corpus", str(tmp_path), "--upstream", str(repo), commit, "https://github.com/o/r",
                               "--out", str(tmp_path / "x.personas.toml")]) == 2
