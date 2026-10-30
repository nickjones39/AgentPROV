"""Presets, model facts, model-aware concurrency and the local-server preflight (agentprov.presets; MN N.2.1a).

All inputs are synthetic: facts are built by hand, model directories are temporary directories with a synthetic
``config.json`` and placeholder ``*.safetensors`` files (sizes only, never weights; large sizes are declared, not
allocated), and the preflight talks to a throwaway ``http.server`` on 127.0.0.1. Nothing needs the target machine or the network.
"""

from __future__ import annotations

import dataclasses
import http.client
import http.server
import json
import os
import pathlib
import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from agentprov import presets as p
from agentprov.errors import AgentProvError, IngestError
from agentprov.host import Capabilities, Decided, HostProfile
from agentprov.ingest import IngestLimits
from agentprov.presets import GIB, Fact, ModelFacts, MoEInfo

# ---- synthetic hosts and facts ---------------------------------------------------------------------------------


def make_host(*, os_family: str = "darwin", arch: str = "arm64", memory: int | None = 256 * GIB) -> HostProfile:
    d = lambda v: Decided(v, "synthetic")  # noqa: E731
    caps = Capabilities(
        resource_module=d(True), rlimits=d(()), rlimit_as_enforced=d(False), rss_sampler=d("libproc"),
        tree_kill=d("killpg"), hard_memory_cap=d("none"), cpu_limit=d("rlimit_cpu"),
    )
    return HostProfile(
        os_family=os_family, os_release="0", arch=arch, machine=arch, python_implementation="CPython",
        python_version="3.14.8", cpu_count=32, memory_bytes=memory, memory_how="synthetic", page_size=16384,
        page_size_how="synthetic", caps=caps,
    )


M5 = make_host()
SHIPPED = p.load_preset("m5ultra")
# The concurrency tests use v1's distinct compute rows (8 / 6 / 4), so every class boundary and tie shows; the shipped
# values (v2: 4 in every row) are pinned in test_m5ultra_values_exactly_as_specified.
PRESET = dataclasses.replace(SHIPPED, compute_caps=(p.ComputeRow(15.0, 8), p.ComputeRow(40.0, 6), p.ComputeRow(None, 4)))


def facts(
    w_gib: float | None = 20, a: float | None = 3.0, layers: int | None = 48, kvh: int | None = 4, hd: int | None = 128
) -> ModelFacts:
    def f(v: Any, src: p.Source = "model_dir") -> Fact[Any]:
        return Fact(None, "unknown") if v is None else Fact(v, src)

    return ModelFacts(
        weights_bytes=f(None if w_gib is None else int(w_gib * GIB)),
        active_params_b=f(a), layers=f(layers), kv_heads=f(kvh), head_dim=f(hd),
    )


# ---- preset data -----------------------------------------------------------------------------------------------


def test_m5ultra_values_exactly_as_specified() -> None:
    q = p.load_preset("m5ultra")
    assert (q.name, q.version, q.endpoint, q.calibrated) == ("m5ultra", 2, "omlx", True)
    assert (q.expected_host.os_family, q.expected_host.arch, q.expected_host.min_memory_gib) == ("darwin", "arm64", 240)
    assert q.start_stagger_per_worker_s == 1 and q.request_timeout_s == 900
    assert q.gpu_budget_fraction == 0.75 and q.reserve_gib == 16 and q.per_worker_reserve_gib == 0.5
    assert [(r.max_active_params_b, r.jobs, r.basis) for r in q.compute_caps] == [
        (15.0, 4, "measured"), (40.0, 4, "provisional"), (None, 4, "provisional")]
    assert [(c.max_active_params_b, c.p50, c.p90, c.jobs) for c in q.cell_seconds] == [(15.0, 14.3, 27.4, 4)]
    assert (q.default_context_tokens, q.kv_bytes, q.kv_trace_fallback_gib) == (32768, 2, 4)
    assert q.server_max_concurrency_default == 8
    assert len(q.evidence) >= 7
    sources = " ".join(s for _, s in q.evidence)
    assert "oMLX" in sources and "2609.19169" in sources and "MacStories" in sources  # v1's prior rows stay
    assert sources.count("docs/reports/mac-studio-calibration/tune-jobs/") == 3 and sources.count("sha256:") == 3


