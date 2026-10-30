"""D-662/D-663: the per-backend table of cli/live/envs.py, the Inspect task-files digest and the dataset provisioning.

The AgentDojo and AutoDojo entries must be the constants they always were (their markers are unchanged: the registered
environments still pass --offline-check). No backend environment is needed here."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from agentprov.cli.live import envs
from agentprov.errors import BackendUnavailable, IdentityMismatch

#: The cross-implementation vector: agentprov_backend_inspect.identity.task_files_sha256 must give the same value
#: (backends/inspect/tests/test_units.py pins it too).
VECTOR = "sha256:3d990265afa7131bef8f42050ddc4675dec8e787ee980e294286be1ca05fd5f6"


def test_the_existing_kinds_are_unchanged():
    assert envs.BACKEND_IDS[:2] == ("agentdojo", "autodojo")
    agentdojo, autodojo = envs.BACKEND_KINDS["agentdojo"], envs.BACKEND_KINDS["autodojo"]
    assert (agentdojo.project, agentdojo.primary, agentdojo.watched) == ("agentdojo", "agentdojo", envs.WATCHED_DISTRIBUTIONS)
    assert agentdojo.guarded_modules == envs.GUARDED_MODULES and agentdojo.rebuilt == envs.SHARED_PACKAGES
    assert autodojo.guarded_modules == (*envs.GUARDED_MODULES, *envs.FORK_GUARDED_MODULES["autodojo"])
    assert agentdojo.task_dirs == autodojo.task_dirs == ()
    assert agentdojo.worker_module == autodojo.worker_module == "agentprov_backend.worker"
    assert agentdojo.hello_keys == autodojo.hello_keys == envs.HELLO_RECORDED_KEYS


def test_the_inspect_kind():
    kind = envs.backend_kind("inspect-agentharm")
    assert kind.project == "inspect/envs/agentharm" and kind.primary == "inspect-ai"
    assert "inspect-evals" in kind.watched and "agentprov-backend-inspect" in kind.rebuilt
    assert kind.task_dirs == ("inspect_evals/agentharm",) and kind.guarded_modules == ()
    assert kind.worker_module == "agentprov_backend_inspect.worker"
    with pytest.raises(BackendUnavailable):
        envs.backend_kind("nonesuch")
    project = envs.backend_project("inspect-agentharm", envs.repository_root())
    assert project.env_name.startswith("inspect-agentharm-") and project.commit is None
    argv = envs.uv_sync_argv(project, offline=True)
    assert argv.count("--reinstall-package") == 3 and "agentprov-backend-inspect" in argv


def test_identity_json_omits_task_files_for_agentdojo():
    ident = envs.EnvIdentity("0" * 64, {}, {})
    assert "task_files" not in ident.to_json() and ident.primary == "agentdojo"
    inspect_ident = envs.EnvIdentity("0" * 64, {}, {}, "inspect-ai", {"inspect_evals/agentharm": VECTOR})
    assert inspect_ident.to_json()["task_files"] == {"inspect_evals/agentharm": VECTOR}


def test_task_files_digest_vector(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__pycache__").mkdir()
    (pkg / "a.py").write_bytes(b"x = 1\n")
    (pkg / "sub" / "b.json").write_bytes(b"{}")
    (pkg / "__pycache__" / "a.pyc").write_bytes(b"\0")
    assert envs.task_files_sha256(pkg, tmp_path) == VECTOR
    (pkg / "a.py").write_bytes(b"x = 2\n")
    assert envs.task_files_sha256(pkg, tmp_path) != VECTOR


def _project_with(tmp_path: Path, recipe: dict) -> envs.BackendProject:
    project = envs.backend_project("inspect-agentharm", envs.repository_root())
    return dataclasses.replace(project, dataset=recipe)


def test_the_project_recipe_is_well_formed():
    project = envs.backend_project("inspect-agentharm", envs.repository_root())
    recipe = envs.dataset_recipe(project)
    assert recipe is not None and recipe["repo"] == "ai-safety-institute/AgentHarm"
    assert recipe["revision"] == "e23b3fe60a0da9037314b88e5ee3a0c054970dad" and len(recipe["files"]) == 6
    assert envs.dataset_recipe(envs.backend_project("agentdojo", envs.repository_root())) is None


@pytest.mark.parametrize("bad", [
    {"kind": "url"}, {"path": "../x"}, {"path": "/abs"}, {"sha256": "z" * 64}, {"bytes": -1}, {"revision": "main"},
])
def test_a_malformed_recipe_refuses(tmp_path, bad):
    data = b"[]"
    recipe = {"kind": "hf", "repo": "org/ds", "revision": "a" * 40, "benchmark": "agentharm",
              "files": [{"path": "benchmark/x.json", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}]}
    file_keys = {"path", "sha256", "bytes"}
    for key, value in bad.items():
        if key in file_keys:
            recipe["files"][0][key] = value
        else:
            recipe[key] = value
    with pytest.raises(BackendUnavailable):
        envs.dataset_recipe(_project_with(tmp_path, recipe))


def test_provision_and_check_a_dataset(tmp_path):
    data = b'{"behaviors": []}'
    recipe = {"kind": "hf", "repo": "org/ds", "revision": "a" * 40, "benchmark": "agentharm",
              "files": [{"path": "benchmark/x.json", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}]}
    project = _project_with(tmp_path, recipe)
    cache = tmp_path / "cache"
    env = tmp_path / "env"
    env.mkdir()
    environ = {"AGENTPROV_UPSTREAM_CACHE": str(cache)}
    with pytest.raises(BackendUnavailable, match="not in the fetch cache"):
        envs.provision_dataset(env, project, environ)
    (cache / "hf" / "org" / "ds" / ("a" * 40) / "benchmark").mkdir(parents=True)
    (cache / "hf" / "org" / "ds" / ("a" * 40) / "benchmark" / "x.json").write_bytes(data)
    record = envs.provision_dataset(env, project, environ)
    assert record is not None and record["files"] == {"benchmark/x.json": hashlib.sha256(data).hexdigest()}
    target = envs.dataset_dir(env, recipe) / "benchmark" / "x.json"
    assert target.read_bytes() == data and not (target.stat().st_mode & 0o222)
    envs.check_dataset(env, project, {"dataset": record})
    with pytest.raises(IdentityMismatch):
        envs.check_dataset(env, project, {"dataset": {**record, "revision": "b" * 40}})
    target.chmod(0o644)
    target.write_bytes(b"[]")
    with pytest.raises(IdentityMismatch, match="differs from its pin"):
        envs.check_dataset(env, project, {"dataset": record})
    with pytest.raises(IdentityMismatch, match="does not declare"):
        envs.check_dataset(env, envs.backend_project("agentdojo", envs.repository_root()), {"dataset": record})


@pytest.mark.parametrize("where", ["cache_file", "cache_dir", "env_dir", "env_file"])
def test_provisioning_follows_no_symlink(tmp_path, where):
    """Rebuild-window final re-check nit: a link below the cache root or below the environment is refused, so no other
    bytes are fed in and nothing is written outside the environment."""
    data = b'{"behaviors": []}'
    digest = hashlib.sha256(data).hexdigest()
    recipe = {"kind": "hf", "repo": "org/ds", "revision": "a" * 40, "benchmark": "agentharm",
              "files": [{"path": "benchmark/x.json", "sha256": digest, "bytes": len(data)}]}
    project = _project_with(tmp_path, recipe)
    cache, env, outside = tmp_path / "cache", tmp_path / "env", tmp_path / "outside"
    env.mkdir()
    outside.mkdir()
    snapshot = cache / "hf" / "org" / "ds" / ("a" * 40)
    snapshot.mkdir(parents=True)
    (outside / "x.json").write_bytes(data)  # the right bytes, reached through a link: still refused
    if where == "cache_file":
        (snapshot / "benchmark").mkdir()
        (snapshot / "benchmark" / "x.json").symlink_to(outside / "x.json")
    elif where == "cache_dir":
        (snapshot / "benchmark").symlink_to(outside)
    else:
        (snapshot / "benchmark").mkdir()
        (snapshot / "benchmark" / "x.json").write_bytes(data)
        dest = envs.dataset_dir(env, recipe)
        if where == "env_dir":
            dest.mkdir(parents=True)
            (dest / "benchmark").symlink_to(outside)
        else:
            (dest / "benchmark").mkdir(parents=True)
            (dest / "benchmark" / "x.json").symlink_to(outside / "y.json")
    with pytest.raises(BackendUnavailable):
        envs.provision_dataset(env, project, {"AGENTPROV_UPSTREAM_CACHE": str(cache)})
    assert sorted(p.name for p in outside.iterdir()) == ["x.json"]  # nothing written outside the environment
