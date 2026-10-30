"""Unit tests of the T1 worker protocol and pool configuration (G.4.2, G.4.3, G.4.6, G.4.9); no subprocess here."""

from __future__ import annotations

import hashlib
import io
import os
import struct

import pytest

from agentprov.errors import AgentProvError
from agentprov.io import workers as w
from agentprov.io.workers import (
    ENV_ALLOWLIST,
    ENV_ALLOWLIST_LOADER,
    JOB_KINDS,
    MIB,
    PROTOCOL,
    TAG_DATA,
    TAG_DONE,
    TAG_FAIL,
    TAG_JSON,
    FrameWriter,
    InProcessRefusedError,
    Job,
    JobResult,
    MemberOutput,
    WorkerLimitError,
    WorkerLimits,
    WorkerPool,
    WorkerProtocolError,
    build_worker_env,
    jcs,
    resolve_worker_count,
    result_fingerprint,
    strict_loads,
    validate_request,
)

SMALL = WorkerLimits(max_frame_bytes=1024, max_json_job_bytes=4096, max_member_bytes=64, max_total_bytes=100)


def frame(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">4sQ", tag, len(payload)) + payload


def jframe(obj: object) -> bytes:
    return frame(TAG_JSON, jcs(obj))


def done(job: int = 0, **counters: int) -> bytes:
    return frame(TAG_DONE, jcs({"job": job, "counters": counters}))


def collect(data: bytes, limits: WorkerLimits = SMALL, job: int = 0):
    return w._collect(io.BytesIO(data), job, limits)


# ---- framing ----------------------------------------------------------------------------------------------


def test_frame_layout_is_tag_then_big_endian_length():
    buffer = io.BytesIO()
    FrameWriter(buffer).write(TAG_JSON, b'{"a":1}')
    assert buffer.getvalue() == b"JSON" + (7).to_bytes(8, "big") + b'{"a":1}'


def test_protocol_constants():
    assert PROTOCOL == "agentprov-job/0.1"
    assert {TAG_JSON, TAG_DATA, TAG_DONE, TAG_FAIL} == {b"JSON", b"DATA", b"DONE", b"FAIL"}


def test_round_trip_json_member_data_done():
    stream = jframe({"k": 1}) + jframe({"$member": {"label": "a", "size": 6}})
    stream += frame(TAG_DATA, b"abc") + frame(TAG_DATA, b"def") + jframe({"k": 2}) + done(0, n=2)
    out = collect(stream)
    assert out.counters == {"n": 2}
    first, member, last = out.outputs
    assert first == {"k": 1} and last == {"k": 2}
    assert isinstance(member, MemberOutput)
    assert member.header == {"label": "a", "size": 6}
    assert member.read_bytes() == b"abcdef" and member.size == 6
    assert b"".join(member.iter_chunks(2)) == b"abcdef"
    member.close()


def test_member_closes_on_next_json_frame():
    stream = (
        jframe({"$member": {"size": 3}}) + frame(TAG_DATA, b"abc") + jframe({"x": 1}) + frame(TAG_DATA, b"d")
    )
    with pytest.raises(WorkerProtocolError, match="without an open member"):
        collect(stream + done())


def test_fewer_data_bytes_than_declared_is_allowed():
    """A ``not_selected`` member declares its size and sends nothing (G.3.5)."""
    out = collect(jframe({"$member": {"label": "x", "size": 10}}) + done())
    assert out.outputs[0].size == 0  # type: ignore[union-attr]


def test_writer_enforces_its_own_frame_cap():
    with pytest.raises(WorkerLimitError) as info:
        FrameWriter(io.BytesIO(), max_frame_bytes=8).write(TAG_JSON, b"x" * 9)
    assert info.value.code == "worker.limit.output"


# ---- the parent's rejections (G.4.6) -----------------------------------------------------------------------


def test_unknown_tag_rejected():
    with pytest.raises(WorkerProtocolError, match="unknown frame tag"):
        collect(frame(b"WHAT", b"{}"))


def test_data_without_member_rejected():
    with pytest.raises(WorkerProtocolError, match="without an open member"):
        collect(frame(TAG_DATA, b"abc"))


