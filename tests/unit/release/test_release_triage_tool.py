"""``tools/release_triage.py`` (C-3): reviewed class decisions -> the per-root-digest ``[[triage]]`` file.

Synthetic data only: the account names and secret values are assembled at run time and name nobody. gitleaks is a fake
runner (redacted reports to a file, unredacted ones to standard output, as ``--report-path -`` does). Checked: the
origin of a gitleaks finding (suite data, AER record kind, copies that follow their execution's AER finding), account
ordinals in order of first appearance, refused decisions and counts, the triage file beside the corpus that
``release_scan.py --triage`` accepts with nothing left untriaged, and that no value or name is ever written or printed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import release_support as rs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "security"))
import format_support as fs  # noqa: E402

from agentprov.corpus.integrity import root_digest
from agentprov.corpus.layout import shard
from agentprov.release.builder import scan_path_for


def _load(name: str):
    path = Path(__file__).resolve().parents[3] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


release_scan = _load("release_scan")
triage_tool = _load("release_triage")

EX1 = "ex_" + "a" * 26
EX2 = "ex_" + "b" * 26
SHA = "c" * 64
AER1 = f"aer/{shard(EX1, 1)}/{EX1}.aer.jsonl"
AER2 = f"aer/{shard(EX2, 1)}/{EX2}.aer.jsonl"
PROV1 = f"prov/agentprov-prov-0.1/{shard(EX1, 1)}/{EX1}.prov.json"
RAW1 = f"raw/objects/cc/{SHA}.json"
RAW2 = "raw/objects/dd/" + "d" * 64 + ".json"
#: synthetic account names and values (assembled, so no literal looks like an account or a token)
NAME_BENCH = "zq" + "persona"
NAME_MODEL = "zq" + "agentmade"
VALUE_BENCH = "Bench" + "Value" + "0123456789abcdef"
VALUE_MODEL = "Model" + "Value" + "fedcba9876543210"


class FakeGitleaks:
    """``version``, and ``dir`` with ``(path, rule, line, key, value)`` findings: a redacted report to the report file,
    or with no ``--redact`` an unredacted one to standard output."""

    def __init__(self, findings):
        self.findings = findings
        self.calls = []

    def __call__(self, argv, env, timeout):
        self.calls.append(list(argv))
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, b"8.30.1\n", b"")
        target = Path(argv[-1])
        redact = "--redact" in argv
        items = []
        for path, rule, line, key, value in self.findings:
            shown = "REDACTED" if redact else value
            items.append({"File": str(target / path), "RuleID": rule, "StartLine": line, "EndLine": line,
                          "Secret": shown, "Match": f'"{key}": "{shown}"' if key else shown})
        report = argv[argv.index("--report-path") + 1]
        if report == "-":
            return subprocess.CompletedProcess(argv, 0, json.dumps(items).encode(), b"")
        Path(report).write_text(json.dumps(items))
        return subprocess.CompletedProcess(argv, 0, b"", b"")


def _jl(*records) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


def _tree(root: Path) -> dict[str, bytes]:
    """Synthetic files: two executions' AER, a PROV copy, an indexed raw object and an uncited one."""
    files = {
        AER1: _jl(
            {"k": "execution", "id": "h"},
            {"k": "message", "role": "user", "text": f"use {VALUE_BENCH} in /home/{NAME_BENCH}/notes"},
            {"k": "message", "role": "assistant", "text": f"I set {VALUE_MODEL} and wrote /home/{NAME_MODEL}/out"},
            {"k": "tool_call", "args": {"path": f"/home/{NAME_BENCH}/a /home/{NAME_MODEL}/b"}}),
        AER2: _jl({"k": "message", "role": "assistant", "text": "nothing here"}),
        PROV1: _jl({"copy": VALUE_BENCH}, {"copy": VALUE_MODEL}),
        RAW1: _jl({"user": VALUE_BENCH}, {"agent": VALUE_MODEL}),
        RAW2: _jl({"orphan": VALUE_MODEL}),
    }
    for label, data in files.items():
        (root / label).parent.mkdir(parents=True, exist_ok=True)
        (root / label).write_bytes(data)
    (root / "executions.jsonl").write_bytes(_jl({"ex": EX1, "raw": [{"sha256": "sha256:" + SHA}]}, {"ex": EX2, "raw": []}))
    return files


