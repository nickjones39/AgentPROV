"""``tools/building_commit_snapshots.py`` (D-911, D-940): building-commit source snapshots and their manifest.

Synthetic data only: each test builds a small git repository whose ``src/agentprov`` is a stand-in package with the
same digest construction as the real one (``code_sha256``: sha256 of the compact JSON of sorted ``[relpath,
sha256(file)]`` pairs), a restricted and a free test fixture, and corpora whose ``corpus.json`` and ``derivation.json``
record digests the test computes independently. Checked: the commit attribution (build steps, the building-commit
statement, ``--attribute``, the sealing commit), refusals (no commit, a dirty step, an unequal digest, a commit before
the history scrub, a non-empty ``--out``), the copyleft exclusions, the tree check, byte-identical rebuilds, and
``verify`` (a clean pass, a tampered archive).
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


def _load(name: str):
    path = Path(__file__).resolve().parents[3] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bcs = _load("building_commit_snapshots")

#: the stand-in package: the module names and functions the tool's helper calls, nothing else
PACKAGE = {
    "__init__.py": "",
    "stage_definitions.py": '''
import hashlib, json
from pathlib import Path
PACKAGE_ROOT = Path(__file__).resolve().parent
def code_sha256(dirs, exclude=()):
    entries = []
    for directory in dirs:
        base = PACKAGE_ROOT / directory
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in files:
            rel = path.relative_to(PACKAGE_ROOT).as_posix()
            if path.suffix not in (".py", ".toml", ".json", ".ttl") or "__pycache__" in rel:
                continue
            if any(rel.startswith(e) for e in exclude):
                continue
            entries.append([rel, hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(sorted(entries), separators=(",", ":")).encode()).hexdigest()
''',
    "stage_scopes.py": '''
PROV_EXCLUDE = ("prov/compat/",)
def aer_scope(family): return ["aer"]
def sem_scope(families): return ["sem", *sorted(set(families))]
def prov_scope(): return ["prov"]
def validation_scope(): return ["validate"]
''',
    "raw/__init__.py": "",
    "raw/members.py": '''
from agentprov.stage_definitions import code_sha256
def engine_code_sha256(): return code_sha256(["raw"])
''',
    "sem/__init__.py": "",
    "sem/engine.py": "RULES = 1\n",
    "sem/types.py": "def sem_profile_dir(pid, version): return f'{pid}-{version}'\n",
    "sem/profiles.py": '''
import hashlib, json
def profile_digest(files):
    return hashlib.sha256(json.dumps({k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}).encode()).hexdigest()
''',
    "aer/__init__.py": "",
    "aer/writer.py": "FORMAT = 'aer/0.1'\n",
    "prov/__init__.py": "",
    "prov/engine.py": "SPEC = 'agentprov-prov/0.1'\n",
    "prov/compat/frozen.py": "FROZEN = True\n",
    "validate/__init__.py": "",
    "validate/tiers.py": "TIERS = 4\n",
    "adapters/__init__.py": "",
    "adapters/semantics_profiles.py": '''
from importlib import resources
def semantics_families():
    root = resources.files("agentprov").joinpath("adapters")
    return tuple(sorted(c.name for c in root.iterdir() if c.is_dir() and c.joinpath("semantics").is_dir()))
def _collect(node, prefix, out):
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        name = f"{prefix}{child.name}"
        if child.is_dir():
            _collect(child, f"{name}/", out)
        else:
            out[name] = child.read_bytes()
''',
    "adapters/fam/__init__.py": "",
    "adapters/fam/mapper.py": "MAPPER = 'fam.map'\n",
    "adapters/fam/profiles/src.profile.toml": "[profile]\nid = 'src'\nversion = 1\n",
    "adapters/fam/rules/fam.rules.toml": "[catalogue]\nid = 'fam'\n",
    "adapters/fam/semantics/fam.sem-1/table.toml": "[table]\nrows = 1\n",
}
FIXTURE_RESTRICTED = [{"licence_class": "restricted", "repo": "https://example.invalid/cop"}]
FIXTURE_FREE = [{"licence_class": "permissive", "repo": "https://example.invalid/free"}]


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_AUTHOR_DATE="2026-10-01T00:00:00Z",
               GIT_COMMITTER_DATE="2026-10-01T00:00:00Z", GIT_CONFIG_NOSYSTEM="1", HOME=str(repo))
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def _write(root: Path, rel: str, data: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def code(root: Path, dirs, exclude=()) -> str:
    """The test's own digest (independent of the tool and the stand-in package)."""
    pkg = root / "src" / "agentprov"
    entries = []
    for d in dirs:
        base = pkg / d
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(pkg).as_posix()
            if path.suffix in (".py", ".toml", ".json", ".ttl") and not any(rel.startswith(e) for e in exclude):
                entries.append([rel, hashlib.sha256(path.read_bytes()).hexdigest()])
    return "sha256:" + hashlib.sha256(json.dumps(sorted(entries), separators=(",", ":")).encode()).hexdigest()