def test_frame_over_cap_is_a_limit_and_is_not_read():
    # only the header is present: the parent must reject on the declared length, before reading the payload
    with pytest.raises(WorkerLimitError) as info:
        collect(struct.pack(">4sQ", TAG_JSON, 1 << 40))
    assert info.value.code == "worker.limit.output"


def test_json_total_over_job_cap():
    one = jframe({"p": "x" * 500})  # < frame cap 1024, 5 frames > 4096 job cap
    with pytest.raises(WorkerLimitError, match="JSON output"):
        collect(one * 9)


def test_data_beyond_declared_member_size():
    with pytest.raises(WorkerProtocolError, match="declared member size"):
        collect(jframe({"$member": {"size": 2}}) + frame(TAG_DATA, b"abc"))


def test_member_declaring_more_than_max_member_bytes():
    with pytest.raises(WorkerLimitError):
        collect(jframe({"$member": {"size": 65}}))


def test_data_total_over_job_cap():
    members = b"".join(jframe({"$member": {"size": 40}}) + frame(TAG_DATA, b"x" * 40) for _ in range(3))
    with pytest.raises(WorkerLimitError, match="per job"):
        collect(members)  # 120 > max_total_bytes 100


@pytest.mark.parametrize(
    "header",
    [{"$member": "nope"}, {"$member": {"label": "a"}}, {"$member": {"size": -1}}, {"$member": {"size": True}},
     {"$member": {"size": 1}, "extra": 1}],
)  # fmt: skip
def test_malformed_member_header(header):
    with pytest.raises(WorkerProtocolError, match="member header"):
        collect(jframe(header))


@pytest.mark.parametrize(
    "payload",
    [b"{oops", b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b"\xff\xfe", b"[1]", b"7"],
)
def test_bad_json_frames_rejected(payload):
    with pytest.raises(WorkerProtocolError):
        collect(frame(TAG_JSON, payload))


def test_done_for_another_job_rejected():
    with pytest.raises(WorkerProtocolError, match="does not match"):
        collect(done(job=5), job=0)


def test_fail_frame_becomes_failed():
    payload = jcs({"job": 0, "code": "worker.job.error", "message": "bad\x1b[31m", "type": "ValueError"})
    with pytest.raises(w._Failed) as info:
        collect(frame(TAG_FAIL, payload))
    assert info.value.code == "worker.job.error"
    assert "\x1b" not in info.value.message  # escaped: derived from untrusted input


def test_truncated_stream():
    with pytest.raises(w._StreamEnded):
        collect(jframe({"a": 1}))
    with pytest.raises(w._StreamEnded):
        collect(struct.pack(">4sQ", TAG_JSON, 10) + b"{")


def test_spools_are_closed_when_collection_fails():
    seen: list[MemberOutput] = []
    real = MemberOutput

    class Spy(real):  # type: ignore[valid-type,misc]
        def __init__(self, header, spool_max=8 * MIB, spool_dir=None):
            super().__init__(header, spool_max, spool_dir)
            seen.append(self)

    original = w.MemberOutput
    w.MemberOutput = Spy  # type: ignore[misc]
    try:
        with pytest.raises(w._StreamEnded):
            collect(jframe({"$member": {"size": 3}}) + frame(TAG_DATA, b"abc"))
    finally:
        w.MemberOutput = original  # type: ignore[misc]
    assert seen and seen[0]._spool.closed


# ---- strict JSON ----------------------------------------------------------------------------------------------


def test_strict_loads_accepts_plain_documents():
    assert strict_loads(b'{"a":[1,2.5,"x",null,true]}') == {"a": [1, 2.5, "x", None, True]}


def test_strict_loads_rejects_long_integers_and_deep_nesting():
    with pytest.raises(WorkerProtocolError):
        strict_loads(b'{"a":' + b"9" * 1001 + b"}")
    with pytest.raises(WorkerProtocolError):
        strict_loads(b"[" * 100000 + b"]" * 100000)


# ---- environment, limits, sizing ---------------------------------------------------------------------------


