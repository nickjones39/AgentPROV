"""``tools/release_scan.py`` (G.9.4): the gitleaks wrapper that writes ``<corpus>.release-scan.json``.

gitleaks is replaced by a fake runner (it writes a report the way gitleaks does), so the tests run without it; one test
runs the real binary when it is installed. Checked: the argv (explicit config, empty ignore path, ``--redact``,
``--ignore-gitleaks-allow``, reduced environment); findings keep path, rule and line, never a matched value; the home
path and host name search across chunk boundaries; triage; and that the deposit builder accepts the written document.
"""

from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import release_support as rs

from agentprov.corpus.integrity import root_digest
from agentprov.release.builder import scan_path_for

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "release_scan.py"
_spec = importlib.util.spec_from_file_location("release_scan_tool", _TOOL)
assert _spec is not None and _spec.loader is not None
release_scan = importlib.util.module_from_spec(_spec)
sys.modules["release_scan_tool"] = release_scan
_spec.loader.exec_module(release_scan)


def _pinned_gitleaks() -> str | None:
    """The installed gitleaks when it is the pinned scanner (D-620), else ``None``: another version is refused by the
    tool (``ScanError``), so the real-gitleaks tests skip on it instead of failing (pre-round verification V-6)."""
    executable = shutil.which("gitleaks")
    if executable is None:
        return None
    try:
        release_scan.gitleaks_version(executable)
    except release_scan.ScanError:
        return None
    return executable


def test_another_gitleaks_version_skips_the_real_gitleaks_tests(tmp_path, monkeypatch):
    """V-6: a gitleaks on PATH at another version than the pin makes the real-gitleaks tests skip (before: they failed
    with ScanError); the pinned one, or none, behaves as before."""
    other = tmp_path / "gitleaks"
    other.write_text("#!/bin/sh\necho 8.0.0\n")
    other.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda name: str(other) if name == "gitleaks" else None)
    assert _pinned_gitleaks() is None
    other.write_text(f"#!/bin/sh\necho {release_scan.GITLEAKS_VERSION}\n")
    assert _pinned_gitleaks() == str(other)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert _pinned_gitleaks() is None


#: the real-gitleaks tests need gitleaks at the pinned version (``GITLEAKS_VERSION``); missing or another: skipped
needs_pinned_gitleaks = pytest.mark.skipif(_pinned_gitleaks() is None,
                                           reason=f"gitleaks {release_scan.GITLEAKS_VERSION} (the pinned scanner) is not "
                                                  "installed")


class FakeGitleaks:
    """Answers ``version`` and writes a JSON report for ``dir`` (redacted members, as gitleaks writes them)."""

    def __init__(self, findings, version=b"8.30.1\n"):
        self.findings = findings
        self.version = version
        self.calls = []

    def __call__(self, argv, env, timeout):
        self.calls.append((list(argv), dict(env)))
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, self.version, b"")
        target = Path(argv[-1])
        report = Path(argv[argv.index("--report-path") + 1])
        items = [{"File": str(target / path), "RuleID": rule, "StartLine": line, "Secret": "REDACTED", "Match": "REDACTED",
                  "Fingerprint": f"{target / path}:{rule}:{line}"} for path, rule, line in self.findings]
        report.write_text(json.dumps(items))
        return subprocess.CompletedProcess(argv, 0, b"", b"")


@pytest.fixture
def corpus(tmp_path_factory, tmp_path):
    return rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")


def without_emails(doc):
    """The findings of a scan document less the ``email-address`` ones: the fixture corpus quotes benchmark persona
    addresses (D-810), which these tests are not about (``test_release_scan_email.py`` is)."""
    return [f for f in doc["findings"] if f["rule"] != "email-address"]


def test_the_scan_document_binds_the_root_digest_and_records_no_value(corpus):
    aer = next(p for p in (corpus / "aer").rglob("*.aer.jsonl")).relative_to(corpus).as_posix()
    fake = FakeGitleaks([(aer, "generic-api-key", 7)])
    doc = release_scan.scan(corpus, gitleaks="/fake/gitleaks", run=fake, needles={})
    assert doc["format"] == "agentprov-release-scan/0.1"
    assert doc["target"] == {"corpus_id": "mini-mit", "corpus_version": "0.1.0", "kind": "corpus",
                             "root_digest": root_digest(corpus)}
    assert doc["tools"][0]["name"] == "gitleaks" and doc["tools"][0]["version"] == "8.30.1"
    assert doc["tools"][0]["key_cuts_resolved"] == 0
    assert without_emails(doc) == [{"basis": None, "detector": "gitleaks", "fingerprint": f"{aer}:generic-api-key:7",
                                    "line": 7, "path": aer, "reason": None, "rule": "generic-api-key", "triage": None}]
    assert {f["rule"] for f in doc["findings"]} == {"generic-api-key", "email-address"}  # the fixture's persona addresses
    assert doc["triage"] is None
    assert "REDACTED" not in json.dumps(doc)
    argv, env = fake.calls[1]
    assert {"--redact", "--ignore-gitleaks-allow", "--no-banner", "--config", "--gitleaks-ignore-path"} <= set(argv)
    assert argv[argv.index("--exit-code") + 1] == "0" and argv[argv.index("--max-archive-depth") + 1] == "0"
    assert set(env) == {"HOME", "LC_ALL", "PATH"}


def test_triage_then_the_builder_accepts_the_scan(corpus, tmp_path):
    aer = next(p for p in (corpus / "aer").rglob("*.aer.jsonl")).relative_to(corpus).as_posix()
    fake = FakeGitleaks([(aer, "generic-api-key", 7)])
    untriaged = release_scan.scan(corpus, gitleaks="/g", run=fake, needles={})
    scan_path_for(corpus).write_text(json.dumps(untriaged))
    with pytest.raises(Exception) as exc:
        rs.build([corpus], tmp_path / "refused", scan=None)
    assert getattr(exc.value, "code", "") == "release.refused.scan_untriaged"
    emails = [f["fingerprint"] for f in untriaged["findings"] if f["rule"] == "email-address"]
    text = (f'root_digest = "{root_digest(corpus)}"\n[[triage]]\nfingerprint = "{aer}:generic-api-key:7"\n'
            'triage = "synthetic-benchmark"\nreason = "benchmark text"\n' + "".join(
                f'[[triage]]\nfingerprint = "{fp}"\ntriage = "synthetic-benchmark"\nreason = "benchmark persona"\n'
                for fp in emails)).encode()
    triage = release_scan.load_triage(text)
    triaged = release_scan.scan(corpus, gitleaks="/g", triage=triage, run=FakeGitleaks(fake.findings), needles={})
    assert triaged["triage"] == {"root_digest": root_digest(corpus), "sha256": hashlib.sha256(text).hexdigest()}
    scan_path_for(corpus).write_text(json.dumps(triaged))
    report = rs.build([corpus], tmp_path / "ok", scan=None)
    assert report.corpora[0]["release_scan"]["by_triage"] == {"synthetic-benchmark": 1 + len(emails)}