GITLEAKS = [(AER1, "generic-api-key", 2, "password", VALUE_BENCH),
            (AER1, "generic-api-key", 3, "password", VALUE_MODEL),
            (PROV1, "generic-api-key", 1, "password", VALUE_BENCH),
            (PROV1, "generic-api-key", 2, "password", VALUE_MODEL),
            (RAW1, "generic-api-key", 1, "password", VALUE_BENCH),
            (RAW1, "generic-api-key", 2, "password", VALUE_MODEL),
            (RAW2, "generic-api-key", 1, "password", VALUE_MODEL)]


def _classes(root: Path, blob: bytes = b"") -> dict[str, str]:
    matches: dict[str, list[str]] = {}
    findings, _ = release_scan.run_gitleaks("/g", root, run=FakeGitleaks(GITLEAKS), matches=matches)
    return {c.fingerprint: (c.origin, c.key, c.layer)
            for c in triage_tool.secret_classes(root, findings, matches, blob)}


def test_origins_follow_the_aer_record_and_copies_follow_their_execution(tmp_path):
    _tree(tmp_path)
    got = _classes(tmp_path)
    aer, prov, raw = AER1, PROV1, RAW1
    assert got[f"{aer}:generic-api-key:2"] == ("benchmark-input", "password", "aer")
    assert got[f"{aer}:generic-api-key:3"] == ("model-generated", "password", "aer")
    # one execution with both origins: the n-th copy in the file pairs with the n-th AER finding
    assert got[f"{prov}:generic-api-key:1"][0] == "benchmark-input"
    assert got[f"{prov}:generic-api-key:2"][0] == "model-generated"
    assert got[f"{raw}:generic-api-key:1"] == ("benchmark-input", "password", "raw-object")
    assert got[f"{raw}:generic-api-key:2"][0] == "model-generated"
    # a raw object no execution cites has no AER record to follow
    assert got[f"{RAW2}:generic-api-key:1"][0] == "unclassified"


def test_a_copy_with_another_count_takes_the_aer_finding_in_line_order(tmp_path):
    """Check 4b's rule for a copy whose execution has AER findings of several origins and another count (a PROV
    document's one line copies them all): the n-th copy takes the n-th AER finding in line order."""
    _tree(tmp_path)
    matches: dict[str, list[str]] = {}
    one_copy = [f for f in GITLEAKS if not (f[0] == PROV1 and f[2] == 2)]
    findings, _ = release_scan.run_gitleaks("/g", tmp_path, run=FakeGitleaks(one_copy), matches=matches)
    got = {c.fingerprint: c.origin for c in triage_tool.secret_classes(tmp_path, findings, matches, b"")}
    assert got[f"{PROV1}:generic-api-key:1"] == "benchmark-input"
    assert got[f"{RAW1}:generic-api-key:2"] == "model-generated"  # equal counts: still paired one to one


def test_a_token_in_the_suite_data_is_upstream_data(tmp_path):
    _tree(tmp_path)
    got = _classes(tmp_path, blob=b"suite file holding " + VALUE_BENCH.encode())
    assert got[f"{AER1}:generic-api-key:2"][0] == "upstream-data"
    assert got[f"{RAW1}:generic-api-key:1"][0] == "upstream-data"
    assert got[f"{AER1}:generic-api-key:3"][0] == "model-generated"


def test_key_names_are_plain_identifiers_and_joined_when_a_line_has_several():
    assert triage_tool.key_name(['"password": "REDACTED"']) == "password"
    assert triage_tool.key_name(["REDACTED"]) == "(none)"
    assert triage_tool.key_name(['"b": "REDACTED"', '"a": "REDACTED"', '"b": "REDACTED"']) == "a+b"
    assert triage_tool.key_name([]) == "(none)"


