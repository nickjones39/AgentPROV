"""``agentprov_zenodo.draft`` (HL H.10.1(2); D-5, D-790, D-870, D-880): the draft-only Zenodo upload helper.

Every network test talks to a fake Zenodo on 127.0.0.1 (``zenodo_fake``); nothing here contacts zenodo.org or
sandbox.zenodo.org, not even with a fake token. The fake records any request outside the helper's allowlist, a publish
above all, and the ``server`` fixture fails the test on any. The token is a canary value that must never appear in any
output, receipt, URL or exception text.

Deposit drafts are built by the real builder from the sealed test corpus (``release_support``). The tool's release-mode
verify needs CPython 3.14.8 and root digests, which the interpreter of some development machines lacks, so the tests turn
it off through ``run(release_verify=False)``, a parameter no command-line option reaches (one test pins that).
"""

from __future__ import annotations

import ast
import dataclasses
import io
import json
import re
import shutil
import ssl
import sys
from pathlib import Path
from typing import Any

import agentprov_zenodo.draft as zd
import pytest
import release_support as rs
from zenodo_fake import FakeZenodo

_REPO = Path(__file__).resolve().parents[3]
_TOOL = Path(zd.__file__).resolve()
_SHIM = _REPO / "tools" / "zenodo_draft.py"

CANARY = "ZENODO-CANARY-TOKEN-9f3a6c1e7b24d85a0c91"
SANDBOX_PHRASE = "create unpublished draft on sandbox.zenodo.org"
AGENTDOJO_PROV_CONCEPT = "10.5281/zenodo.20692312"
OWN_CONCEPT = "10.5281/zenodo.99999990"


# ================================================================================================ fixtures
@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("zenodo-template")
    sealed = rs.sealed(tmp_path_factory, base / "corpora")
    out = base / "deposit"
    rs.build([sealed], out)
    return out


@pytest.fixture(scope="module")
def versioned_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("zenodo-template-v2")
    sealed = rs.sealed(tmp_path_factory, base / "corpora")
    out = base / "deposit"
    rs.build([sealed], out, metadata=dataclasses.replace(rs.METADATA, concept_doi=OWN_CONCEPT))
    return out


@pytest.fixture(scope="module")
def agentdojo_prov_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("zenodo-template-adprov")
    sealed = rs.sealed(tmp_path_factory, base / "corpora")
    out = base / "deposit"
    rs.build([sealed], out, metadata=dataclasses.replace(rs.METADATA, concept_doi=AGENTDOJO_PROV_CONCEPT))
    return out


