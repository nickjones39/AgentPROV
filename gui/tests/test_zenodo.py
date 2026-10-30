"""D-880: Zenodo in the GUI (Settings › Zenodo, the Keys rows, Package › Create Zenodo drafts…, the pseudo-terminal).

Nothing here runs the real uploader or contacts Zenodo: the dialog runs a fake uploader script under the pseudo-terminal,
which checks it has a terminal, asks for a phrase like the real one and records its arguments. The token never reaches
the GUI: every run passes ``--keychain`` and the child's environment is the given allowlist.
"""

from __future__ import annotations

import json
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui import zenodo_run as Z

ROOT = "sha256:" + "a" * 64
ROOT2 = "sha256:" + "b" * 64
pty_only = pytest.mark.skipif(not Z.available(), reason="needs a POSIX pseudo-terminal")

FAKE_UPLOADER = r'''
import json, sys
args = sys.argv[1:]
with open(sys.argv[0] + ".calls", "a", encoding="utf-8") as log:
    log.write(json.dumps({"args": args, "tty": [sys.stdin.isatty(), sys.stdout.isatty()]}) + "\n")
if not (sys.stdin.isatty() and sys.stdout.isatty()):
    print("no terminal")
    sys.exit(4)
host = args[args.index("--target") + 1] + ".zenodo.org" if "--target" in args else "?"
host = host.replace("production.", "")
phrase = ("link" if "--cross-link" in args else "create unpublished draft on") + " " + host
print(f"Type exactly  {phrase}  to continue, anything else cancels:")
answer = input("> ")
print("confirmed" if answer.strip() == phrase else "not confirmed")
sys.exit(0 if answer.strip() == phrase else 4)
'''


def _wait(predicate: Any, qapp: Any = None, timeout: float = 90.0) -> None:  # generous: a loaded machine is slow
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if qapp is not None:
            qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


# ================================================================================================ the plan (no Qt)
def test_deposits_parse_with_root_digests_and_the_first_is_the_umbrella(tmp_path: Path) -> None:
    text = f"{tmp_path / 'u'} {ROOT}\n\n{tmp_path / 'm'} {ROOT} {ROOT2}\n"
    deposits = Z.parse_deposits(text)
    assert [d.directory.name for d in deposits] == ["u", "m"] and deposits[1].roots == (ROOT, ROOT2)
    for bad in (f"{tmp_path / 'u'}", f"{tmp_path / 'u'} sha256:abc", f"{tmp_path / 'u'} {ROOT}\n{tmp_path / 'u'} {ROOT}"):
        with pytest.raises(ValueError):
            Z.parse_deposits(bad)
    assert Z.parse_communities("agentprov, ai-safety_2") == ["agentprov", "ai-safety_2"]
    with pytest.raises(ValueError):
        Z.parse_communities("Upper")


def test_an_index_umbrella_is_named_alone_on_the_first_line(tmp_path: Path) -> None:
    """D-947: an index-only umbrella (``package --index``) holds no corpus, so it takes no root digest; only the first
    line may be one, and a corpus deposit still needs its digests."""
    from agentprov.release.index import INDEX_MANIFEST_FORMAT

    assert Z.INDEX_MANIFEST_FORMAT == INDEX_MANIFEST_FORMAT
    index, part = tmp_path / "index", tmp_path / "part"
    for d in (index, part):
        d.mkdir()
    (index / "DEPOSIT-MANIFEST.json").write_text(json.dumps({"format": INDEX_MANIFEST_FORMAT, "kind": "index"}))
    (part / "DEPOSIT-MANIFEST.json").write_text(json.dumps({"format": "agentprov-deposit-manifest/0.1"}))
    deposits = Z.parse_deposits(f"{index}\n{part} {ROOT}\n")
    assert deposits[0] == Z.Deposit(index, ()) and deposits[1].roots == (ROOT,)
    plan = Z.plan_steps(deposits, "sandbox", [])
    assert "--root-digest" not in plan.steps[0].args and plan.steps[0].args[0] == str(index)
    assert plan.steps[-1].args[plan.steps[-1].args.index("--umbrella") + 1] == str(Z.receipt_path(index, "sandbox"))
    for bad in (f"{index} {ROOT}", f"{part}", f"{part} {ROOT}\n{index}"):
        with pytest.raises(ValueError):
            Z.parse_deposits(bad)