def test_aliases_unknown_and_json() -> None:
    assert p.PRESET_ALIASES == {"m5ultra": "m5ultra"}
    assert p.load_preset("m5ultra") is p.load_preset("m5ultra")
    with pytest.raises(p.PresetUsageError) as exc:
        p.load_preset("nope")
    assert exc.value.exit_code == 2 and exc.value.code == "run.preset.unknown"
    blob = json.dumps(PRESET.to_json(), sort_keys=True)
    assert len(PRESET.data_sha256) == 64 and PRESET.data_sha256 in blob


def test_data_directory_has_no_init() -> None:
    root = pathlib.Path(p.__file__).parent / "presets"
    assert (root / "presets.toml").is_file() and not (root / "__init__.py").exists()


def test_omlx_registry_entry_agrees_with_preset() -> None:
    from agentprov_capture.endpoints import get_endpoint

    entry = get_endpoint(PRESET.endpoint)
    assert entry.local and entry.server_max_concurrency == PRESET.server_max_concurrency_default


# ---- the formula -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, expected",
    [(0.5, 8), (3.0, 8), (15.0, 8), (15.0001, 6), (22.0, 6), (40.0, 6), (40.0001, 4), (235.0, 4)],
)
def test_compute_table_boundaries(a: float, expected: int) -> None:
    plan = p.local_concurrency(PRESET, facts(a=a), host=M5, server_max_concurrency=64)
    assert plan.j_compute == expected


def test_unknown_active_params_takes_most_conservative_row() -> None:
    plan = p.local_concurrency(PRESET, facts(a=None), host=M5)
    assert plan.j_compute == 4 and any("conservative" in w for w in plan.warnings)
    a = next(i for i in plan.inputs if i.name == "active_params_b")
    assert a.value is None and a.source == "preset"


def test_memory_term_exact_numbers() -> None:
    # M_budget = 192 GiB; W = 20 GiB; KV = 2*48*4*128*32768*2 = 3 GiB; J_memory = floor((192-20-16-0.5J)/3) -> J <= 44.57
    plan = p.local_concurrency(PRESET, facts(), host=M5, server_max_concurrency=100)
    assert plan.m_budget_bytes == 192 * GIB and plan.kv_trace_bytes == 3 * GIB
    assert plan.j_memory == 44  # floor(156 / 3.5)
    # The reported R is for the workers actually run, and the spec formula holds at that J.
    assert plan.reserve_bytes == 16 * GIB + plan.jobs * GIB // 2
    assert (plan.m_budget_bytes - plan.weights_bytes - plan.reserve_bytes) // plan.kv_trace_bytes >= plan.jobs


@pytest.mark.parametrize(
    "kw, server, jobs, binding, tied",
    [
        # small model: compute (8) and the server default (8) tie; memory is far away
        (dict(w_gib=16, a=3.3, layers=48, kvh=4, hd=128), None, 8, "compute", ("compute", "server")),
        # compute binds alone: 70B dense, A=70 -> 4
        (dict(w_gib=37.3, a=70.6, layers=80, kvh=8, hd=128), None, 4, "compute", ("compute",)),
        # server binds alone
        (dict(w_gib=16, a=3.3), 2, 2, "server", ("server",)),
        # memory binds alone: a 160 GiB model leaves 16 GiB; KV 10 GiB/trace
        (dict(w_gib=160, a=10, layers=80, kvh=8, hd=128), None, 1, "memory", ("memory",)),
        # memory binds below compute (8) and server (8): floor(46 / (10 + 0.5)) = 4
        (dict(w_gib=130, a=10, layers=80, kvh=8, hd=128), None, 4, "memory", ("memory",)),
    ],
)
def test_binding_term(kw: dict[str, Any], server: int | None, jobs: int, binding: str, tied: tuple[str, ...]) -> None:
    plan = p.local_concurrency(PRESET, facts(**kw), host=M5, server_max_concurrency=server)
    assert (plan.jobs, plan.binding, plan.binding_all) == (jobs, binding, tied)
    assert plan.jobs == max(1, min(plan.j_compute, plan.j_memory, plan.j_server))


def test_server_default_and_flag_sources() -> None:
    d = p.local_concurrency(PRESET, facts(), host=M5)
    s = next(i for i in d.inputs if i.name == "server_max_concurrency")
    assert (d.j_server, s.source) == (8, "preset")
    f = p.local_concurrency(PRESET, facts(), host=M5, server_max_concurrency=3)
    s = next(i for i in f.inputs if i.name == "server_max_concurrency")
    assert (f.j_server, s.source, f.jobs) == (3, "flag", 3)