def file_sha(root: Path, rel: str) -> str:
    return "sha256:" + hashlib.sha256((root / "src" / "agentprov" / rel).read_bytes()).hexdigest()


def sem_profile_sha(root: Path) -> str:
    base = root / "src/agentprov/adapters/fam/semantics/fam.sem-1"
    files = {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}
    return "sha256:" + hashlib.sha256(json.dumps(
        {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}).encode()).hexdigest()


def derivation(root: Path) -> dict:
    return {
        "format": "agentprov-derivation/0.1",
        "lockfile_sha256": "sha256:" + hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "stages": [
            {"stage": "expand", "engine_code_sha256": code(root, ["raw"])},
            {"stage": "aer", "adapter_code_sha256": code(root, ["adapters/fam"]), "engine_code_sha256": code(root, ["aer"]),
             "profile_sha256": file_sha(root, "adapters/fam/profiles/src.profile.toml"),
             "rules_sha256": {"fam": file_sha(root, "adapters/fam/rules/fam.rules.toml")}},
            {"stage": "sem", "engine_code_sha256": code(root, ["sem", "adapters/fam/semantics"]),
             "profiles": {"fam.sem@1": sem_profile_sha(root)}},
            {"stage": "prov", "engine_code_sha256": code(root, ["prov"], exclude=["prov/compat/"])},
            {"stage": "validation", "engine_code_sha256": code(root, ["validate"])},
        ],
    }


@pytest.fixture
def repo(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "README.md", "stand-in\n")
    scrub = _commit(root, "scrub")
    for rel, text in PACKAGE.items():
        _write(root, f"src/agentprov/{rel}", text)
    _write(root, "uv.lock", "version = 1\n")
    _write(root, "tests/fixtures/cop/SOURCE.json", json.dumps(FIXTURE_RESTRICTED))
    _write(root, "tests/fixtures/cop/run.json", '{"copyleft": true}\n')
    _write(root, "tests/fixtures/free/SOURCE.json", json.dumps(FIXTURE_FREE))
    _write(root, "tests/fixtures/free/run.json", '{"free": true}\n')
    _write(root, "tests/fixtures/ah/SOURCE.json", json.dumps([
        {"licence_class": "restricted_use", "synthetic": False, "sample_file": "use.json"},
        {"licence_class": "permissive", "synthetic": False, "sample_file": "open.json"},
        {"licence_class": "restricted_use", "synthetic": True, "sample_file": "made.json"},
        {"licence_class": "restricted_use", "synthetic": False, "sample_file": "../LICENSES/ah-clause.txt"}]))
    _write(root, "tests/fixtures/LICENSES/ah-clause.txt", "use clause\n")
    for name in ("use.json", "open.json", "made.json"):
        _write(root, f"tests/fixtures/ah/{name}", "{}\n")
    _write(root, "tests/fixtures/unk/SOURCE.json", json.dumps([{"synthetic": False, "repo": "https://example.invalid/u"}]))
    _write(root, "tests/fixtures/unk/data/run.json", "{}\n")
    _write(root, "tests/fixtures/free/sub/SOURCE.json", json.dumps([{"licence_class": "permissive", "sample_file": "x.json"}]))
    _write(root, "tests/fixtures/free/sub/x.json", "{}\n")
    _write(root, "tests/fixtures/LICENSES/cop-GPL-3.0.txt", "GPL text\n")
    _write(root, "tests/fixtures/LICENSES/free-MIT.txt", "MIT text\n")
    _write(root, "tools/run.sh", "#!/bin/sh\necho hi\n")
    os.chmod(root / "tools/run.sh", 0o755)
    build = _commit(root, "build")
    deriv = derivation(root)
    _write(root, "src/agentprov/prov/engine.py", "SPEC = 'agentprov-prov/0.1'\nCHANGED = True\n")
    seal = _commit(root, "seal")
    return {"root": root, "scrub": scrub, "build": build, "seal": seal, "derivation": deriv}


