"""The deposit builder is offline (HL H.10.1(1), G.9.4; HL-T9; MN M.5.3).

Static (``ast``; nothing imported): no module under ``src/agentprov/release/`` imports a network or process module,
calls ``os.system``/``popen``/``exec*``/``spawn*``/``fork``, or calls anything named like an upload or publish. The
release scan that runs gitleaks lives in ``tools/release_scan.py``, outside ``src/``. Dynamic: importing
``agentprov.release`` in a fresh interpreter loads no network module. (``subprocess`` is loaded transitively by the
corpus layer's worker pool, ``agentprov.io.workers``; that is why the static rule is on ``release/``'s own imports and the
builder test ``test_a_build_starts_no_process_and_opens_no_socket`` checks behaviour.)
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RELEASE = REPO / "src" / "agentprov" / "release"

FORBIDDEN_MODULES = frozenset({
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "nntplib", "telnetlib", "xmlrpc",
    "asyncio", "selectors", "subprocess", "multiprocessing", "concurrent", "pty", "webbrowser", "requests", "httpx",
    "aiohttp", "urllib3", "zenodo", "agentprov.raw.fetch", "agentprov.io.workers", "agentprov.cli", "agentprov.worker",
})  # fmt: skip
FORBIDDEN_OS_CALLS = frozenset({"system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp", "execv", "execve",
                                "execl", "execle", "execlp", "execlpe", "execvp", "execvpe", "spawnv", "spawnve", "spawnl",
                                "spawnle", "startfile"})  # fmt: skip
NETWORK_MODULES = ("socket", "ssl", "http.client", "urllib.request", "ftplib", "smtplib", "asyncio")


def _modules() -> list[Path]:
    files = sorted(RELEASE.rglob("*.py"))
    assert files, "src/agentprov/release/ is missing"
    return files


def _forbidden(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN_MODULES)


def test_release_imports_no_network_or_process_module():
    found = []
    for path in _modules():
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
                func = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                if func in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant):
                    names = [str(node.args[0].value)]
            found += [f"{path.name}:{node.lineno} {n}" for n in names if _forbidden(n)]  # type: ignore[attr-defined]
    assert found == []


def test_release_calls_no_process_and_no_upload_or_publish():
    found = []
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "os" and (
                    func.attr in FORBIDDEN_OS_CALLS):
                found.append(f"{path.name}:{node.lineno} os.{func.attr}")
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if any(word in name.lower() for word in ("upload", "publish", "deposit_to", "post")):
                found.append(f"{path.name}:{node.lineno} {name}")
    assert found == []


def test_importing_release_loads_no_network_module():
    code = ("import sys, agentprov.release, agentprov.release.builder, agentprov.release.metadata\n"
            f"print(sorted(m for m in {NETWORK_MODULES!r} if m in sys.modules))")
    done = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, check=True, timeout=120)
    assert done.stdout.strip() == "[]"