def test_worker_env_is_exactly_the_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret")
    monkeypatch.setenv("UV_CACHE_DIR", "/x")
    env = build_worker_env(tmp_path)
    assert ENV_ALLOWLIST == {"PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR"}
    expected = ENV_ALLOWLIST | (ENV_ALLOWLIST_LOADER if "SYSTEMROOT" in os.environ else set())
    assert set(env) == expected
    assert env["HOME"] == env["TMPDIR"] == str(tmp_path)
    assert env["TZ"] == "UTC" and env["LC_ALL"] == "C.UTF-8"
    if "SYSTEMROOT" not in os.environ:
        assert env["PATH"] == "/usr/bin:/bin"
    assert "sentinel-secret" not in env.values()


def test_default_limits_are_the_g43_values():
    lim = WorkerLimits()
    assert (lim.cpu_s, lim.cpu_s_max, lim.wall_s) == (300, 540, 600)
    assert (lim.rss_bytes, lim.as_bytes, lim.nofile) == (2 << 30, None, 64)
    assert dict(lim.kind_rss_bytes) == {"prov": 4 << 30} and lim.max_rss_bytes == 4 << 30
    assert lim.effective_as_bytes == 5 << 30  # largest RSS cap + 1 GiB (D-55); 4 GiB before
    assert (lim.max_frame_bytes, lim.max_json_job_bytes) == (16 << 20, 256 << 20)
    assert (lim.max_member_bytes, lim.max_total_bytes, lim.stderr_tail_bytes) == (
        256 << 20,
        4 << 30,
        64 << 10,
    )


def test_expand_scaling_is_capped_by_max_total_bytes():
    base = WorkerLimits()
    one = base.with_expand_scaling(1 << 30)
    assert (one.cpu_s, one.wall_s) == (base.cpu_s + 60, base.wall_s + 120)
    top = base.with_expand_scaling(100 << 30)  # capped at 4 GiB: +240 s CPU, +480 s wall
    assert (top.cpu_s, top.wall_s) == (base.cpu_s + 240, base.wall_s + 480)
    assert top.cpu_s <= base.cpu_s_max
    with pytest.raises(ValueError):
        base.with_expand_scaling(-1)


def test_resolve_worker_count_uses_the_host_constants():
    from agentprov.host import constants_for, detect_host

    assert resolve_worker_count(3) == 3
    host = detect_host(probe=False)
    # the default counts the largest cap any job kind can get (D-55, user choice (a)): prov's 4 GiB
    assert resolve_worker_count(0) == constants_for(host, rss_cap_bytes=4 << 30).default_workers >= 1
    with pytest.raises(ValueError):
        resolve_worker_count(-1)


def test_the_prov_kind_gets_its_declared_cap_and_every_other_kind_the_default():
    lim = WorkerLimits()
    assert lim.for_kind("prov").rss_bytes == 4 << 30
    assert lim.for_kind("map").rss_bytes == lim.for_kind("expand").rss_bytes == 2 << 30
    assert lim.for_kind("map") is lim
    raised = WorkerLimits(kind_rss_bytes={"prov": 16 << 30})
    assert raised.for_kind("prov").rss_bytes == 16 << 30 and raised.effective_as_bytes == 17 << 30
    assert WorkerLimits(kind_rss_bytes={}).max_rss_bytes == 2 << 30
    assert WorkerLimits(as_bytes=0).effective_as_bytes == 0 and WorkerLimits(as_bytes=1 << 30).effective_as_bytes == 1 << 30


@pytest.mark.parametrize(
    "kwargs",
    [{"rss_bytes": (16 << 30) + 1}, {"kind_rss_bytes": {"prov": (16 << 30) + 1}}, {"kind_rss_bytes": {"prov": 1 << 20}},
     {"rss_bytes": 0}, {"kind_rss_bytes": {"prov": True}}, {"kind_rss_bytes": {"prov": 4.0 * (1 << 30)}},
     {"kind_rss_bytes": {"Prov!": 4 << 30}}, {"as_bytes": -1}],
)  # fmt: skip
def test_memory_caps_are_bounded_and_never_unlimited(kwargs):
    with pytest.raises(ValueError):
        WorkerLimits(**kwargs)


def test_the_kind_caps_cannot_be_changed_after_construction():
    lim = WorkerLimits()
    with pytest.raises(TypeError):
        lim.kind_rss_bytes["prov"] = 1 << 40  # type: ignore[index]
    assert lim.caps_record() == {"rss_bytes": 2 << 30, "kind_rss_bytes": {"prov": 4 << 30}, "rss_cap_ceiling": 16 << 30,
                                 "as_bytes": 5 << 30}  # fmt: skip