def corpus(tmp_path: Path, name: str, deriv: dict, *, steps=None, statements=(), sealed=False, sealing=None,
           datasheet: str | None = None) -> Path:
    path = tmp_path / "corpora" / name
    path.mkdir(parents=True)
    producer: dict = {"agentprov_version": "0.1.0"}
    if steps is not None:
        producer["build_steps"] = steps
    if sealing:
        producer["git_commit"] = sealing
        producer["git_tree_clean"] = True
    manifest = {"corpus_id": name.split(".")[0], "sealed": sealed, "producer": producer,
                "datasheet": {"statements": list(statements)}}
    (path / "corpus.json").write_text(json.dumps(manifest))
    (path / "derivation.json").write_text(json.dumps(deriv))
    if datasheet is not None:
        (path / "DATASHEET.md").write_text(datasheet)
    return path


def step(commit: str, stages=("aer", "expand", "prov", "sem", "validation"), clean=True) -> dict:
    return {"command": "import", "agentprov_version": "0.1.0", "git_commit": commit, "git_tree_clean": clean,
            "stages": list(stages)}


def run(*args: str) -> int:
    return bcs.main([*args])


def build_args(repo, out: Path, corpora, *extra) -> list[str]:
    args = ["build", "--repo", str(repo["root"]), "--out", str(out), "--scrub-commit", repo["scrub"]]
    for c in corpora:
        args += ["--corpus", str(c)]
    return [*args, *extra]


# ----------------------------------------------------------------------------------------------- tests
def test_build_checks_every_digest_and_leaves_out_the_copyleft_fixtures(repo, tmp_path, capsys):
    a = corpus(tmp_path, "alpha.partial", repo["derivation"], steps=[step(repo["build"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [a])) == 0
    manifest = json.loads((out / bcs.MANIFEST).read_text())
    assert manifest["format"] == bcs.FORMAT
    (snap,) = manifest["snapshots"]
    assert snap["commit"] == repo["build"]
    assert snap["tree"] == _git(repo["root"], "rev-parse", f"{repo['build']}^{{tree}}").strip()
    assert snap["roles"] == [{"basis": "producer.build_steps", "corpus_dir": "alpha.partial", "corpus_id": "alpha",
                              "role": "build", "stages": ["aer", "expand", "prov", "sem", "validation"]}]
    reasons = {e["path"]: e["reason"] for e in snap["excluded"]}
    assert set(reasons) == {"tests/fixtures/cop/SOURCE.json", "tests/fixtures/cop/run.json",
                            "tests/fixtures/LICENSES/cop-GPL-3.0.txt",  # copyleft (D-911)
                            "tests/fixtures/ah/use.json",  # restricted_use, by its sample_file (U-06)
                            "tests/fixtures/LICENSES/ah-clause.txt",  # its licence text, named from ../LICENSES
                            "tests/fixtures/unk/data/run.json"}  # no class, no sample_file: its whole directory
    assert reasons["tests/fixtures/ah/use.json"] == "restricted_use fixture (U-06, D-943)"
    assert reasons["tests/fixtures/unk/data/run.json"].startswith("fixture with no licence_class")
    checks = snap["stage_checks"]
    assert len(checks["code_digests"]) == 7 and all(r["equal"] for r in checks["code_digests"])
    assert {(r["stage"], r["field"]) for r in checks["code_digests"]} == {
        ("expand", "engine_code_sha256"), ("aer", "adapter_code_sha256"), ("aer", "engine_code_sha256"),
        ("sem", "engine_code_sha256"), ("sem", "profiles"), ("prov", "engine_code_sha256"),
        ("validation", "engine_code_sha256")}
    assert [r["check"] for r in checks["files_by_digest"]] == ["aer.profile_sha256", "aer.rules_sha256.fam"]
    assert all(r["equal"] for r in checks["files_by_digest"])
    assert checks["lockfile"][0]["equal"] and checks["unchecked"] == []

    data = (out / snap["archive"]["name"]).read_bytes()
    assert snap["archive"]["sha256"] == "sha256:" + hashlib.sha256(data).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(data))) as tar:
        names = tar.getnames()
        assert tar.pax_headers["comment"] == repo["build"]
        modes = {m.name: m.mode for m in tar.getmembers()}
    prefix = f"agentprov-{repo['build'][:12]}/"
    assert all(n.startswith(prefix.rstrip("/")) for n in names)
    assert prefix + "tests/fixtures/free/run.json" in names
    assert prefix + "tests/fixtures/LICENSES/free-MIT.txt" in names
    for kept in ("ah/open.json", "ah/made.json", "ah/SOURCE.json", "unk/SOURCE.json", "free/sub/x.json"):
        assert prefix + "tests/fixtures/" + kept in names
    assert not any("fixtures/cop" in n or "cop-GPL" in n for n in names)
    assert modes[prefix + "tools/run.sh"] & 0o111