def test_a_relative_corpus_path_gives_corpus_relative_findings(corpus, monkeypatch):
    """gitleaks reports ``File`` as the path it was given plus the path inside it, so a relative corpus argument
    (``release_scan.py mini-mit``) once gave labels ``mini-mit/aer/...`` that the key-cut check could not open and the
    native de-duplication missed (ultra seal-release #3). The corpus root is resolved before gitleaks runs."""
    aer = next(p for p in (corpus / "aer").rglob("*.aer.jsonl")).relative_to(corpus).as_posix()
    monkeypatch.chdir(corpus.parent)
    fake = FakeGitleaks([(aer, "generic-api-key", 7)])
    doc = release_scan.scan(Path(corpus.name), gitleaks="/g", run=fake, needles={})
    assert [f["fingerprint"] for f in without_emails(doc)] == [f"{aer}:generic-api-key:7"]
    assert Path(fake.calls[1][0][-1]).is_absolute()
    monkeypatch.chdir(corpus)
    doc = release_scan.scan(Path("."), gitleaks="/g", run=FakeGitleaks([(aer, "generic-api-key", 7)]), needles={})
    assert [f["fingerprint"] for f in without_emails(doc)] == [f"{aer}:generic-api-key:7"]


def _fake_gitleaks_executable(where: Path) -> Path:
    """A stand-in gitleaks binary for :func:`release_scan.main`: ``version`` prints the pin; ``dir`` writes an empty
    report."""
    executable = where / "gitleaks"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n"
                          'if [ "$1" = version ]; then echo 8.30.1; exit 0; fi\n'
                          'while [ $# -gt 0 ]; do\n'
                          '  if [ "$1" = --report-path ]; then shift; printf "[]" > "$1"; fi\n'
                          "  shift\n"
                          "done\n")
    executable.chmod(0o755)
    return executable


@pytest.mark.parametrize("form", ["relative", "dot", "symlink"])
def test_the_default_output_is_where_the_builder_looks(corpus, tmp_path, monkeypatch, form):
    """The default ``--out`` is ``scan_path_for`` of the resolved corpus root, as the deposit builder computes it
    (``scan_path_for(reader.root)``, a realpath): a relative path, ``.`` and a symlink to the sealed directory all write
    ``<sealed dir>.release-scan.json`` (ultra seal-release #5)."""
    executable = _fake_gitleaks_executable(tmp_path / "bin")
    if form == "relative":
        monkeypatch.chdir(corpus.parent)
        argument = corpus.name
    elif form == "dot":
        monkeypatch.chdir(corpus)
        argument = "."
    else:
        link = tmp_path / "link"
        link.symlink_to(corpus, target_is_directory=True)
        argument = str(link)
    code = release_scan.main([argument, "--gitleaks", str(executable)])
    assert code in (0, 1)
    written = scan_path_for(corpus)
    assert written.is_file() and json.loads(written.read_text())["target"]["root_digest"] == root_digest(corpus)
    assert not (tmp_path / "link.release-scan.json").exists()


def test_a_finding_outside_the_tree_is_an_error(corpus):
    with pytest.raises(release_scan.ScanError):
        release_scan.parse_gitleaks_report(json.dumps([{"File": "/etc/hosts", "RuleID": "r", "StartLine": 1}]).encode(),
                                           corpus)


def test_home_path_and_host_name_hits_are_found_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(release_scan, "_CHUNK", 8)
    (tmp_path / "a.txt").write_bytes(b"line one\nline two /home/someone/x\nthird\n...example-host...\n")
    (tmp_path / "b.txt").write_bytes(b"nothing here\n")
    needles = release_scan.personal_needles(home="/home/someone", host="example-host.local")
    found = release_scan.path_scan(tmp_path, needles)
    assert [(f.path, f.rule, f.line) for f in found] == [("a.txt", "home-path", 2), ("a.txt", "host-name", 4)]
    assert release_scan.personal_needles(home="/", host="lo")["host-name"] == []


# ------------------------------------------------------------------------------------------------ account paths (D-457)
#: A synthetic third-party account name (made up here; it names nobody).
_NAME = "zq-synthetic.7"
_ACCOUNT_FORMS = {
    "macos": "/Users/{}/projects/run_manifest.json",
    "linux": "/home/{}/work/task.py",
    "windows": "C:\\Users\\{}\\AppData\\x.json",
    "windows_json": "C:\\\\Users\\\\{}\\\\AppData\\\\x.json",
    "windows_slash": "C:/Users/{}/Desktop/x.json",
    "windows_lower_drive": "c:\\users\\{}\\x.json",
    "windows_other_drive": "D:\\USERS\\{}\\x.json",
    "wsl": "/mnt/c/Users/{}/x.json",
    "file_url": "file:///Users/{}/x.json",
    "macos_escaped_slash": "\\/Users\\/{}\\/x.json",
    "linux_escaped_slash": "\\/home\\/{}\\/x.json",
}


def _accounts(root: Path, **kwargs) -> list[tuple[str, str, int]]:
    return [(f.path, f.rule, f.line) for f in release_scan.path_scan(root, {}, decode=False, **kwargs)]


@pytest.mark.parametrize("form", sorted(_ACCOUNT_FORMS))
def test_each_account_path_form_is_a_finding(tmp_path, form):
    text = '{"a": 1}\n{"cwd": "' + _ACCOUNT_FORMS[form].format(_NAME) + '"}\n'
    (tmp_path / "run_manifest.json").write_text(text)
    assert _accounts(tmp_path) == [("run_manifest.json", "account-path", 2)]
    assert _accounts(tmp_path, accounts=False) == []


_GENERIC = ["user", "users", "ubuntu", "runner", "runneradmin", "root", "shared", "guest", "vscode", "codespace",
            "jovyan", "ec2-user", "admin", "administrator", "default", "public", "travis", "circleci", "appveyor",
            "vagrant", "docker", "app", "node", "nobody", "username", "you", "me", "name", "example"]


