"""``agentprov models`` and the local-model discovery module (D-691..D-693), against stub loopback servers.

No real model server and no model: ``agentprov.testing.local_server.StubServer`` serves synthetic bodies in each server
kind's shape, including hostile ones. File digests use temporary HF-cache, LM Studio and operator trees.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.live import localmodels as lm
from agentprov.testing.local_server import StubServer

COMMIT = "c" * 40


# ---- fingerprint and listings --------------------------------------------------------------------------------


@pytest.mark.parametrize("kind, observed", [("ollama", "ollama"), ("lmstudio", "lmstudio"), ("llamacpp", "llamacpp"),
                                             ("vllm", "vllm"), ("omlx", "openai_generic"), ("mlx_lm", "openai_generic")])
def test_detect_server_names_each_kind(kind: str, observed: str) -> None:
    with StubServer(kind) as srv:
        listing = lm.list_server(srv.base_url, endpoint=kind, expected_kind=kind)
    assert listing.server.kind == observed
    assert listing.rows and all(r["servable"] for r in listing.rows if not r["remote"])


@pytest.mark.parametrize("expected, actual", [("omlx", "vllm"), ("mlx_lm", "llamacpp"), ("lmstudio", "mlx_lm"),
                                              ("vllm", "omlx"), ("ollama", "lmstudio")])
def test_wrong_server_kind_on_a_shared_port_is_refused(expected: str, actual: str) -> None:
    with StubServer(actual) as srv, pytest.raises(lm.LocalModelError) as exc:
        lm.list_server(srv.base_url, endpoint=expected, expected_kind=expected)
    assert (exc.value.code, exc.value.exit_code) == ("run.local.wrong_server", 4)


def test_ollama_rows_identity_and_cloud_model() -> None:
    with StubServer("ollama") as srv:
        listing = lm.list_server(srv.base_url, endpoint="ollama", expected_kind="ollama")
        tiny = listing.row("tiny-llm:1b")
        assert tiny is not None and tiny["digest"] == "sha256:" + "a" * 64
        assert (tiny["family"], tiny["params"], tiny["quantization"], tiny["remote"]) == ("tinyllm", "1.0B", "Q4_K_M", False)
        assert listing.row("big-llm:70b-cloud")["remote"] is True  # type: ignore[index]
        rec = lm.model_identity(listing, "tiny-llm:1b")
        with pytest.raises(lm.LocalModelError) as exc:
            lm.model_identity(listing, "big-llm:70b-cloud")
        posts = [s for s in srv.seen if s["method"] == "POST"]
    assert (exc.value.code, exc.value.exit_code) == ("run.local.remote_model", 4)
    ident = rec["server_identity"]
    assert ident["digest"] == "sha256:" + "a" * 64 and ident["capabilities"] == ["completion", "tools"]
    assert ident["architecture"] == "tinyllm" and ident["context_length"] == 4096
    assert ident["template_sha256"] == "sha256:" + hashlib.sha256(b"{{ .Prompt }}").hexdigest()
    assert rec["files"] is None and rec["files_reason"] == "ollama_manifest_digest"
    assert rec["server"]["version"] == "0.0.1-stub" and rec["identity_sha256"] == lm.identity_sha256(rec)
    assert json.loads(posts[0]["body"]) == {"model": "tiny-llm:1b"}  # the only POST: metadata, no inference
    assert all("authorization" not in s["headers"] for s in srv.seen)


def test_model_not_served_is_exit_3() -> None:
    with StubServer("vllm") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="vllm")
        with pytest.raises(lm.LocalModelError) as exc:
            lm.model_identity(listing, "nope")
    assert (exc.value.code, exc.value.exit_code) == ("run.local.model_not_served", 3)


def test_lmstudio_rows_skip_embeddings_and_report_load_state() -> None:
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
    assert [r["id"] for r in listing.rows] == ["plain-model", "tiny-model-4bit"]
    tiny = listing.row("tiny-model-4bit")
    assert tiny is not None and (tiny["loaded"], tiny["parallel"], tiny["tool_use"], tiny["context_length"]) == (True, 4, True, 8192)
    assert listing.row("plain-model")["tool_use"] is False  # type: ignore[index]


# ---- hostile responses ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("body", [
    b'{"data": [{"id": "a"}], "data": []}',  # duplicate key
    b'{"data": [{"id": NaN}]}',
    b"not json",
    b'{"data": "x"}',
    b"[" * 10_000 + b"]" * 10_000,
])
def test_bad_listing_is_exit_3(body: bytes) -> None:
    with StubServer("omlx") as srv:
        srv.set("/v1/models", 200, body)
        with pytest.raises(lm.LocalModelError) as exc:
            lm.list_server(srv.base_url)
    assert (exc.value.code, exc.value.exit_code) == ("run.local.bad_listing", 3)


def test_oversize_and_redirect_are_never_followed() -> None:
    with StubServer("omlx") as srv:
        srv.set("/v1/models", 200, b" " * (lm.MAX_BODY_BYTES + 10))
        with pytest.raises(lm.LocalModelError):
            lm.list_server(srv.base_url)
        srv.set("/v1/models", 302, b"")
        with pytest.raises(lm.LocalModelError):
            lm.list_server(srv.base_url)
        assert [s["path"] for s in srv.seen if s["path"] == "/v1/models"]  # only the stub was contacted


def test_path_like_and_control_ids_are_dropped() -> None:
    models = [{"id": "../etc"}, {"id": "/abs"}, {"id": "ok-model"}, {"id": "bad\u202eid"}, {"id": "x" * 300}]
    with StubServer("omlx", models=models) as srv:
        listing = lm.list_server(srv.base_url)
    assert listing.ids() == ["ok-model"]


@pytest.mark.parametrize("url, code", [("http://192.168.1.5:1234/v1", "run.local.url"),
                                        ("https://api.example.com/v1", "run.local.not_loopback"),
                                        ("http://10.0.0.1/v1", "run.local.url")])
def test_non_loopback_is_refused_before_connecting(url: str, code: str) -> None:
    with pytest.raises(lm.LocalModelError) as exc:
        lm.LoopbackClient(url)
    assert (exc.value.code, exc.value.exit_code) == (code, 4)


def test_unreachable_is_exit_3() -> None:
    with StubServer("omlx") as srv:
        url = srv.base_url
    with pytest.raises(lm.LocalModelError) as exc:
        lm.list_server(url)
    assert (exc.value.code, exc.value.exit_code) == ("run.local.unreachable", 3)


# ---- files ---------------------------------------------------------------------------------------------------


def _hf_repo(root: Path, repo: str, weights: bytes, config: bytes) -> str:
    org, name = repo.split("/")
    base = root / f"models--{org}--{name}"
    (base / "refs").mkdir(parents=True)
    (base / "refs" / "main").write_text(COMMIT)
    blobs, snap = base / "blobs", base / "snapshots" / COMMIT
    blobs.mkdir()
    snap.mkdir(parents=True)
    wsha = hashlib.sha256(weights).hexdigest()
    (blobs / wsha).write_bytes(weights)
    (blobs / ("e" * 40)).write_bytes(config)
    os.symlink(f"../../blobs/{wsha}", snap / "model.safetensors")
    os.symlink(f"../../blobs/{'e' * 40}", snap / "config.json")
    return wsha


def test_hf_cache_snapshot_uses_blob_names_for_weights(tmp_path: Path) -> None:
    wsha = _hf_repo(tmp_path, "stub-org/tiny-model-4bit", b"W" * 1000, b'{"model_type": "tiny"}')
    with StubServer("mlx_lm") as srv:
        listing = lm.list_server(srv.base_url, endpoint="mlx_lm", expected_kind="mlx_lm")
        rec = lm.model_identity(listing, "stub-org/tiny-model-4bit", environ={"HF_HUB_CACHE": str(tmp_path)})
    files = rec["files"]
    assert (files["method"], files["label"], files["snapshot_commit"]) == ("hf_cache", "stub-org/tiny-model-4bit", COMMIT)
    by = {f["name"]: f for f in files["files"]}
    assert by["model.safetensors"] == {"name": "model.safetensors", "size": 1000, "sha256": "sha256:" + wsha,
                                       "sha256_source": "hf_blob_name"}
    assert by["config.json"]["sha256"] == "sha256:" + hashlib.sha256(b'{"model_type": "tiny"}').hexdigest()
    assert str(tmp_path) not in json.dumps(rec)  # no absolute path is recorded


def _lmstudio_tree(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "lmhome"
    models = tmp_path / "elsewhere" / "models"
    model = models / "stub-pub" / "Tiny-Model-4bit"
    model.mkdir(parents=True)
    (model / "config.json").write_bytes(b"{}")
    (model / "model.safetensors").write_bytes(b"\x00" * 2048)
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"downloadsFolder": str(models)}))
    return home, model


def test_lmstudio_dir_from_settings_with_digest_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, _model = _lmstudio_tree(tmp_path)
    calls: list[Path] = []
    real = lm._hash_file
    monkeypatch.setattr(lm, "_hash_file", lambda p: calls.append(p) or real(p))
    cache = lm.DigestCache(tmp_path / "cache" / "digests.jsonl", writable=True)
    env = {"LMSTUDIO_HOME": str(home)}
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
        rec1 = lm.model_identity(listing, "tiny-model-4bit", environ=env, cache=cache)
        weights_hashed = len([c for c in calls if c.name.endswith(".safetensors")])
        rec2 = lm.model_identity(listing, "tiny-model-4bit", environ=env,
                                 cache=lm.DigestCache(tmp_path / "cache" / "digests.jsonl", writable=False))
    assert weights_hashed == 1
    assert len([c for c in calls if c.name.endswith(".safetensors")]) == 1  # the second run read the cache
    assert rec1["files"]["label"] == "stub-pub/Tiny-Model-4bit" and rec1["files"]["method"] == "lmstudio_dir"
    assert rec1["identity_sha256"] == rec2["identity_sha256"]
    assert rec1["server_identity"]["trained_for_tool_use"] is True
    assert str(tmp_path) not in json.dumps(rec1)


def test_lmstudio_key_differs_from_dir_name_resolved_by_size(tmp_path: Path) -> None:
    """LM Studio 0.4.23 serves key ``qwen3-8b-abliterated-v2`` for ``Qwen3-8B-abliterated-v2-mxfp4``: a name-prefix
    candidate is accepted only when its total file size equals the server's ``size_bytes``."""
    home = tmp_path / "lmhome"
    root = home / "models" / "stub-pub"
    for name, size in (("Tiny-Model-mxfp4", 300), ("Tiny-Model-8bit", 500), ("Tiny-Modelx", 300)):
        (root / name).mkdir(parents=True)
        (root / name / "model.safetensors").write_bytes(b"\x00" * size)
    models = [{"type": "llm", "publisher": "stub-pub", "key": "tiny-model", "size_bytes": 300, "loaded_instances": []}]
    env = {"LMSTUDIO_HOME": str(home)}
    with StubServer("lmstudio", models=models) as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
        rec = lm.model_identity(listing, "tiny-model", environ=env)
        assert (rec["files"]["label"], rec["files"]["match"]) == ("stub-pub/Tiny-Model-mxfp4", "name_and_size")
        (root / "Tiny-Model-other" / "x").mkdir(parents=True)
        (root / "Tiny-Model-other" / "x" / "w.gguf").write_bytes(b"\x01" * 300)
        rec = lm.model_identity(listing, "tiny-model", environ=env)
    assert rec["files"] is None and rec["files_reason"] == "ambiguous"