def test_the_plan_creates_resumes_skips_and_cross_links_with_the_keychain(tmp_path: Path) -> None:
    dirs = [tmp_path / name / "deposit" for name in ("u", "m1", "m2")]
    for d in dirs:
        d.mkdir(parents=True)
    Z.receipt_path(dirs[1], "sandbox").write_text(json.dumps({"status": "uploading"}))
    Z.receipt_path(dirs[2], "sandbox").write_text(json.dumps({"status": "complete"}))
    plan = Z.plan_steps([Z.Deposit(d, (ROOT,)) for d in dirs], "sandbox", ["agentprov"])
    assert len(plan.steps) == 3 and "complete" in plan.notes[0] and "m2" in plan.notes[0]
    assert "--resume" not in plan.steps[0].args and plan.steps[1].args[-1] == "--resume"
    assert plan.steps[1].args[0] == str(dirs[1])
    create, _resume, link = plan.steps
    assert create.args[:4] == (str(dirs[0]), "--target", "sandbox", "--create-draft")
    assert create.args[create.args.index("--community"):][:2] == ("--community", "agentprov")
    assert link.args[:4] == ("--target", "sandbox", "--cross-link", "--keychain")
    assert link.args[link.args.index("--umbrella") + 1] == str(Z.receipt_path(dirs[0], "sandbox"))
    assert link.args.count("--member") == 2
    for step in plan.steps:
        assert "--keychain" in step.args and not any("publish" in a for a in step.args)
    with pytest.raises(ValueError):
        Z.plan_steps([], "staging", [])


def test_one_deposit_needs_no_cross_link(tmp_path: Path) -> None:
    plan = Z.plan_steps([Z.Deposit(tmp_path / "d", (ROOT,))], "production", [])
    assert len(plan.steps) == 1 and "--cross-link" not in plan.steps[0].args


@pty_only
def test_the_pseudo_terminal_gives_the_program_a_terminal_and_a_typed_line(tmp_path: Path) -> None:
    script = tmp_path / "fake.py"
    script.write_text(FAKE_UPLOADER)
    run = Z.PtyRun([sys.executable, str(script), "--target", "sandbox"], {"PATH": "/usr/bin:/bin"})
    seen = ""
    try:
        end = time.monotonic() + 90
        while "Type exactly" not in seen and time.monotonic() < end:
            seen += run.read()
            time.sleep(0.02)
        run.send_line("create unpublished draft on sandbox.zenodo.org\x07\x00")  # control characters are dropped
        _wait(lambda: run.poll() is not None)
        seen += run.read()
    finally:
        run.close()
    assert run.poll() == 0 and "\nconfirmed" in seen and "not confirmed" not in seen and "\r" not in seen
    assert json.loads((tmp_path / "fake.py.calls").read_text().splitlines()[0])["tty"] == [True, True]


# ================================================================================================ the dialog
class _Cli:
    def __init__(self, script: Path) -> None:
        self.python = (sys.executable, str(script))