def test_generic_account_names_and_placeholders_are_not_reported(tmp_path):
    lines = []
    for name in _GENERIC:
        for form in ("/Users/{}/x", "/home/{}/x", "C:\\Users\\{}\\x", "c:/users/{}/x"):
            lines.extend((form.format(name), form.format(name.upper()), form.format(name.title())))
    lines += ["/home/<user>/x", "/home/$USER/x", "C:\\Users\\%USERNAME%\\x", "/home/${USER}/x", "/home/../x", "/Users/./x"]
    (tmp_path / "generic.txt").write_text("\n".join(lines) + "\n")
    assert _accounts(tmp_path) == []
    assert {"<user>", "$user", "%username%"} <= release_scan.ACCOUNT_ALLOWLIST


def test_a_d604_redaction_label_is_not_an_account(tmp_path):
    """The family redactions put ``acct-<12 hex>`` where an account was (D-604): a redacted AER names nobody, so it gives
    no ``account-path`` finding; a name of another shape in the same place still does."""
    label = "acct-" + "0123456789ab"
    lines = [form.format(label) for form in ("/home/{}/x", "/Users/{}/x", "C:\\Users\\{}\\x", "\\/home\\/{}\\/x")]
    lines += ["/home/acct-0123456789ABCDEF/x", "/home/acct-01234/x"]  # upper-case hex or the wrong length: not a label
    (tmp_path / "aer.jsonl").write_text("\n".join(lines) + "\n")
    assert _accounts(tmp_path) == [("aer.jsonl", "account-path", 5), ("aer.jsonl", "account-path", 6)]


def test_the_controlarena_account_label_is_not_an_account(tmp_path):
    """Pre-round review #21: controlarena-persistent redacts ``/Users/<name>`` to ``/Users/account-<12 hex>`` (D-604, the
    same salted ``{span12}``); it names nobody either. Only that exact shape is exempt: other ``account-`` names, upper
    hex, another length or a prefix glued on are still findings (lines 3 to 6)."""
    lines = ["/Users/account-0123456789ab/x", "\\/Users\\/account-0123456789ab\\/x",
             "/Users/account-0123456789AB/x", "/Users/account-0123456789abc/x", "/Users/myaccount-0123456789ab/x",
             "/home/account-name/x"]
    (tmp_path / "aer.jsonl").write_text("\n".join(lines) + "\n")
    assert _accounts(tmp_path) == [("aer.jsonl", "account-path", n) for n in (3, 4, 5, 6)]


def test_the_operator_home_path_is_reported_as_home_path_only(tmp_path):
    needles = release_scan.personal_needles(home="/Users/" + _NAME, host="example-host.local")
    (tmp_path / "a.json").write_text('{"x": "/Users/' + _NAME + '/repo/a.py"}\n{"y": "/home/zq-other/b"}\n')
    found = [(f.path, f.rule, f.line) for f in release_scan.path_scan(tmp_path, needles, decode=False)]
    assert found == [("a.json", "account-path", 2), ("a.json", "home-path", 1)]


def test_account_paths_start_an_absolute_path(tmp_path):
    """``/Users/`` and ``/home/`` must not follow a path-name byte, so a URL path or a deeper path is not an account;
    lines 1 to 5 are not account paths, lines 6 and 7 are."""
    lines = [
        "https://example.com/home/page/index.html",
        "https://example.com/Users/" + _NAME + "/profile",
        "see docs/home/" + _NAME + "/x and /var/home/" + _NAME + "/y",
        "/home/" + _NAME + "+x",  # neither a separator nor an ending after the name
        "xC:\\Users\\" + _NAME + "\\a",
        '"/home/' + _NAME + '/a"',
        "HOME=/home/" + _NAME + "/",
    ]
    (tmp_path / "t.txt").write_text("\n".join(lines) + "\n")
    assert _accounts(tmp_path) == [("t.txt", "account-path", 6), ("t.txt", "account-path", 7)]


def test_a_bare_home_ended_by_a_quote_a_delimiter_or_the_end_of_the_file_is_a_finding(tmp_path, monkeypatch):
    monkeypatch.setattr(release_scan, "_CHUNK", 8)
    (tmp_path / "a.json").write_text('{"x": 1}\n{"HOME": "/Users/' + _NAME + '"}\n')
    (tmp_path / "b.env").write_text("X=1\nHOME=/home/" + _NAME)  # at the end of the file, no line end
    (tmp_path / "c.txt").write_text('C:\\Users\\' + _NAME + '"\n')
    endings = ["'", " x", "\tx", ",", ":", ";", ")", "]", "}", "\x00", "\\n"]  # the last: a JSON escape after the name
    (tmp_path / "d.txt").write_text("\n".join("/home/" + _NAME + end for end in endings) + "\n")
    generic = ["/home/user", '"/Users/Shared"', "/home/runner.", "/home/..", "/home/" + _NAME + "+x"]
    (tmp_path / "e.txt").write_text("\n".join(generic) + "\n")
    assert _accounts(tmp_path) == [("a.json", "account-path", 2), ("b.env", "account-path", 2),
                                   ("c.txt", "account-path", 1),
                                   *(("d.txt", "account-path", n) for n in range(1, len(endings) + 1))]


def test_the_operator_bare_home_stays_home_path_only(tmp_path):
    """The bare ``/Users/<name>`` of the operator is ``home-path`` only; its ``\\/``-escaped form, which ``home-path``
    does not see, is an ``account-path`` finding."""
    needles = release_scan.personal_needles(home="/Users/" + _NAME, host="example-host.local")
    (tmp_path / "a.json").write_text('{"HOME": "/Users/' + _NAME + '"}\n{"cwd": "\\/Users\\/' + _NAME + '"}\n'
                                     "HOME=/home/zq-other")
    found = [(f.path, f.rule, f.line) for f in release_scan.path_scan(tmp_path, needles, decode=False)]
    assert found == [("a.json", "account-path", 2), ("a.json", "account-path", 3), ("a.json", "home-path", 1)]


def test_escaped_slash_paths_start_an_absolute_path(tmp_path):
    """The ``\\/`` forms keep the boundary: the escaped slash may not follow a path-name byte."""
    lines = [
        "https:\\/\\/example.com\\/home\\/page\\/index.html",
        "docs\\/home\\/" + _NAME + "\\/x",
        '"\\/home\\/' + _NAME + '"',
        "file:\\/\\/\\/Users\\/" + _NAME + "\\/a",
    ]
    (tmp_path / "t.json").write_text("\n".join(lines) + "\n")
    assert _accounts(tmp_path) == [("t.json", "account-path", 3), ("t.json", "account-path", 4)]


