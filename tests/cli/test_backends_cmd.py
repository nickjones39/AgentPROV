"""``agentprov backends build`` without building (MN N.2.10, N.2.1b; M.1.7 rules 2-4; G.6.2; G.4.10).

The real build runs in ``tests/integration/test_run_live_agentdojo.py`` (``backend_agentdojo``). Here: the repository
root rule, typed refusals, the ``uv`` command line and environment, the dry run, the guarded-module list against the
worker's (by AST, never by import), the sandbox profile wrapper, and the T0 identity helpers on synthetic trees.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def in_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)


def test_outside_a_checkout_exits_3(cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = cli("backends", "build", "agentdojo", "--dry-run")
    assert run.code == 3 and "repository checkout" in run.err


def test_autodojo_dry_run_names_the_fork_pin_and_the_nltk_plan(cli, in_repo, tmp_path, monkeypatch, check_summary):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    run = cli("backends", "build", "autodojo", "--dry-run", "--json")
    assert run.code == 0, run.err
    check_summary(run.json())
    assert "autodojo-aa458794" in run.err and "--exclude-newer 2026-10-07T00:00:00Z" in run.err and "--offline" in run.err
    assert "https://github.com/xhOwenMa/AutoDojo@aa458794b7eb7f082e94daeac4c0f55bfc0c90cc" in run.err
    assert "NLTK punkt_tab" in run.err
    assert not home.exists()


def test_the_autodojo_project_pins_the_fork_and_declares_nltk(in_repo):
    from agentprov.cli.live import envs

    project = envs.backend_project("autodojo", envs.repository_root())
    assert envs.pinned_source(project) == {"kind": "git", "repo": "https://github.com/xhOwenMa/AutoDojo",
                                           "commit": "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc",
                                           "subdirectory": "agentdojo"}
    assert project.nltk is not None and project.nltk["package"] == "tokenizers/punkt_tab"
    assert envs.pinned_source(envs.backend_project("agentdojo", envs.repository_root())) is None


def test_an_action_is_required(cli, in_repo):
    assert cli("backends").code == 2
    assert cli("backends", "build", "nonesuch").code == 2


def test_dry_run_prints_the_locked_no_config_sync_and_writes_nothing(cli, in_repo, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    run = cli("backends", "build", "agentdojo", "--dry-run", "--json")
    assert run.code == 0, run.err
    for flag in ("--locked", "--no-config", "--no-dev", "--offline", "--exclude-newer 2026-10-07T00:00:00Z",
                 "--no-build-package agentdojo", "--reinstall-package agentprov-backend", "--link-mode copy"):
        assert flag in run.err, flag
    assert "commit8" in run.err and "lock_sha256" in run.err
    assert not home.exists()
    assert "--offline" not in cli("backends", "build", "agentdojo", "--dry-run", "--allow-network").err.split("would run:")[1].split("\n")[0]


def test_uv_missing_exits_3(cli, in_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path))
    run = cli("backends", "build", "agentdojo")
    assert run.code == 3 and "uv is not on PATH" in run.err


def test_offline_check_without_a_build_exits_3(cli, in_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    run = cli("backends", "build", "agentdojo", "--offline-check")
    assert run.code == 3 and "backends build agentdojo" in run.err


def test_the_env_name_comes_from_the_lock_digest_for_a_pypi_pin(in_repo):
    import hashlib

    from agentprov.cli.live import envs

    project = envs.backend_project("agentdojo", envs.repository_root())
    lock = hashlib.sha256((REPO / "backends" / "agentdojo" / "uv.lock").read_bytes()).hexdigest()
    assert project.commit is None and project.commit8 == lock[:8] and project.env_name == f"agentdojo-{lock[:8]}"
    autodojo = envs.backend_project("autodojo", envs.repository_root())
    assert autodojo.commit8_source == "fork_commit" and autodojo.commit8 == "aa458794"


def test_the_uv_environment_is_scrubbed(tmp_path):
    from agentprov.cli.live.envs import SCRUBBED_UV_VARIABLES, uv_environment

    parent = {name: "x" for name in SCRUBBED_UV_VARIABLES} | {
        "UV_CACHE_DIR": "/cache", "UV_PYTHON": "3.11", "UV_NO_CONFIG": "0", "VIRTUAL_ENV": "/v", "PATH": "/bin",
        "HOME": "/h", "OPENAI_API_KEY": "sk-should-not-pass-123456", "OPENAI_BASE_URL": "https://api.openai.com/v1",
    }  # fmt: skip
    env = uv_environment(parent, tmp_path / "env")
    assert env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "env") and env["UV_CACHE_DIR"] == "/cache"
    assert not set(SCRUBBED_UV_VARIABLES) & set(env) and "UV_PYTHON" not in env and "UV_NO_CONFIG" not in env
    assert "VIRTUAL_ENV" not in env and "OPENAI_API_KEY" not in env
    assert env["PATH"] == "/bin" and env["OPENAI_BASE_URL"].startswith("https://")  # public configuration passes


def test_guarded_modules_match_the_workers_guarded_names():
    """The core list mirrors agentprov_backend.identity.GUARDED_NAMES (read by AST; the core never imports it)."""
    from agentprov.cli.live.envs import GUARDED_MODULES

    tree = ast.parse((REPO / "backends/shared/src/agentprov_backend/identity.py").read_text(encoding="utf-8"))
    names = next(n for n in ast.walk(tree) if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "GUARDED_NAMES")
    modules = {elt.elts[0].value for elt in names.value.elts}  # type: ignore[union-attr]
    assert set(GUARDED_MODULES) == modules
    from agentprov.cli.live.envs import FORK_GUARDED_MODULES

    fork = next(n for n in ast.walk(tree)
                if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "AUTODOJO_GUARDED_NAMES")
    fork_modules = {elt.elts[0].value for elt in fork.value.elts}  # type: ignore[union-attr]
    assert set(FORK_GUARDED_MODULES["autodojo"]) == fork_modules - modules
    dyn = next(n for n in ast.walk(tree)
               if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "AGENTDYN_GUARDED_NAMES")
    dyn_modules = {elt.elts[0].value for elt in dyn.value.elts}  # type: ignore[union-attr]
    assert set(FORK_GUARDED_MODULES["agentdyn"]) == dyn_modules - modules


def test_the_sandbox_profile_is_parameterised_and_its_digest_fixed(tmp_path):
    from agentprov.cli.live import sandbox

    argv = sandbox.wrap_argv(["/env/bin/python", "-I"], staging_root=tmp_path / "s", t2home_root=tmp_path / "t",
                             repo=tmp_path / "r", home=tmp_path / "h", egress_port=40001)
    assert argv[0] == "/usr/bin/sandbox-exec" and argv[-2:] == ["/env/bin/python", "-I"]
    assert argv[argv.index("-p") + 1] == sandbox.PROFILE
    params = dict(a.split("=", 1) for a in argv if "=" in a)
    assert set(params) == {"STAGING", "T2HOME", "REPO", "HOME", "EGRESS_PORT", "LOOPBACK_PORT"}
    assert params["EGRESS_PORT"] == params["LOOPBACK_PORT"] == "40001"  # the ports are parameters: the digest is fixed
    assert sandbox.PROFILE_SHA256.startswith("sha256:") and "(deny file-write*)" in sandbox.PROFILE
    # D-664: outbound connections are denied except to the two loopback ports
    assert "(deny network-outbound)" in sandbox.PROFILE and sandbox.PROFILE.count('(param "EGRESS_PORT")') == 1
    for bad in (0, 65536, True):
        with pytest.raises(ValueError):
            sandbox.wrap_argv(["x"], staging_root=tmp_path, t2home_root=tmp_path, repo=tmp_path, home=tmp_path,
                              egress_port=bad)


def test_the_probe_is_not_applicable_off_macos(tmp_path, monkeypatch):
    from agentprov.cli.live import sandbox

    monkeypatch.setattr(sandbox.platform, "system", lambda: "Linux")
    result = sandbox.probe(tmp_path / "python", tmp_path)
    assert result["status"] == "not_applicable" and result["profile_sha256"] == sandbox.PROFILE_SHA256


def test_a_marker_that_is_not_strict_json_is_an_identity_mismatch(tmp_path):
    from agentprov.cli.live import envs
    from agentprov.errors import IdentityMismatch

    (tmp_path / envs.ENV_MARKER).write_text('{"format": "x", "format": "y"}')
    with pytest.raises(IdentityMismatch):
        envs.read_marker(tmp_path)
    (tmp_path / envs.ENV_MARKER).write_text(json.dumps({"format": "other"}))
    with pytest.raises(IdentityMismatch):
        envs.read_marker(tmp_path)
    assert envs.read_marker(tmp_path / "absent") is None


# ------------------------------------------------------------------------------------------------ AutoDojo (D.11.2)
def _autodojo(**changes):
    import dataclasses

    from agentprov.cli.live import envs

    return dataclasses.replace(envs.backend_project("autodojo", REPO), **changes)


PUNKT = b"PK synthetic punkt_tab bytes (not the real data)"


def _pinned_nltk(sha256: str) -> dict:
    return {"package": "tokenizers/punkt_tab", "url": "https://nltk.invalid/punkt_tab.zip", "sha256": sha256}


def test_nltk_is_provisioned_unextracted_from_the_verified_cache_without_network(tmp_path):
    import hashlib

    from agentprov.cli.live import envs
    from agentprov.errors import IdentityMismatch

    digest = hashlib.sha256(PUNKT).hexdigest()
    home = tmp_path / "aphome"
    (home / "cache" / "url").mkdir(parents=True)
    (home / "cache" / "url" / digest).write_bytes(PUNKT)
    env = tmp_path / "env"
    env.mkdir()
    record = envs.provision_nltk(env, _autodojo(nltk=_pinned_nltk(digest)), {"AGENTPROV_HOME": str(home)},
                                 allow_network=False)
    assert record["status"] == "provisioned" and record["sha256"] == digest and record["fetched"] is False
    zipped = env / "nltk_data" / "tokenizers" / "punkt_tab.zip"
    assert zipped.read_bytes() == PUNKT and not (env / "nltk_data" / "tokenizers" / "punkt_tab").exists()
    assert not (home / "cache" / "acquisitions.jsonl").exists()  # nothing was acquired
    assert envs.check_nltk(env, {"nltk_sha256": digest}) == str(env / "nltk_data")
    assert envs.check_nltk(env, {"nltk_sha256": None}) is None
    zipped.write_bytes(b"tampered")
    with pytest.raises(IdentityMismatch):
        envs.check_nltk(env, {"nltk_sha256": digest})


def test_nltk_without_cache_or_pin_is_recorded_null(tmp_path):
    import hashlib

    from agentprov.cli.live import envs

    environ = {"AGENTPROV_HOME": str(tmp_path / "aphome")}
    offline = envs.provision_nltk(tmp_path / "env", _autodojo(nltk=_pinned_nltk(hashlib.sha256(PUNKT).hexdigest())),
                                  environ, allow_network=False)
    assert offline["status"] == "not_cached" and offline["sha256"] is None
    unpinned = envs.provision_nltk(tmp_path / "env", _autodojo(nltk={"package": "tokenizers/punkt_tab"}), environ,
                                   allow_network=True)  # the recipe has no url: nothing can be fetched
    assert unpinned["status"] == "recipe_unpinned" and unpinned["sha256"] is None
    assert envs.provision_nltk(tmp_path / "env", _autodojo(nltk=None), environ, allow_network=False)["status"] == "not_declared"
    assert not (tmp_path / "env").exists()


def test_a_cache_that_does_not_match_the_pin_is_an_error(tmp_path):
    from agentprov.cli.live import envs
    from agentprov.errors import BackendUnavailable

    home = tmp_path / "aphome"
    (home / "cache" / "url").mkdir(parents=True)
    (home / "cache" / "url" / ("ab" * 32)).write_bytes(PUNKT)
    with pytest.raises(BackendUnavailable):
        envs.provision_nltk(tmp_path / "env", _autodojo(nltk=_pinned_nltk("ab" * 32)), {"AGENTPROV_HOME": str(home)},
                            allow_network=False)


def test_the_worker_environment_carries_nltk_data_only_when_given(tmp_path):
    from agentprov.cli.live.worker import worker_environment

    assert "NLTK_DATA" not in worker_environment(home=tmp_path, block_network=True)
    assert worker_environment(home=tmp_path, block_network=True, nltk_data="/env/nltk_data")["NLTK_DATA"] == "/env/nltk_data"


def _fake_fork_env(tmp_path: Path, commit: str) -> Path:
    import sys

    sys.path.insert(0, str(REPO / "tests" / "integration"))
    from live_fake import _dist

    from agentprov.cli.live import envs

    env = tmp_path / "env"
    sp = env / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    modules = (*envs.GUARDED_MODULES, *envs.FORK_GUARDED_MODULES["autodojo"])
    files = {m.replace(".", "/") + ".py": f"# fake {m}\n".encode() for m in modules}
    direct = {"url": "https://github.com/xhOwenMa/AutoDojo", "subdirectory": "agentdojo",
              "vcs_info": {"vcs": "git", "commit_id": commit, "requested_revision": commit}}
    _dist(sp, "agentdojo", "0.1.35", {"agentdojo/__init__.py": b"", **files,
                                      "agentdojo-0.1.35.dist-info/direct_url.json": json.dumps(direct).encode()})
    _dist(sp, "agentprov-backend", "0.1.0", {"agentprov_backend/__init__.py": b""})
    _dist(sp, "agentprov-capture", "0.1.0", {"agentprov_capture/__init__.py": b""})
    return env


def test_t0_identity_requires_the_pinned_fork_commit(tmp_path):
    from agentprov.cli.live import envs
    from agentprov.errors import IdentityMismatch

    project = _autodojo()
    good = envs.compute_identity(_fake_fork_env(tmp_path / "a", project.commit), project)
    assert good.distributions["agentdojo"].source == envs.pinned_source(project)
    assert "agentdojo/attacks/autodojo_attack.py" in good.guarded_files
    with pytest.raises(IdentityMismatch, match="not the pinned"):
        envs.compute_identity(_fake_fork_env(tmp_path / "b", "0" * 40), project)


def test_an_environment_built_under_another_guarded_list_must_be_rebuilt(tmp_path):
    """D-656 added anthropic_llm.py to the guarded modules: an environment whose build record lacks it is refused with
    a rebuild instruction; the same list with a different digest stays a plain mismatch."""
    from agentprov.cli.live import envs
    from agentprov.errors import IdentityMismatch

    project = _autodojo()
    identity = envs.compute_identity(_fake_fork_env(tmp_path / "a", project.commit), project)
    assert "agentdojo/agent_pipeline/llms/anthropic_llm.py" in identity.guarded_files
    current = identity.to_json()
    marker = {"status": "complete", "backend": project.backend, "lock_sha256": project.lock_sha256,
              "commit": project.commit, "t0_identity": current}
    envs.check_against_marker(identity, marker, project)
    old = {k: v for k, v in current["guarded_files"].items() if not k.endswith("anthropic_llm.py")}
    with pytest.raises(IdentityMismatch, match="rebuild it with 'agentprov backends build autodojo'"):
        envs.check_against_marker(identity, {**marker, "t0_identity": {**current, "guarded_files": old}}, project)
    tampered = {**current["guarded_files"], "agentdojo/benchmark.py": "0" * 64}
    with pytest.raises(IdentityMismatch, match="guarded_files differs"):
        envs.check_against_marker(identity, {**marker, "t0_identity": {**current, "guarded_files": tampered}}, project)


def test_check_hello_refuses_another_backend():
    from agentprov.cli.live.envs import EnvIdentity, check_hello
    from agentprov.errors import IdentityMismatch

    ident = EnvIdentity("0" * 64, {}, {})
    hello = {"identity": {"lock_sha256": "0" * 64}, "worker": {"backend": "agentdojo"}}
    check_hello(hello, ident, None, backend="agentdojo")
    with pytest.raises(IdentityMismatch):
        check_hello(hello, ident, None, backend="autodojo")


def _live_child():
    import subprocess
    import sys

    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


def test_a_build_refuses_while_a_run_uses_the_environment(cli, in_repo, tmp_path, monkeypatch):
    """CLI robustness item 3 (G6a): a rebuild never replaces an environment under a live run; nothing is run."""
    import platform

    from agentprov.cli.live import envs

    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    name = envs.backend_project("agentdojo", REPO).env_name
    child = _live_child()
    try:
        users = home / "locks" / "envs" / f"{name}.users"
        users.mkdir(parents=True)
        (users / f"{child.pid}@{platform.node()}.json").write_text(json.dumps(
            {"command": "run", "host": platform.node(), "pid": child.pid, "started": "2026-10-14T10:00:00Z"}))
        run = cli("backends", "build", "agentdojo", "--json")
    finally:
        child.kill()
        child.wait()
    assert run.code == 4 and f"in use by pid {child.pid}" in run.err, run.err
    assert "[io.resource_busy]" in run.err
    assert not (home / "envs").exists()


def test_offline_check_is_refused_while_the_environment_is_being_built(cli, in_repo, tmp_path, monkeypatch):
    """Pre-round review D #14: --offline-check took no lock, so it could read an environment a concurrent build was
    rewriting. It now registers as a user of the environment, which the build lock refuses."""
    from agentprov.cli.live import envs
    from agentprov.io.locks import backend_build_lock

    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    project = envs.backend_project("agentdojo", envs.repository_root())
    with backend_build_lock(home, project.env_name):
        run = cli("backends", "build", "agentdojo", "--offline-check")
    assert run.code != 0 and "being built" in run.err, run.err
    run = cli("backends", "build", "agentdojo", "--offline-check")  # no build running: the usual missing-build refusal
    assert run.code == 3 and "backends build agentdojo" in run.err
