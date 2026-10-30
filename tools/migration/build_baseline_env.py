"""Build the isolated baseline environment of the differential gates (docs/architecture J.1.6; K.19 ``old-vs-new``).

    python tools/migration/build_baseline_env.py [--baseline-repo DIR] [--offline] [--dest DIR]
    python tools/migration/build_baseline_env.py --write-requirements --freeze investigation/baseline/pip_freeze.txt

The environment is CPython 3.12.14 with the frozen baseline package ``agentdojo-prov 1.0.0`` at
``579a908354b93361efe0905ffb7623256aa96a06`` and its frozen dependency set:

1. ``uv venv --python 3.12.14 <dest>`` (``<dest>`` defaults to ``$AGENTPROV_HOME/baseline/venv-579a908``, outside the
   repository; ``AGENTPROV_HOME`` defaults to ``~/.agentprov``);
2. ``uv pip install --require-hashes --no-deps -r migration/baseline-requirements.txt`` (the hash-locked export of
   ``pip_freeze.txt`` minus its ``-e`` line; R-49);
3. a wheel built from ``git archive 579a908 agentdojo_prov pyproject.toml README.md`` unpacked into a temporary
   directory **outside the old repository** (MP-1; never an editable install, which writes ``agentdojo_prov.egg-info``
   into the checkout), with ``SOURCE_DATE_EPOCH`` set to the commit time so that its digest is reproducible, installed
   non-editable with ``--no-deps``;
4. a check that the installed package imports, reports version 1.0.0 and lives in ``<dest>``.

On success it prints the interpreter path (export it as ``AGENTPROV_BASELINE_PYTHON``) and writes
``<dest>/AGENTPROV_BASELINE.json`` (commit, wheel sha256, requirements sha256, Python and uv versions). ``--offline``
installs from the uv cache only (local work; CI resolves from the index, verified by the same hashes).

``--write-requirements`` regenerates ``migration/baseline-requirements.txt`` from ``pip_freeze.txt`` (whose sha256 must
equal the lock's ``environment.pip_freeze_sha256``) with ``uv pip compile --no-deps --universal --generate-hashes``: the
pins are the freeze verbatim; the hashes are those of the package index (from the uv cache with ``--offline``).

The build backend that makes the wheel (the baseline's ``[build-system]`` asks for ``setuptools>=68``; the freeze does not
pin it) is pinned with hashes by ``migration/baseline-build-constraints.txt`` (setuptools 84.0.0), so the wheel digest the
lock records is reproducible; its version is also recorded in the wheel's ``WHEEL`` file and in the JSON record.
Stdlib only; reads the old repository with ``git`` read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"
PYTHON = "3.12.14"
PACKAGE = "agentdojo_prov"
VERSION = "1.0.0"
REQUIREMENTS = REPO_ROOT / "migration" / "baseline-requirements.txt"
BUILD_CONSTRAINTS = REPO_ROOT / "migration" / "baseline-build-constraints.txt"
LOCK = REPO_ROOT / "migration" / "baseline.lock.json"
EXPORT_PATHS = ("agentdojo_prov", "pyproject.toml", "README.md")
RECORD_NAME = "AGENTPROV_BASELINE.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, check=True, capture_output=True, **kw)  # type: ignore[call-overload, no-any-return]


def _git(repo: Path, *args: str) -> bytes:
    return _run(["git", "--no-pager", "--no-optional-locks", "-C", str(repo), *args]).stdout


def find_baseline_repo(explicit: Path | None) -> Path:
    """The old repository: ``--baseline-repo``, else ``$AGENTPROV_BASELINE_CORPUS``, else a sibling directory named
    ``AgentDojo-PROV-framework`` of the repository root or of any of its parents (worktrees sit below the root)."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    elif os.environ.get("AGENTPROV_BASELINE_CORPUS"):
        candidates.append(Path(os.environ["AGENTPROV_BASELINE_CORPUS"]).expanduser())
    else:
        candidates += [p.parent / "AgentDojo-PROV-framework" for p in (REPO_ROOT, *REPO_ROOT.parents)]
    for path in candidates:
        if (path / ".git").exists():
            return path.resolve()
    raise SystemExit("no baseline repository found: pass --baseline-repo or set AGENTPROV_BASELINE_CORPUS")


def default_dest() -> Path:
    home = Path(os.environ.get("AGENTPROV_HOME") or Path.home() / ".agentprov").expanduser()
    return home / "baseline" / f"venv-{COMMIT[:7]}"


def export_source(repo: Path, into: Path) -> int:
    """``git archive`` of the package files at the pinned commit, unpacked into ``into`` (outside the old repo);
    returns the commit time (``SOURCE_DATE_EPOCH``)."""
    kind = _git(repo, "cat-file", "-t", COMMIT).decode().strip()
    if kind != "commit":
        raise SystemExit(f"the baseline repository has no commit {COMMIT}")
    epoch = int(_git(repo, "log", "-1", "--format=%ct", COMMIT).decode().strip())
    data = _git(repo, "archive", "--format=tar", COMMIT, *EXPORT_PATHS)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        tar.extractall(into, filter="data")  # our own pinned export, into a fresh temporary directory
    return epoch