def test_account_ordinals_number_names_by_first_appearance_and_never_hold_them_out(tmp_path):
    _tree(tmp_path)
    labels = [AER1, RAW1]
    (tmp_path / labels[1]).write_bytes(f"/home/{NAME_MODEL}./x\n/home/user/x\n/home/{NAME_BENCH}/y\n".encode())
    ordinals = triage_tool.account_ordinals(tmp_path, labels, blob=f"persona {NAME_BENCH}".encode())
    assert ordinals.hits == {1: Counter({"aer": 2, "raw-object": 1}), 2: Counter({"aer": 2, "raw-object": 1})}
    assert ordinals.by_finding == {f"{labels[0]}:account-path:2": {1}, f"{labels[0]}:account-path:3": {2},
                                   f"{labels[0]}:account-path:4": {1, 2}, f"{labels[1]}:account-path:1": {2},
                                   f"{labels[1]}:account-path:3": {1}}
    assert ordinals.in_suite == {1: (True, False), 2: (False, False)}
    assert NAME_BENCH not in repr(ordinals) and NAME_MODEL not in repr(ordinals)


def test_account_paths_in_archive_members_are_read_decoded_as_the_scan_read_them(tmp_path, monkeypatch):
    """D-491: a finding in an archive member (``<archive>#<locator>``) gets its ordinal from the decoded member; without
    the members it is left out (untriaged)."""
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))  # the decoded read's scratch store
    root = tmp_path / "c"
    _tree(root)
    member = f'{{"a": 1}}\n{{"cwd": "/home/{NAME_MODEL}/run"}}\n'.encode() * 2
    archive = fs.zip_bytes([("header.json", b'{"ok": true}\n'), ("run.json", member)])
    assert NAME_MODEL.encode() not in archive  # deflated: only the decoded member holds it
    label = f"raw/objects/{hashlib.sha256(archive).hexdigest()[:2]}/{hashlib.sha256(archive).hexdigest()}.zip"
    (root / label).parent.mkdir(parents=True, exist_ok=True)
    (root / label).write_bytes(archive)
    found = [f for f in release_scan.path_scan(root, {}, secrets=False, in_process=True, release=False)
             if f.rule == "account-path"]
    labels = [f.path for f in found]
    members = triage_tool.member_bytes(root, labels, in_process=True, release=False)
    assert set(members) == {f"{label}#1"}
    ordinals = triage_tool.account_ordinals(root, labels, members=members)
    assert set(ordinals.by_finding) == {f"{f.path}:account-path:{f.line}" for f in found}
    assert ordinals.hits == {1: Counter({"aer": 2}), 2: Counter({"aer": 2, "raw-object": 2})}
    assert ordinals.by_finding[f"{label}#1:account-path:4"] == {2}
    assert NAME_MODEL not in repr(ordinals) and NAME_MODEL not in repr(members.keys())
    assert all("#" not in key for key in triage_tool.account_ordinals(root, labels).by_finding)


def _decisions(digest: str, secrets=(), accounts=()) -> bytes:
    lines = ['format = "agentprov-triage-decisions/0.1"', f'root_digest = "{digest}"']
    for rule, key, origin, triage, n in secrets:
        lines += ["[[secret]]", f'rule = "{rule}"', f'key = "{key}"', f'origin = "{origin}"', f'triage = "{triage}"',
                  f"findings = {n}", 'reason = "synthetic decision"']
    for ordinal, triage, hits in accounts:
        lines += ["[[account]]", f"ordinal = {ordinal}", f'triage = "{triage}"',
                  "hits = {" + ", ".join(f'{k} = {v}' for k, v in hits.items()) + "}", 'reason = "synthetic decision"']
    return ("\n".join(lines) + "\n").encode()


DIGEST = "sha256:" + "0" * 64


