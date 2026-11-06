"""D-1130: the checkout shortcut (``git pull --ff-only`` + ``uv sync --frozen --group docs``, only for a clean ``main``
with the project's remote) and the desktop bundle's own agentprov (``AgentPROV --cli``, the ``-I -m`` forms, the
Windows helper's copy). git is faked except in one local test, which opens no connection."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from agentprov.cli import frozen as F
from agentprov.cli import update as update_cmd
from agentprov.cli.main import main
from agentprov.update import checkout as C
from agentprov.update import install as I
from agentprov.update.releases import UpdateError
from agentprov.versions import __version__

ROOT = Path(__file__).resolve().parents[2]
GIT = shutil.which("git")


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv, "--progress", "off"])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "AgentPROV"
    (root / "src" / "agentprov").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "agentprov"\nversion = "0.2.1"\n')
    return root


class FakeGit:
    """git and uv as the shortcut calls them: answers per subcommand, and a log of every argv."""

    def __init__(self, **answers: Any) -> None:
        self.answers = {"symbolic-ref": (0, "main\n"), "rev-parse HEAD": (0, "a" * 40 + "\n"),
                        "@{upstream}": (0, "origin/main\n"), "get-url": (0, "https://github.com/nickjones39/AgentPROV.git\n"),
                        "status": (0, ""), "fetch": (0, ""), "rev-list": (0, "0\n"), "merge": (0, ""),
                        "sync": (0, ""), "diff": (0, ""), **answers}
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(argv))
        assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0" and not any(k.startswith("GIT_DIR") for k in kw["env"])
        words = " ".join(argv[3:] if argv[1:2] == ["-C"] else argv[1:])  # not the folder (a test's name is in it)
        assert "pull" not in argv and "reset" not in argv and "stash" not in argv and "checkout" not in argv[1:]
        key = next(k for k in ("symbolic-ref", "@{upstream}", "get-url", "status", "fetch", "rev-list", "merge",
                               "sync", "diff", "rev-parse HEAD") if k in words)
        code, out = self.answers[key]
        if key == "merge" and code == 0:
            self.answers["rev-parse HEAD"] = (0, "b" * 40 + "\n")
        return subprocess.CompletedProcess(argv, code, out.encode(), b"")


def _which(name: str) -> str | None:
    return f"/usr/bin/{name}"


# ---------------------------------------------------------------------------------------------- the conditions


@pytest.mark.parametrize(("answers", "which", "why"), [
    ({}, _which, None),
    ({"status": (0, " M src/agentprov/x.py\n")}, _which, "has changes"),
    ({"status": (0, "?? notes.txt\n")}, _which, "has changes or untracked files"),
    ({"symbolic-ref": (0, "feature\n")}, _which, "not on main (it is on feature)"),
    ({"symbolic-ref": (1, "")}, _which, "a detached HEAD"),
    ({"@{upstream}": (0, "fork/main\n")}, _which, "upstream is not origin/main"),
    ({"get-url": (0, "https://github.com/someone/AgentPROV.git\n")}, _which, "project's GitHub repositories"),
    ({"get-url": (0, "https://evil.example/nickjones39/AgentPROV.git\n")}, _which, "project's GitHub repositories"),
    ({"rev-list": (0, "2\n")}, _which, "local main has 2 commits that origin/main lacks"),
    ({}, lambda n: None if n == "git" else "/bin/uv", "git is not on PATH"),
    ({}, lambda n: None if n == "uv" else "/bin/git", "uv is not on PATH"),
])
def test_the_shortcut_applies_only_to_a_clean_main_of_the_projects_remote(tmp_path: Path, answers: dict[str, Any],
                                                                           which: Any, why: str | None) -> None:
    git = FakeGit(**answers)
    facts = C.inspect_checkout(_checkout(tmp_path), run=git, which=which)
    assert facts["ok"] is (why is None) and (why is None or why in facts["why"]), facts
    assert not any("fetch" in c or "merge" in c for c in git.calls)  # the inspection never reaches the network


@pytest.mark.parametrize("url", ["https://github.com/nickjones39/AgentPROV", "git@github.com:nickjones39/agentprov-framework.git",
                                 "ssh://git@github.com/nickjones39/AgentPROV.git"])
def test_the_projects_remotes_are_accepted_over_https_and_ssh(tmp_path: Path, url: str) -> None:
    assert C.inspect_checkout(_checkout(tmp_path), run=FakeGit(**{"get-url": (0, url)}), which=_which)["ok"]


def test_a_folder_that_is_not_an_agentprov_checkout_is_left_alone(tmp_path: Path) -> None:
    root = tmp_path / "other"
    (root / "src" / "agentprov").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "something-else"\n')
    git = FakeGit()
    assert C.inspect_checkout(root, run=git, which=_which)["why"] == "the folder is not an AgentPROV checkout"
    assert git.calls == []


def test_update_checkout_fast_forwards_then_syncs(tmp_path: Path) -> None:
    root, git = _checkout(tmp_path), FakeGit()
    done = C.update_checkout(root, run=git, which=_which, version=lambda: "9.0.0")
    assert ["/usr/bin/git", "-C", str(root), "fetch", "origin", "main"] in git.calls
    assert ["/usr/bin/git", "-C", str(root), "merge", "--ff-only", "FETCH_HEAD"] in git.calls
    assert git.calls[-1] == ["/usr/bin/uv", "sync", "--frozen", "--group", "docs", "--project", str(root)]
    assert (done["from_commit"], done["to_commit"], done["changed"], done["synced"]) == ("a" * 40, "b" * 40, True, True)
    assert done["restore"][0] == ["git", "-C", str(root), "reset", "--keep", "a" * 40]


def test_the_sync_names_every_installed_extra_again(tmp_path: Path) -> None:
    """D-1130 review: uv sync is exact; an extra it is not given (live's python-dotenv, render's pydot) is removed."""
    root, git = _checkout(tmp_path), FakeGit()
    done = C.update_checkout(root, run=git, which=_which, extras=["live", "render"])
    assert git.calls[-1] == ["/usr/bin/uv", "sync", "--frozen", "--group", "docs", "--extra", "live", "--extra",
                             "render", "--project", str(root)]
    assert done["restore"][1] == ["uv", "sync", "--frozen", "--group", "docs", "--extra", "live", "--extra", "render",
                                  "--project", str(root)]
    assert done["extras"] == ["live", "render"]


def test_installed_extras_are_those_whose_every_requirement_is_here() -> None:
    requires = ['rfc8785>=0.1', 'python-dotenv>=1.2.2; extra == "live"', "pydot>=4.0.1 ; extra == 'render'",
                'pyshacl>=0.40.1; extra == "shacl"', 'agentprov-zenodo==0.2.1; extra == "zenodo"',
                'a; extra == "two"', 'b; extra == "two"']
    have = {"python-dotenv", "pydot", "a"}
    assert C.installed_extras(requires=requires, installed=lambda n: n in have) == ["live", "render"]
    assert C.installed_extras(requires=[], installed=lambda n: True) == []


def test_a_program_outside_the_checkouts_venv_is_not_synced_behind_its_back(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / ".venv").mkdir()
    assert C.inspect_checkout(root, run=FakeGit(), which=_which, prefix=root / ".venv")["ok"]
    facts = C.inspect_checkout(root, run=FakeGit(), which=_which, prefix=tmp_path / "elsewhere")
    assert not facts["ok"] and "not the checkout's .venv" in facts["why"]


def test_an_ignored_file_the_merge_would_overwrite_refuses_before_the_merge(tmp_path: Path) -> None:
    """D-1130 review: git overwrites an ignored file when a fetched commit adds that path; a clean status hides it."""
    root = _checkout(tmp_path)
    (root / "notes").mkdir()
    (root / "notes" / "mine.md").write_text("local")
    git = FakeGit(diff=(0, "src/agentprov/new.py\0notes/mine.md\0"))
    with pytest.raises(UpdateError) as exc:
        C.update_checkout(root, run=git, which=_which)
    assert exc.value.code == "update.checkout.refused" and "notes/mine.md" in str(exc.value)
    assert "new.py" not in str(exc.value)
    assert not any("merge" in c or "sync" in c for c in git.calls)
    assert (root / "notes" / "mine.md").read_text() == "local"
    diff = next(c for c in git.calls if "diff" in c)
    assert diff[3:] == ["diff", "--no-renames", "--name-only", "--diff-filter=A", "-z", "HEAD", "FETCH_HEAD"]
    with pytest.raises(UpdateError) as failed:
        C.update_checkout(root, run=FakeGit(diff=(128, "")), which=_which)
    assert failed.value.code == "update.checkout.pull"


@pytest.mark.parametrize("answers", [{"fetch": (1, "")}, {"merge": (128, "")}])
def test_a_failed_fetch_or_a_diverged_main_changes_nothing_and_never_syncs(tmp_path: Path,
                                                                          answers: dict[str, Any]) -> None:
    git = FakeGit(**answers)
    with pytest.raises(UpdateError) as exc:
        C.update_checkout(_checkout(tmp_path), run=git, which=_which)
    assert exc.value.code == "update.checkout.pull" and not any("sync" in c for c in git.calls)


def test_commits_origin_lacks_after_the_fetch_are_never_put_at_risk(tmp_path: Path) -> None:
    git = FakeGit()
    real = git.__call__

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        if "fetch" in argv:  # the fetch shows that origin/main was rewound under the local commits
            git.answers["rev-list"] = (0, "1\n")
        return real(argv, **kw)

    with pytest.raises(UpdateError) as exc:
        C.update_checkout(_checkout(tmp_path), run=run, which=_which)
    assert exc.value.code == "update.checkout.refused" and not any("merge" in c for c in git.calls)


def test_a_dirty_tree_is_refused_before_any_git_write(tmp_path: Path) -> None:
    git = FakeGit(status=(0, " M x\n"))
    with pytest.raises(UpdateError) as exc:
        C.update_checkout(_checkout(tmp_path), run=git, which=_which)
    assert exc.value.code == "update.checkout.refused" and not any("fetch" in c for c in git.calls)


@pytest.mark.skipif(GIT is None, reason="git is not installed")
def test_a_real_local_checkout_is_inspected_without_the_network(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

    def git(*args: str) -> None:
        subprocess.run([GIT, "-C", str(root), *args], check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-q", "-m", "x")
    git("remote", "add", "origin", "https://github.com/nickjones39/AgentPROV.git")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("config", "branch.main.remote", "origin")
    git("config", "branch.main.merge", "refs/heads/main")
    which = lambda n: GIT if n == "git" else "/bin/uv"  # noqa: E731
    assert C.inspect_checkout(root, which=which)["ok"] is True
    (root / "scratch.txt").write_text("x")
    assert "untracked" in C.inspect_checkout(root, which=which)["why"]


@pytest.mark.skipif(GIT is None, reason="git is not installed")
def test_an_ignored_file_a_fetched_rename_or_copy_would_overwrite_is_found(tmp_path: Path) -> None:
    """git's diff detects renames by default (and copies under diff.renames=copies): a fetched commit that renames a
    tracked file onto a local ignored file shows as R, not A, and the merge overwrites that file all the same."""
    root = tmp_path / "repo"
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

    def git(*args: str) -> str:
        return subprocess.run([GIT, "-C", str(root), *args], check=True, capture_output=True, env=env,
                              text=True).stdout.strip()

    body = "".join(f"line {i} of a file long enough for git to see a rename\n" for i in range(40))
    git("init", "-q", "-b", "main")
    git("config", "diff.renames", "copies")  # a user's setting: copies are hidden from an A filter too
    (root / ".gitignore").write_text("b.txt\nc.txt\n")
    (root / "a.txt").write_text(body)
    (root / "keep.txt").write_text(body.upper())
    git("add", ".")
    git("commit", "-q", "-m", "a")
    first = git("rev-parse", "HEAD")
    git("rm", "-q", "--cached", "a.txt")
    (root / "a.txt").rename(root / "b.txt")
    (root / "c.txt").write_text(body.upper())
    git("add", "-f", "b.txt", "c.txt")
    git("commit", "-q", "-m", "rename and copy")
    fetched = git("rev-parse", "HEAD")
    git("reset", "-q", "--hard", first)
    (root / "b.txt").write_text("precious, ignored")
    (root / "c.txt").write_text("precious too")
    (root / ".git" / "FETCH_HEAD").write_text(f"{fetched}\t\tbranch 'main' of x\n")
    assert sorted(C._ignored_in_the_way(GIT, root, subprocess.run) or []) == ["b.txt", "c.txt"]


def test_the_checkout_root_comes_from_the_editable_install(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    doc = {"url": root.as_uri(), "dir_info": {"editable": True}}
    assert C.checkout_root(json.dumps(doc)) == root
    assert C.checkout_root(json.dumps({**doc, "dir_info": {}})) is None
    assert C.checkout_root(json.dumps({**doc, "url": "https://example.org/x"})) is None


# ---------------------------------------------------------------------------------------------- the CLI


@pytest.fixture
def as_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, FakeGit]:
    root, git = _checkout(tmp_path), FakeGit()
    monkeypatch.setattr(update_cmd, "KIND", lambda: {"kind": "checkout", "command": None, "text": "use git"})
    monkeypatch.setattr(update_cmd, "CHECKOUT_ROOT", lambda: root)
    monkeypatch.setattr(update_cmd, "GIT_RUN", git)
    monkeypatch.setattr(update_cmd, "WHICH", _which)
    monkeypatch.setattr(update_cmd, "HAVE", lambda name: ("9.0.0", []) if name == "agentprov" else None)
    monkeypatch.setattr(update_cmd, "PREFIX", lambda: str(root / ".venv"))
    monkeypatch.setattr(update_cmd, "EXTRAS", lambda: ["live", "render"])
    return root, git


def test_install_checkout_needs_confirm_and_the_network_flag(cli, as_checkout) -> None:
    root, git = as_checkout
    assert cli("update", "install", "--checkout").code == 4
    no_net = cli("update", "install", "--checkout", "--confirm")
    assert no_net.code == 4 and "--allow-network" in no_net.err
    assert not any("pull" in c for c in git.calls)
    run = cli("update", "install", "--checkout", "--confirm", "--allow-network", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert (doc["kind"], doc["action"], doc["from_version"], doc["to_version"], doc["synced"]) == (
        "checkout", "installed", __version__, "9.0.0", True)
    assert any("reset --keep" in line for line in doc["lines"])


def test_the_plan_offers_the_checkout_shortcut_or_says_why_not(cli, as_checkout) -> None:
    _root, git = as_checkout
    doc = json.loads(cli("update", "install", "--format", "json").out)
    assert doc["automatic"]["how"] == "checkout" and doc["automatic"]["available"] is True
    assert doc["automatic"]["argv"] == ["update", "install", "--checkout", "--confirm", "--allow-network"]
    git.answers["status"] = (0, " M x\n")
    doc = json.loads(cli("update", "install", "--format", "json").out)
    assert doc["automatic"]["available"] is False and "never touched" in doc["automatic"]["why"]
    assert any("cannot do it here" in line for line in doc["lines"])


def test_install_checkout_is_refused_for_a_package_install(cli, monkeypatch) -> None:
    monkeypatch.setattr(update_cmd, "KIND", lambda: {"kind": "pip", "command": ["x"], "text": "pip"})
    run = cli("update", "install", "--checkout", "--confirm", "--allow-network")
    assert run.code == 4 and "update.checkout.kind" in run.err


# ---------------------------------------------------------------------------------------------- the bundle's agentprov


class Loaded:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def __call__(self, name: str) -> Any:
        calls = self.calls

        class Module:
            @staticmethod
            def main(*args: Any) -> int:
                calls.append((name, args[0] if args else sys.argv[:]))
                return 7

        return Module


@pytest.mark.parametrize(("argv", "module", "args"), [
    (["--cli", "info", "--format", "json"], "agentprov.cli.main", ["info", "--format", "json"]),
    (["-I", "-m", "agentprov", "jobs", "list"], "agentprov.cli.main", ["jobs", "list"]),
    (["-I", "-m", "agentprov.jobs.supervisor", "/j"], "agentprov.jobs.supervisor", ["/j"]),
    (["-I", "-B", "-m", "agentprov.worker", "--protocol", "1"], "agentprov.worker", ["--protocol", "1"]),
    (["-I", "-m", "agentprov.update.apply", "/p.json"], "agentprov.update.apply", ["/p.json"]),
    (["-I", "-m", "agentprov.keys.helper"], "agentprov.keys.helper", ["agentprov.keys.helper"]),
    (["--keychain-helper"], "agentprov.keys.helper", ["agentprov.keys.helper"]),
])
def test_the_bundle_answers_the_cli_forms_the_core_starts(argv: list[str], module: str, args: list[str],
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", list(sys.argv))  # dispatch sets the module's argv, as python -m does
    load = Loaded()
    assert F.dispatch(argv, load=load) == 7 and load.calls == [(module, args)]


@pytest.mark.parametrize("argv", [["-c", "import os"], ["-I", "-B", "-c", "pass"], ["-I", "-m", "os"],
                                  ["-I", "/repo/tools/suite_queue.py"], ["-I"], ["-m"], ["--keychain-helper", "x"]])
def test_the_bundle_is_not_a_general_interpreter(argv: list[str]) -> None:
    load, said = Loaded(), []
    assert F.dispatch(argv, load=load, err=said.append) == 2 and load.calls == [] and said


@pytest.mark.parametrize("argv", [[], ["--smoke"], ["--preview-helper", "/h"], ["/Users/x/corpus"]])
def test_anything_else_starts_the_desktop_app(argv: list[str]) -> None:
    assert F.dispatch(argv, load=Loaded()) is None and not F.is_cli_call(argv)


def test_every_module_the_core_starts_with_this_interpreter_is_answered_by_the_bundle() -> None:
    """The ``sys.executable ... -m MODULE`` argv in the core: each MODULE is one the bundle runs (a new one must be
    added to ``agentprov.cli.frozen.MODULES``, or the bundled agentprov would start the GUI in its place)."""
    started: set[str] = set()
    for path in (ROOT / "src" / "agentprov").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.List):
                items = [e.value if isinstance(e, ast.Constant) else None for e in node.elts]
                for i, item in enumerate(items[:-1]):
                    if item == "-m" and isinstance(items[i + 1], str) and items[i + 1].startswith("agentprov"):
                        started.add(items[i + 1])
    assert {"agentprov", "agentprov.jobs.supervisor", "agentprov.worker", "agentprov.update.apply"} <= started
    assert started <= set(F.MODULES), sorted(started - set(F.MODULES))


def test_the_windows_helper_of_the_bundles_own_agentprov_runs_from_a_copy(tmp_path: Path, home: Path) -> None:
    apps = tmp_path / "apps"
    bundle = apps / "AgentPROV"
    bundle.mkdir(parents=True)
    (bundle / "AgentPROV.exe").write_bytes(b"MZ old")
    stage = apps / I.STAGE_DIR
    new = stage / "new" / "AgentPROV"
    new.mkdir(parents=True)
    (new / "AgentPROV.exe").write_bytes(b"MZ new")
    plan = I._plan(stage, home, op="install", bundle=bundle, previous=apps / I.PREVIOUS_DIR / "AgentPROV", new=new,
                   record={})
    assert I.helper_argv(plan, frozen=False)[:4] == [sys.executable, "-I", "-m", "agentprov.update.apply"]
    argv = I.helper_argv(plan, frozen=True, running=bundle)  # the running bundle: it wrote the plan, so it reads it
    copy = apps / I.HELPER_DIR / "AgentPROV" / "AgentPROV.exe"
    assert argv == [str(copy), "-I", "-m", "agentprov.update.apply", str(plan)] and copy.read_bytes() == b"MZ old"
    assert not str(copy).startswith(str(bundle) + os.sep) and not str(copy).startswith(str(new))
    assert I.helper_argv(plan, frozen=True, running=bundle) == argv  # a leftover copy of this program's is replaced
    # a rollback to a bundle older than D-1130 (0.2.0's executable opens the app for -m): the helper is still a copy
    # of the running bundle, never of the one restored
    previous = apps / I.PREVIOUS_DIR / "AgentPROV"
    previous.mkdir(parents=True)
    (previous / "AgentPROV.exe").write_bytes(b"MZ 0.2.0")
    back = I._plan(stage, home, op="rollback", bundle=bundle, previous=previous, new=None, record={})
    assert I.helper_argv(back, frozen=True, running=bundle)[0] == str(copy) and copy.read_bytes() == b"MZ old"
    with pytest.raises(UpdateError) as missing:
        I.helper_argv(back, frozen=True, running=tmp_path / "nowhere")
    assert missing.value.code == "update.install.stage"
    shutil.rmtree(apps / I.HELPER_DIR)
    (apps / I.HELPER_DIR).mkdir()
    (apps / I.HELPER_DIR / "mine.txt").write_text("x")
    with pytest.raises(UpdateError) as exc:
        I.helper_argv(plan, frozen=True, running=bundle)  # a folder this program did not make is never removed
    assert exc.value.code == "update.install.stage" and (apps / I.HELPER_DIR / "mine.txt").is_file()


def test_the_bundles_own_agentprov_says_it_is_updated_with_the_app(cli, monkeypatch) -> None:
    monkeypatch.setattr(update_cmd, "KIND", lambda: I.package_install(frozen=True))
    doc = json.loads(cli("update", "install", "--format", "json").out)
    assert doc["kind"] == "bundle" and doc["automatic"]["how"] == "bundle" and doc["automatic"]["available"] is False
    run = cli("update", "download", "--package", "--allow-network")
    assert run.code == 4 and "update.package.kind" in run.err


def test_on_windows_the_cli_attaches_to_the_parent_console_only_for_missing_streams(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """A GUI-subsystem bundle started from cmd has no streams (None); a pipe from the app or a job is kept."""
    opened: list[tuple[str, str]] = []

    def reopen(name: str, mode: str) -> str:
        opened.append((name, mode))
        return f"<{name}>"

    assert F.attach_console(platform="darwin", attach=lambda: True, reopen=reopen) == []
    for name in ("stdout", "stderr", "stdin"):
        monkeypatch.setattr(sys, name, getattr(sys, name))
    assert F.attach_console(platform="win32", attach=lambda: True, reopen=reopen) == [] and not opened  # piped
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stdin", None)
    assert F.attach_console(platform="win32", attach=lambda: False, reopen=reopen) == []  # no parent console
    assert F.attach_console(platform="win32", attach=lambda: True, reopen=reopen) == ["stdout", "stdin"]
    assert opened == [("CONOUT$", "w"), ("CONIN$", "r")] and sys.stdout == "<CONOUT$>"


# ---------------------------------------------------------------------------------------------- no update under a job


class _Job:
    def __init__(self, job_id: str, argv: list[str], state: str = "running", label: str = "import x") -> None:
        self.job_id, self.state, self.command = job_id, state, "import"
        self.record = {"label": label, "argv": argv}
        self.argv = argv


def test_jobs_using_names_only_running_jobs_inside_the_folder(tmp_path: Path, home: Path) -> None:
    from agentprov.update.busy import jobs_using

    app = tmp_path / "AgentPROV.app"
    exe = app / "Contents" / "MacOS" / "AgentPROV"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    other = tmp_path / "AgentPROV.app.old" / "x"  # a sibling whose name starts the same is not inside
    jobs = [_Job("j1", [str(exe), "-I", "-m", "agentprov", "import"]), _Job("j2", [str(exe)], state="ended"),
            _Job("j3", [str(other)]), _Job("j4", ["agentprov", "relative"])]
    got = jobs_using(home, [app], jobs=lambda _h: jobs)
    assert [j["job_id"] for j in got] == ["j1"]


def test_a_venv_interpreter_link_counts_as_inside_the_checkout(tmp_path: Path, home: Path) -> None:
    from agentprov.update.busy import jobs_using

    root = _checkout(tmp_path)
    real = tmp_path / "uv-python" / "python3.14"
    real.parent.mkdir()
    real.write_bytes(b"x")
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").symlink_to(real)
    jobs = [_Job("j1", [str(root / ".venv" / "bin" / "python"), "-I", "-m", "agentprov.jobs.supervisor"])]
    assert [j["job_id"] for j in jobs_using(home, [root], jobs=lambda _h: jobs)] == ["j1"]


def test_the_checkout_is_not_pulled_under_a_running_job(cli, as_checkout, monkeypatch: pytest.MonkeyPatch) -> None:
    root, git = as_checkout
    job = _Job("01a1b019-d567-702d", [str(root / ".venv" / "bin" / "python"), "-I", "-m", "agentprov"],
               label="derive" + chr(0x202E) + " evil")
    monkeypatch.setattr(update_cmd, "JOBS", lambda _h: [job])
    run = cli("update", "install", "--checkout", "--confirm", "--allow-network")
    assert run.code == 4 and "update.install.busy" in run.err and "01a1b019-d567" in run.err
    assert chr(0x202E) not in run.err and "jobs stop" in run.err  # the label is shown escaped
    assert not any("fetch" in c or "sync" in c for c in git.calls)
    job.state = "ended"
    assert cli("update", "install", "--checkout", "--confirm", "--allow-network").code == 0


def test_the_bundle_is_not_swapped_under_a_job_its_own_agentprov_runs(cli, monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Path, home: Path) -> None:
    import update_support as us
    from agentprov.update import releases as R

    bundle = tmp_path / "apps" / "AgentPROV"
    (bundle / "_internal").mkdir(parents=True)
    (bundle / "AgentPROV").write_text("#!/bin/sh\necho 0.1.1\n")
    (bundle / "AgentPROV").chmod(0o755)
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", "9.0.0")
    name = "AgentPROV-linux-x86_64.tar.gz"
    import hashlib

    files = {name: archive.read_bytes()}
    files["SHA256SUMS"] = f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n".encode()
    routes: dict[str, Any] = {R.API_URL: us.answer(us.release("v9.0.0", [(n, len(b)) for n, b in files.items()]))}
    routes.update({f"{us.REPO_DL}/v9.0.0/{n}": b for n, b in files.items()})
    empty = tmp_path / "signers"
    empty.write_text("# none\n")
    monkeypatch.setattr(update_cmd, "SIGNERS", empty)
    monkeypatch.setattr(update_cmd, "transport", lambda: us.FakeTransport(routes))
    assert cli("update", "download", "--allow-network", "--platform", "linux-x86_64").code == 0
    monkeypatch.setattr(update_cmd, "JOBS", lambda _h: [_Job("job-1", [str(bundle / "AgentPROV"), "--cli", "x"])])
    for argv in (("install", "--confirm"), ("rollback", "--yes")):
        run = cli("update", *argv, "--bundle", str(bundle), "--platform", "linux-x86_64")
        assert run.code == 4 and "update.install.busy" in run.err, run.err
    assert "0.1.1" in (bundle / "AgentPROV").read_text()