def test_lmstudio_embeddings_are_not_listed_and_unknown_routes_answer_200() -> None:
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
    assert "embed-small" not in listing.ids(servable_only=False)
    assert listing.server.kind == "lmstudio"  # the 200 error bodies of /api/version, /props, /version mislead nothing


def test_no_hash_weights_records_size_only(tmp_path: Path) -> None:
    home, _ = _lmstudio_tree(tmp_path)
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
        rec = lm.model_identity(listing, "tiny-model-4bit", environ={"LMSTUDIO_HOME": str(home)}, hash_weights=False)
    weights = next(f for f in rec["files"]["files"] if f["name"] == "model.safetensors")
    assert weights == {"name": "model.safetensors", "size": 2048, "sha256": None, "sha256_source": "not_hashed"}
    assert rec["files"]["weights_hashed"] is False


def test_symlink_outside_the_model_dir_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read")
    model = tmp_path / "m"
    model.mkdir()
    (model / "config.json").write_bytes(b"{}")
    os.symlink(outside, model / "tokenizer.json")
    facts = lm.walk_model_dir(model, "m", "operator_dir", hash_weights=True, cache=lm.DigestCache(None, writable=False))
    assert [f["name"] for f in facts.files] == ["config.json"]
    assert facts.problems == ["symlink_outside_root"]