def test_an_account_path_in_a_binary_file_is_found_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(release_scan, "_CHUNK", 8)
    data = (b"\x00\xff\xfe binary\n" + b"\x01" * 300 + b"\n\x89PNG C:\\\\Users\\\\" + _NAME.encode() + b"\\\\x\x00\n"
            + b"y" * 50 + b" /home/" + _NAME.encode() + b"/z\n")
    (tmp_path / "blob.bin").write_bytes(data)
    (tmp_path / "start.bin").write_bytes(b"/Users/" + _NAME.encode() + b"/a")  # at offset 0, no line end
    assert _accounts(tmp_path) == [("blob.bin", "account-path", 3), ("blob.bin", "account-path", 4),
                                   ("start.bin", "account-path", 1)]


def test_account_path_findings_record_neither_the_name_nor_the_match(corpus):
    aux = corpus / "raw" / "context-probe.bin"
    aux.write_bytes(b"\x00\x01" + ("C:\\Users\\" + _NAME + "\\run_manifest.json").encode() + b"\n")
    try:
        doc = release_scan.scan(corpus, gitleaks="/g", run=FakeGitleaks([]), needles={})
    finally:
        aux.unlink()
    assert without_emails(doc) == [{"basis": None, "detector": "agentprov-path-scan",
                                    "fingerprint": "raw/context-probe.bin:account-path:1", "line": 1,
                                    "path": "raw/context-probe.bin", "reason": None, "rule": "account-path",
                                    "triage": None}]  # fmt: skip
    text = json.dumps(doc)
    assert _NAME not in text and _NAME.lower() not in text and "Users\\\\" not in text
    assert doc["tools"][1]["version"] == "6"


# ------------------------------------------------------------------------------------------------ secret shapes (D-600)
def _secrets(root: Path, **kwargs) -> list[tuple[str, str, int]]:
    return [(f.path, f.rule, f.line) for f in release_scan.path_scan(root, {}, accounts=False, decode=False, **kwargs)]


@pytest.mark.parametrize("index", range(len(rs.secret_shapes())))
def test_each_secret_shape_in_a_plain_file_is_a_finding(tmp_path, index):
    rule, value = rs.secret_shapes()[index]
    (tmp_path / "run.json").write_text('{"a": 1}\n{"env": {"TOKEN": "' + value + '"}}\n')
    assert _secrets(tmp_path) == [("run.json", rule, 2)]
    assert _secrets(tmp_path, secrets=False) == []
    assert rule in release_scan.SECRET_RULES


def test_the_native_rule_ids_are_gitleaks_ids_or_named_langfuse():
    """The ids are gitleaks 8.30.1's own for the GitHub and Hugging Face shapes (so a policy's ``scan_rules`` names one
    rule for both detectors); Langfuse has no gitleaks rule."""
    assert release_scan.SECRET_RULES == {"github-pat", "github-oauth", "github-app-token", "github-refresh-token",
                                         "github-fine-grained-pat", "huggingface-access-token", "langfuse-secret-key",
                                         "langfuse-public-key"}  # fmt: skip


def test_secret_shapes_are_found_across_chunks_at_the_start_and_at_the_end_of_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(release_scan, "_CHUNK", 8)
    shapes = rs.secret_shapes(1)
    body = "\n".join(f"x={value};" for _rule, value in shapes) + "\n"
    (tmp_path / "a.env").write_text(body)
    (tmp_path / "b.txt").write_text(shapes[0][1])  # at offset 0 and at the end of the file, no line end
    (tmp_path / "c.txt").write_text("y\n" + shapes[6][1])  # at the end of the file
    assert sorted(_secrets(tmp_path)) == sorted([*(("a.env", rule, n) for n, (rule, _v) in enumerate(shapes, 1)),
                                                 ("b.txt", shapes[0][0], 1), ("c.txt", shapes[6][0], 2)])  # fmt: skip


def _near_misses() -> list[str]:
    """Strings that hold a secret prefix but no secret shape: wrong lengths, a non-UUID ``sk-lf-``/``pk-lf-``, and a
    shape inside a longer token (a letter, digit or ``_`` before it, a body character after it)."""
    shapes = dict(rs.secret_shapes(2)[::-1])  # one value per rule
    pat, hf, lf = shapes["github-pat"], shapes["huggingface-access-token"], shapes["langfuse-secret-key"]
    fine = shapes["github-fine-grained-pat"]
    uuid = lf[len("sk-lf-"):]
    return [
        pat[:-1], pat + "Z", pat + "7", "a" + pat, "9" + pat, "_" + pat, pat[:4] + pat[5:],
        fine[:-1], fine + "_", "x" + fine,
        hf[:-1], hf + "q", "z" + hf, "_" + hf, hf[:3] + hf[3:20] + "-" + hf[21:],
        "sk" + "-lf-" + uuid[:-1], lf + "a", lf + "0", "x" + lf, "sk" + "-lf-" + uuid.replace("-", ""),
        "sk" + "-lf-" + "g" + uuid[1:], "sk" + "-lf-" + uuid[:8] + "-" + uuid[9:13] + uuid[14:],
        "pk" + "-lf-" + uuid[:-2], "pk" + "-lf-" + uuid + "f", "ask" + "-lf-" + uuid,
    ]


@pytest.mark.parametrize("chunk", [1 << 20, 7])
def test_near_misses_are_not_findings(tmp_path, monkeypatch, chunk):
    monkeypatch.setattr(release_scan, "_CHUNK", chunk)
    (tmp_path / "near.txt").write_text("\n".join(f'"{miss}"' for miss in _near_misses()) + "\n")
    assert _secrets(tmp_path) == []


@pytest.mark.parametrize("index", range(len(rs.secret_shapes())))
def test_a_longer_token_cut_at_a_chunk_boundary_is_not_a_finding(tmp_path, monkeypatch, index):
    """A window that ends right after a shape has not seen the byte after it: the look-ahead is judged in the next
    window, so a longer token cut there is not reported."""
    rule, value = rs.secret_shapes(3)[index]
    data = ("k=" + value).encode()
    monkeypatch.setattr(release_scan, "_CHUNK", len(data))
    (tmp_path / "long.txt").write_bytes(data + b"Q9_more\n")
    assert _secrets(tmp_path) == []  # "Q" continues the body of every shape
    (tmp_path / "long.txt").write_bytes(data + b";\n")
    assert _secrets(tmp_path) == [("long.txt", rule, 1)]


