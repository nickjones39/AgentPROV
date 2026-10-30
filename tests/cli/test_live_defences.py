"""T0's side of defended live runs (D-670, D-677, D-679; ``agentprov.cli.live.defences``).

The registry is the backend harness's data file, read here as TOML (the core never imports ``agentprov_backend``).
Live profiles v1 allow no defence, so every defended run is refused with exit 5 before anything is spawned, from the
flag and from a plan alike; the checks that apply once a profile allows a defence are exercised with a live table
that does. Provisioning copies a pinned file from a local bare fetch cache (a synthetic repository; no network).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.live import defences
from agentprov.cli.live.defences import (
    DefenceRefused,
    allowed_defences,
    check_defence,
    check_environment,
    load_registry,
    plan_defence,
    provision,
    registry_path,
    verify_provisioned,
)

ROOT = Path(__file__).resolve().parents[2]
ALLOWING = {"defences": ["repeat_user_prompt", "tool_filter", "mandate_intent"]}


def test_the_repository_registry_loads():
    reg = load_registry(registry_path(ROOT))
    assert {"repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter", "transformers_pi_detector",
            "mandate_envelope", "mandate_scoped", "mandate_intent"} <= set(reg)
    mandate = reg["mandate_intent"]
    assert mandate.provider == "provisioned" and mandate.suites == ("banking",) and mandate.files


def test_profiles_v1_v2_allow_no_defence_and_v3_allows_the_first_set():
    from agentprov.adapters.profiles import load_profile

    for pid in ("agentdojo-live", "autodojo-live"):
        for version in (1, 2):
            assert allowed_defences(load_profile(pid, version).data["family"]["agentdojo"]["live"]) == ()
    assert set(allowed_defences(load_profile("agentdojo-live").data["family"]["agentdojo"]["live"])) == {
        "repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter", "transformers_pi_detector",
        "mandate_envelope", "mandate_scoped", "mandate_intent", "melon", "melon_sm", "melon_at"}  # D-671
    assert allowed_defences(load_profile("autodojo-live").data["family"]["agentdojo"]["live"]) == ()
    with pytest.raises(DefenceRefused) as exc:
        check_defence("tool_filter", backend="agentdojo", suites=["banking"], live={}, root=ROOT,
                      profile_label="agentdojo-live v1")
    assert "D-677" in " ".join(exc.value.lines)


@pytest.mark.parametrize(("defence", "backend", "suites", "words"), [
    ("no_such_defence", "agentdojo", ["banking"], "not in the defence registry"),
    ("tool_filter", "autodojo", ["banking"], "builds it on: agentdojo"),
    ("mandate_intent", "agentdojo", ["banking", "slack"], "runs on banking only"),
    ("spotlighting_with_delimiting", "agentdojo", ["banking"], "allows no such defence"),
])
def test_refusals(defence, backend, suites, words):
    with pytest.raises(DefenceRefused) as exc:
        check_defence(defence, backend=backend, suites=suites, live=ALLOWING, root=ROOT, profile_label="p v2")
    assert words in " ".join(exc.value.lines)


def test_an_allowed_defence_passes():
    entry = check_defence("tool_filter", backend="agentdojo", suites=["banking", "slack"], live=ALLOWING, root=ROOT,
                          profile_label="p v2")
    assert entry.id == "tool_filter" and entry.aux_llm == "agent_endpoint"


def test_plan_defence_reads_either_spelling():
    assert plan_defence({"plan": {"defence": "tool_filter"}}) == "tool_filter"
    assert plan_defence({"plan": {"defense": "tool_filter"}}) == "tool_filter"
    assert plan_defence({"plan": {"defence": "none"}}) is None
    assert plan_defence({}) is None


def _env_with_registry(tmp_path: Path, data: bytes) -> Path:
    env = tmp_path / "env"
    target = env / "lib" / "python3.12" / "site-packages" / "agentprov_backend" / "defences.toml"
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    return env


def test_the_environment_must_hold_the_repository_s_registry(tmp_path):
    entry = load_registry(registry_path(ROOT))["tool_filter"]
    good = _env_with_registry(tmp_path / "a", registry_path(ROOT).read_bytes())
    assert check_environment(good, entry, ROOT) == (None, None)
    stale = _env_with_registry(tmp_path / "b", b'format = "agentprov-defence-registry/0.1"\n')
    problem, _ = check_environment(stale, entry, ROOT)
    assert problem is not None and "rebuild" in problem


# ---------------------------------------------------------------------------------------------- provisioning


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo),
                               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}).stdout.strip()


@pytest.fixture
def pinned(tmp_path: Path) -> dict[str, Any]:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    from agentprov.raw.fetch import Fetcher, Recipe

    repo = tmp_path / "upstream"
    repo.mkdir()
    data = b"def make():\n    return 1\n"
    (repo / "gate.py").write_bytes(data)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "gate")
    commit = _git(repo, "rev-parse", "HEAD")
    blob = _git(repo, "rev-parse", "HEAD:gate.py")
    url = "https://github.com/example/gate"
    cache = tmp_path / "fetch-cache"
    Fetcher(cache, allow_network=True, remote_urls={url: f"file://{repo}"}, file_protocol=True).fetch(
        Recipe(kind="git", repo=url, commit=commit))
    base = load_registry(registry_path(ROOT))["mandate_intent"]
    entry = replace(base, id="test_gate", repo=url, commit=commit,
                    files=({"path": "gate.py", "blob_sha1": blob, "sha256": hashlib.sha256(data).hexdigest()},))
    return {"entry": entry, "cache": cache, "data": data}


def test_provision_copies_the_pinned_blob_and_verify_checks_it(tmp_path, pinned):
    env = tmp_path / "env"
    record = provision(env, pinned["entry"], cache_dir=pinned["cache"], allow_network=False)
    assert record["files"] == {"gate.py": hashlib.sha256(pinned["data"]).hexdigest()}
    target = defences.provisioned_dir(env, pinned["entry"]) / "gate.py"
    assert target.read_bytes() == pinned["data"]
    assert verify_provisioned(env, pinned["entry"]) is None
    target.chmod(0o644)
    target.write_bytes(b"tampered\n")
    assert "differs" in verify_provisioned(env, pinned["entry"])


def test_provision_refuses_another_blob_and_an_uncached_commit(tmp_path, pinned):
    wrong = replace(pinned["entry"], files=({**pinned["entry"].files[0], "blob_sha1": "0" * 40},))
    with pytest.raises(ValueError, match="not the pinned blob"):
        provision(tmp_path / "env", wrong, cache_dir=pinned["cache"], allow_network=False)
    absent = replace(pinned["entry"], commit="1" * 40)
    with pytest.raises(ValueError, match="not in the fetch cache"):
        provision(tmp_path / "env", absent, cache_dir=pinned["cache"], allow_network=False)


def test_a_missing_provisioned_file_is_a_refusal_not_an_environment_error(tmp_path):
    entry = load_registry(registry_path(ROOT))["mandate_intent"]
    env = _env_with_registry(tmp_path, registry_path(ROOT).read_bytes())
    problem, refusal = check_environment(env, entry, ROOT)
    assert problem is None and refusal is not None and "--defence-assets mandate_intent" in refusal


# ---------------------------------------------------------------------------------------------- weights (D-672)


def test_the_pi_detector_entry_pins_its_weights_and_modules():
    entry = load_registry(registry_path(ROOT))["transformers_pi_detector"]
    (weights,) = entry.weights
    assert weights["repo"] == "protectai/deberta-v3-base-prompt-injection-v2" and len(weights["revision"]) == 40
    assert {f["path"] for f in weights["files"]} >= {"config.json", "model.safetensors", "tokenizer.json"}
    assert entry.python == ("torch", "transformers")


def _fake_weights_entry(tmp_path: Path) -> tuple[Any, Path]:
    from agentprov.raw.fetch import Recipe

    data = {"config.json": b'{"model_type": "fake"}\n', "model.safetensors": b"\x00" * 64}
    cache = tmp_path / "fetch-cache"
    files = []
    for path, blob in data.items():
        sha = hashlib.sha256(blob).hexdigest()
        files.append({"path": path, "sha256": sha, "size": len(blob)})
        url = f"https://huggingface.co/example/fake-model/resolve/{'a' * 40}/{path}"
        target = Recipe(kind="url", url=url, sha256=sha, size=len(blob)).cache_path(cache)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    base = load_registry(registry_path(ROOT))["transformers_pi_detector"]
    entry = replace(base, weights=({"repo": "example/fake-model", "revision": "a" * 40, "hosts": [], "files": files},))
    return entry, cache


def test_weights_are_provisioned_from_the_fetch_cache_and_verified(tmp_path):
    entry, cache = _fake_weights_entry(tmp_path)
    env = _env_with_registry(tmp_path / "e", registry_path(ROOT).read_bytes())
    problem, refusal = check_environment(env, entry, ROOT)
    assert problem is None and "torch" in refusal  # the defences group is not installed yet
    for module in ("torch", "transformers"):
        (env / "lib" / "python3.12" / "site-packages" / module).mkdir()
    assert "not provisioned" in check_environment(env, entry, ROOT)[1]
    (record,) = defences.provision_weights(env, entry, cache_dir=cache, allow_network=False)
    assert record["revision"] == "a" * 40 and set(record["files"]) == {"config.json", "model.safetensors"}
    model = defences.hf_cache_dir(env) / "models--example--fake-model"
    assert (model / "refs" / "main").read_text() == "a" * 40
    assert check_environment(env, entry, ROOT) == (None, None)
    weight = model / "snapshots" / ("a" * 40) / "model.safetensors"
    weight.chmod(0o644)
    weight.write_bytes(b"\x01" * 64)  # same size, other bytes
    assert "differs" in check_environment(env, entry, ROOT)[1]


def test_uncached_weights_need_the_network_flag(tmp_path):
    entry, _cache = _fake_weights_entry(tmp_path)
    with pytest.raises(ValueError, match="--allow-network"):
        defences.provision_weights(tmp_path / "env", entry, cache_dir=tmp_path / "empty-cache", allow_network=False)


def test_the_worker_gets_the_offline_hub_cache_only_for_weights():
    from agentprov.cli.live.worker import worker_environment

    plain = worker_environment(home=Path("/h"), block_network=True)
    assert not any(k.startswith(("HF_", "TRANSFORMERS")) for k in plain)
    env = worker_environment(home=Path("/h"), block_network=True, hf_cache="/env/agentprov_defences/hf")
    assert env["HF_HUB_CACHE"] == "/env/agentprov_defences/hf"
    assert env["HF_HUB_OFFLINE"] == "1" and env["TRANSFORMERS_OFFLINE"] == "1" and env["HF_HUB_DISABLE_TELEMETRY"] == "1"


# ---------------------------------------------------------------------------------------------- MELON's needs (D-674, D-675)


def test_melon_entries_are_ports_with_a_defence_endpoint():
    reg = load_registry(registry_path(ROOT))
    for did in ("melon", "melon_sm", "melon_at"):
        entry = reg[did]
        assert entry.provider == "port" and entry.aux_llm == "defence_endpoint" and entry.repo == "https://github.com/xwsdid/MELON"
    assert "melon_r" not in reg and "melon_rp" not in reg


def test_defence_source_accepts_only_the_pinned_blob(tmp_path):
    entry, _cache = _fake_weights_entry(tmp_path)  # any entry; the code pins are replaced below
    data = b"def make():\n    return 2\n"
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    entry = replace(entry, provider="port", repo="https://github.com/example/gate", commit="b" * 40,
                    files=({"path": "pkg/gate.py", "blob_sha1": blob, "sha256": hashlib.sha256(data).hexdigest()},))
    tree = tmp_path / "tree"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "gate.py").write_bytes(data)
    record = provision(tmp_path / "env", entry, cache_dir=tmp_path / "no-cache", allow_network=False, source_dir=tree)
    assert record["source"].startswith("local") and (defences.provisioned_dir(tmp_path / "env", entry) / "pkg/gate.py").read_bytes() == data
    (tree / "pkg" / "gate.py").write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="not the pinned blob"):
        provision(tmp_path / "env2", entry, cache_dir=tmp_path / "no-cache", allow_network=False, source_dir=tree)
    (tree / "pkg" / "gate.py").unlink()
    (tree / "pkg" / "gate.py").symlink_to(tmp_path / "elsewhere.py")
    (tmp_path / "elsewhere.py").write_bytes(data)
    with pytest.raises(ValueError, match="regular file"):
        provision(tmp_path / "env3", entry, cache_dir=tmp_path / "no-cache", allow_network=False, source_dir=tree)
    # an entry whose files the tree lacks falls back to the fetch cache (here uncached: the network flag is needed)
    with pytest.raises(ValueError, match="not in the fetch cache"):
        provision(tmp_path / "env4", entry, cache_dir=tmp_path / "no-cache", allow_network=False,
                  source_dir=tmp_path / "empty-tree")


def test_the_defence_endpoint_is_needed_by_real_melon_runs_only():
    import argparse

    from agentprov.cli.common import CliUsageError, CommandResult
    from agentprov.cli.run import _defence_endpoint

    melon = load_registry(registry_path(ROOT))["melon"]
    tool_filter = load_registry(registry_path(ROOT))["tool_filter"]
    args = argparse.Namespace(defence_endpoint=None, allow_custom_endpoint=False)
    assert _defence_endpoint(args, melon, {}, {}, CommandResult(), scripted=True) is None
    with pytest.raises(CliUsageError, match="--defence-endpoint"):
        _defence_endpoint(args, melon, {}, {}, CommandResult(), scripted=False)
    args.defence_endpoint = "openai"
    with pytest.raises(CliUsageError, match="calls its own endpoint"):
        _defence_endpoint(args, tool_filter, {}, {}, CommandResult(), scripted=False)
    keys: dict[str, str] = {}
    spec = _defence_endpoint(args, melon, {"OPENAI_API_KEY": "sk-test-0123456789abcdef"}, keys, CommandResult(),
                             scripted=False)
    assert spec is not None and spec["endpoint"] == "openai" and spec["api_key_env"] == "OPENAI_API_KEY"
    assert keys == {"OPENAI_API_KEY": "sk-test-0123456789abcdef"}
