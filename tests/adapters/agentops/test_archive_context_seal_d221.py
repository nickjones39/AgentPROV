"""D-221 with D-530 (pre-round review PR-1): an archive context tree, resolved the way the CLI resolves a download pin
(an ``ArchiveTree`` with no ``PinCheck``), seals as ``agentprov-corpus/0.2`` end to end.

The CLI hands the importer every download context pin, and a git pin read from the fetch cache, without a ``PinCheck``:
those trees verify themselves (the archive by sha256 and size against the pin; each cached blob by its SHA-1). Before
the fix the importer recorded ``verification: null`` for them, and ``package`` (D-221) refused every such corpus. Here
the AgentOps fixture is imported with its ``tasks`` tree as a Zenodo zip; the zip holds an account path in a selected
task file and in an unselected member, so sealing also exercises the D-608 withholding of the context archive. The
corpus must seal, keep the context tree and its archive input, hold the account path in no sealed byte, and pass
``verify --level chain --release``.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

import agentops_support


def _load_e2e() -> Any:
    """This family's ``test_withhold_e2e`` by its path: other families have a module of the same name on ``sys.path``."""
    import importlib.util

    path = Path(__file__).resolve().parent / "test_withhold_e2e.py"
    spec = importlib.util.spec_from_file_location("agentops_test_withhold_e2e", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e2e = _load_e2e()

TASKS_FILE = "supp.zip"


def _tasks_zip(path: Path) -> dict[str, Any]:
    tasks = dict(agentops_support.tasks_files())
    first = sorted(tasks)[0]
    tasks[first] = tasks[first] + f"\n# notes: {e2e.HOME}/work/tasks\n".encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in [*sorted(tasks.items()), ("README.md", f"built in {e2e.HOME}/proj/\n".encode())]:
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
    data = buf.getvalue()
    path.write_bytes(data)
    return {"role": "tasks", "kind": "zenodo", "doi": "10.5281/zenodo.9", "file": TASKS_FILE,
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


@pytest.fixture
def imported(tmp_path: Path) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, ContextTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    pin, _digests = e2e._tar(tmp_path / e2e.PIN_FILE)
    tasks_pin = _tasks_zip(tmp_path / TASKS_FILE)
    tree = ArchiveTree(tmp_path / e2e.PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    context = ArchiveTree(tmp_path / TASKS_FILE, pin=tasks_pin, sha256=tasks_pin["sha256"], size=tasks_pin["bytes"])
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("agentops-bench", tree, corpus=writer, profile_id=e2e.PROFILE, part="pilot-v1-seeded",
                               pin=pin, workers=1, mode="release",
                               context_trees=[ContextTree("tasks", context, None, pin=tasks_pin)])  # the CLI's route
    assert report.exit_code == 0, report.counters
    return {"root": tmp_path / "c", "partial": tmp_path / "c.partial", "tasks_pin": tasks_pin}


def test_the_import_records_how_the_archive_vouched_for_the_context_files(imported):
    snapshot = json.loads((imported["partial"] / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    (context,) = snapshot["context"]
    assert context["stored"] > 0
    assert context["verification"] == {"kind": "download", "verified": context["stored"], "unverified": 0}


def test_the_corpus_seals_with_its_context_withholds_the_path_and_verifies(imported):
    from agentprov.cli.main import main

    e2e._seal(imported)
    root: Path = imported["root"]
    manifest = json.loads((root / "corpus.json").read_text())
    assert manifest["format"] == "agentprov-corpus/0.2"
    (context,) = manifest["sources"][0]["snapshots"][0]["context"]
    tasks_pin = imported["tasks_pin"]
    assert context["role"] == "tasks" and context["verification"]["kind"] == "download"
    assert context["origin"] == {"kind": "zenodo", "doi": tasks_pin["doi"], "file": TASKS_FILE}
    assert context["input"] == {"kind": "archive", "label": TASKS_FILE, "sha256": "sha256:" + tasks_pin["sha256"],
                                "bytes": tasks_pin["bytes"]}
    assert not [p for p in root.rglob("*") if p.is_file() and e2e._holds(p.read_bytes())]
    assert main(["verify", "--corpus", str(root), "--json", "--level", "chain", "--release",
                 "--root-digest", e2e.vs.root_digest(root)]) == 0