def test_llamacpp_needs_and_checks_model_dir(tmp_path: Path) -> None:
    gguf = tmp_path / "tiny-model-4bit.gguf"
    gguf.write_bytes(b"GGUF" + b"\x00" * 100)
    other = tmp_path / "other.gguf"
    other.write_bytes(b"GGUF")
    with StubServer("llamacpp", models=[{"id": "tiny"}]) as srv:
        listing = lm.list_server(srv.base_url, expected_kind="llamacpp")
        rec = lm.model_identity(listing, "tiny")
        assert rec["files"] is None and "model-dir" in rec["files_reason"]
        assert rec["observed_state"]["total_slots"] == 2 and "total_slots" not in rec["server_identity"]  # D-736
        assert rec["server_identity"]["model_file"] == "tiny-model-4bit.gguf"
        rec = lm.model_identity(listing, "tiny", model_dir=str(gguf))
        assert rec["files"]["files"][0]["sha256"] == "sha256:" + hashlib.sha256(gguf.read_bytes()).hexdigest()
        with pytest.raises(lm.LocalModelError) as exc:
            lm.model_identity(listing, "tiny", model_dir=str(other))
    assert exc.value.code == "run.local.model_dir_mismatch"


def test_server_side_digest_ignores_load_state() -> None:
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
        a = lm.model_identity(listing, "tiny-model-4bit", files=False)
        models: list[dict[str, Any]] = json.loads(srv.routes[("GET", "/api/v1/models")][1])["models"]
        models[0]["loaded_instances"] = []
        srv.set("/api/v1/models", 200, {"models": models})
        b = lm.model_identity(lm.list_server(srv.base_url, expected_kind="lmstudio"), "tiny-model-4bit", files=False)
        models[0]["quantization"] = {"name": "8bit", "bits_per_weight": 8}
        srv.set("/api/v1/models", 200, {"models": models})
        c = lm.model_identity(lm.list_server(srv.base_url, expected_kind="lmstudio"), "tiny-model-4bit", files=False)
    assert lm.server_side_sha256(a) == lm.server_side_sha256(b) != lm.server_side_sha256(c)