@pytest.mark.parametrize("bad", [
    b'root_digest = "sha256:' + b"0" * 64 + b'"\n',  # no format
    b'format = "agentprov-triage-decisions/0.1"\n',  # no root digest
    _decisions(DIGEST, secrets=[("generic-api-key", "password", "model-generated", "real", 1)]),  # real by a tool
    _decisions(DIGEST, secrets=[("generic-api-key", "password", "elsewhere", "model-generated", 1)]),
    _decisions(DIGEST, secrets=[("generic-api-key", "password", "model-generated", "model-generated", 0)]),
    _decisions(DIGEST, secrets=[("r", "k", "model-generated", "model-generated", 1)] * 2),  # decided twice
    _decisions(DIGEST, accounts=[(0, "false-positive", {"aer": 1})]),
    _decisions(DIGEST, accounts=[(1, "false-positive", {})]),
    _decisions(DIGEST, accounts=[(1, "false-positive", {"aer": 1})] * 2),
    _decisions(DIGEST, accounts=[(1, "pinned-account", {"aer": 1, "raw-object": 1})]),  # D-604 item 7: raw only
    _decisions(DIGEST, secrets=[("generic-api-key", "password", "model-generated", "pinned-account", 1)]),
    _decisions(DIGEST) + b"[[triage]]\n",  # an unknown table
])
def test_bad_decisions_are_refused(bad):
    with pytest.raises(triage_tool.Refused):
        triage_tool.load_decisions(bad)


def _row(fp, rule, detector="agentprov-path-scan"):
    return {"fingerprint": fp, "rule": rule, "detector": detector, "triage": None}


def test_counts_that_differ_are_errors_and_mixed_ordinals_take_the_first_triage():
    classes = [triage_tool.SecretClass("a:generic-api-key:1", "generic-api-key", "password", "model-generated", "aer")]
    ordinals = triage_tool.Ordinals(by_finding={"f:account-path:1": {1, 2}, "f:account-path:2": {2}, "f:account-path:3": {3}},
                                    hits={1: Counter(aer=1), 2: Counter(aer=2), 3: Counter(aer=1)})
    decisions = triage_tool.load_decisions(_decisions(DIGEST, secrets=[
        ("generic-api-key", "password", "model-generated", "model-generated", 1)], accounts=[
        (1, "synthetic-benchmark", {"aer": 1}), (2, "false-positive", {"aer": 2})]))
    untriaged = [_row("a:generic-api-key:1", "generic-api-key", "gitleaks"), _row("f:account-path:1", "account-path"),
                 _row("f:account-path:2", "account-path"), _row("f:account-path:3", "account-path"),
                 _row("e:email-address:1", "email-address")]
    plan = triage_tool.plan_triage(untriaged, classes, ordinals, decisions)
    assert plan.errors == []
    assert plan.entries["a:generic-api-key:1"][0] == "model-generated"
    assert plan.entries["f:account-path:1"][0] == "synthetic-benchmark"  # ACCOUNT_ORDER
    assert "account #1" in plan.entries["f:account-path:1"][1] and "account #2" in plan.entries["f:account-path:1"][1]
    assert plan.entries["f:account-path:2"][0] == "false-positive"
    assert plan.left == Counter({"account-path": 1, "email-address": 1})  # #3 is undecided
    wrong = triage_tool.load_decisions(_decisions(DIGEST, secrets=[
        ("generic-api-key", "password", "model-generated", "model-generated", 2),
        ("generic-api-key", "token", "model-generated", "model-generated", 1)], accounts=[
        (1, "synthetic-benchmark", {"aer": 1, "prov": 1})]))
    errors = triage_tool.plan_triage(untriaged, classes, ordinals, wrong).errors
    assert len(errors) == 3 and all("the decision says" in e for e in errors)


# ------------------------------------------------------------------------------------------------ end to end
@pytest.fixture
def sealed(tmp_path_factory, tmp_path):
    """A sealed fixture copy with the synthetic files added; its index cites no synthetic raw object, so both raw objects'
    findings are ``unclassified`` here."""
    root = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    rs.restamp(root, add={label: data for label, data in _tree(tmp_path / "synthetic").items()})
    return root