def test_rebuild_is_byte_identical_and_verify_passes(repo, tmp_path, capsys):
    a = corpus(tmp_path, "alpha.partial", repo["derivation"], steps=[step(repo["build"])])
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    assert run(*build_args(repo, out1, [a])) == 0
    assert run(*build_args(repo, out2, [a])) == 0
    for name in os.listdir(out1):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name
    capsys.readouterr()
    assert run("verify", "--manifest", str(out1 / bcs.MANIFEST), "--corpus", str(a)) == 0
    assert json.loads(capsys.readouterr().out) == {"problems": 0, "snapshots": 1}


def test_verify_finds_a_tampered_archive_and_a_corpus_that_differs(repo, tmp_path, capsys):
    a = corpus(tmp_path, "alpha.partial", repo["derivation"], steps=[step(repo["build"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [a])) == 0
    manifest = json.loads((out / bcs.MANIFEST).read_text())
    other = dict(repo["derivation"], stages=[dict(s) for s in repo["derivation"]["stages"]])
    other["stages"][3]["engine_code_sha256"] = "sha256:" + "0" * 64
    b = corpus(tmp_path / "elsewhere", "alpha.partial", other)  # same directory name, another prov digest
    capsys.readouterr()
    assert run("verify", "--manifest", str(out / bcs.MANIFEST), "--corpus", str(b)) == 1
    assert "prov.engine_code_sha256" in capsys.readouterr().err
    archive = out / manifest["snapshots"][0]["archive"]["name"]
    data = archive.read_bytes()
    archive.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    assert run("verify", "--manifest", str(out / bcs.MANIFEST)) == 1
    assert "size or digest differs" in capsys.readouterr().err


def test_statement_attribution_and_sealing_commit(repo, tmp_path, capsys):
    sealed = corpus(tmp_path, "beta", repo["derivation"], statements=[f"building-commit-by-digest-{repo['build'][:8]}"],
                    sealed=True, sealing=repo["seal"], datasheet=f"built at `{repo['build']}`\n")
    capsys.readouterr()
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(sealed)) == 0
    commits = json.loads(capsys.readouterr().out)["commits"]
    roles = {c["commit"]: [r["role"] for r in c["roles"]] for c in commits}
    assert roles == {repo["build"]: ["build"], repo["seal"]: ["sealing"]}
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [sealed])) == 0
    snaps = {s["commit"]: s for s in json.loads((out / bcs.MANIFEST).read_text())["snapshots"]}
    assert snaps[repo["seal"]]["stage_checks"]["code_digests"] == []  # a sealing commit has no stage checks
    assert all(r["equal"] for r in snaps[repo["build"]]["stage_checks"]["code_digests"])
    capsys.readouterr()
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(sealed), "--no-sealing") == 0
    assert [c["commit"] for c in json.loads(capsys.readouterr().out)["commits"]] == [repo["build"]]


def test_a_statement_the_datasheet_does_not_name_is_refused(repo, tmp_path, capsys):
    sealed = corpus(tmp_path, "beta", repo["derivation"], statements=[f"building-commit-by-digest-{repo['build'][:8]}"],
                    sealed=True, sealing=repo["seal"], datasheet="no commit here\n")
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(sealed)) == 4
    assert "DATASHEET.md does not name" in capsys.readouterr().err