# ---- the command ---------------------------------------------------------------------------------------------


def test_models_command_lists_one_server_as_json(cli: Callable[..., Any]) -> None:
    with StubServer("ollama") as srv:
        run = cli("models", "--base-url", srv.base_url, "--format", "json")
    assert run.code == 0, run.err
    doc = run.json()
    assert doc["format"] == "agentprov-local-models/0.1"
    (entry,) = doc["endpoints"]
    assert entry["status"] == "up" and entry["server"]["kind_observed"] == "ollama"
    assert {m["id"] for m in entry["models"]} == {"tiny-llm:1b", "big-llm:70b-cloud"}


def test_models_command_identity_and_not_served(cli: Callable[..., Any]) -> None:
    with StubServer("ollama") as srv:
        ok = cli("models", "--base-url", srv.base_url, "--model-id", "tiny-llm:1b", "--format", "json")
        text = cli("models", "--base-url", srv.base_url, "--model-id", "tiny-llm:1b")
        missing = cli("models", "--base-url", srv.base_url, "--model-id", "tiny-llm:2b")
    assert ok.code == 0 and ok.json()["format"] == "agentprov-local-model/0.2"
    assert text.code == 0 and "identity sha256:" in text.out
    assert missing.code == 3 and "tiny-llm:1b" in missing.err and "did you mean" in missing.err


def test_models_command_refuses_wrong_kind_and_remote_endpoints(cli: Callable[..., Any]) -> None:
    with StubServer("vllm") as srv:
        wrong = cli("models", "--endpoint", "omlx", "--base-url", srv.base_url)
    assert wrong.code == 4
    provider = cli("models", "--endpoint", "openai")  # D-730: an API provider shows its cached list (none here)
    assert provider.code == 0 and "none, fetched never" in provider.out
    assert cli("models", "--base-url", "http://192.168.0.2:1234/v1").code == 4
    assert cli("models", "--model-id", "x").code == 2