def test_a_job_runs_under_the_cap_of_its_kind(monkeypatch):
    seen: list[int] = []
    pool = WorkerPool(workers=1, in_process=True, test_kinds=True)
    original = pool._request

    def spy(number, job, limits):
        seen.append(limits.rss_bytes)
        return original(number, job, limits)

    monkeypatch.setattr(pool, "_request", spy)
    pool.run([Job("a", "echo")])
    assert seen == [2 << 30]


# ---- job table and requests --------------------------------------------------------------------------------


def test_job_table_is_closed_and_namespaced():
    assert {"echo", "sha256"} <= set(JOB_KINDS)
    for kind, target in JOB_KINDS.items():
        module, _, attr = target.partition(":")
        assert module.startswith("agentprov.") and attr, kind
    assert not any(k.startswith("test.") for k in w.kind_table(test_kinds=False))
    assert any(k.startswith("test.") for k in w.kind_table(test_kinds=True))
    with pytest.raises(TypeError):
        JOB_KINDS["x"] = "agentprov.y:z"  # type: ignore[index]


def test_preload_refuses_targets_outside_the_namespace():
    with pytest.raises(WorkerProtocolError):
        w.preload_job_kinds({"evil": "os:system"})
    with pytest.raises(WorkerProtocolError):
        w.preload_job_kinds({"evil": "agentprov.io.workers"})


def test_job_validation():
    with pytest.raises(ValueError):
        Job("", "echo")
    with pytest.raises(ValueError):
        Job("k", "Bad Kind")
    with pytest.raises(ValueError):
        Job("k", "echo", inputs=({"sha256": "XYZ", "role": "primary"},))
    assert Job("k", "echo", inputs=({"sha256": "0" * 64, "role": "primary"},)).inputs[0]["role"] == "primary"


def test_unknown_kind_is_refused_before_anything_starts():
    pool = WorkerPool(workers=1)
    with pytest.raises(WorkerProtocolError) as info:
        pool.run([Job("a", "not-registered".replace("-", "_"))])
    assert info.value.code == "worker.protocol.unknown_kind"
    with pytest.raises(WorkerProtocolError):
        pool.run([Job("a", "test.spin")])  # test kinds are not in the production table


def test_duplicate_keys_refused():
    with pytest.raises(ValueError, match="unique"):
        WorkerPool(in_process=True).run([Job("a", "echo"), Job("a", "echo")])


@pytest.mark.parametrize(
    "request_obj",
    [
        [],
        {"v": "agentprov-job/9", "job": 0, "kind": "echo", "inputs": [], "params": {}, "limits": {}},
        {"v": PROTOCOL, "job": -1, "kind": "echo", "inputs": [], "params": {}, "limits": {}},
        {"v": PROTOCOL, "job": 0, "kind": "nope", "inputs": [], "params": {}, "limits": {}},
        {"v": PROTOCOL, "job": 0, "kind": "echo", "inputs": [{"sha256": "zz"}], "params": {}, "limits": {}},
        {"v": PROTOCOL, "job": 0, "kind": "echo", "inputs": [], "params": [], "limits": {}},
    ],
)
def test_validate_request_rejects(request_obj):
    with pytest.raises(WorkerProtocolError):
        validate_request(request_obj, {"echo": None})


def test_audit_event_table_covers_both_groups():
    events = w.AUDIT_BLOCKED_EVENTS
    assert {
        "socket.connect",
        "socket.bind",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.sendto",
    } <= set(events["network"])
    assert {
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
        "os.fork",
        "os.forkpty",
    } <= set(events["subprocess"])


# ---- --in-process (G.4.9) -------------------------------------------------------------------------------------


def test_in_process_with_release_is_refused_with_exit_4():
    with pytest.raises(InProcessRefusedError) as info:
        WorkerPool(in_process=True, release=True)
    assert info.value.exit_code == 4
    assert isinstance(info.value, AgentProvError)
    WorkerPool(in_process=False, release=True)  # release alone is fine