def test_secret_findings_record_no_value(corpus):
    shapes = rs.secret_shapes(4)
    probe = corpus / "raw" / "secret-probe.txt"
    probe.write_text("\n".join(f'"{value}"' for _rule, value in shapes) + "\n")
    try:
        doc = release_scan.scan(corpus, gitleaks="/g", run=FakeGitleaks([]), needles={})
    finally:
        probe.unlink()
    assert sorted((f["rule"], f["line"]) for f in without_emails(doc)) == sorted(
        (rule, n) for n, (rule, _v) in enumerate(shapes, 1))  # fmt: skip
    assert all(f["triage"] is None and f["detector"] == "agentprov-path-scan" for f in without_emails(doc))
    text = json.dumps(doc)
    for _rule, value in shapes:
        tail = value[-24:]  # past every prefix (the longest, github_pat_, has 11 characters)
        assert all(tail[i:i + 8] not in text for i in range(len(tail) - 7))


def test_a_native_finding_gitleaks_also_reported_is_dropped():
    gl = [release_scan.Finding("a.json", "github-pat", 2, "gitleaks")]
    native = [release_scan.Finding("a.json", "github-pat", 2, "agentprov-path-scan"),
              release_scan.Finding("a.json", "github-pat", 3, "agentprov-path-scan"),
              release_scan.Finding("z.zip#0", "github-pat", 2, "agentprov-path-scan")]
    assert release_scan.native_findings(gl, native) == native[1:]


@needs_pinned_gitleaks
def test_a_secret_shape_gitleaks_finds_is_reported_once(corpus):
    """A ``github-pat`` and a ``huggingface-access-token`` in a stored file are found by gitleaks and by the native
    rules under the same fingerprint; the scan document holds each once, as gitleaks'. A ``langfuse-secret-key``, which
    gitleaks has no rule for, is the native scan's."""
    import io
    import zipfile

    shapes = dict(rs.secret_shapes(5)[::-1])
    probe = corpus / "raw" / "secret-probe.txt"
    probe.write_text('{"a": 1}\n{"t": "' + shapes["github-pat"] + '"}\n{"h": "' + shapes["huggingface-access-token"]
                     + '"}\n{"l": "' + shapes["langfuse-secret-key"] + '"}\n')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a.json", b"{}\n")
        z.writestr("b.json", ('{"t": "' + shapes["github-pat"] + '"}\n') * 4)
    member = corpus / "raw" / "secret-probe.zip"
    member.write_bytes(buf.getvalue())
    executable = shutil.which("gitleaks")
    assert executable is not None
    try:
        doc = release_scan.scan(corpus, gitleaks=executable, needles={}, timeout=300)
    finally:
        probe.unlink()
        member.unlink()
    rows = [(f["path"], f["rule"], f["line"], f["detector"]) for f in doc["findings"]
            if f["path"].startswith("raw/secret-probe")]  # fmt: skip
    assert sorted(rows) == [("raw/secret-probe.txt", "github-pat", 2, "gitleaks"),
                            ("raw/secret-probe.txt", "huggingface-access-token", 3, "gitleaks"),
                            ("raw/secret-probe.txt", "langfuse-secret-key", 4, "agentprov-path-scan"),
                            *(("raw/secret-probe.zip#1", "github-pat", n, "agentprov-path-scan") for n in range(1, 5))]
    assert len({f["fingerprint"] for f in doc["findings"]}) == len(doc["findings"])


_BOUND = b'root_digest = "sha256:' + b"a" * 64 + b'"\n'


@pytest.mark.parametrize("bad", [
    _BOUND + b'[[triage]]\nfingerprint = "x"\ntriage = "maybe"\nreason = "r"\n',
    _BOUND + b'[[triage]]\nfingerprint = "x"\ntriage = "real"\nreason = ""\n',
    _BOUND + b'[[triage]]\nfingerprint = "x"\ntriage = "real"\nreason = "r"\n[[triage]]\nfingerprint = "x"\ntriage = "real"\nreason = "r"\n',
    _BOUND + b'other = 1\n',
    b'[[triage]]\nfingerprint = "x"\ntriage = "real"\nreason = "r"\n',  # bound to no sealed root digest (D-42)
    b'root_digest = "sha256:abc"\n',
    b'root_digest = "SHA256:' + b"A" * 64 + b'"\n',
    b'root_digest = 1\n',
    _BOUND + b'[[triage]]\nfingerprint = "aer/00/x.aer.jsonl:account-path:3"\ntriage = "pinned-account"\nreason = "r"\n',
    _BOUND + b'[[triage]]\nfingerprint = "raw/objects/ab/x.json:github-pat:3"\ntriage = "pinned-account"\nreason = "r"\n',
])  # fmt: skip
def test_bad_triage_files_are_refused(bad):
    with pytest.raises(ValueError):
        release_scan.load_triage(bad)


@pytest.mark.parametrize("fingerprint", [b"12", b'["raw/x:account-path:1"]', b"true", b"{ a = 1 }"])
@pytest.mark.parametrize("triage", ["pinned-account", "false-positive"])
def test_a_fingerprint_that_is_not_a_string_is_a_usage_error(tmp_path, capsys, corpus, fingerprint, triage):
    """A non-string fingerprint is a ``ValueError`` (exit 2), also for ``pinned-account``, whose raw/ check once called a
    string method on it first and raised ``AttributeError`` (exit 1, a traceback; ultra seal-release #7)."""
    data = _BOUND + b"[[triage]]\nfingerprint = " + fingerprint + b'\ntriage = "' + triage.encode() + b'"\nreason = "r"\n'
    with pytest.raises(ValueError, match="fingerprint is a string"):
        release_scan.load_triage(data)
    path = tmp_path / "triage.toml"
    path.write_bytes(data)
    assert release_scan.main([str(corpus), "--triage", str(path), "--gitleaks", "/g"]) == 2
    assert "fingerprint is a string" in capsys.readouterr().err