def test_models_command_lists_every_local_endpoint(cli: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from agentprov_capture import endpoints

    real = endpoints.load_endpoints()
    with StubServer("lmstudio") as srv:
        down = StubServer("omlx")
        with down:
            down_url = down.base_url
        fake = {n: e for n, e in real.items() if not e.local}
        fake["lmstudio"] = dataclasses.replace(real["lmstudio"], base_url=srv.base_url)
        fake["omlx"] = dataclasses.replace(real["omlx"], base_url=down_url)
        monkeypatch.setattr(endpoints, "load_endpoints", lambda: fake)
        from agentprov.cli import run as run_mod

        monkeypatch.setattr(run_mod, "_read_env_file", lambda args, root: {})  # omlx's optional key (D-827): no .env
        run = cli("models", "--format", "json")
    assert run.code == 0, run.err
    status = {e["endpoint"]: e["status"] for e in run.json()["endpoints"]}
    assert status == {"lmstudio": "up", "omlx": "down"}


# ---- D-698: LAN endpoints (opt-in) ----------------------------------------------------------------------------


class _PeerSock:
    """A socket whose peer address is reported as ``peer`` (the stub listens on loopback; no LAN traffic is sent)."""

    def __init__(self, sock: Any, peer: str) -> None:
        self._sock, self._peer = sock, peer

    def getpeername(self) -> tuple[str, int]:
        return (self._peer, 0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)


def _lan_client(srv: StubServer, lan_url: str, reported_peer: str) -> lm.LoopbackClient:
    import http.client

    class Conn(http.client.HTTPConnection):
        def __init__(self, host: str, port: int, timeout: float) -> None:
            super().__init__("127.0.0.1", srv.port, timeout=timeout)

        def connect(self) -> None:
            super().connect()
            self.sock = _PeerSock(self.sock, reported_peer)  # type: ignore[assignment]

    return lm.LoopbackClient(lan_url, allow_lan=True, connection=Conn)


def test_a_lan_url_needs_the_opt_in_and_a_literal_private_address() -> None:
    url = "http://192.168.1.20:1234/v1"
    with pytest.raises(lm.LocalModelError) as exc:
        lm.resolve_local("lmstudio", url)
    assert exc.value.exit_code == 4
    assert lm.resolve_local("lmstudio", url, allow_lan=True) == ("lmstudio", url, "lmstudio")
    for bad in ("http://8.8.8.8:1234/v1", "http://lan-box.local:1234/v1", "http://169.254.0.9:1234/v1"):
        with pytest.raises(lm.LocalModelError):
            lm.resolve_local("lmstudio", bad, allow_lan=True)


def test_a_lan_server_is_listed_and_recorded_without_local_files(tmp_path: Path) -> None:
    home, _ = _lmstudio_tree(tmp_path)  # a same-named copy on this machine must not be taken for the LAN model's files
    url = "http://192.168.1.20:1234/v1"
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(url, expected_kind="lmstudio", client=_lan_client(srv, url, "192.168.1.20"))
        rec = lm.model_identity(listing, "tiny-model-4bit", client=_lan_client(srv, url, "192.168.1.20"),
                                environ={"LMSTUDIO_HOME": str(home)})
    assert listing.lan and rec["network"] == "lan" and rec["base_url"] == url
    assert rec["files"] is None and rec["files_reason"].startswith("lan_host_files_unavailable")


def test_a_lan_peer_must_be_exactly_the_target_address() -> None:
    url = "http://192.168.1.20:1234/v1"
    with StubServer("lmstudio") as srv, pytest.raises(lm.LocalModelError) as exc:
        lm.list_server(url, expected_kind="lmstudio", client=_lan_client(srv, url, "192.168.1.99"))
    assert exc.value.code == "run.local.not_loopback"


# ---- D-699: the base URL from agentprov settings ------------------------------------------------------------------


def test_models_uses_the_settings_base_url_unless_given(cli: Callable[..., Any]) -> None:
    from agentprov import settings

    with StubServer("lmstudio") as srv, StubServer("lmstudio") as other:
        settings.set("endpoints.lmstudio.base_url", srv.base_url)
        listed = cli("models", "--endpoint", "lmstudio", "--format", "json")
        given = cli("models", "--endpoint", "lmstudio", "--base-url", other.base_url, "--format", "json")
    assert listed.code == 0 and listed.json()["endpoints"][0]["base_url"] == srv.base_url, listed.err
    assert given.code == 0 and given.json()["endpoints"][0]["base_url"] == other.base_url


def test_the_settings_refuse_a_host_name_and_a_public_address(tmp_path: Path) -> None:
    from agentprov import settings

    for bad in ("http://lan-box.local:1234/v1", "http://8.8.8.8:1234/v1", "http://u:p@127.0.0.1:1234/v1"):
        with pytest.raises(settings.SettingsError):
            settings.set("endpoints.lmstudio.base_url", bad, home=tmp_path)
    assert not (tmp_path / "settings.json").exists()


# ---- D-736: load and serving state never changes the identity -----------------------------------------------------


def _lmstudio_models(*, loaded: bool, quant: str = "4bit") -> list[dict[str, Any]]:
    instances = [{"id": "m", "config": {"context_length": 8192, "parallel": 4}}] if loaded else []
    return [{"type": "llm", "publisher": "p", "key": "m", "display_name": "M", "architecture": "a", "format": "mlx",
             "quantization": {"name": quant, "bits_per_weight": 4}, "size_bytes": 10, "params_string": "1B",
             "max_context_length": 32768, "loaded_instances": instances,
             "capabilities": {"trained_for_tool_use": True}}]


def test_lmstudio_identity_ignores_load_state_but_not_the_model() -> None:
    def record(**kw: Any) -> dict[str, Any]:
        with StubServer("lmstudio", models=_lmstudio_models(**kw)) as srv:
            return lm.model_identity(lm.list_server(srv.base_url, expected_kind="lmstudio"), "m", files=False)

    cold, warm, other = record(loaded=False), record(loaded=True), record(loaded=False, quant="8bit")
    assert cold["identity_sha256"] == warm["identity_sha256"] != other["identity_sha256"]
    assert lm.server_side_sha256(cold) == lm.server_side_sha256(warm)
    assert warm["observed_state"] == {"loaded_instances": 1, "parallel": 4, "context_length": 8192}
    assert cold["observed_state"] == {"loaded_instances": 0}
    assert not {"loaded_instances", "parallel", "context_length"} & set(warm["server_identity"])
    assert warm["server"]["version"] is None and warm["server"]["version_source"] == "not exposed by the server"
    assert warm["format"] == "agentprov-local-model/0.2"


def test_lmstudio_greeting_is_fingerprint_evidence() -> None:
    with StubServer("lmstudio") as srv:
        listing = lm.list_server(srv.base_url, expected_kind="lmstudio")
        assert "/lmstudio-greeting" in [r.path for r in listing.server.evidence]
        srv.drop("/lmstudio-greeting")  # an older LM Studio without the route is still recognised by its listing
        assert lm.list_server(srv.base_url, expected_kind="lmstudio").server.kind == "lmstudio"


def test_ollama_keeps_the_models_own_context_length_and_a_version_source() -> None:
    with StubServer("ollama") as srv:
        rec = lm.model_identity(lm.list_server(srv.base_url, expected_kind="ollama"), "tiny-llm:1b")
    assert rec["server_identity"]["context_length"] == 4096 and "show_sha256" not in rec["server_identity"]
    assert rec["server"]["version_source"] == "GET /api/version" and rec["observed_state"] == {}
    assert any(r["path"] == "/api/show" for r in rec["listing"]["responses"])  # the show response is still cited


def test_llamacpp_version_is_its_build_info() -> None:
    with StubServer("llamacpp", models=[{"id": "tiny"}]) as srv:
        rec = lm.model_identity(lm.list_server(srv.base_url, expected_kind="llamacpp"), "tiny", files=False)
    assert rec["server"]["version"] == "b0000-stub" and rec["server"]["version_source"] == "GET /props build_info"
    assert "build_info" not in rec["server_identity"]