def test_isolation_is_recorded():
    assert WorkerPool(in_process=True).isolation["mode"] == "in-process"
    assert WorkerPool(in_process=True).isolation["grade"] is None
    result = WorkerPool(in_process=True).run_one(Job("a", "echo", params={"x": 1}))
    assert result.ok and result.isolation == "in-process" and result.worker_pid is None


def test_in_process_runs_the_same_frame_round_trip():
    pool = WorkerPool(in_process=True)
    r = pool.run_one(Job("a", "echo", params={"members": [{"label": "m", "text": "hello"}]}))
    assert r.json == ({"echo": {"members": [{"label": "m", "text": "hello"}]}, "inputs": 0},)
    assert r.members[0].read_bytes() == b"hello" and r.members[0].header == {"label": "m", "size": 5}
    r.close()


def test_in_process_applies_the_output_caps_too():
    pool = WorkerPool(in_process=True, limits=WorkerLimits(max_frame_bytes=64))
    r = pool.run_one(Job("a", "echo", params={"pad": "x" * 200}))
    assert not r.ok and r.error.code == "worker.limit.output"  # type: ignore[union-attr]


def test_in_process_job_exception_is_a_failed_result():
    pool = WorkerPool(in_process=True, test_kinds=True)
    r = pool.run_one(Job("a", "test.raise_error", params={"message": "bad\x1b[31m"}))
    assert not r.ok and r.error.code == "worker.job.error"  # type: ignore[union-attr]
    assert "\x1b" not in str(r.error)


def test_results_sorted_by_key_regardless_of_submission_order():
    pool = WorkerPool(in_process=True)
    jobs = [Job(k, "echo", params={"k": k}) for k in ("b", "c", "a")]
    assert [r.key for r in pool.run(jobs)] == ["a", "b", "c"]


# ---- inputs by digest (G.4.5), in-process --------------------------------------------------------------------


def _store(tmp_path, data: bytes, *, name: str | None = None, ext: str = "json"):
    sha = hashlib.sha256(data).hexdigest()
    directory = tmp_path / sha[:2]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"{sha}.{ext}")
    path.write_bytes(data)
    path.chmod(0o444)
    return sha, path


def test_input_read_by_digest_and_verified(tmp_path):
    sha, _ = _store(tmp_path, b"payload")
    pool = WorkerPool(in_process=True, store_root=tmp_path)
    r = pool.run_one(Job("a", "sha256", inputs=({"sha256": sha, "role": "primary"},)))
    assert r.ok and r.json[0]["sha256"] == sha and r.json[0]["size"] == 7


def test_input_with_wrong_content_is_rejected(tmp_path):
    sha = hashlib.sha256(b"expected").hexdigest()
    (tmp_path / sha[:2]).mkdir()
    (tmp_path / sha[:2] / f"{sha}.json").write_bytes(b"corrupted")
    r = WorkerPool(in_process=True, store_root=tmp_path).run_one(
        Job("a", "sha256", inputs=({"sha256": sha, "role": "primary"},))
    )
    assert not r.ok and r.error.code == "worker.input.digest_mismatch"  # type: ignore[union-attr]


def _context(tmp_path, sha: str) -> w.JobContext:
    request = {"job": 0, "kind": "echo", "inputs": [{"sha256": sha, "role": "primary"}], "params": {}, "limits": {}}
    return w.JobContext(request, w.FrameWriter(io.BytesIO()), store_root=tmp_path)


def test_open_input_checks_the_digest_in_chunks_and_returns_a_rewound_handle(tmp_path):
    """HL.R7 / D-58: ``expand`` reads its container through this handle instead of a whole in-memory copy."""
    data = os.urandom(3 * (1 << 20) + 17)  # more than one 1 MiB hashing chunk
    sha, _ = _store(tmp_path, data, ext="zip")
    ctx = _context(tmp_path, sha)
    with ctx.open_input(0) as handle:
        assert handle.tell() == 0 and handle.seekable()
        assert handle.read(10) == data[:10]
        handle.seek(-5, os.SEEK_END)
        assert handle.read() == data[-5:]
    assert ctx.read_input(0) == data