def test_a_triage_file_for_another_root_digest_is_refused(corpus, tmp_path, capsys):
    """D-42: triage is per fingerprint *and* per sealed root digest. A file reviewed for one sealed version must not
    triage a finding at the same path, rule and line in another version's bytes (CB-17)."""
    aer = next(p for p in (corpus / "aer").rglob("*.aer.jsonl")).relative_to(corpus).as_posix()
    stale = (f'root_digest = "sha256:{"1" * 64}"\n[[triage]]\nfingerprint = "{aer}:generic-api-key:7"\n'
             'triage = "false-positive"\nreason = "reviewed for an earlier version"\n')
    triage = release_scan.load_triage(stale.encode())
    fake = FakeGitleaks([(aer, "generic-api-key", 7)])
    with pytest.raises(ValueError, match="root digest"):
        release_scan.scan(corpus, gitleaks="/g", triage=triage, run=fake, needles={})
    assert fake.calls == []  # refused before gitleaks runs
    path = tmp_path / "triage.toml"
    path.write_text(stale)
    out = tmp_path / "scan.json"
    assert release_scan.main([str(corpus), "--triage", str(path), "--gitleaks", "/g", "--out", str(out)]) == 2
    assert not out.exists()
    assert root_digest(corpus) in capsys.readouterr().err


@pytest.mark.parametrize("step", ["version", "dir"])
def test_a_gitleaks_timeout_is_a_scan_error(corpus, step):
    """A timeout (or another subprocess failure) of ``gitleaks version`` or ``gitleaks dir`` is "gitleaks failed"
    (``ScanError``, exit 3), never a traceback with exit 1, which means "a finding is untriaged" (ultra seal-release #6)."""
    fake = FakeGitleaks([])

    def run(argv, env, timeout):
        if argv[1] == step:
            raise subprocess.TimeoutExpired(list(argv), timeout or 60)
        return fake(argv, env, timeout)

    with pytest.raises(release_scan.ScanError, match="gitleaks"):
        release_scan.scan(corpus, gitleaks="/g", run=run, needles={})


def test_main_exits_3_when_gitleaks_times_out(corpus, tmp_path, capsys):
    executable = tmp_path / "bin" / "gitleaks"
    executable.parent.mkdir()
    executable.write_text('#!/bin/sh\nif [ "$1" = version ]; then echo 8.30.1; exit 0; fi\nexec sleep 30\n')
    executable.chmod(0o755)
    out = tmp_path / "scan.json"
    assert release_scan.main([str(corpus), "--gitleaks", str(executable), "--timeout", "0.5", "--out", str(out)]) == 3
    assert not out.exists()
    assert "timed out" in capsys.readouterr().err


@pytest.mark.parametrize("version", [b"8.18.4\n", b"v8.30.0\n", b"9.0.0\n"])
def test_an_unpinned_gitleaks_is_refused_before_it_scans(corpus, tmp_path, capsys, version):
    """G.9.4: gitleaks 8.30.1 is the pinned scanner; another version (other default rules) is refused, exit 3, before
    ``gitleaks dir`` runs and before a document is written (ultra seal-release #2)."""
    fake = FakeGitleaks([], version=version)
    with pytest.raises(release_scan.ScanError, match="8.30.1"):
        release_scan.scan(corpus, gitleaks="/g", run=fake, needles={})
    assert [argv[1] for argv, _env in fake.calls] == ["version"]
    executable = tmp_path / "bin" / "gitleaks"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nprintf '%s' '" + version.decode() + "'\n")
    executable.chmod(0o755)
    out = tmp_path / "scan.json"
    assert release_scan.main([str(corpus), "--gitleaks", str(executable), "--out", str(out)]) == 3
    assert not out.exists()
    assert "pinned" in capsys.readouterr().err


def test_the_scan_document_names_the_pinned_scanners(corpus):
    """The tool records exactly what the deposit builder's check requires (one copy of the pins)."""
    from agentprov.release.metadata import GITLEAKS_CONFIG_SHA256, GITLEAKS_VERSION, PATH_SCAN_VERSION

    doc = release_scan.scan(corpus, gitleaks="/g", run=FakeGitleaks([]), needles={})
    assert [(t["name"], t["version"]) for t in doc["tools"]] == [("gitleaks", GITLEAKS_VERSION),
                                                                  ("agentprov-path-scan", PATH_SCAN_VERSION)]
    assert doc["tools"][0]["config_sha256"] == GITLEAKS_CONFIG_SHA256 == release_scan.GITLEAKS_CONFIG_SHA256
    assert hashlib.sha256(release_scan._GITLEAKS_CONFIG.encode("ascii")).hexdigest() == GITLEAKS_CONFIG_SHA256


@needs_pinned_gitleaks
def test_the_real_gitleaks_runs_on_a_clean_tree(tmp_path):
    (tmp_path / "plain.txt").write_text("no secret here\n")
    executable = shutil.which("gitleaks")
    assert executable is not None
    assert release_scan.run_gitleaks(executable, tmp_path, timeout=120) == ([], 0)
    assert release_scan.gitleaks_version(executable).count(".") == 2


def _keyed(field: str, value: str) -> str:
    return '"' + field + '":"' + value + '"'


@needs_pinned_gitleaks
def test_the_key_allowlist_hides_only_agentprov_keys(tmp_path):
    """The committed allowlist (user-approved) silences AgentPROV's content-addressed keys and nothing else: a secret on
    the same JSONL line, an off-shape value under an allowlisted name, and a token are still found. The secret-shaped
    strings are built at run time, so the repository's own gitleaks hook never sees them."""
    key = "".join(("sqiqihpu", "663jlihl", "zircr3rd", "oc"))
    secret = "".join(("Zq8vT3xR", "9mK2pL7w", "N4sB6yH1", "cJ5dF0gE"))
    token = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    lines = [
        "{" + _keyed("apv:derivationKey", key) + "}",
        "{" + _keyed("subject_key", "ex_" + key) + "}",
        "{" + _keyed("logical_key", "lk_" + key) + "," + _keyed("api_key", secret) + "}",
        "{" + _keyed("logical_key", secret) + "}",
        "{" + _keyed("apv:derivationKey", key) + "," + _keyed("token", token) + "}",
    ]
    (tmp_path / "rows.jsonl").write_text("\n".join(lines) + "\n")
    executable = shutil.which("gitleaks")
    assert executable is not None
    found = {(f.line, f.rule) for f in release_scan.run_gitleaks(executable, tmp_path, timeout=120)[0]}
    assert {line for line, _ in found} == {3, 4, 5}
    assert (5, "github-pat") in found


def test_the_scan_records_the_config_digest():
    assert release_scan._KEY_ALLOWLIST in release_scan._GITLEAKS_CONFIG
    assert len(release_scan.GITLEAKS_CONFIG_SHA256) == 64


