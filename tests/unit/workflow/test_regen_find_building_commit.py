"""``tools/regen/find_building_commit.py`` on a synthetic repository in ``tmp_path``: a commit matches only when every
stage digest the derivation records matches, the sem stage's included (AU-TRG-10)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from wf_support import commit, git, write

TOOL = Path(__file__).resolve().parents[3] / "tools" / "regen" / "find_building_commit.py"
PKG = "src/agentprov"
FILES = {
    "uv.lock": "lock\n",
    "adapters/runner/run.py": "r\n", "aer/a.py": "a\n", "adapters/fam/a.py": "f\n", "prov/p.py": "p\n",
    "prov/compat/c.py": "c\n", "vocab/v.ttl": "v\n", "validate/v.py": "v\n", "sem/validate.py": "sv\n",
    "sem/engine.py": "s1\n", "adapters/semantics_profiles.py": "sp\n",
    "adapters/fam/semantics/__init__.py": "b\n", "adapters/fam/semantics/fam.suites-1/tables.toml": "t\n",
}


def _digest(root: Path, dirs: list[str], exclude: tuple[str, ...] = ()) -> str:
    """The importer's ``code_sha256`` over a working tree (an independent copy of the construction, CRLF normalised as
    ``stage_definitions.code_sha256`` normalises it: on Windows ``write_text`` writes ``\\r\\n``)."""
    pkg = root / PKG
    entries = []
    for d in dirs:
        base = pkg / d
        for path in [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(pkg).as_posix()
            if path.suffix in (".py", ".toml", ".json", ".ttl") and not rel.startswith(exclude):
                entries.append([rel, hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()])
    return "sha256:" + hashlib.sha256(json.dumps(sorted(entries), separators=(",", ":")).encode()).hexdigest()


def test_a_commit_that_differs_only_in_the_sem_code_does_not_match(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for rel, text in FILES.items():
        write(repo, rel if rel == "uv.lock" else f"{PKG}/{rel}", text)
    built = commit(repo, "the building commit")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    derivation = {"lockfile_sha256": "sha256:" + hashlib.sha256(b"lock\n").hexdigest(), "stages": [
        {"stage": "aer", "adapter": "fam.x", "adapter_code_sha256": _digest(repo, ["adapters/fam"]),
         "engine_code_sha256": _digest(repo, ["adapters/runner", "aer"])},
        {"stage": "sem", "profiles": {"fam.suites@1": "sha256:" + "0" * 64},
         "engine_code_sha256": _digest(repo, ["sem", "adapters/semantics_profiles.py", "adapters/fam/semantics"])},
        {"stage": "prov", "engine_code_sha256": _digest(repo, ["prov", "vocab"], ("prov/compat/",))},
        {"stage": "validation", "engine_code_sha256": _digest(repo, ["validate", "aer/validate.py", "aer/accounting.py",
                                                                     "sem/validate.py"])}]}
    (corpus / "derivation.json").write_text(json.dumps(derivation), encoding="utf-8")
    write(repo, f"{PKG}/sem/engine.py", "s2\n")  # outside every other stage's scope
    commit(repo, "a sem-only change")
    proc = subprocess.run([sys.executable, "-I", str(TOOL), str(corpus), "--repo", str(repo)], capture_output=True,
                          text=True, timeout=60)
    matched = [line.split()[0] for line in proc.stdout.splitlines()]
    assert proc.returncode == 0, proc.stderr
    assert matched == [built]
