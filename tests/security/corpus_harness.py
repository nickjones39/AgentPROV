"""Sealed and working test corpora for the phase-12c security suites (SEC-11, 12, 15, 19, 22, 25, 26; not collected).

``tests/security/conftest.py`` belongs to another session, so this module puts the phase-11 helper modules on the path
itself (``release_support``, ``seal_support``, ``derive_support``, ``purge_support`` from ``tests/unit/{corpus,release}``,
``verify_support`` from ``tests/corpus``, ``import_support``, ``inspect_support`` and ``agentdojo_support`` from
``tests/adapters``, ``render_support`` from ``tests/render``) and defines the fixtures the suites bind:

* :func:`cli` runs ``agentprov`` in-process with a fresh ``$AGENTPROV_HOME`` (no user cache or corpus is ever read; the
  same device as ``tests/corpus/conftest.py``);
* :func:`sealed` is a fresh copy of the sealed three-log test corpus ``mini-mit`` (``release_support``; golden
  licence-cleared fixtures whose text is never printed).

Every corpus lives under ``tmp_path``; nothing under ``~/.agentprov`` is read or written.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, NamedTuple

import pytest

_TESTS = Path(__file__).resolve().parents[1]
for _path in (_TESTS / "adapters", _TESTS / "adapters" / "inspect", _TESTS / "adapters" / "agentdojo", _TESTS / "unit" / "raw",
              _TESTS / "unit" / "corpus", _TESTS / "unit" / "release", _TESTS / "corpus", _TESTS / "render"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


class Run(NamedTuple):
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)

    def codes(self) -> dict[str, int]:
        """``issues_by_code`` of a ``--json`` summary."""
        return dict(self.json()["issues_by_code"])


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory) -> Callable[..., Run]:
    """Run the CLI in-process with a fresh ``$AGENTPROV_HOME``."""
    from agentprov.cli.main import main

    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("agentprov-home")))

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


@pytest.fixture
def sealed(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> Path:
    """A fresh copy of the sealed three-log test corpus ``mini-mit``."""
    import release_support as rs

    return rs.sealed(tmp_path_factory, tmp_path / "corpora")


def verify(cli: Callable[..., Run], root: Path, *flags: str) -> Run:
    return cli("verify", "--corpus", str(root), "--json", *flags)


# ------------------------------------------------------------------------------------------------ T1 worker launch
def is_t1_worker_launch(argv: Any) -> bool:
    """True only for the exact argv :class:`agentprov.io.workers._Worker` builds for a T1 worker: this interpreter,
    ``-I -B -m agentprov.worker --protocol <PROTOCOL> --cpu-hard N --nofile N --as-bytes N``, then optionally
    ``--store-root PATH`` and optionally ``--test-kinds``, in that order and nothing else (G.4; K.12.6(a): a process
    AgentPROV starts with an argv built from no data). A string command, another interpreter, another module, a shell
    or any extra argument is not one."""
    from agentprov.io.workers import PROTOCOL

    if not isinstance(argv, (list, tuple)) or not all(isinstance(a, str) for a in argv):
        return False
    head = [sys.executable, "-I", "-B", "-m", "agentprov.worker", "--protocol", PROTOCOL]
    if list(argv[: len(head)]) != head or len(argv) < len(head) + 6:
        return False
    numbers = argv[len(head): len(head) + 6]
    if [numbers[0], numbers[2], numbers[4]] != ["--cpu-hard", "--nofile", "--as-bytes"] or not all(
            n.isascii() and n.isdigit() for n in (numbers[1], numbers[3], numbers[5])):
        return False
    rest = list(argv[len(head) + 6:])
    if rest[:1] == ["--store-root"]:
        if len(rest) < 2 or not rest[1] or rest[1].startswith("-"):
            return False
        rest = rest[2:]
    return rest in ([], ["--test-kinds"])


# ------------------------------------------------------------------------------------------------ open spy
#: The marker every sentinel file outside a corpus carries in its name; :class:`OpenSpy` records opens of such paths.
SENTINEL: Final = "SENTINEL-outside"
_SPIES: list[list[str]] = []
_HOOKED = False


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if _SPIES and event in ("open", "os.listdir", "os.scandir") and args:
        path = args[0]
        text = os.fsdecode(path) if isinstance(path, (str, bytes, os.PathLike)) else ""
        if SENTINEL in text:
            for spy in _SPIES:
                spy.append(f"{event} {text}")


class OpenSpy:
    """Record every ``open`` (and directory listing) of a path whose name holds :data:`SENTINEL`, through CPython's
    audit hooks (``open`` is raised by ``open()``, ``os.open`` and ``io.open``; a hook cannot be removed, so one hook
    is installed once and is inert outside a spy)."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def __enter__(self) -> OpenSpy:
        global _HOOKED
        if not _HOOKED:
            sys.addaudithook(_audit)
            _HOOKED = True
        _SPIES.append(self.events)
        return self

    def __exit__(self, *exc: object) -> None:
        _SPIES.remove(self.events)


def sentinel(directory: Path, data: bytes, name: str = "") -> Path:
    """A file outside every corpus whose name carries :data:`SENTINEL`."""
    path = directory / f"{SENTINEL}{name or '.json'}"
    path.write_bytes(data)
    return path


# ------------------------------------------------------------------------------------------------ synthetic sources
INSPECT_LABEL: Final = "agentharm/results/synthetic/2026-08-21T00-00-00-00-00_agentharm_Synthetic.eval"


def inspect_working(base: Path, *, mode: str, samples: int = 1, **kwargs: Any) -> Path:
    """A working corpus of one synthetic Inspect ``.eval`` (an archive container, ``samples`` samples) imported at
    ``base/c.partial`` under the survey AgentHarm profile; returns ``base/c``. Nothing is read from fixtures."""
    import import_support as support
    import inspect_support as isp

    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    source = base / "in"
    (source / INSPECT_LABEL).parent.mkdir(parents=True)
    data = isp.build_eval(isp.synthetic_header(), {f"s{n}_epoch_1.json": isp.basic_sample(f"s{n}")
                                                   for n in range(1, samples + 1)})
    (source / INSPECT_LABEL).write_bytes(data)
    pin = {"commit": support.SURVEY_COMMIT, "kind": "git", "repo": support.SURVEY, "role": "git", "tree": "agentharm/results"}
    if mode == "release":
        kwargs.setdefault("workers", 1)
    else:
        kwargs.setdefault("in_process", True)
    with CorpusWriter(base / "c") as writer:
        report = import_source("agent-security-tools-survey", LocalTree(source), corpus=writer, part="agentharm",
                               mode=mode, pin=pin, pin_check=support.vouch(source, repo=support.SURVEY,
                                                                          commit=support.SURVEY_COMMIT), **kwargs)
    assert report.counters["mapped"] == samples, report.counters
    return base / "c"