@pytest.mark.parametrize(("match", "hidden"), [
    ("full", True), ("subject", True), ("logical", True),
    ("field_cut", False), ("quote_cut", False), ("value_cut", False), ("subject_no_prefix", False),
    ("logical_wrong_prefix", False), ("other_full_name", False), ("project_key", False), ("api_key", False),
    ("bare_key", False), ("upper", False), ("trailing", False), ("short_value", False),
])
def test_the_allowlist_hides_uncut_members_of_the_three_fields_only(match, hidden):
    """D-310: the allowlist hides an uncut ``<field>":"<key>"`` with the field's own prefix; a match cut at a fragment
    boundary is left to the key-cut check, because a cut field suffix (``ionKey``, ``ct_key``) also ends other names."""
    import re

    key = "".join(("sqiqihpu", "663jlihl", "zircr3rd", "oc"))
    q = '":"'
    cases = {
        "full": "derivationKey" + q + key + '"', "field_cut": "ivationKey" + q + key + '"',
        "quote_cut": "derivationKey" + q + key, "value_cut": "derivationKey" + q + key[:18],
        "subject": "subject_key" + q + "ex_" + key + '"', "logical": "logical_key" + q + "lk_" + key + '"',
        "subject_no_prefix": "subject_key" + q + key + '"', "logical_wrong_prefix": "logical_key" + q + "ex_" + key + '"',
        "other_full_name": "activationKey" + q + key + '"', "project_key": "project_key" + q + "ex_" + key + '"',
        "api_key": "api_key" + q + key + '"', "bare_key": "Key" + q + key + '"', "upper": "derivationKey" + q + key.upper(),
        "trailing": "derivationKey" + q + key + '","x":1', "short_value": "derivationKey" + q + key[:8],
    }
    assert bool(re.search(release_scan._KEY_ALLOWLIST, cases[match])) is hidden


# ------------------------------------------------------------------------------------------------ key cuts (D-310)
_B32 = "abcdefghijklmnopqrstuvwxyz234567"


def _keys(seed: int, n: int, prefix: str = "") -> list[str]:
    """Key-shaped values, made at run time (the repository's own gitleaks hook never sees them)."""
    rnd = random.Random(seed)
    return [prefix + "".join(rnd.choice(_B32) for _ in range(26)) for _ in range(n)]


def _entropy(text: str) -> float:
    counts = collections.Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def _redacted(line: str, start: int, end: int, value: tuple[int, int], *, column: int = 1) -> dict:
    """The report entry gitleaks writes for the match ``line[start:end]`` whose secret is ``line[value[0]:value[1]]``:
    redacted, with columns counted from a fragment start (``column``), as gitleaks does on a long line."""
    secret = line[value[0]:value[1]]
    match = line[start:value[0]] + "REDACTED" + line[value[1]:end]
    return {"RuleID": "generic-api-key", "StartLine": 1, "EndLine": 1, "StartColumn": column,
            "EndColumn": column + len(line[start:end].encode()) - 1, "Match": match, "Secret": "REDACTED",
            "Entropy": _entropy(secret)}


def _prov_line(keys: list[str], *extra: str) -> str:
    """A JCS-shaped PROV line: entities with an ``apv:derivationKey`` each, plus extra members."""
    entities = ",".join(f'"e{i}":{{"apv:derivationKey":"{k}","prov:type":["prov:Bundle"]}}' for i, k in enumerate(keys))
    return '{"entity":{' + entities + "}" + "".join("," + e for e in extra) + "}"


def _cut(line: str, member: str, *, field_chars: int | None = None, value_chars: int = 26,
         closing: bool = True) -> dict:
    """gitleaks' entry for a match over ``member`` (``"<field>":"<26 base32>"``) on ``line``, cut at the start to
    ``field_chars`` characters of the field name (default: uncut, after ``apv:``, where gitleaks' match starts) and at
    the end to ``value_chars`` characters of the value (the closing quote only with all 26)."""
    at = line.index(member)
    field = member[1:member.index('":"')].split(":")[-1]
    value = at + len(member) - 27  # the value starts 26 characters and a quote before the member's end
    begin = value - 3 - (len(field) if field_chars is None else field_chars)
    end = value + value_chars + (1 if closing and value_chars == 26 else 0)
    return _redacted(line, begin, end, (value, value + value_chars))


_MEMBER = '"apv:derivationKey":"{}"'


@pytest.mark.parametrize(("field_chars", "value_chars", "closing"), [
    (None, 26, True), (13, 26, False), (10, 26, True), (6, 26, True), (5, 26, True), (4, 26, True), (3, 26, True),
    (None, 20, False), (None, 16, False), (None, 12, False), (5, 12, False),
])  # fmt: skip
def test_a_cut_derivation_key_is_resolved_at_any_offset(field_chars, value_chars, closing):
    keys = _keys(1, 40)
    line = _prov_line(keys, '"text":"plain words"')
    item = _cut(line, _MEMBER.format(keys[17]), field_chars=field_chars, value_chars=value_chars, closing=closing)
    assert release_scan.key_cut_explained(line.encode(), item)


@pytest.mark.parametrize(("field", "prefix", "chars"), [("subject_key", "ex_", 3), ("subject_key", "ex_", 6),
                                                         ("logical_key", "lk_", 6), ("logical_key", "lk_", 11)])
def test_cut_register_and_index_keys_are_resolved(field, prefix, chars):
    keys = _keys(2, 5, prefix)
    line = "{" + ",".join(f'"code":"c{i}","{field}":"{k}"' for i, k in enumerate(keys)) + "}"
    member = f'"{field}":"{keys[3]}"'
    at = line.index(member)
    begin = at + 1 + len(field) - chars
    value = (at + len(field) + 4, at + len(member) - 1)
    assert release_scan.key_cut_explained(line.encode(), _redacted(line, begin, at + len(member), value))


def test_a_real_looking_key_in_another_field_is_still_reported():
    """An ``apiKey`` with a 26-character lower-case base32 value, uncut or cut to ``Key":"`` (the cut a lower minimum
    would have hidden), stays a finding, also on a line full of AgentPROV keys."""
    keys = _keys(3, 30)
    secret = _keys(4, 1)[0]
    api = f'"apiKey":"{secret}"'
    line = _prov_line(keys, api)
    at = line.index(api)
    value = (at + 10, at + 10 + 26)
    uncut = _redacted(line, at + 1, at + len(api), value)
    cut = _redacted(line, at + 4, at + len(api), value)
    assert cut["Match"] == 'Key":"REDACTED"'
    assert not release_scan.key_cut_explained(line.encode(), uncut)
    assert not release_scan.key_cut_explained(line.encode(), cut)
    # the same cut of a derivation key is ambiguous on this line (the apiKey fits too), so it stays as well ...
    own = _cut(line, _MEMBER.format(keys[9]), field_chars=3)
    assert own["Match"] == 'Key":"REDACTED"'
    assert not release_scan.key_cut_explained(line.encode(), own)
    # ... and is resolved on a line without the apiKey
    clean = _prov_line(keys)
    assert release_scan.key_cut_explained(clean.encode(), _cut(clean, _MEMBER.format(keys[9]), field_chars=3))