@pytest.mark.parametrize(
    "name, kw, jobs, binding",
    [
        # ~30B-A3B MoE, 4-bit (Qwen3-30B-A3B-like): W 17 GB
        ("moe30b", dict(w_gib=15.8, a=3.3, layers=48, kvh=4, hd=128), 8, "compute"),
        # 70B dense, 4-bit (Llama-3.3-70B-like): W 40 GB
        ("dense70b", dict(w_gib=37.3, a=70.6, layers=80, kvh=8, hd=128), 4, "compute"),
        # 235B-A22B, 4-bit (Qwen3-235B-A22B-like): W 132 GB
        ("moe235b", dict(w_gib=123, a=22, layers=94, kvh=4, hd=128), 6, "compute"),
    ],
)
def test_example_plans_on_the_m5ultra_host(name: str, kw: dict[str, Any], jobs: int, binding: str) -> None:
    plan = p.local_concurrency(PRESET, facts(**kw), host=M5)
    assert (plan.jobs, plan.binding) == (jobs, binding), name


def test_does_not_fit_is_a_usage_error() -> None:
    for w in (180, 175.6, 400):  # budget 192 GiB; R(1) = 16.5 GiB
        with pytest.raises(p.PresetUsageError) as exc:
            p.local_concurrency(PRESET, facts(w_gib=w), host=M5)
        assert exc.value.exit_code == 2 and exc.value.code == "run.model.does_not_fit"
    # just under the line fits: jobs floored to 1 with a warning when no KV slot remains
    plan = p.local_concurrency(PRESET, facts(w_gib=174.0, layers=80, kvh=8, hd=128), host=M5)
    assert plan.jobs == 1 and plan.j_memory == 0 and plan.binding == "memory" and plan.warnings


def test_missing_weights_and_memory_are_usage_errors() -> None:
    with pytest.raises(p.PresetUsageError) as exc:
        p.local_concurrency(PRESET, facts(w_gib=None), host=M5)
    assert exc.value.code == "run.model.facts_missing" and exc.value.exit_code == 2
    with pytest.raises(p.PresetUsageError) as exc:
        p.local_concurrency(PRESET, facts(), host=make_host(memory=None))
    assert exc.value.code == "run.host.memory_unknown"