def _scan(root: Path) -> dict:
    doc = release_scan.scan(root, gitleaks="/g", run=FakeGitleaks(GITLEAKS), needles={})
    scan_path_for(root).write_text(json.dumps(doc))
    return doc


def _good_decisions(root: Path) -> bytes:
    return _decisions(root_digest(root), secrets=[
        ("generic-api-key", "password", "benchmark-input", "synthetic-benchmark", 2),
        ("generic-api-key", "password", "model-generated", "model-generated", 2),
        ("generic-api-key", "password", "unclassified", "model-generated", 3)], accounts=[
        (1, "synthetic-benchmark", {"aer": 2}), (2, "false-positive", {"aer": 2})])


def test_the_triage_file_lands_beside_the_corpus_and_clears_the_scan(sealed, tmp_path, capsys):
    doc = _scan(sealed)
    emails = [f for f in doc["findings"] if f["triage"] is None and f["rule"] == "email-address"]
    decisions = tmp_path / "decisions.toml"
    decisions.write_bytes(_good_decisions(sealed))
    code = triage_tool.main([str(sealed), "--decisions", str(decisions), "--gitleaks", "/g"], run=FakeGitleaks(GITLEAKS))
    out = sealed.with_name(sealed.name + ".release-triage.toml")
    assert out.is_file() and not (sealed / out.name).exists()
    assert code == (1 if emails else 0)
    text = out.read_text()
    for secret in (VALUE_BENCH, VALUE_MODEL, NAME_BENCH, NAME_MODEL):
        assert secret not in text and secret not in capsys.readouterr().err
    triage = release_scan.load_triage(text.encode())
    assert triage.root_digest == root_digest(sealed)
    assert Counter(t for t, _ in triage.entries.values()) == Counter(
        {"synthetic-benchmark": 2 + 2, "model-generated": 2 + 3, "false-positive": 1})  # line 4 holds #1 and #2
    rescan = release_scan.scan(sealed, gitleaks="/g", triage=triage, run=FakeGitleaks(GITLEAKS), needles={})
    assert rescan["summary"]["by_triage"].get("untriaged", 0) == len(emails)
    assert rescan["triage"]["root_digest"] == root_digest(sealed)


def test_a_count_that_differs_writes_nothing(sealed, tmp_path, capsys):
    _scan(sealed)
    decisions = tmp_path / "decisions.toml"
    decisions.write_bytes(_good_decisions(sealed).replace(b"findings = 2", b"findings = 4", 1))
    code = triage_tool.main([str(sealed), "--decisions", str(decisions), "--gitleaks", "/g"], run=FakeGitleaks(GITLEAKS))
    assert code == 2 and "nothing written" in capsys.readouterr().err
    assert not sealed.with_name(sealed.name + ".release-triage.toml").exists()


def test_refused_inputs(sealed, tmp_path, capsys):
    _scan(sealed)
    decisions = tmp_path / "decisions.toml"
    decisions.write_bytes(_good_decisions(sealed))
    run = FakeGitleaks(GITLEAKS)
    assert triage_tool.main([str(sealed), "--decisions", str(decisions), "--gitleaks", "/g",
                             "--out", str(sealed / "aer" / "x.toml")], run=run) == 2  # inside the sealed tree
    other = tmp_path / "other.toml"
    other.write_bytes(_good_decisions(sealed).replace(root_digest(sealed).encode(), DIGEST.encode()))
    assert triage_tool.main([str(sealed), "--decisions", str(other), "--gitleaks", "/g"], run=run) == 2  # D-42
    doc = json.loads(scan_path_for(sealed).read_text())
    doc["tools"][1]["version"] = "1"
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(doc))
    assert triage_tool.main([str(sealed), "--decisions", str(decisions), "--scan", str(stale), "--gitleaks", "/g"],
                            run=run) == 2  # another path-scan version
    # gitleaks now reports another finding set than the scan document
    assert triage_tool.main([str(sealed), "--decisions", str(decisions), "--gitleaks", "/g"],
                            run=FakeGitleaks(GITLEAKS[:-1])) == 2
    assert "scan it again" in capsys.readouterr().err
    assert not sealed.with_name(sealed.name + ".release-triage.toml").exists()