@pytest.mark.parametrize("case", ["upper", "short", "subject_no_prefix", "escaped", "other_name", "unquoted_end"])
def test_off_shape_members_are_not_resolved(case):
    keys = _keys(5, 3)
    k = keys[1]
    members = {
        "upper": f'"apv:derivationKey":"{k.upper()}"', "short": f'"apv:derivationKey":"{k[:25]}"',
        "subject_no_prefix": f'"subject_key":"{k}"', "escaped": f'"note":"{{\\"apv:derivationKey\\":\\"{k}\\"}}"',
        "other_name": f'"xapv:derivationKey":"{k}"', "unquoted_end": f'"apv:derivationKey":"{k}1"',
    }
    line = '{"a":1,' + members[case] + ',"z":2}'
    at = line.index({"upper": k.upper(), "short": k[:25]}.get(case, k))
    value = (at, at + (25 if case == "short" else 26))
    begin = line.rindex("ey", 0, at) - 1  # the match starts at "Key" or "key"
    item = _redacted(line, begin, value[1], value)
    assert not release_scan.key_cut_explained(line.encode(), item)


@pytest.mark.parametrize("change", ["secret", "lines", "columns", "entropy", "two_redacted", "no_entropy", "length"])
def test_any_doubt_keeps_the_finding(change):
    keys = _keys(6, 10)
    line = _prov_line(keys)
    item = _cut(line, _MEMBER.format(keys[4]), field_chars=4)
    assert release_scan.key_cut_explained(line.encode(), item)
    if change == "secret":
        item["Secret"] = item["Match"][6:12]
    elif change == "lines":
        item["EndLine"] = 2
    elif change == "columns":
        del item["EndColumn"]
    elif change == "entropy":
        item["Entropy"] += 0.01
    elif change == "two_redacted":
        item["Match"] = "REDACTED" + item["Match"]
    elif change == "no_entropy":
        del item["Entropy"]
    else:
        item["EndColumn"] += 1
    assert not release_scan.key_cut_explained(line.encode(), item)


def test_the_report_post_pass_drops_resolved_cuts_and_writes_no_value(tmp_path, monkeypatch):
    monkeypatch.setattr(release_scan, "_CHUNK", 64)
    keys = _keys(7, 60)
    secret = _keys(8, 1)[0]
    clean = _prov_line(keys)
    mixed = _prov_line(keys, f'"apiKey":"{secret}"')
    (tmp_path / "prov").mkdir()
    (tmp_path / "prov" / "a.provjson").write_bytes(("{}\r\n" + clean + "\n" + mixed + "\n" + clean).encode())  # no final newline
    cut = _cut(clean, _MEMBER.format(keys[30]), field_chars=3)  # 'Key":"': the apiKey on line 3 fits it too
    entries = []
    for line_no in (2, 3, 4):
        entries.append(dict(cut, File=str(tmp_path / "prov" / "a.provjson"), StartLine=line_no, EndLine=line_no))
    entries.append({"File": "prov/a.provjson", "RuleID": "curl-auth-user", "StartLine": 2, "EndLine": 2})
    findings, resolved = release_scan.parse_gitleaks_report(json.dumps(entries).encode(), tmp_path)
    assert resolved == 2
    assert [(f.path, f.rule, f.line) for f in findings] == [("prov/a.provjson", "curl-auth-user", 2),
                                                            ("prov/a.provjson", "generic-api-key", 3)]
    assert not any(v in repr(findings) for v in [secret, *keys])
    monkeypatch.setattr(release_scan, "_MAX_LINE_BYTES", len(clean) - 1)  # a line too long to read is reported
    findings, resolved = release_scan.parse_gitleaks_report(json.dumps(entries[:1]).encode(), tmp_path)
    assert resolved == 0 and [f.line for f in findings] == [2]


@needs_pinned_gitleaks
def test_the_real_gitleaks_cuts_long_prov_lines_and_the_post_pass_resolves_them(tmp_path):
    """On lines longer than gitleaks' fragment (about 100 kB), keys are cut at fragment boundaries beyond the uncut-only
    allowlist; every cut is resolved, and real-looking ``apiKey`` values on another line stay findings."""

    def long_line(keys: list[str], every: int = 0, secrets: list[str] | None = None) -> str:
        members = []
        for i, k in enumerate(keys):
            members.append(f'"t{i}":"' + ("\u00e9" if i % 7 == 0 else "x") * (1 + i % 31) + '"')
            members.append(f'"apv:derivationKey":"{k}"')
            if every and secrets and i % every == 0:
                members.append(f'"apiKey":"{secrets[i // every]}"')
        return "{" + ",".join(members) + "}"

    executable = shutil.which("gitleaks")
    assert executable is not None
    clean = long_line(_keys(9, 8000))
    (tmp_path / "clean").mkdir()
    (tmp_path / "clean" / "a.provjson").write_bytes((clean + "\n" + clean + "\n").encode())
    findings, resolved = release_scan.run_gitleaks(executable, tmp_path / "clean", timeout=300)
    assert findings == [] and resolved >= 1
    mixed = long_line(_keys(11, 8000), every=100, secrets=_keys(10, 80))
    (tmp_path / "mixed").mkdir()
    (tmp_path / "mixed" / "b.provjson").write_bytes((mixed + "\n" + clean + "\n").encode())
    findings, _ = release_scan.run_gitleaks(executable, tmp_path / "mixed", timeout=300)
    assert {(f.line, f.rule) for f in findings} == {(1, "generic-api-key")}


def test_a_pinned_account_triage_of_a_raw_account_path_is_loaded():
    data = _BOUND + b'[[triage]]\nfingerprint = "raw/objects/ab/x.json:account-path:3"\ntriage = "pinned-account"\nreason = "D-186 (c)"\n'
    triage = release_scan.load_triage(data)
    assert triage.entries == {"raw/objects/ab/x.json:account-path:3": ("pinned-account", "D-186 (c)")}