def test_unknown_kv_uses_four_gib_fallback() -> None:
    for kw in (dict(layers=None), dict(kvh=None), dict(hd=None)):
        plan = p.local_concurrency(PRESET, facts(**kw), host=M5)
        kv = next(i for i in plan.inputs if i.name == "kv_trace_bytes")
        assert plan.kv_trace_bytes == 4 * GIB and kv.source == "preset" and plan.warnings
        assert plan.j_memory == int((192 * GIB - 20 * GIB - 16 * GIB) // (4 * GIB + GIB // 2))


def test_kv_flag_and_context_flag() -> None:
    f = facts().with_flags(kv_gb_per_trace=2.0)
    plan = p.local_concurrency(PRESET, f, host=M5)
    assert plan.kv_trace_bytes == 2_000_000_000
    assert next(i for i in plan.inputs if i.name == "kv_trace_bytes").source == "flag"
    # context flag scales the computed KV: 2*48*4*128*65536*2
    plan = p.local_concurrency(PRESET, facts().with_flags(context_tokens=65536), host=M5)
    assert plan.kv_trace_bytes == 2 * 48 * 4 * 128 * 65536 * 2
    assert next(i for i in plan.inputs if i.name == "context_tokens").source == "flag"
    # default context is the preset's, labelled as such
    plan = p.local_concurrency(PRESET, facts(), host=M5)
    assert next(i for i in plan.inputs if i.name == "context_tokens").source == "preset"
    assert next(i for i in plan.inputs if i.name == "context_tokens").value == 32768


def test_flags_replace_model_dir_facts() -> None:
    base = facts(w_gib=20, a=3.0)
    f = base.with_flags(model_size_gb=40, active_params_b=70)
    assert f.weights_bytes == Fact(40_000_000_000, "flag", "--model-size-gb")
    assert f.active_params_b.source == "flag" and f.active_params_b.value == 70.0
    assert base.weights_bytes.source == "model_dir"  # immutability
    for bad in (0, -1, float("nan"), True):
        with pytest.raises(p.PresetUsageError):
            base.with_flags(model_size_gb=bad)  # type: ignore[arg-type]


def test_jobs_override_keeps_terms_and_warns() -> None:
    plan = p.local_concurrency(PRESET, facts(), host=M5, jobs_override=16)
    assert (plan.jobs, plan.jobs_source, plan.j_server) == (16, "flag", 8) and plan.warnings
    ok = p.local_concurrency(PRESET, facts(), host=M5, jobs_override=2)
    assert ok.jobs == 2 and not any("exceeds" in w for w in ok.warnings)
    for bad in (0, -3):
        with pytest.raises(p.PresetUsageError) as exc:
            p.local_concurrency(PRESET, facts(), host=M5, jobs_override=bad)
        assert exc.value.exit_code == 2
    with pytest.raises(p.PresetUsageError):
        p.local_concurrency(PRESET, facts(), host=M5, server_max_concurrency=0)


def test_pure_and_deterministic() -> None:
    f = facts(w_gib=37.3, a=70.6, layers=80, kvh=8, hd=128)
    runs = [json.dumps(p.local_concurrency(PRESET, f, host=M5).to_json(), sort_keys=True) for _ in range(5)]
    assert len(set(runs)) == 1
    plan = json.loads(runs[0])
    assert plan["terms"]["j_compute"] == 4 and plan["binding"] == "compute"
    assert {i["source"] for i in plan["inputs"]} <= {"model_dir", "flag", "preset", "default"}


def test_preset_record_shape() -> None:
    plan = p.local_concurrency(PRESET, facts(), host=M5)
    mism = p.check_host(PRESET, make_host(arch="x86_64"))
    rec = p.preset_record(PRESET, plan, host_mismatches=mism)
    assert rec["name"] == "m5ultra" and rec["version"] == PRESET.version
    r = rec["resolved"]
    assert r["start_stagger_s"] == {"value": float(plan.jobs), "source": "preset"}
    assert r["request_timeout_s"] == {"value": 900, "source": "preset"}
    assert r["concurrency"]["jobs"] == plan.jobs and r["host_mismatches"][0]["field"] == "arch"
    over = p.preset_record(PRESET, plan, start_stagger_s=0.0, request_timeout_s=30.0)["resolved"]
    assert over["start_stagger_s"]["source"] == "flag" and over["request_timeout_s"] == {"value": 30.0, "source": "flag"}
    json.dumps(rec)


# ---- host check ------------------------------------------------------------------------------------------------


def test_check_host_matches_and_mismatches() -> None:
    assert p.check_host(PRESET, M5) == []
    assert p.check_host(PRESET, make_host(memory=240 * GIB)) == []
    assert [m.field for m in p.check_host(PRESET, make_host(memory=240 * GIB - 1))] == ["memory_bytes"]
    bad = p.check_host(PRESET, make_host(os_family="linux", arch="x86_64", memory=32 * GIB))
    assert [(m.field, m.actual) for m in bad] == [("os_family", "linux"), ("arch", "x86_64"), ("memory_bytes", "32.0 GiB")]
    assert "preset expects darwin" in bad[0].message()
    unknown = p.check_host(PRESET, make_host(memory=None))
    assert unknown[0].actual == "unknown"


# ---- model directory -------------------------------------------------------------------------------------------

QWEN3_30B_A3B = {
    "model_type": "qwen3_moe", "hidden_size": 2048, "num_hidden_layers": 48, "num_attention_heads": 32,
    "num_key_value_heads": 4, "head_dim": 128, "num_experts": 128, "num_experts_per_tok": 8,
    "moe_intermediate_size": 768, "intermediate_size": 6144, "vocab_size": 151936, "tie_word_embeddings": False,
}
LLAMA_70B = {
    "model_type": "llama", "hidden_size": 8192, "num_hidden_layers": 80, "num_attention_heads": 64,
    "num_key_value_heads": 8, "intermediate_size": 28672, "vocab_size": 128256, "tie_word_embeddings": False,
}


REAL_SIZE_LIMIT = 1 << 20  # larger declared sizes are never allocated: tests declare them, whatever the filesystem does
DECLARED: dict[str, int] = {}  # realpath of a placeholder -> the size the test declares for it


class _Declared:
    """A stat result whose ``st_size`` is the declared one (everything else is the real stat)."""

    def __init__(self, st: os.stat_result, size: int) -> None:
        self._st, self.st_size = st, size

    def __getattr__(self, name: str) -> Any:
        return getattr(self._st, name)


@pytest.fixture(autouse=True)
def declared_sizes(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Weights are sized by ``stat`` only. Placeholders above 1 MiB stay tiny on disk (NTFS does not make truncated files
    sparse, so a real 40 GB placeholder filled the CI disk) and the size is injected through the ``stat`` seam."""
    DECLARED.clear()
    real = p._stat_weight

    def stat_weight(entry: os.DirEntry[str]) -> Any:
        st = real(entry)
        size = DECLARED.get(os.path.realpath(entry.path))
        return st if size is None else _Declared(st, size)

    monkeypatch.setattr(p, "_stat_weight", stat_weight)
    yield
    DECLARED.clear()


def make_placeholder(path: pathlib.Path, size: int) -> None:
    """A weight placeholder of ``size`` bytes: real (and tiny) below 1 MiB, otherwise declared through :data:`DECLARED`."""
    with open(path, "wb") as fh:
        if size <= REAL_SIZE_LIMIT:
            fh.truncate(size)
        else:
            fh.write(b"\0")
            DECLARED[os.path.realpath(path)] = size


def make_model_dir(root: pathlib.Path, config: Any, shards: tuple[int, ...] = (3_000_000, 2_000_000)) -> pathlib.Path:
    d = root / "model"
    d.mkdir()
    if config is not None:
        (d / "config.json").write_bytes(config if isinstance(config, bytes) else json.dumps(config).encode())
    for i, size in enumerate(shards):
        make_placeholder(d / f"model-{i:05d}-of-{len(shards):05d}.safetensors", size)  # a size, never weights
    return d


def test_model_dir_moe(tmp_path: pathlib.Path) -> None:
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, QWEN3_30B_A3B)))
    assert mf.weights_bytes.value == 5_000_000 and mf.weights_bytes.source == "model_dir"
    assert (mf.layers.value, mf.kv_heads.value, mf.head_dim.value) == (48, 4, 128)
    assert mf.moe.value == MoEInfo(128, 8)
    assert mf.active_params_b.value is not None and 3.2 < mf.active_params_b.value < 3.5  # Qwen3-30B-A3B: 3.3 B
    assert mf.total_params_b.value is not None and 30.0 < mf.total_params_b.value < 31.0
    assert mf.active_params_b.source == "model_dir"
    json.dumps(mf.to_json())


def test_model_dir_dense(tmp_path: pathlib.Path) -> None:
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, LLAMA_70B)))
    assert mf.head_dim.value == 128 and mf.head_dim.note == "hidden_size / num_attention_heads"
    assert mf.active_params_b.value is not None and 70.0 < mf.active_params_b.value < 71.0  # Llama-3.3-70B: 70.6 B
    assert mf.active_params_b.value == mf.total_params_b.value and mf.moe.value is None


def test_model_dir_composes_with_concurrency(tmp_path: pathlib.Path) -> None:
    d = make_model_dir(tmp_path, LLAMA_70B, shards=(40 * 10**9 // 4,) * 4)
    mf = p.model_facts_from_dir(str(d)).with_flags(context_tokens=32768)
    plan = p.local_concurrency(PRESET, mf, host=M5)
    assert plan.jobs == 4 and plan.binding == "compute" and plan.kv_trace_bytes == 2 * 80 * 8 * 128 * 32768 * 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(model_type="mamba"),  # not a modelled gated-MLP decoder
        lambda c: c.update(kv_lora_rank=512),  # latent attention
        lambda c: c.pop("tie_word_embeddings"),  # absent flag: do not guess
        lambda c: c.pop("vocab_size"),
        lambda c: c.update(mlp_only_layers=[0, 1]),
        lambda c: c.update(decoder_sparse_step=2),
        lambda c: c.pop("moe_intermediate_size"),
        lambda c: c.pop("num_experts_per_tok"),
    ],
)
def test_active_params_left_unknown_not_guessed(tmp_path: pathlib.Path, mutate: Any) -> None:
    cfg = dict(QWEN3_30B_A3B)
    mutate(cfg)
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, cfg)))
    assert mf.active_params_b.value is None and mf.active_params_b.source == "unknown"
    assert mf.layers.value == 48  # the other facts survive
    assert any("active parameters" in n for n in mf.notes)


def test_model_dir_text_config_and_mha_default(tmp_path: pathlib.Path) -> None:
    (tmp_path / "x").mkdir()
    inner = {k: v for k, v in LLAMA_70B.items() if k != "num_key_value_heads"}
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, {"model_type": "vlm", "text_config": inner})))
    assert mf.layers.value == 80 and mf.kv_heads.value == 64 and "multi-head" in mf.kv_heads.note
    assert any("text_config" in n for n in mf.notes)
    assert mf.active_params_b.value is not None and 79.9 < mf.active_params_b.value < 80.0  # inner llama, 64 KV heads
    no_type = {k: v for k, v in inner.items() if k != "model_type"}
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path / "x", {"model_type": "vlm", "text_config": no_type})))
    assert mf.active_params_b.value is None  # the outer model_type is not a modelled decoder


def test_model_dir_missing_pieces(tmp_path: pathlib.Path) -> None:
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, None, shards=())))
    assert mf.weights_bytes.value is None and mf.layers.value is None and len(mf.notes) == 2
    with pytest.raises(p.PresetUsageError) as exc:
        p.local_concurrency(PRESET, mf, host=M5)
    assert exc.value.code == "run.model.facts_missing"


def test_model_dir_weights_never_read_and_only_top_level(tmp_path: pathlib.Path) -> None:
    d = make_model_dir(tmp_path, LLAMA_70B, shards=(7,))
    shard = d / "model-00000-of-00001.safetensors"
    shard.chmod(0)  # stat works, open would fail: the sum must come from stat alone
    (d / "sub").mkdir()
    (d / "sub" / "extra.safetensors").write_bytes(b"x" * 100)
    (d / "model.safetensors.index.json").write_bytes(b"{}")
    try:
        mf = p.model_facts_from_dir(str(d))
    finally:
        shard.chmod(0o600)
    assert mf.weights_bytes.value == 7


def make_hf_cache(root: pathlib.Path, config: Any, shard_sizes: tuple[int, ...]) -> pathlib.Path:
    """A synthetic Hugging Face cache layout: snapshots/<rev>/<file> -> ../../blobs/<hash> (symlinks)."""
    repo = root / "models--org--name"
    blobs, snap = repo / "blobs", repo / "snapshots" / "rev0123"
    blobs.mkdir(parents=True)
    snap.mkdir(parents=True)
    blob = blobs / ("c" * 40)
    blob.write_bytes(json.dumps(config).encode())
    os.symlink(os.path.join("..", "..", "blobs", blob.name), snap / "config.json")  # native separators (Windows)
    for i, size in enumerate(shard_sizes):
        target = blobs / f"{i:040d}"
        make_placeholder(target, size)
        os.symlink(os.path.join("..", "..", "blobs", target.name), snap / f"model-{i:05d}-of-{len(shard_sizes):05d}.safetensors")
    return snap


def test_model_dir_hugging_face_cache_layout_follows_symlinks(tmp_path: pathlib.Path) -> None:
    snap = make_hf_cache(tmp_path, QWEN3_30B_A3B, (4_000_000, 1_000_000))
    assert (snap / "config.json").is_symlink()
    mf = p.model_facts_from_dir(str(snap))
    assert mf.weights_bytes.value == 5_000_000 and "followed_symlinks: true" in mf.weights_bytes.note
    assert mf.followed_symlinks is True and any("followed_symlinks: true" in n for n in mf.notes)
    assert mf.layers.value == 48 and mf.moe.value == MoEInfo(128, 8) and mf.active_params_b.value is not None
    assert mf.to_json()["followed_symlinks"] is True
    # a plain directory records no followed symlink
    assert p.model_facts_from_dir(str(make_model_dir(tmp_path, QWEN3_30B_A3B))).followed_symlinks is False


def test_model_dir_symlink_to_a_directory_or_dangling_is_not_weights(tmp_path: pathlib.Path) -> None:
    d = make_model_dir(tmp_path, LLAMA_70B, shards=(10,))
    os.symlink(tmp_path, d / "dirlink.safetensors")  # resolves to a directory
    mf = p.model_facts_from_dir(str(d))
    assert mf.weights_bytes.value is None and any("not resolvable" in n for n in mf.notes)
    (tmp_path / "b").mkdir()
    d2 = make_model_dir(tmp_path / "b", LLAMA_70B, shards=(10,))
    os.symlink(tmp_path / "gone", d2 / "dangling.safetensors")
    assert p.model_facts_from_dir(str(d2)).weights_bytes.value is None


def test_model_dir_weights_are_not_opened(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = make_hf_cache(tmp_path, LLAMA_70B, (123,))
    opened: list[str] = []
    real_open = os.open

    def spy(path: Any, *a: Any, **k: Any) -> int:
        opened.append(str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr(os, "open", spy)
    p.model_facts_from_dir(str(snap))
    assert opened and all("safetensors" not in o and not o.endswith("0" * 40) for o in opened)


@pytest.mark.parametrize(
    "config, exc_type",
    [
        (b'{"a": 1, "a": 2}', IngestError),  # duplicate keys
        (b"{bad", IngestError),
        (b"\xef\xbb\xbf{}", IngestError),  # BOM refused by the strict profile
        (b'{"a":' * 300 + b"1" + b"}" * 300, IngestError),  # depth
        (b"[1, 2]", p.PresetUsageError),
    ],
)
def test_model_dir_hostile_config(tmp_path: pathlib.Path, config: bytes, exc_type: type[Exception]) -> None:
    with pytest.raises(exc_type):
        p.model_facts_from_dir(str(make_model_dir(tmp_path, config)))


def test_model_dir_config_that_is_not_a_regular_file_and_oversize(tmp_path: pathlib.Path) -> None:
    d = make_model_dir(tmp_path, None, shards=())
    os.symlink(tmp_path, d / "config.json")  # resolves to a directory
    mf = p.model_facts_from_dir(str(d))
    assert mf.layers.value is None and any("regular file" in n for n in mf.notes)
    d2 = tmp_path / "m2"
    d2.mkdir()
    (d2 / "config.json").write_bytes(b"{" + b" " * 2000 + b"}")
    with pytest.raises(IngestError) as exc:
        p.model_facts_from_dir(str(d2), limits=IngestLimits(max_json_bytes=1000))
    assert exc.value.code == "ingest.size.file"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root reads a mode-000 file")
def test_model_dir_unreadable_config_is_a_usage_error(tmp_path: pathlib.Path) -> None:
    """CC-13: an unreadable config.json is a typed refusal (exit 2), not an internal error (exit 70)."""
    d = make_model_dir(tmp_path, {"model_type": "llama"})
    (d / "config.json").chmod(0)
    try:
        with pytest.raises(p.PresetUsageError) as exc:
            p.model_facts_from_dir(str(d))
    finally:
        (d / "config.json").chmod(0o644)
    assert exc.value.code == "run.model.config" and exc.value.exit_code == 2


def test_model_dir_oversized_architecture_integers_are_left_unknown(tmp_path: pathlib.Path) -> None:
    """CC-14: a 161-digit ``hidden_size`` in the untrusted config.json is not a fact: it is left unknown instead of
    overflowing the float parameter count (exit 70)."""
    huge = 10**160
    cfg = {"model_type": "llama", "hidden_size": huge, "num_hidden_layers": 2, "num_attention_heads": 1, "head_dim": 1,
           "vocab_size": 10, "tie_word_embeddings": True, "intermediate_size": huge, "num_key_value_heads": huge}
    mf = p.model_facts_from_dir(str(make_model_dir(tmp_path, cfg)))
    assert mf.active_params_b.value is None and mf.total_params_b.value is None
    assert mf.kv_heads.value is None and mf.layers.value == 2
    at_bound = dict(cfg, hidden_size=p.MAX_ARCHITECTURE_INT, intermediate_size=p.MAX_ARCHITECTURE_INT,
                    num_key_value_heads=1)
    (tmp_path / "b").mkdir()
    bounded = p.model_facts_from_dir(str(make_model_dir(tmp_path / "b", at_bound)))
    assert bounded.active_params_b.value is not None and bounded.kv_heads.value == 1


def test_model_dir_not_a_directory(tmp_path: pathlib.Path) -> None:
    for target in (tmp_path / "missing", make_model_dir(tmp_path, {}) / "config.json"):
        with pytest.raises(p.PresetUsageError) as exc:
            p.model_facts_from_dir(str(target))
        assert exc.value.exit_code == 2


# ---- server preflight (loopback only) --------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200
    body: bytes = b""
    location: str | None = None
    seen: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
        self.send_response(type(self).status)
        if type(self).location:
            self.send_header("Location", type(self).location)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[tuple[str, type[_Handler]]]:
    handler = type("H", (_Handler,), {"seen": [], "status": 200, "body": b"", "location": None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/v1", handler
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def listing(*ids: str) -> bytes:
    return json.dumps({"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}).encode()


def test_preflight_ok_records_listing_digest(server: tuple[str, type[_Handler]]) -> None:
    import hashlib

    base, h = server
    h.body = listing("qwen3-30b-a3b-4bit", "other")
    res = p.preflight_local_server(base, "qwen3-30b-a3b-4bit")
    assert res.listing_sha256 == hashlib.sha256(h.body).hexdigest()
    assert (res.status, res.listed_models, res.model_listed) == (200, 2, True)
    assert h.seen[0]["path"] == "/v1/models"
    assert "authorization" not in h.seen[0]["headers"]  # no credential is ever sent


def test_preflight_accepts_a_registry_endpoint_object(server: tuple[str, type[_Handler]]) -> None:
    from agentprov_capture.endpoints import Endpoint

    base, h = server
    h.body = listing("m")
    ep = Endpoint("omlx", base, "127.0.0.1", None, None, None, True, 8)
    assert p.preflight_local_server(ep, "m").listed_models == 1


def test_preflight_localhost_name(server: tuple[str, type[_Handler]]) -> None:
    base, h = server
    h.body = listing("m")
    assert p.preflight_local_server(base.replace("127.0.0.1", "localhost"), "m").model_listed


@pytest.mark.parametrize(
    "status, body, code",
    [
        (200, listing("a"), "model_not_listed"),
        (200, b"not json", "bad_listing"),
        (200, b'{"data": [{"id": 3}]}', "bad_listing"),
        (200, b'{"data": 1}', "bad_listing"),
        (200, b'{"data": [], "data": []}', "bad_listing"),
        (200, b"[]", "bad_listing"),
        (500, b"boom", "http_status"),
        (404, b"", "http_status"),
        (302, b"", "http_status"),
    ],
)
def test_preflight_failures_exit_3(server: tuple[str, type[_Handler]], status: int, body: bytes, code: str) -> None:
    base, h = server
    h.status, h.body = status, body
    h.location = "http://203.0.113.9/elsewhere" if status == 302 else None
    with pytest.raises(p.ServerPreflightError) as exc:
        p.preflight_local_server(base, "wanted")
    assert exc.value.exit_code == 3 and exc.value.code == f"run.endpoint.preflight.{code}"
    assert "boom" not in str(exc.value)  # server text never enters the message
    assert len(h.seen) == 1  # the redirect was not followed


def test_preflight_oversize_listing(server: tuple[str, type[_Handler]], monkeypatch: pytest.MonkeyPatch) -> None:
    base, h = server
    monkeypatch.setattr(p, "MAX_LISTING_BYTES", 64)
    h.body = listing(*[f"model-{i}" for i in range(20)])
    with pytest.raises(p.ServerPreflightError) as exc:
        p.preflight_local_server(base, "model-1")
    assert exc.value.code.endswith("bad_listing")


def test_preflight_unreachable_server() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(p.ServerPreflightError) as exc:
        p.preflight_local_server(f"http://127.0.0.1:{port}/v1", "m", timeout=1.0)
    assert exc.value.exit_code == 3 and exc.value.code.endswith("unreachable")


def test_preflight_timeout() -> None:
    with socket.socket() as s:  # accepts connections (kernel backlog) but never answers
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        with pytest.raises(p.ServerPreflightError) as exc:
            p.preflight_local_server(f"http://127.0.0.1:{s.getsockname()[1]}/v1", "m", timeout=0.3)
    assert exc.value.code.endswith("unreachable")


@pytest.mark.parametrize(
    "url, code",
    [
        ("https://example.com/v1", "not_loopback"),
        ("https://203.0.113.5:8000/v1", "not_loopback"),
        ("https://127.0.0.2.example.com/v1", "not_loopback"),
        ("http://203.0.113.5:8000/v1", "url"),  # http off loopback
        ("http://127.0.0.1:8000/v1?key=1", "url"),
        ("http://user:pw@127.0.0.1:8000/v1", "url"),
        ("http://127.0.0.1:8000/v1#f", "url"),
        ("ftp://127.0.0.1/v1", "url"),
    ],
)
def test_preflight_refuses_non_loopback_without_connecting(
    monkeypatch: pytest.MonkeyPatch, url: str, code: str
) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", boom)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    with pytest.raises(p.ServerPreflightError) as exc:
        p.preflight_local_server(url, "m")
    assert exc.value.exit_code == 4 and exc.value.code == f"run.endpoint.preflight.{code}"  # refused (N.1.3)


def test_error_types_are_agentprov_errors() -> None:
    assert issubclass(p.PresetUsageError, AgentProvError) and issubclass(p.ServerPreflightError, AgentProvError)