def test_report_and_list_secrets_print_no_value(sealed, capsys, monkeypatch):
    _scan(sealed)
    assert triage_tool.main([str(sealed), "--report", "--gitleaks", "/g"], run=FakeGitleaks(GITLEAKS)) == 0
    printed = capsys.readouterr().out
    doc = json.loads(printed)
    assert [(r["origin"], r["findings"]) for r in doc["secret"]] == [
        ("benchmark-input", 2), ("model-generated", 2), ("unclassified", 3)]
    assert [(r["ordinal"], r["hits"], r["findings"]) for r in doc["account"]] == [(1, {"aer": 2}, 2), (2, {"aer": 2}, 2)]
    run = FakeGitleaks(GITLEAKS)
    assert triage_tool.main([str(sealed), "--list-secrets", "--gitleaks", "/g"], run=run) == 0
    listed = capsys.readouterr().out
    assert any("--redact" not in argv and argv[1] == "dir" for argv in run.calls)
    lines = listed.strip().splitlines()
    assert len(lines) == 2 and all(" rule=generic-api-key keys=password " in line for line in lines)
    assert sorted(line.split(" findings=")[1].split()[0] for line in lines) == ["3", "4"]
    printed += listed
    for secret in (VALUE_BENCH, VALUE_MODEL, NAME_BENCH, NAME_MODEL):
        assert secret not in printed
    # --show adds the values only on a terminal
    assert triage_tool.main([str(sealed), "--list-secrets", "--show", "--gitleaks", "/g"], run=run) == 2
    assert "terminal only" in capsys.readouterr().err
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert triage_tool.main([str(sealed), "--list-secrets", "--show", "--gitleaks", "/g"], run=run) == 0
    shown = capsys.readouterr().out
    assert VALUE_BENCH in shown and VALUE_MODEL in shown and "<<UNTRUSTED" in shown


def test_the_unredacted_report_is_read_from_standard_output(tmp_path):
    _tree(tmp_path)
    run = FakeGitleaks(GITLEAKS[:1])
    values: dict[str, list[str]] = {}
    release_scan.run_gitleaks("/g", tmp_path, run=run, matches=values, redact=False)
    argv = run.calls[-1]
    assert "--redact" not in argv and argv[argv.index("--report-path") + 1] == "-"
    assert values == {f"{AER1}:generic-api-key:2": [VALUE_BENCH]}


def test_pinned_account_is_an_account_triage_for_raw_only_ordinals_and_wins_on_a_shared_line():
    """D-604 item 7: a third-party account in a raw object that ships as pinned; the deposit builder accepts it in
    ``raw/`` only, so a decision gives it only to an ordinal whose hits are all ``raw-object``."""
    decisions = triage_tool.load_decisions(_decisions(DIGEST, accounts=[
        (1, "pinned-account", {"raw-object": 2}), (2, "synthetic-benchmark", {"raw-object": 1})]))
    ordinals = triage_tool.Ordinals(by_finding={"raw/objects/aa/x.json:account-path:1": {1, 2},
                                                "raw/objects/aa/x.json:account-path:2": {1}},
                                    hits={1: Counter({"raw-object": 2}), 2: Counter({"raw-object": 1})})
    untriaged = [{"fingerprint": fp, "rule": "account-path", "detector": "agentprov-path-scan"}
                 for fp in ordinals.by_finding]
    plan = triage_tool.plan_triage(untriaged, [], ordinals, decisions)
    assert not plan.errors and not plan.left
    assert {fp: t for fp, (t, _r) in plan.entries.items()} == {fp: "pinned-account" for fp in ordinals.by_finding}
    text = triage_tool.render_triage(DIGEST, plan.entries, [])
    assert len(release_scan.load_triage(text.encode()).entries) == 2  # the scan's loader accepts it in raw/