@pytest.fixture
def agentdojo_prov(agentdojo_prov_template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "deposit"
    shutil.copytree(agentdojo_prov_template, dest)
    return dest


@pytest.fixture
def deposit(template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "deposit"
    shutil.copytree(template, dest)
    return dest


@pytest.fixture
def versioned(versioned_template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "deposit"
    shutil.copytree(versioned_template, dest)
    return dest


@pytest.fixture
def server():
    fake = FakeZenodo(CANARY).start()
    yield fake
    fake.stop()
    assert fake.violations == [], fake.violations  # no request outside the allowlist, and never a publish


class Result:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code, self.out, self.err = code, out, err


def go(args: list[str], server: FakeZenodo | None, *, token: str | None = CANARY, phrase: str | None = SANDBOX_PHRASE,
       tty: bool = True, target_variable: str = "ZENODO_SANDBOX_TOKEN", release_verify: bool = False) -> Result:
    out, err = io.StringIO(), io.StringIO()
    environ = {} if token is None else {target_variable: token}
    answers = iter([phrase or ""])
    code = zd.run(args, environ=environ, stdout=out, stderr=err, input_fn=lambda prompt: next(answers),
                  interactive=lambda: tty, test_base_url=None if server is None else server.base,
                  release_verify=release_verify)
    return Result(code, out.getvalue(), err.getvalue())


def draft(deposit: Path, *extra: str) -> list[str]:
    return [str(deposit), "--target", "sandbox", "--create-draft", *extra]


def receipt_of(deposit: Path) -> dict[str, Any]:
    return json.loads((deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json").read_text("utf-8"))


def tree(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def manifest_files(deposit: Path) -> dict[str, tuple[int, str]]:
    doc = json.loads((deposit / "DEPOSIT-MANIFEST.json").read_text("utf-8"))
    return {e["name"]: (e["bytes"], e["md5"]) for key in ("archives", "documents") for e in doc[key]}


# ================================================================================================ the happy path
def test_a_draft_is_created_filled_checked_and_left_unpublished(deposit, server):
    before = tree(deposit)
    run = go(draft(deposit), server)
    assert run.code == 0, run.err
    assert run.out.rstrip().splitlines()[-1].startswith("Draft created, NOT published. Review it at http://127.0.0.1:")
    assert run.out.rstrip().endswith("and press Publish yourself.")
    (dep,) = server.depositions.values()
    expected = {name: value for name, value in manifest_files(deposit).items()}
    expected["DEPOSIT-MANIFEST.json"] = (
        (deposit / "DEPOSIT-MANIFEST.json").stat().st_size,
        zd._digests(deposit / "DEPOSIT-MANIFEST.json")[1])
    assert {n: (f["size"], f["md5"]) for n, f in dep["files"].items()} == expected
    assert dep["submitted"] is False and dep["state"] == "unsubmitted"
    assert server.counts("POST", "/api/deposit/depositions") == 1
    assert tree(deposit) == before  # the checksummed directory is never touched: the receipt lies beside it
    receipt = receipt_of(deposit)
    assert receipt["status"] == "complete" and receipt["deposition_id"] == next(iter(server.depositions))
    assert receipt["target"] == "sandbox" and receipt["metadata_set"] is True and receipt["kind"] == "new"
    assert all(f["uploaded"] for f in receipt["files"])
    assert {f["name"] for f in receipt["files"]} == set(expected)
    assert all(f["sha256"].startswith("sha256:") and len(f["md5"]) == 32 for f in receipt["files"])


def test_a_licence_stored_under_zenodos_own_id_and_a_draft_without_conceptdoi_are_not_errors(deposit, server):
    """Sandbox trial 2026-10-23: ``mit`` was accepted and read back as ``mit-license``; a draft has ``conceptrecid`` but
    no ``conceptdoi`` key; its DOI is reserved, not registered; ``state`` was ``unsubmitted`` with ``submitted: false``."""
    assert go(draft(deposit), server).code == 0
    (dep_id,) = server.depositions
    view = server._view(server.depositions[dep_id])
    assert view["metadata"]["license"] == "mit-license" and server.depositions[dep_id]["metadata"]["license"] == "mit"
    assert "conceptdoi" not in view and "conceptrecid" in view and "doi" not in view
    assert view["state"] == "unsubmitted" and view["submitted"] is False and view["metadata"]["prereserve_doi"]["recid"] == dep_id


def test_the_consent_screen_shows_host_files_hashes_and_the_draft_notice(deposit, server):
    run = go(draft(deposit), server)
    assert "Target host: sandbox.zenodo.org" in run.out
    assert "Title: AgentPROV test deposit" in run.out and "Licence: mit" in run.out and "Creators: Test Creator" in run.out
    for planned in zd.build_plan(deposit, release_verify=False).files:
        assert f"{planned.name}  {planned.bytes} bytes  {planned.sha256}" in run.out
    assert "This creates an unpublished draft; nothing is published." in run.out
    assert f"Type exactly  {SANDBOX_PHRASE}  to continue" in run.out


def test_check_runs_the_offline_checks_with_no_token_no_terminal_and_no_request(deposit, server):
    run = go([str(deposit), "--target", "production", "--check"], server, token=None, tty=False)
    assert run.code == 0, run.err
    assert "Offline checks passed (--check): nothing was sent." in run.out and "Target host: zenodo.org" in run.out
    assert server.requests == []
    assert not list(deposit.parent.glob("*receipt*"))


def test_the_metadata_sent_is_the_mapping_of_deposit_metadata(deposit, server):
    plan = zd.build_plan(deposit, release_verify=False)
    assert go(draft(deposit), server).code == 0
    assert server.metadata_bodies == [{"metadata": plan.metadata}]


# ================================================================================================ metadata mapping
def _document(deposit: Path) -> dict[str, Any]:
    return json.loads((deposit / "deposit-metadata.json").read_text("utf-8"))


def test_the_mapping_follows_zenodo_field_names(deposit):
    doc = _document(deposit)
    doc["related_identifiers"] = [
        {"identifier": "10.1234/abc", "origin": "release.toml", "relation": "IsDerivedFrom", "scheme": "DOI"},
        {"identifier": "10.1234/old", "origin": "release.toml", "relation": "IsOriginalFormOf", "scheme": "DOI"},
        {"identifier": "10.1234/def", "origin": "release.toml", "relation": "HasVersion", "scheme": "DOI"},
    ]
    doc["description"] = "First <b>paragraph</b>\nsecond line\n\nSecond & last"
    doc["keywords"] = ["a", "b"]
    doc["creators"] = [{"affiliation": None, "name": "Doe, Jane", "orcid": "0000-0002-1694-233X"},
                       {"affiliation": "Lab", "name": "Roe, Rob", "orcid": None}]
    meta, not_sent, concept = zd.map_metadata(doc)
    assert meta["upload_type"] == "dataset" and meta["access_right"] == "open" and meta["license"] == "mit"
    assert meta["title"] == doc["title"] and meta["version"] == doc["version"] and meta["keywords"] == ["a", "b"]
    assert meta["publication_date"] == doc["publication_date"]
    assert meta["creators"] == [{"name": "Doe, Jane", "orcid": "0000-0002-1694-233X"},
                                {"affiliation": "Lab", "name": "Roe, Rob"}]
    assert meta["description"] == "<p>First &lt;b&gt;paragraph&lt;/b&gt;<br />second line</p><p>Second &amp; last</p>"
    assert zd._html("it's \"quoted\"") == "<p>it's \"quoted\"</p>"  # quotes are not entity-escaped (&#x27; shows as text)
    assert meta["related_identifiers"] == [{"identifier": "10.1234/abc", "relation": "isDerivedFrom"},
                                           {"identifier": "10.1234/old", "relation": "isOriginalFormof"}]
    assert not_sent == ("HasVersion 10.1234/def",) and concept is None
    assert "notes" not in meta


#: Ids present in the sandbox's licence vocabulary on 2026-10-23 (the trial's evidence; ``cc-zero`` was not among them).
SANDBOX_VOCABULARY_2026_10_23 = {"cc-by-4.0", "cc-by-sa-4.0", "cc-by-nc-4.0", "cc-by-nc-sa-4.0", "cc0-1.0", "mit",
                                 "apache-2.0", "agpl-3.0-only", "gpl-3.0-only", "gpl-3.0-or-later"}


def test_every_mapped_licence_id_is_in_the_sandbox_vocabulary_and_the_repos_classes_are_mapped():
    assert set(zd.LICENCE_IDS.values()) == SANDBOX_VOCABULARY_2026_10_23
    assert "cc-zero" not in zd.LICENCE_IDS.values()
    # every SPDX id the declared corpora and source profiles use for a deposit's licence class
    for spdx in ("MIT", "CC-BY-4.0", "Apache-2.0", "AGPL-3.0-only", "GPL-3.0", "GPL-3.0-or-later"):
        assert spdx in zd.LICENCE_IDS


def test_use_restrictions_travel_in_the_notes(deposit):
    doc = _document(deposit)
    doc["licences"][0]["restrictions"] = ["use only to improve AI safety"]
    meta, _, _ = zd.map_metadata(doc)
    assert "use only to improve AI safety" in meta["notes"]


@pytest.mark.parametrize(("change", "message"), [
    (lambda d: d["licences"].append(dict(d["licences"][0])), "one licence per record"),
    (lambda d: d["licences"][0].update(spdx="LGPL-2.1-only"), "no Zenodo licence id is mapped"),
    (lambda d: d.update(version_doi="10.5281/zenodo.1"), "version DOI is already set"),
    (lambda d: d.update(status="published"), "draft-unpublished"),
    (lambda d: d.update(format="agentprov-deposit/9"), "is not a"),
    (lambda d: d.update(resource_type="software"), "dataset"),
    (lambda d: d.update(creators=[]), "no creators"),
    (lambda d: d.update(concept_doi="not a doi"), "not a DOI"),
])
def test_a_deposit_that_does_not_map_is_refused(deposit, change, message):
    doc = _document(deposit)
    change(doc)
    with pytest.raises(zd.Refusal, match=message):
        zd.map_metadata(doc)


# ================================================================================================ integrity
def test_a_checksum_mismatch_stops_the_run_and_deletes_nothing(deposit, server):
    victim = next(f.name for f in zd.build_plan(deposit, release_verify=False).files if f.name.endswith(".zip"))
    server.md5_override[victim] = "0" * 32
    run = go(draft(deposit), server)
    assert run.code == 1 and victim in run.err and "nothing was deleted" in run.err
    assert receipt_of(deposit)["status"] == "failed:checksum_mismatch" and receipt_of(deposit)["mismatch"] == victim
    assert server.counts("DELETE") == 0 and server.counts("POST", "/api/deposit/depositions/") == 0
    assert "Draft created, NOT published" not in run.out


def test_a_partial_upload_resumes_with_only_the_missing_files(deposit, server):
    server.fail_put_after = 3  # the metadata PUT is not a bucket PUT: three files arrive, the fourth fails with HTTP 500
    first = go(draft(deposit), server)
    assert first.code == 1 and "HTTP 500" in first.err
    state = receipt_of(deposit)
    assert state["status"] == "uploading" and sum(f["uploaded"] for f in state["files"]) == 3
    (dep,) = server.depositions.values()
    assert len(dep["files"]) == 3
    server.fail_put_after = None
    puts_before = server.counts("PUT", "/api/files/")
    second = go([str(deposit), "--target", "sandbox", "--create-draft", "--resume"], server,
                phrase=f"resume unpublished draft {state['deposition_id']} on sandbox.zenodo.org")
    assert second.code == 0, second.err
    assert server.counts("POST", "/api/deposit/depositions") == 1  # no second deposition
    assert server.counts("PUT", "/api/files/") - puts_before == len(state["files"]) - 3
    assert len(dep["files"]) == len(state["files"]) and receipt_of(deposit)["status"] == "complete"
    assert second.out.rstrip().endswith("and press Publish yourself.")


def test_resume_refuses_a_directory_that_changed_since_the_receipt(deposit, server):
    server.fail_put_after = 1
    assert go(draft(deposit), server).code == 1
    server.fail_put_after = None
    receipt = deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json"
    data = json.loads(receipt.read_text("utf-8"))
    data["files"][0]["md5"] = "f" * 32
    receipt.write_text(json.dumps(data), "utf-8")
    run = go([str(deposit), "--target", "sandbox", "--create-draft", "--resume"], server,
             phrase=f"resume unpublished draft {data['deposition_id']} on sandbox.zenodo.org")
    assert run.code == 4 and "no longer matches the receipt" in run.err


def test_a_second_create_is_refused_while_a_receipt_exists(deposit, server):
    assert go(draft(deposit), server).code == 0
    seen = len(server.requests)
    again = go(draft(deposit), server)
    assert again.code == 4 and "No second deposition is created" in again.err
    assert len(server.requests) == seen


def test_a_receipt_of_the_other_target_does_not_block_this_one(deposit, server):
    (deposit.parent / "deposit.zenodo-production-draft-receipt.json").write_text("{}", "utf-8")
    assert go(draft(deposit), server).code == 0


def test_a_create_the_server_rejects_leaves_no_pending_receipt(deposit, server):
    server.token = "another-token"  # every request answers 401: a clear rejection, nothing was created
    assert go(draft(deposit), server).code == 1
    assert not list(deposit.parent.glob("*receipt*"))


# ================================================================================================ refusals before any network
@pytest.mark.parametrize("case", ["no tty", "no flag", "both flags", "no target", "no token", "empty token", "bad token",
                                  "wrong phrase", "resume without receipt", "resume and new version"])
def test_refusals_happen_before_any_request(deposit, server, case):
    args, kwargs = draft(deposit), {}
    code = 4
    if case == "no tty":
        kwargs["tty"] = False
    elif case == "no flag":
        args, code = [str(deposit), "--target", "sandbox"], 2
    elif case == "both flags":
        args, code = [*draft(deposit), "--check"], 2
    elif case == "no target":
        args, code = [str(deposit), "--create-draft"], 2
    elif case == "no token":
        kwargs["token"], code = None, 2
    elif case == "empty token":
        kwargs["token"], code = "", 2
    elif case == "bad token":
        kwargs["token"], code = "has space", 2
    elif case == "wrong phrase":
        kwargs["phrase"] = "yes"
    elif case == "resume without receipt":
        args, code = [*draft(deposit), "--resume"], 2
    else:
        args, code = [*draft(deposit), "--resume", "--new-version-of", "5"], 2
    run = go(args, server, **kwargs)
    assert run.code == code, run.err
    assert server.requests == [] and not list(deposit.parent.glob("*receipt*"))
    assert "has space" not in run.out + run.err


def test_the_production_token_is_not_used_for_the_sandbox(deposit, server):
    run = go(draft(deposit), server, target_variable="ZENODO_TOKEN")
    assert run.code == 2 and "ZENODO_SANDBOX_TOKEN" in run.err and server.requests == []


def test_there_is_no_yes_flag_and_the_test_hooks_are_not_options():
    parser = zd._parser()
    options = {o for a in parser._actions for o in a.option_strings}
    assert "--yes" not in options and "-y" not in options and "--test-base-url" not in options
    assert not any("base" in o or "http" in o or "host" in o for o in options)


# ================================================================================================ the offline pre-verify
def test_a_tampered_archive_is_refused_before_any_request(deposit, server):
    archive = next(deposit.glob("*.zip"))
    data = bytearray(archive.read_bytes())
    data[-1] ^= 0xFF
    archive.write_bytes(bytes(data))
    run = go(draft(deposit), server)
    assert run.code == 4 and archive.name in run.err and "differ from DEPOSIT-MANIFEST.json" in run.err
    assert server.requests == []


def test_an_extra_file_is_refused_before_any_request(deposit, server):
    (deposit / "extra.txt").write_text("not in the manifest", "utf-8")
    run = go(draft(deposit), server)
    assert run.code == 4 and "1 file(s) it does not list" in run.err and server.requests == []


def test_a_missing_file_is_refused_before_any_request(deposit, server):
    next(deposit.glob("*.zip")).unlink()
    run = go(draft(deposit), server)
    assert run.code == 4 and "listed file(s) absent" in run.err and server.requests == []


def test_a_link_or_subdirectory_in_the_deposit_is_refused(deposit, server):
    (deposit / "sub").mkdir()
    run = go(draft(deposit), server)
    assert run.code == 4 and "not a regular file" in run.err
    (deposit / "sub").rmdir()
    (deposit / "link.zip").symlink_to(next(deposit.glob("*.zip")))
    assert go(draft(deposit), server).code == 4 and server.requests == []


def test_a_changed_document_fails_its_digest(deposit, server):
    (deposit / "README.md").write_bytes(b"changed")
    run = go(draft(deposit), server)
    assert run.code == 4 and "README.md" in run.err and server.requests == []


def test_archive_mode_verify_runs_and_its_refusal_is_reported(deposit, server, monkeypatch):
    class _Failing:
        def passed(self) -> bool:
            return False

        def codes(self) -> dict[str, int]:
            return {"deposit.archive.orphan": 1}

    monkeypatch.setattr(zd, "verify_deposit", lambda *a, **k: _Failing())
    run = go(draft(deposit), server)
    assert run.code == 4 and "deposit.archive.orphan x1" in run.err and server.requests == []


def test_the_real_verify_is_called_in_release_chain_mode_by_default(deposit, monkeypatch):
    seen: dict[str, Any] = {}

    def fake(path, **kwargs):
        seen.update(kwargs)
        raise zd.AgentProvError("below the floor", code="x.y")

    monkeypatch.setattr(zd, "verify_deposit", fake)
    with pytest.raises(zd.ToolError):
        zd.build_plan(deposit, root_digests=["sha256:" + "a" * 64])
    assert seen == {"level": "chain", "release": True, "root_digests": ("sha256:" + "a" * 64,)}


def test_release_mode_verify_needs_the_published_root_digest_and_then_passes(deposit, server):
    root = json.loads((deposit / "DEPOSIT-MANIFEST.json").read_text("utf-8"))["corpora"][0]["root_digest"]
    missing = go(draft(deposit), server, release_verify=True)
    assert missing.code == 2 and "--root-digest" in missing.err and server.requests == []
    wrong = go(draft(deposit, "--root-digest", "sha256:" + "0" * 64), server, release_verify=True)
    assert wrong.code == 4 and "root_digest" in wrong.err and server.requests == []
    ok = go(draft(deposit, "--root-digest", root), server, release_verify=True)
    assert ok.code == 0, ok.err


def test_a_real_run_cannot_reach_the_test_parameters():
    import inspect

    defaults = {n: p.default for n, p in inspect.signature(zd.run).parameters.items()}
    assert defaults["test_base_url"] is None and defaults["release_verify"] is True
    assert defaults["interactive"] is None and defaults["input_fn"] is None and defaults["environ"] is None
    assert list(inspect.signature(zd.main).parameters) == []


def test_a_bad_root_digest_is_a_usage_error(deposit):
    with pytest.raises(zd.Refusal, match="--root-digest"):
        zd.build_plan(deposit, root_digests=["abc"])


def test_zenodo_limits_are_named_constants_and_enforced(deposit):
    files = [zd.PlannedFile(f"f{i}.zip", 1, "sha256:" + "0" * 64, "0" * 32) for i in range(zd.MAX_FILES + 1)]
    with pytest.raises(zd.Refusal, match="MAX_FILES"):
        zd._check_limits(files)
    with pytest.raises(zd.Refusal, match="MAX_FILE_BYTES"):
        zd._check_limits([zd.PlannedFile("a.zip", zd.MAX_FILE_BYTES + 1, "sha256:" + "0" * 64, "0" * 32)])
    half = zd.MAX_TOTAL_BYTES // 2 + 1
    with pytest.raises(zd.Refusal, match="MAX_TOTAL_BYTES"):
        zd._check_limits([zd.PlannedFile(f"{i}.zip", half, "sha256:" + "0" * 64, "0" * 32) for i in range(2)])


# ================================================================================================ the token
def test_the_token_never_appears_in_any_output_receipt_url_or_repr(deposit, server):
    server.echo_token_on_metadata = True  # the server echoes the bearer value into an error message
    run = go(draft(deposit), server)
    assert run.code == 1 and "<token redacted>" in run.err
    secret = zd.Secret(CANARY)
    everything = [run.out, run.err, repr(secret), str(secret), f"{secret}", f"{secret!r}",
                  (deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json").read_text("utf-8"),
                  *(p for _, p in server.requests)]
    assert not any(CANARY in text for text in everything)
    assert "Authorization" not in everything[6]


def test_the_token_is_hidden_in_a_successful_run_too(deposit, server):
    run = go(draft(deposit), server)
    receipt = (deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json").read_text("utf-8")
    assert CANARY not in run.out + run.err + receipt and "Bearer" not in receipt


def test_an_unexpected_exception_prints_no_traceback_and_no_token(deposit, server, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError(f"failure carrying {CANARY}")

    monkeypatch.setattr(zd.Client, "request", boom)
    run = go(draft(deposit), server)
    assert run.code == 1 and "Traceback" not in run.err and CANARY not in run.err + run.out


def test_the_secret_hides_its_url_quoted_form_too():
    secret = zd.Secret("a b/c")
    assert secret.redact("x a b/c y a%20b%2Fc z") == "x <token redacted> y <token redacted> z"


# ================================================================================================ the client
def test_tls_is_verified_and_the_hosts_are_a_fixed_allowlist():
    assert {t.host for t in zd.TARGETS.values()} == {"zenodo.org", "sandbox.zenodo.org"}
    client = zd.Client(zd.TARGETS["production"], zd.Secret(CANARY))
    assert client.scheme == "https" and client.host == "zenodo.org" and client.port == 443
    assert client._context is not None and client._context.verify_mode == ssl.CERT_REQUIRED
    assert client._context.check_hostname is True


@pytest.mark.parametrize("url", ["http://example.com:80", "https://127.0.0.1:9", "http://localhost:9", "http://127.0.0.1",
                                 "http://127.0.0.1:9/api", "http://sandbox.zenodo.org:80"])
def test_plain_http_exists_only_for_loopback_through_the_test_parameter(url):
    with pytest.raises(zd.Refusal):
        zd.Client(zd.TARGETS["sandbox"], zd.Secret(CANARY), test_base_url=url)


@pytest.mark.parametrize(("method", "path"), [
    ("POST", "/api/deposit/depositions/5/actions/publish"),
    ("POST", "/api/deposit/depositions/5/actions/edit"),
    ("POST", "/api/deposit/depositions/5/actions/discard"),
    ("DELETE", "/api/deposit/depositions/5"),
    ("DELETE", "/api/deposit/depositions/5/files/abc"),
    ("DELETE", "/api/files/00000000-0000-0000-0000-000000000000/a.zip"),
    ("GET", "/api/records"),
    ("PUT", "/api/deposit/depositions/5/files"),
    ("PUT", "/api/deposit/depositions/5?access_token=x"),
    ("GET", "/api/deposit/depositions/5/../6"),
    ("PUT", "/api/files/00000000-0000-0000-0000-000000000000/../a.zip"),
    ("POST", "/api/deposit/depositions/5"),
    ("POST", "/api/deposit/depositions/5/actions/newversion/"),
    ("GET", "https://evil.example/api/deposit/depositions"),
])
def test_a_request_outside_the_allowlist_is_refused_before_a_socket_opens(server, method, path):
    client = zd.Client(zd.TARGETS["sandbox"], zd.Secret(CANARY), test_base_url=server.base)
    with pytest.raises(zd.Refusal, match="not an allowed request"):
        client.request(method, path)
    assert server.requests == []


def test_the_allowlist_holds_only_get_post_and_put_and_no_publish_edit_discard_or_delete():
    assert {m for m, _ in zd.ALLOWED} == {"GET", "POST", "PUT"}
    for _, pattern in zd.ALLOWED:
        for word in ("publish", "edit", "discard", "files/abc", "delete"):
            assert word not in pattern.pattern.replace("/api/files/", "").replace("depositions/[0-9]{1,20}/files", "")
    actions = [p.pattern for m, p in zd.ALLOWED if "actions" in p.pattern]
    assert actions == ["/api/deposit/depositions/[0-9]{1,20}/actions/newversion"]


def test_a_redirect_is_never_followed(deposit, server):
    server.redirect_create = True
    run = go(draft(deposit), server)
    assert run.code == 1 and "redirect" in run.err and server.counts("POST") == 1
    assert receipt_of(deposit)["status"] == "pending"  # an unclear outcome keeps the receipt: a draft may exist


def test_a_bucket_link_on_another_host_is_not_used(deposit, server):
    server.foreign_bucket = True
    run = go(draft(deposit), server)
    assert run.code == 1 and "bucket link does not point at the target host" in run.err
    assert server.counts("PUT", "/api/files/") == 0 and receipt_of(deposit)["status"] == "pending"


# ================================================================================================ a new version
def test_newversion_is_refused_for_the_agentdojo_prov_concept_by_doi_and_by_record_id(versioned, server):
    for doi, recid in ((AGENTDOJO_PROV_CONCEPT, "1"), (OWN_CONCEPT, "20692312")):
        dep = server.add_published(concept_doi=doi, concept_recid=recid)
        run = go(draft(versioned, "--new-version-of", str(dep)), server)
        assert run.code == 4 and "AgentDojo-PROV" in run.err
    assert server.counts("POST") == 0 and not list(versioned.parent.glob("*receipt*"))


def test_newversion_is_refused_for_a_concept_the_metadata_does_not_record(versioned, server):
    dep = server.add_published(concept_doi="10.5281/zenodo.55555555", concept_recid="55555555")
    run = go(draft(versioned, "--new-version-of", str(dep)), server)
    assert run.code == 4 and "not the one the deposit metadata records" in run.err and server.counts("POST") == 0


def test_newversion_needs_a_recorded_concept_doi(deposit, server):
    dep = server.add_published(concept_doi=OWN_CONCEPT, concept_recid="1")
    run = go(draft(deposit, "--new-version-of", str(dep)), server)
    assert run.code == 4 and "records no concept_doi" in run.err and server.counts("POST") == 0


def test_a_concept_doi_of_the_agentdojo_prov_concept_in_the_metadata_is_refused_offline(agentdojo_prov, server):
    run = go([str(agentdojo_prov), "--target", "sandbox", "--check"], server, token=None, tty=False)
    assert run.code == 4 and "AgentDojo-PROV concept DOI" in run.err and server.requests == []


def test_a_new_version_of_the_recorded_concept_makes_a_draft_and_reports_inherited_files(versioned, server):
    dep = server.add_published(concept_doi=OWN_CONCEPT, concept_recid="99999990",
                               files={"old-v0.0.1.meta.zip": b"old bytes", "README.md": b"old readme"})
    run = go(draft(versioned, "--new-version-of", str(dep)), server)
    assert run.code == 1, run.err
    assert server.counts("POST", "/api/deposit/depositions/") == 1 and server.counts("POST") == 1
    assert "old-v0.0.1.meta.zip" in run.out and "this tool never deletes" in run.out
    assert run.out.rstrip().endswith("press Publish yourself.") and "remove the inherited files" in run.out
    state = receipt_of(versioned)
    assert state["status"] == "inherited_files" and state["kind"] == "newversion" and state["new_version_of"] == dep
    draft_id = state["deposition_id"]
    assert draft_id != dep and server.depositions[draft_id]["submitted"] is False
    assert server.depositions[dep]["files"].keys() == {"old-v0.0.1.meta.zip", "README.md"}  # the published one is untouched


# ================================================================================================ static properties
def _tool_tree() -> ast.Module:
    return ast.parse(_TOOL.read_text("utf-8"))


def test_the_tool_imports_no_third_party_package():
    roots = set()
    for node in ast.walk(_tool_tree()):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    third_party = {r for r in roots if r not in sys.stdlib_module_names and r not in ("agentprov", "__future__")}
    assert third_party == set()
    assert not roots & {"requests", "httpx", "aiohttp", "urllib3", "zenodo", "zenodo_client", "invenio_client"}


def test_the_tool_has_no_publish_edit_discard_or_delete_path():
    tree = _tool_tree()
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [s for s in strings if re.search(r"/actions/(?!newversion)|DELETE", s)]
    assert not [s for s in strings if s.lower() in {"delete", "publish", "discard"}]
    names = [n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
             for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not [n for n in names if re.search(r"publish|delete|discard", n, re.I)]
    methods = {a.value for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "request"
               for a in n.args[:1] if isinstance(a, ast.Constant)}
    assert methods <= {"GET", "POST", "PUT"}


def test_the_tool_is_its_own_distribution_outside_agentprov_and_the_release_package_stays_offline():
    """D-880: ``agentprov-zenodo`` (``zenodo/``), not a module of ``agentprov``; ``tools/zenodo_draft.py`` only delegates."""
    assert _TOOL == (_REPO / "zenodo" / "src" / "agentprov_zenodo" / "draft.py").resolve()
    assert not _TOOL.is_relative_to(_REPO / "src")
    for path in (_REPO / "src" / "agentprov" / "release").rglob("*.py"):
        text = path.read_text("utf-8")
        assert "zenodo_draft" not in text and "agentprov_zenodo" not in text
        assert "http.client" not in text and "urllib.request" not in text
    shim = ast.parse(_SHIM.read_text("utf-8"))
    imports = [n for n in ast.walk(shim) if isinstance(n, ast.Import | ast.ImportFrom)]
    assert {getattr(n, "module", None) or n.names[0].name for n in imports} == {"sys", "agentprov_zenodo.draft"}
    assert len([n for n in shim.body if isinstance(n, ast.FunctionDef | ast.ClassDef)]) == 0


def test_the_module_entry_runs_the_tool():
    import subprocess

    done = subprocess.run([sys.executable, "-I", "-m", "agentprov_zenodo", "--help"], capture_output=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin"})
    assert done.returncode == 0 and b"UNPUBLISHED Zenodo draft" in done.stdout
    shim = subprocess.run([sys.executable, "-I", str(_SHIM), "--help"], capture_output=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin"})
    assert shim.returncode == 0 and b"UNPUBLISHED Zenodo draft" in shim.stdout
    # the usage line names how the tool was started (F-19), so the two help texts differ only in that name's wrapping
    assert done.stdout.startswith(b"usage: python -m agentprov_zenodo ")
    assert shim.stdout.startswith(b"usage: zenodo_draft.py ")
    assert b" ".join(done.stdout.split(b"\n\n", 1)[1].split()) == b" ".join(shim.stdout.split(b"\n\n", 1)[1].split())


def test_the_confirmation_phrase_names_the_host(deposit):
    plan = zd.build_plan(deposit, release_verify=False)
    _, phrase = zd.consent_text(plan, zd.TARGETS["production"], resume_id=None, new_version_of=None)
    assert phrase == "create unpublished draft on zenodo.org"
    _, resume = zd.consent_text(plan, zd.TARGETS["sandbox"], resume_id=7, new_version_of=None)
    assert resume == "resume unpublished draft 7 on sandbox.zenodo.org"



# ================================================================================================ communities (D-870)
def test_communities_are_sent_shown_and_recorded(deposit, server):
    run = go(draft(deposit, "--community", "agentprov", "--community", "ai-safety_2"), server)
    assert run.code == 0, run.err
    assert "Communities (each one's curators accept or decline the request): agentprov, ai-safety_2" in run.out
    (body,) = server.metadata_bodies
    assert body["metadata"]["communities"] == [{"identifier": "agentprov"}, {"identifier": "ai-safety_2"}]
    receipt = receipt_of(deposit)
    assert receipt["communities"] == ["agentprov", "ai-safety_2"]
    assert receipt["metadata"]["communities"] == body["metadata"]["communities"]


def test_no_community_sends_no_communities_field(deposit, server):
    assert go(draft(deposit), server).code == 0
    assert "communities" not in server.metadata_bodies[0]["metadata"] and receipt_of(deposit)["communities"] == []


def test_check_shows_the_communities_offline(deposit, server):
    run = go([str(deposit), "--target", "sandbox", "--check", "--community", "agentprov"], server, token=None, tty=False)
    assert run.code == 0 and "agentprov" in run.out and server.requests == []


@pytest.mark.parametrize("slugs", [["Upper"], ["has space"], ["_lead"], ["a/b"], ["x" * 101], ["dup", "dup"]])
def test_a_bad_or_repeated_community_is_a_usage_error_before_any_request(deposit, server, slugs):
    args = draft(deposit)
    for slug in slugs:
        args += ["--community", slug]
    run = go(args, server)
    assert run.code == 2 and "--community" in run.err
    assert server.requests == [] and not list(deposit.parent.glob("*receipt*"))


# ================================================================================================ reserved DOI (D-870)
def test_the_receipt_is_format_0_2_and_records_the_reserved_doi_and_the_metadata(deposit, server):
    run = go(draft(deposit), server)
    assert run.code == 0, run.err
    (dep_id,) = server.depositions
    receipt = receipt_of(deposit)
    assert receipt["format"] == zd.RECEIPT_FORMAT == "agentprov-zenodo-draft-receipt/0.2"
    assert receipt["reserved_doi"] == f"10.5281/zenodo.{dep_id}" and receipt["reserved_recid"] == dep_id
    assert receipt["metadata"] == zd.build_plan(deposit, release_verify=False).metadata
    assert receipt["cross_links"] is None
    assert f"Reserved DOI (registered only when you publish): 10.5281/zenodo.{dep_id}" in run.out
    # the sandbox's drafts had a DOI unasked, so none is requested: the metadata sent is the mapping alone
    assert server.prereserve_requests == 0 and "prereserve_doi" not in server.metadata_bodies[0]["metadata"]


def test_a_draft_without_a_doi_gets_one_requested_once_with_the_metadata(deposit, server):
    server.reserve_on_create = False
    assert go(draft(deposit), server).code == 0
    (dep_id,) = server.depositions
    assert server.prereserve_requests == 1 and server.metadata_bodies[0]["metadata"]["prereserve_doi"] is True
    assert receipt_of(deposit)["reserved_doi"] == f"10.5281/zenodo.{dep_id}"
    assert "prereserve_doi" not in receipt_of(deposit)["metadata"]  # a request, never part of the recorded metadata


def test_resume_reads_the_doi_back_and_never_reserves_another(deposit, server):
    server.reserve_on_create, server.fail_put_after = False, 2
    assert go(draft(deposit), server).code == 1
    first = receipt_of(deposit)
    assert first["reserved_doi"] is not None and server.prereserve_requests == 1
    server.fail_put_after = None
    metadata_puts = len(server.metadata_bodies)
    run = go([*draft(deposit), "--resume"], server,
             phrase=f"resume unpublished draft {first['deposition_id']} on sandbox.zenodo.org")
    assert run.code == 0, run.err
    assert server.prereserve_requests == 1 and len(server.metadata_bodies) == metadata_puts
    assert receipt_of(deposit)["reserved_doi"] == first["reserved_doi"] and receipt_of(deposit)["status"] == "complete"


def test_resume_after_a_rejected_metadata_put_requests_the_doi_then(deposit, server):
    server.reserve_on_create, server.echo_token_on_metadata = False, True
    assert go(draft(deposit), server).code == 1
    first = receipt_of(deposit)
    assert first["reserved_doi"] is None and first["metadata_set"] is False
    server.echo_token_on_metadata = False
    run = go([*draft(deposit), "--resume"], server,
             phrase=f"resume unpublished draft {first['deposition_id']} on sandbox.zenodo.org")
    assert run.code == 0, run.err
    assert server.prereserve_requests == 1 and receipt_of(deposit)["reserved_doi"] == f"10.5281/zenodo.{first['deposition_id']}"


def test_a_reserved_doi_that_changes_stops_the_run(deposit, server):
    assert go(draft(deposit), server).code == 0
    (dep,) = server.depositions.values()
    recorded = receipt_of(deposit)["reserved_doi"]
    dep["doi"] = "10.5281/zenodo.1"
    run = go([*draft(deposit), "--resume"], server, phrase=f"resume unpublished draft {dep['id']} on sandbox.zenodo.org")
    assert run.code == 1 and "differs from the receipt's" in run.err
    receipt = receipt_of(deposit)
    assert receipt["status"] == "failed:reserved_doi_changed" and receipt["reserved_doi"] == recorded


def test_no_reserved_doi_stops_before_any_upload(deposit, server):
    server.never_reserve = True
    run = go(draft(deposit), server)
    assert run.code == 1 and "no reserved DOI" in run.err
    assert server.counts("PUT", "/api/files/") == 0 and receipt_of(deposit)["status"] == "failed:no_reserved_doi"


def test_resume_refuses_other_communities_than_the_create(deposit, server):
    server.fail_put_after = 1
    assert go(draft(deposit, "--community", "agentprov"), server).code == 1
    server.fail_put_after = None
    dep_id = receipt_of(deposit)["deposition_id"]
    run = go([*draft(deposit), "--resume"], server, phrase=f"resume unpublished draft {dep_id} on sandbox.zenodo.org")
    assert run.code == 4 and "--community" in run.err
    ok = go([*draft(deposit, "--community", "agentprov"), "--resume"], server,
            phrase=f"resume unpublished draft {dep_id} on sandbox.zenodo.org")
    assert ok.code == 0, ok.err


def _old_receipt(deposit: Path, **extra: Any) -> Path:
    path = deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json"
    path.write_text(json.dumps({"format": zd.RECEIPT_FORMAT_0_1, "target": "sandbox", "host": "sandbox.zenodo.org",
                                "deposition_id": 4242, "status": "complete", "files": [], **extra}), "utf-8")
    return path


def test_a_0_1_receipt_still_blocks_a_create_and_is_refused_by_resume(deposit, server):
    _old_receipt(deposit)
    again = go(draft(deposit), server)
    assert again.code == 4 and "No second deposition is created" in again.err
    resume = go([*draft(deposit), "--resume"], server, phrase="resume unpublished draft 4242 on sandbox.zenodo.org")
    assert resume.code == 4 and "0.1 receipt" in resume.err
    assert server.requests == []


# ================================================================================================ cross-links (D-870)
def _collection(template: Path, tmp_path: Path, server: FakeZenodo, *extra: str, n: int = 3) -> list[Path]:
    receipts = []
    for index in range(n):
        dest = tmp_path / f"record{index}" / "deposit"
        shutil.copytree(template, dest)
        run = go(draft(dest, *extra), server)
        assert run.code == 0, run.err
        receipts.append(dest.parent / "deposit.zenodo-sandbox-draft-receipt.json")
    return receipts


def _link_args(receipts: list[Path]) -> list[str]:
    return ["--target", "sandbox", "--cross-link", "--umbrella", str(receipts[0]),
            *(item for r in receipts[1:] for item in ("--member", str(r)))]


def _link_phrase(n: int) -> str:
    return f"link {n} unpublished drafts on sandbox.zenodo.org"


def _data(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def test_cross_links_are_written_to_every_draft_and_read_back(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, "--community", "agentprov")
    umbrella, *members = (_data(r) for r in receipts)
    original = umbrella["metadata"]["related_identifiers"]
    run = go(_link_args(receipts), server, phrase=_link_phrase(3))
    assert run.code == 0, run.err
    assert run.out.rstrip().endswith("Review each in the web UI and press Publish yourself.")
    assert f"+ hasPart {members[0]['reserved_doi']}" in run.out and f"+ isPartOf {umbrella['reserved_doi']}" in run.out
    stored = {d: server.depositions[d]["metadata"] for d in server.depositions}
    assert stored[umbrella["deposition_id"]]["related_identifiers"] == original + [
        {"identifier": m["reserved_doi"], "relation": "hasPart"} for m in members]
    for member in members:
        assert stored[member["deposition_id"]]["related_identifiers"] == original + [
            {"identifier": umbrella["reserved_doi"], "relation": "isPartOf"}]
    for dep_id, meta in stored.items():
        assert meta["communities"] == [{"identifier": "agentprov"}]  # the recorded metadata is sent again, whole
        assert server.depositions[dep_id]["submitted"] is False and server.depositions[dep_id]["doi"] is not None
    for path, role in zip(receipts, ("umbrella", "member", "member"), strict=True):
        assert _data(path)["cross_links"]["status"] == "linked" and _data(path)["cross_links"]["role"] == role
    assert server.prereserve_requests == 0  # the cross-link step never asks for a DOI


def test_cross_linking_again_changes_nothing(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    assert go(_link_args(receipts), server, phrase=_link_phrase(2)).code == 0
    first = {d: list(dep["metadata"]["related_identifiers"]) for d, dep in server.depositions.items()}
    again = go(_link_args(receipts), server, phrase=_link_phrase(2))
    assert again.code == 0, again.err
    assert {d: dep["metadata"]["related_identifiers"] for d, dep in server.depositions.items()} == first


def test_cross_link_refuses_a_published_record_before_writing_any(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server)
    server.publish_for_test(_data(receipts[2])["deposition_id"])
    puts = server.counts("PUT", "/api/deposit/depositions/")
    run = go(_link_args(receipts), server, phrase=_link_phrase(3))
    assert run.code == 4 and "already published" in run.err
    assert server.counts("PUT", "/api/deposit/depositions/") == puts
    assert all(_data(r)["cross_links"] is None for r in receipts)


@pytest.mark.parametrize("change", [
    lambda d: d.update(reserved_doi=None),
    lambda d: d.update(status="uploading"),
    lambda d: d.update(target="production"),
    lambda d: d.update(format=zd.RECEIPT_FORMAT_0_1),
    lambda d: d.update(metadata=None),
])
def test_cross_link_refuses_a_receipt_before_any_request(template, tmp_path, server, change):
    receipts = _collection(template, tmp_path, server, n=2)
    data = _data(receipts[1])
    change(data)
    receipts[1].write_text(json.dumps(data), "utf-8")
    seen = len(server.requests)
    run = go(_link_args(receipts), server, phrase=_link_phrase(2))
    assert run.code == 4, run.err
    assert len(server.requests) == seen and "Type exactly" not in run.out


def test_cross_link_refuses_a_receipt_given_twice_or_the_umbrella_as_a_member(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    seen = len(server.requests)
    for args in (_link_args([receipts[0], receipts[1], receipts[1]]), _link_args([receipts[0], receipts[0]])):
        run = go(args, server, phrase=_link_phrase(3))
        assert run.code == 2 and "given twice" in run.err
    copy = receipts[1].parent.parent / "copy.json"
    copy.write_bytes(receipts[1].read_bytes())  # another file naming the same deposition and DOI
    run = go(_link_args([receipts[0], receipts[1], copy]), server, phrase=_link_phrase(3))
    assert run.code == 4 and "same deposition" in run.err
    assert len(server.requests) == seen


def test_cross_link_refuses_a_doi_that_differs_on_the_server(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    server.depositions[_data(receipts[1])["deposition_id"]]["doi"] = "10.5281/zenodo.7"
    puts = server.counts("PUT", "/api/deposit/depositions/")
    run = go(_link_args(receipts), server, phrase=_link_phrase(2))
    assert run.code == 4 and "reserved DOI is 10.5281/zenodo.7" in run.err
    assert server.counts("PUT", "/api/deposit/depositions/") == puts


def test_cross_link_refuses_related_identifiers_changed_outside_the_tool(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    meta = server.depositions[_data(receipts[0])["deposition_id"]]["metadata"]
    meta["related_identifiers"] = [*meta.get("related_identifiers", []), {"identifier": "10.1/x", "relation": "cites"}]
    puts = server.counts("PUT", "/api/deposit/depositions/")
    run = go(_link_args(receipts), server, phrase=_link_phrase(2))
    assert run.code == 4 and "did not send" in run.err
    assert server.counts("PUT", "/api/deposit/depositions/") == puts


@pytest.mark.parametrize("case", ["wrong phrase", "no tty", "no token", "deposit dir", "no member", "no umbrella",
                                  "member without cross-link", "with community"])
def test_cross_link_usage_and_consent_refusals_send_nothing(template, tmp_path, server, case):
    receipts = _collection(template, tmp_path, server, n=2)
    args, kwargs, code = _link_args(receipts), {"phrase": _link_phrase(2)}, 4
    if case == "wrong phrase":
        kwargs["phrase"] = "yes"
    elif case == "no tty":
        kwargs["tty"] = False
    elif case == "no token":
        kwargs["token"], code = None, 2
    elif case == "deposit dir":
        args, code = [str(receipts[0].parent / "deposit"), *args], 2
    elif case == "no member":
        args, code = args[:5], 2
    elif case == "no umbrella":
        args, code = ["--target", "sandbox", "--cross-link", "--member", str(receipts[1])], 2
    elif case == "member without cross-link":
        args, code = [*draft(receipts[0].parent / "deposit"), "--member", str(receipts[1])], 2
    else:
        args, code = [*args, "--community", "agentprov"], 2
    seen = len(server.requests)
    run = go(args, server, **kwargs)
    assert run.code == code, run.err
    assert len(server.requests) == seen


def test_the_cross_link_screen_and_phrase_name_the_host_and_every_draft(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    links = zd.plan_links(zd.TARGETS["sandbox"], receipts[0], [receipts[1]])
    lines, phrase = zd.cross_link_text(links, zd.TARGETS["sandbox"])
    assert phrase == "link 2 unpublished drafts on sandbox.zenodo.org"
    assert lines[0].startswith("Target host: sandbox.zenodo.org") and "nothing is published" in lines[1]
    assert sum(" draft " in line for line in lines) == 2


def test_the_token_never_appears_in_a_cross_link_run_or_its_receipts(template, tmp_path, server):
    receipts = _collection(template, tmp_path, server, n=2)
    run = go(_link_args(receipts), server, phrase=_link_phrase(2))
    assert run.code == 0
    assert not any(CANARY in text for text in [run.out, run.err, *(r.read_text("utf-8") for r in receipts)])


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), (True, None), ({}, None), ({"doi": "10.5281/zenodo.5", "recid": 5}, ("10.5281/zenodo.5", 5))])
def test_reserved_doi_readings(value, expected):
    answer = {"metadata": {} if value is None else {"prereserve_doi": value}}
    assert zd._reserved(answer) == expected


@pytest.mark.parametrize("value", [{"doi": "not a doi", "recid": 5}, {"doi": "10.5281/zenodo.5"}, {"recid": True}, "x"])
def test_a_malformed_reserved_doi_stops(value):
    with pytest.raises(zd.ToolError, match="malformed reserved DOI"):
        zd._reserved({"metadata": {"prereserve_doi": value}})


# ================================================================================================ --keychain (D-880)
def test_keychain_reads_the_targets_token_from_the_keychain_not_the_environment(deposit, server, monkeypatch):
    asked: list[list[str]] = []

    def read(names, values=None):
        asked.append(list(names))
        return {names[0]: CANARY}

    monkeypatch.setattr("agentprov.keys.read", read)
    run = go(draft(deposit, "--keychain"), server, token=None)
    assert run.code == 0, run.err
    assert asked == [["ZENODO_SANDBOX_TOKEN"]] and CANARY not in run.out + run.err
    assert CANARY not in (deposit.parent / "deposit.zenodo-sandbox-draft-receipt.json").read_text("utf-8")


def test_keychain_without_the_token_is_refused_before_any_request(deposit, server, monkeypatch):
    from agentprov import keys

    def missing(names, values=None):
        raise keys.KeychainError("keychain.missing")

    monkeypatch.setattr("agentprov.keys.read", missing)
    run = go(draft(deposit, "--keychain"), server, token=None)
    assert run.code == 2 and "agentprov keys set ZENODO_SANDBOX_TOKEN" in run.err and "keychain.missing" in run.err
    assert server.requests == [] and not list(deposit.parent.glob("*receipt*"))


def test_keychain_is_refused_with_check(deposit, server):
    run = go([str(deposit), "--target", "sandbox", "--check", "--keychain"], server, token=None, tty=False)
    assert run.code == 2 and "--keychain" in run.err and server.requests == []


def test_cross_link_takes_keychain(template, tmp_path, server, monkeypatch):
    receipts = _collection(template, tmp_path, server, n=2)
    monkeypatch.setattr("agentprov.keys.read", lambda names, values=None: {names[0]: CANARY})
    run = go([*_link_args(receipts), "--keychain"], server, token=None, phrase=_link_phrase(2))
    assert run.code == 0, run.err