def build_wheel(repo: Path, work: Path, *, offline: bool) -> tuple[Path, str]:
    src = work / "src"
    src.mkdir()
    epoch = export_source(repo, src)
    out = work / "wheel"
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = ["uv", "build", "--wheel", "--python", PYTHON, "--build-constraints", str(BUILD_CONSTRAINTS), "--require-hashes",
           "--out-dir", str(out), str(src)]
    if offline:
        cmd.insert(2, "--offline")
    _run(cmd, env=env)
    (wheel,) = out.glob(f"{PACKAGE}-{VERSION}-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        generator = next((line.split(":", 1)[1].strip() for line in
                          zf.read(f"{PACKAGE}-{VERSION}.dist-info/WHEEL").decode().splitlines()
                          if line.startswith("Generator:")), "unknown")
    return wheel, generator


def write_requirements(freeze: Path, *, offline: bool) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    expected = lock["environment"]["pip_freeze_sha256"]
    if _sha256(freeze) != expected:
        raise SystemExit("pip_freeze.txt does not match the lock's environment.pip_freeze_sha256")
    lines = [ln for ln in freeze.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("-e ")]
    with tempfile.TemporaryDirectory() as tmp:
        req_in = Path(tmp) / "baseline-freeze.in"
        req_in.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd = ["uv", "pip", "compile", "--no-deps", "--universal", "--generate-hashes", "--python-version", "3.12",
               "--no-header", "--no-annotate", str(req_in)]
        if offline:
            cmd.insert(3, "--offline")
        body = _run(cmd).stdout.decode()
    header = (
        "# Hash-locked export of the baseline pip freeze (docs/architecture J.1.6; R-49).\n"
        f"# Source: investigation/baseline/pip_freeze.txt (sha256 {expected}) minus its -e line.\n"
        "# Generated by tools/migration/build_baseline_env.py --write-requirements (uv pip compile --no-deps\n"
        "# --universal --generate-hashes); install with --require-hashes --no-deps. Do not edit by hand.\n"
    )
    REQUIREMENTS.write_text(header + body, encoding="utf-8")
    print(f"{REQUIREMENTS.relative_to(REPO_ROOT)} sha256 {_sha256(REQUIREMENTS)}")


def build(repo: Path, dest: Path, *, offline: bool) -> Path:
    if not REQUIREMENTS.is_file():
        raise SystemExit("migration/baseline-requirements.txt is missing (run with --write-requirements first)")
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    flag = ["--offline"] if offline else []
    _run(["uv", "venv", *flag, "--python", PYTHON, str(dest)])
    python = dest / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run(["uv", "pip", "install", *flag, "--python", str(python), "--require-hashes", "--no-deps",
          "-r", str(REQUIREMENTS)])
    with tempfile.TemporaryDirectory(prefix="agentprov-baseline-") as tmp:
        wheel, generator = build_wheel(repo, Path(tmp), offline=offline)
        wheel_sha = _sha256(wheel)
        recorded = json.loads(LOCK.read_text(encoding="utf-8"))["environment"].get("baseline_wheel_sha256")
        if recorded is not None and wheel_sha != recorded:
            raise SystemExit(f"the rebuilt baseline wheel has sha256 {wheel_sha}; the lock records {recorded} (J.1.6)")
        kept = dest / "wheel" / wheel.name
        kept.parent.mkdir()
        shutil.copy2(wheel, kept)
    _run(["uv", "pip", "install", *flag, "--python", str(python), "--no-deps", str(kept)])
    probe = ("import importlib.metadata as m, json, sys, agentdojo_prov as p; "
             "print(json.dumps({'file': p.__file__, 'version': m.version('agentdojo-prov'), "
             "'agentdojo': m.version('agentdojo'), 'openai': m.version('openai'), 'python': sys.version.split()[0]}))")
    info = json.loads(_run([str(python), "-I", "-B", "-c", probe], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                      .stdout.decode())
    if info["version"] != VERSION or not Path(info["file"]).resolve().is_relative_to(dest.resolve()):
        raise SystemExit(f"the installed baseline package is not the built one: {info}")
    uv_version = _run(["uv", "--version"]).stdout.decode().strip()
    record = {
        "format": "agentprov-baseline-env/1",
        "commit": COMMIT,
        "python": info["python"],
        "uv": uv_version,
        "requirements_sha256": _sha256(REQUIREMENTS),
        "build_constraints_sha256": _sha256(BUILD_CONSTRAINTS),
        "wheel": {"name": wheel.name, "sha256": wheel_sha, "generator": generator},
        "packages": {"agentdojo-prov": info["version"], "agentdojo": info["agentdojo"], "openai": info["openai"]},
        "offline": offline,
    }
    (dest / RECORD_NAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return python


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline-repo", type=Path, default=None)
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--offline", action="store_true", help="install from the uv cache only")
    ap.add_argument("--write-requirements", action="store_true")
    ap.add_argument("--freeze", type=Path, default=None, help="investigation/baseline/pip_freeze.txt")
    args = ap.parse_args(argv)
    if args.write_requirements:
        if args.freeze is None:
            ap.error("--write-requirements needs --freeze")
        write_requirements(args.freeze, offline=args.offline)
        return 0
    python = build(find_baseline_repo(args.baseline_repo), args.dest or default_dest(), offline=args.offline)
    print(python)
    return 0


if __name__ == "__main__":
    sys.exit(main())
