"""D-1130 review (B1): a bundle that lacks the core's source files or the metadata of a recorded distribution never
records a code digest. Its own agentprov refuses every command outside ``SAFE_WITHOUT_SOURCES`` (exit 3), by ``--cli``
and by ``-m agentprov``, and runs the others; an ordinary interpreter is never checked. The console streams Windows
attaches are UTF-8 and never raise on a character the console lacks."""

from __future__ import annotations

import io
import sys
import types
from pathlib import Path

import pytest

from agentprov.cli import frozen
from agentprov.cli.main import build_parser


def _loader(calls: list[list[str]]):
    def load(name: str) -> object:
        mod = types.ModuleType(name)

        def main(args: list[str] | None = None) -> int:
            calls.append(list(args or []))
            return 0

        mod.main = main  # type: ignore[attr-defined]
        return mod

    return load


def test_sources_problem_names_what_is_missing(tmp_path: Path) -> None:
    assert frozen.sources_problem(root=tmp_path, version=lambda n: "1") == "the core's source files"
    real = Path(frozen.__file__).resolve().parents[1]

    def version(name: str) -> str:
        if name in ("prov", "PyYAML"):
            raise LookupError(name)
        return "1"

    assert frozen.sources_problem(root=real, version=version) == "the package metadata of prov, PyYAML"
    assert frozen.sources_problem() is None  # this development environment has both


@pytest.mark.parametrize("argv", [["--cli", "derive", "--corpus", "c", "--out", "o"], ["--cli", "-v", "import", "x"],
                                  ["-I", "-m", "agentprov", "recompute", "--corpus", "c", "--dry-run"],
                                  ["--cli", "validate", "--corpus", "c"], ["--cli", "package", "--corpus", "c"]])
def test_a_bundle_without_its_sources_refuses_what_records_a_digest(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls: list[list[str]] = []
    err = io.StringIO()
    code = frozen.dispatch(argv, load=_loader(calls), err=err.write, problem=lambda: "the core's source files")
    assert code == 3 and calls == []
    assert "lacks the core's source files" in err.getvalue() and "refused" in err.getvalue()


@pytest.mark.parametrize("argv", [["--cli", "info"], ["--cli", "update", "install"], ["--cli", "--version"],
                                  ["--cli", "jobs", "list"], ["--cli", "launcher", "status"], ["--cli", "no-such"]])
def test_commands_that_record_no_digest_still_run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls: list[list[str]] = []
    assert frozen.dispatch(argv, load=_loader(calls), err=lambda t: None, problem=lambda: "x") == 0
    assert calls == [argv[1:]]


def test_an_ordinary_interpreter_is_never_checked(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    calls: list[list[str]] = []

    def boom() -> str:
        raise AssertionError("checked")

    assert frozen.dispatch(["--cli", "derive"], load=_loader(calls), err=lambda t: None, problem=boom) == 0


def test_a_complete_bundle_runs_everything(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls: list[list[str]] = []
    assert frozen.dispatch(["--cli", "derive"], load=_loader(calls), err=lambda t: None, problem=lambda: None) == 0
    assert calls == [["derive"]]


def test_the_safe_commands_are_real_commands() -> None:
    parser = build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    names = set(action.choices)  # type: ignore[arg-type]
    assert frozen.SAFE_WITHOUT_SOURCES <= names
    for unsafe in ("import", "run", "derive", "recompute", "validate", "package", "verify", "purge", "migrate",
                   "fetch", "devrun", "render"):
        assert unsafe in names and unsafe not in frozen.SAFE_WITHOUT_SOURCES


def test_the_console_streams_are_utf8_and_never_raise(tmp_path: Path) -> None:
    target = tmp_path / "console.txt"
    stream = frozen._open_console(str(target), "w")
    try:
        stream.write("agentprov 0.2.1 → 0.2.2 › done…\n")  # type: ignore[attr-defined]
    finally:
        stream.close()  # type: ignore[attr-defined]
    assert target.read_text(encoding="utf-8") == "agentprov 0.2.1 → 0.2.2 › done…\n"