def test_a_derived_corpus_checks_each_stage_at_the_commit_that_wrote_it(repo, tmp_path):
    # aer at the build commit, prov recomputed at the seal commit (whose prov/engine.py differs)
    deriv = json.loads(json.dumps(repo["derivation"]))
    deriv["stages"][3]["engine_code_sha256"] = code(repo["root"], ["prov"], exclude=["prov/compat/"])  # tree = seal
    c = corpus(tmp_path, "gamma.partial", deriv, steps=[step(repo["build"]), step(repo["seal"], stages=["prov"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [c])) == 0
    snaps = {s["commit"]: s["stage_checks"] for s in json.loads((out / bcs.MANIFEST).read_text())["snapshots"]}
    assert {r["stage"] for r in snaps[repo["seal"]]["code_digests"]} == {"prov"}
    assert "prov" not in {r["stage"] for r in snaps[repo["build"]]["code_digests"]}
    assert snaps[repo["build"]]["lockfile"] == [] and snaps[repo["seal"]]["lockfile"] == []  # two commits built it


def test_a_commit_that_recurs_owns_the_stages_its_last_step_wrote(repo, tmp_path):
    # DTap's order: import at the build commit, import at another (the seal commit, whose prov differs), recompute at
    # the build commit; every stage is the build commit's, never credited to the commit in between
    recompute = {**step(repo["build"]), "command": "recompute"}
    c = corpus(tmp_path, "dtap.partial", repo["derivation"], steps=[step(repo["build"]), step(repo["seal"]), recompute])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [c])) == 0
    snaps = {s["commit"]: s["stage_checks"] for s in json.loads((out / bcs.MANIFEST).read_text())["snapshots"]}
    assert {r["stage"] for r in snaps[repo["build"]]["code_digests"]} >= {"aer", "prov", "sem", "validation"}
    assert snaps[repo["seal"]]["code_digests"] == []


def test_an_annotated_tag_resolves_to_its_commit(repo):
    # wave2/build-2efe7ca0 is annotated, the other building tags lightweight: an id always peels to the commit
    _git(repo["root"], "tag", "-a", "-m", "building commit", "wave2/build-x", repo["build"])
    tag = _git(repo["root"], "rev-parse", "wave2/build-x").strip()
    assert tag != repo["build"] and _git(repo["root"], "cat-file", "-t", tag).strip() == "tag"
    assert bcs.resolve_commit(repo["root"], tag) == repo["build"]
    assert bcs.resolve_commit(repo["root"], tag[:12]) == repo["build"]
    with pytest.raises(bcs.Refused, match="not a commit id"):
        bcs.resolve_commit(repo["root"], "wave2/build-x")  # a record names a commit, never a ref


def test_an_unequal_digest_refuses_the_build(repo, tmp_path, capsys):
    deriv = json.loads(json.dumps(repo["derivation"]))
    deriv["stages"][1]["adapter_code_sha256"] = "sha256:" + "1" * 64
    c = corpus(tmp_path, "delta.partial", deriv, steps=[step(repo["build"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [c])) == 4
    assert "aer.adapter_code_sha256" in capsys.readouterr().err
    assert not out.exists()


def test_a_known_stage_that_cannot_be_recomputed_refuses_the_build(repo, tmp_path, capsys):
    deriv = json.loads(json.dumps(repo["derivation"]))
    deriv["stages"][2]["profiles"] = {}  # a sem entry naming no profile: its scope cannot be built
    c = corpus(tmp_path, "kappa.partial", deriv, steps=[step(repo["build"])])
    assert run(*build_args(repo, tmp_path / "out", [c])) == 4
    assert "sem not checked" in capsys.readouterr().err


def test_refusals(repo, tmp_path, capsys):
    none = corpus(tmp_path, "eps.partial", repo["derivation"], steps=[])
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(none)) == 4
    assert "no building commit is recorded" in capsys.readouterr().err
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(none), "--attribute",
               f"eps.partial={repo['build']}") == 0
    assert "operator attribution" in capsys.readouterr().out

    dirty = corpus(tmp_path, "zeta.partial", repo["derivation"], steps=[step(repo["build"], clean=False)])
    assert run("plan", "--repo", str(repo["root"]), "--corpus", str(dirty)) == 4
    assert "dirty tree" in capsys.readouterr().err

    early = corpus(tmp_path, "eta.partial", repo["derivation"], steps=[step(repo["scrub"])])
    assert run("build", "--repo", str(repo["root"]), "--out", str(tmp_path / "o"), "--corpus", str(early),
               "--scrub-commit", repo["build"]) == 4
    assert "does not descend from the history scrub" in capsys.readouterr().err

    ok = corpus(tmp_path, "theta.partial", repo["derivation"], steps=[step(repo["build"])])
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x").write_text("x")
    assert run(*build_args(repo, busy, [ok])) == 4
    assert "not an empty directory" in capsys.readouterr().err
    assert run(*build_args(repo, tmp_path / "o2", [ok], "--exclude", "no/such/path")) == 4
    assert "matches nothing" in capsys.readouterr().err