def test_open_input_refuses_a_corrupted_object_and_closes_it(tmp_path, monkeypatch):
    sha = hashlib.sha256(b"expected").hexdigest()
    (tmp_path / sha[:2]).mkdir()
    (tmp_path / sha[:2] / f"{sha}.zip").write_bytes(b"corrupted")
    opened: list = []
    real = w.open_evidence

    def spy(*args, **kwargs):
        opened.append(real(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(w, "open_evidence", spy)
    with pytest.raises(w.WorkerInputError) as err:
        _context(tmp_path, sha).open_input(0)
    assert err.value.code == "worker.input.digest_mismatch" and opened and opened[0].closed


def test_missing_input_and_missing_store(tmp_path):
    inputs = ({"sha256": "a" * 64, "role": "primary"},)
    r = WorkerPool(in_process=True, store_root=tmp_path).run_one(Job("a", "sha256", inputs=inputs))
    assert r.error.code == "worker.input.missing"  # type: ignore[union-attr]
    r = WorkerPool(in_process=True).run_one(Job("a", "sha256", inputs=inputs))
    assert r.error.code == "worker.input.no_store"  # type: ignore[union-attr]


def test_symlinked_input_is_refused(tmp_path):
    sha, path = _store(tmp_path / "real", b"data")
    store = tmp_path / "store"
    (store / sha[:2]).mkdir(parents=True)
    (store / sha[:2] / f"{sha}.json").symlink_to(path)
    r = WorkerPool(in_process=True, store_root=store).run_one(
        Job("a", "sha256", inputs=({"sha256": sha, "role": "primary"},))
    )
    assert not r.ok and r.error.code == "worker.input.missing"  # type: ignore[union-attr]


# ---- fingerprint -----------------------------------------------------------------------------------------------


def test_result_fingerprint_binds_content_not_timing():
    a = JobResult("k", "echo", 0, ({"x": 1},), {"n": 1}, elapsed_s=1.0, worker_pid=1)
    b = JobResult("k", "echo", 7, ({"x": 1},), {"n": 1}, elapsed_s=9.0, worker_pid=2, stderr_tail=b"noise")
    c = JobResult("k", "echo", 0, ({"x": 2},), {"n": 1})
    assert result_fingerprint([a]) == result_fingerprint([b]) != result_fingerprint([c])
    assert result_fingerprint([a, c]) != result_fingerprint([c, a])


# ---- memory errors under an address-space limit (G.4.12) -------------------------------------------------------------


def test_a_memory_error_releases_the_jobs_locals_before_the_reply_is_built(monkeypatch):
    import weakref

    class Big:
        pass

    probes: list[bool] = []
    refs: list[weakref.ref] = []

    def hog(ctx):
        big = Big()  # stands for a large buffer held by the failing job
        refs.append(weakref.ref(big))
        raise MemoryError

    real = w._failure_for

    def spy(exc):
        probes.append(refs[0]() is None)  # alive here would starve the reply of memory under RLIMIT_AS
        return real(exc)

    monkeypatch.setattr(w, "_failure_for", spy)
    request = {"job": 1, "kind": "hog", "inputs": [], "params": {}, "limits": {}}
    out = io.BytesIO()
    assert w.run_job_request(request, {"hog": hog}, w.FrameWriter(out)) is False
    assert probes == [True]


def _bare_worker(*, as_enforced: bool, tail: bytes):
    worker = object.__new__(w._Worker)
    worker.as_enforced = as_enforced
    worker.tail = w._Tail(1024)
    worker.tail.add(tail)
    return worker


@pytest.mark.parametrize(
    ("as_enforced", "code", "tail", "expected"),
    [
        (True, 1, b"Traceback ...\nMemoryError\n", True),  # died of the limit before it could reply
        (True, -9, b"MemoryError\n", True),
        (True, 1, b"ValueError: x\n", False),  # an ordinary crash stays a crash
        (True, 0, b"MemoryError\n", False),  # a clean exit is not a failure
        (False, 1, b"MemoryError\n", False),  # no enforced address-space cap: not attributable to it
    ],
)
def test_a_worker_that_dies_of_memory_error_under_an_enforced_limit_is_a_memory_limit(as_enforced, code, tail, expected):
    assert _bare_worker(as_enforced=as_enforced, tail=tail).ran_out_of_address_space(code) is expected