@pty_only
def test_the_dialog_runs_creates_then_the_cross_link_each_confirmed_by_a_typed_phrase(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    script = tmp_path / "fake.py"
    script.write_text(FAKE_UPLOADER)
    deposits = f"{tmp_path / 'u' / 'deposit'} {ROOT}\n{tmp_path / 'm' / 'deposit'} {ROOT2}"
    dlg = ZenodoDraftsDialog(_Cli(script), tmp_path, deposits=deposits, settings={"zenodo.communities": ["agentprov"]},
                             env={"PATH": "/usr/bin:/bin"})
    assert dlg.chosen_target() == "sandbox" and dlg.communities.text() == "agentprov"
    asked: list[str] = []
    dlg.confirm_cross_link = lambda text: asked.append(text) or True
    dlg.start()
    assert len(asked) == 1 and "drafted from the terminal" in asked[0]
    phrases = ("create unpublished draft on sandbox.zenodo.org",) * 2 + ("link sandbox.zenodo.org",)
    for i, phrase in enumerate(phrases, start=1):
        _wait(lambda i=i: dlg.output.count("Type exactly") >= i, qapp)
        dlg.typed.setText(phrase)
        dlg.send()
        _wait(lambda i=i: dlg.output.count("\nconfirmed") >= i, qapp)
    _wait(lambda: dlg.run is None and not dlg.queue, qapp)
    calls = [json.loads(line) for line in (tmp_path / "fake.py.calls").read_text().splitlines()]
    assert len(calls) == 3 and all(c["tty"] == [True, True] for c in calls)
    assert [c["args"][:3] for c in calls] == [["-I", "-m", "agentprov_zenodo"]] * 3
    assert "--create-draft" in calls[0]["args"] and "--cross-link" in calls[2]["args"]
    assert all("--keychain" in c["args"] for c in calls)
    assert "NOT published" in dlg.output
    dlg.done(0)


@pty_only
def test_a_refused_phrase_stops_the_remaining_runs(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    script = tmp_path / "fake.py"
    script.write_text(FAKE_UPLOADER)
    deposits = f"{tmp_path / 'u' / 'deposit'} {ROOT}\n{tmp_path / 'm' / 'deposit'} {ROOT2}"
    dlg = ZenodoDraftsDialog(_Cli(script), tmp_path, deposits=deposits, env={"PATH": "/usr/bin:/bin"})
    dlg.confirm_cross_link = lambda text: True
    dlg.start()
    _wait(lambda: "Type exactly" in dlg.output, qapp)
    dlg.typed.setText("yes")
    dlg.send()
    _wait(lambda: dlg.run is None, qapp)
    assert "exit 4" in dlg.output and dlg.queue == []
    assert len((tmp_path / "fake.py.calls").read_text().splitlines()) == 1
    dlg.done(0)


def test_declining_the_cross_link_warning_starts_nothing(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    script = tmp_path / "never.py"
    deposits = f"{tmp_path / 'u' / 'deposit'} {ROOT}\n{tmp_path / 'm' / 'deposit'} {ROOT2}"
    dlg = ZenodoDraftsDialog(_Cli(script), tmp_path, deposits=deposits, env={"PATH": "/usr/bin:/bin"})
    dlg.confirm_cross_link = lambda text: False
    dlg.start()
    assert dlg.run is None and dlg.queue == [] and "cross-linking was declined" in dlg.output
    assert not (tmp_path / "never.py.calls").exists()
    dlg.done(0)


def test_bad_input_starts_nothing(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    dlg = ZenodoDraftsDialog(_Cli(tmp_path / "never.py"), tmp_path, deposits=f"{tmp_path} sha256:short")
    dlg.start()
    assert dlg.run is None and "Not started" in dlg.output
    dlg.done(0)


def test_the_production_preselect_comes_from_the_settings(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    dlg = ZenodoDraftsDialog(_Cli(tmp_path / "x.py"), tmp_path, settings={"zenodo.target_preselect": "production"})
    assert dlg.chosen_target() == "production"
    dlg.done(0)


# ================================================================================================ settings and release.toml
STORED = {"zenodo.target_preselect": "production", "zenodo.communities": ["agentprov", "ai-safety"],
          "zenodo.concept_doi": "10.5281/zenodo.99999990", "zenodo.creators.0.name": "Doe, Jane",
          "zenodo.creators.0.orcid": "0000-0002-1694-233X", "zenodo.creators.1.name": "Roe, Rob",
          "zenodo.creators.1.affiliation": "Lab"}


class _SettingsCli:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Any) -> tuple[int, bytes, bytes]:
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"values": STORED}).encode(), b""
        return 0, b"", b""


def test_the_zenodo_pane_shows_and_saves_only_changes(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    from agentprov_gui.ui.zenodo import ZenodoPane

    cli = _SettingsCli()
    pane = ZenodoPane(None, cli=cli)
    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()
    assert pane.isEnabled() and pane.communities.text() == "agentprov, ai-safety"
    assert pane.creators.toPlainText() == "Doe, Jane; 0000-0002-1694-233X\nRoe, Rob; ; Lab"
    assert pane.values() == STORED
    pane.creators.setPlainText("Doe, Jane; 0000-0002-1694-233X")
    pane.target.setCurrentIndex(0)
    pane.save()
    writes = [c for c in cli.calls if c[:1] == ["settings"] and c[1] in ("set", "unset")]
    assert ["settings", "unset", "zenodo.target_preselect"] in writes
    assert ["settings", "unset", "zenodo.creators.1.name"] in writes
    assert not any("token" in " ".join(c).lower() for c in cli.calls)
    pane.deleteLater()


def test_the_release_toml_template_prefills_creators_and_concept_and_keeps_the_title_empty() -> None:
    from agentprov_gui.ui.zenodo import release_toml_template

    doc = tomllib.loads(release_toml_template({**STORED, "zenodo.creators.0.name": 'Doe, "J"\n'}))
    assert doc["title"] == "" and doc["concept_doi"] == "10.5281/zenodo.99999990"
    assert doc["creators"] == [{"name": 'Doe, "J"\n', "orcid": "0000-0002-1694-233X"},
                               {"name": "Roe, Rob", "affiliation": "Lab"}]
    assert tomllib.loads(release_toml_template({}))["creators"] == [{"name": ""}]


def test_the_keys_pane_lists_the_zenodo_tokens(qapp: Any) -> None:
    from agentprov_gui.ui.livepanes import KeysPane

    pane = KeysPane(None, None)
    assert {"ZENODO_SANDBOX_TOKEN", "ZENODO_TOKEN"} <= set(pane.names)
    pane.deleteLater()


def test_the_package_page_writes_release_toml_only_where_none_exists(qapp: Any, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import package

    page = package.PackagePage(lambda spec: None, None)
    monkeypatch.setattr(page, "_zenodo_settings", lambda: (None, dict(STORED)))
    target = tmp_path / "release.toml"
    page.metadata.setText(str(target))
    page.write_release_toml()
    assert tomllib.loads(target.read_text())["creators"][0]["name"] == "Doe, Jane"
    target.write_text("mine")
    page.write_release_toml()
    assert target.read_text() == "mine" and "never overwritten" in page.texts[-1].toPlainText()
    assert page.zenodo_btn.accessibleName() == "Create Zenodo drafts…"
    page.deleteLater()