def test_operator_exclusion_is_listed_and_left_out(repo, tmp_path):
    c = corpus(tmp_path, "iota.partial", repo["derivation"], steps=[step(repo["build"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [c], "--exclude", "tools")) == 0
    (snap,) = json.loads((out / bcs.MANIFEST).read_text())["snapshots"]
    assert {"path": "tools/run.sh", "reason": "operator exclusion (--exclude)"}.items() <= next(
        e for e in snap["excluded"] if e["path"] == "tools/run.sh").items()


def _exclude_list(tmp_path: Path, entries) -> Path:
    path = tmp_path / "exclude.toml"
    path.write_text("".join(f'[[exclude]]\npath = "{p}"\nreason = "{r}"\n\n' for p, r in entries))
    return path


def test_an_exclude_list_leaves_out_paths_absent_at_some_commits_with_their_reasons(repo, tmp_path, capsys):
    """P-3a: the coding-agent files leave every snapshot; a listed path may exist only at some commits."""
    _write(repo["root"], "CLAUDE.md", "agent notes\n")
    _write(repo["root"], "docs/agents/brief.md", "a brief\n")
    later = _commit(repo["root"], "agent files")
    sealed = corpus(tmp_path, "theta", repo["derivation"], steps=[step(repo["build"])], sealed=True, sealing=later)
    listed = _exclude_list(tmp_path, [("CLAUDE.md", "agent notes (P-3a)"), ("docs/agents/", "agent briefs (P-3a)"),
                                      ("tools/", "tooling (test)")])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [sealed], "--exclude-list", str(listed))) == 0
    snaps = {s["commit"]: s for s in json.loads((out / bcs.MANIFEST).read_text())["snapshots"]}
    reasons = {c: {e["path"]: e["reason"] for e in s["excluded"]} for c, s in snaps.items()}
    assert reasons[repo["build"]]["tools/run.sh"] == "tooling (test)" and "CLAUDE.md" not in reasons[repo["build"]]
    assert reasons[later]["CLAUDE.md"] == "agent notes (P-3a)"
    assert reasons[later]["docs/agents/brief.md"] == "agent briefs (P-3a)"
    for s in snaps.values():
        with tarfile.open(out / s["archive"]["name"]) as tar:
            names = {m.name.split("/", 1)[1] for m in tar.getmembers() if "/" in m.name}
        assert not names & {"CLAUDE.md", "docs/agents/brief.md", "tools/run.sh"}
    assert all(r["equal"] for r in snaps[repo["build"]]["stage_checks"]["code_digests"])
    capsys.readouterr()
    assert run("verify", "--manifest", str(out / bcs.MANIFEST), "--corpus", str(sealed)) == 0
    assert json.loads(capsys.readouterr().out) == {"problems": 0, "snapshots": 2}


def test_an_exclude_list_path_that_matches_no_commit_or_has_no_reason_is_refused(repo, tmp_path, capsys):
    c = corpus(tmp_path, "kappa.partial", repo["derivation"], steps=[step(repo["build"])])
    out = tmp_path / "out"
    assert run(*build_args(repo, out, [c], "--exclude-list", str(_exclude_list(tmp_path, [("no/such", "x")])))) == 4
    assert "matches nothing at any snapshot commit" in capsys.readouterr().err
    assert not out.exists() or not any(out.iterdir())
    bad = tmp_path / "bad.toml"
    bad.write_text('[[exclude]]\npath = "tools/"\n')
    assert run(*build_args(repo, out, [c], "--exclude-list", str(bad))) == 4
    assert "needs a reason" in capsys.readouterr().err


def test_a_sample_file_outside_the_fixture_tree_is_refused(repo, tmp_path, capsys):
    _write(repo["root"], "tests/fixtures/bad/SOURCE.json", json.dumps([{"licence_class": "restricted_use",
                                                                         "sample_file": "../../../README.md"}]))
    commit = _commit(repo["root"], "bad")
    c = corpus(tmp_path, "lam.partial", repo["derivation"], steps=[step(commit)])
    assert run(*build_args(repo, tmp_path / "out", [c])) == 4
    assert "outside tests/fixtures/" in capsys.readouterr().err


def test_tree_check_detects_a_changed_member():
    tree = {"a.txt": bcs.TreeEntry("100644", "blob", "0" * 40, "a.txt")}
    read = bcs.ArchiveRead(None, {"a.txt": bcs.TreeEntry("100644", "blob", "1" * 40, "a.txt")}, {}, "p/")
    with pytest.raises(bcs.Refused, match="1 changed"):
        bcs.tree_check(tree, {}, read)
    with pytest.raises(bcs.Refused, match="1 missing"):
        bcs.tree_check(tree, {}, bcs.ArchiveRead(None, {}, {}, "p/"))
