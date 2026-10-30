"""Host profile, capability probes and the pure constants table (agentprov.host; G.4.3, G.4.11).

Platform-specific tests are selected by probed capabilities (``skipif`` on ``CAPS``), never by operating-system name.
Synthetic profiles stand in for Linux-like, macOS-like, Windows-like and degraded hosts: they are described by what
the host can do, and ``constants_for`` must give the same answer for the same capabilities whatever the OS label.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import warnings

import pytest

from agentprov import host as h
from agentprov.host import (
    GIB,
    MIB,
    Calibration,
    Capabilities,
    Decided,
    HostProfile,
    attach_tree_killer,
    constants_for,
    detect_host,
    make_rss_sampler,
    minimal_environment,
    select_grade,
    spawn_kwargs,
)
from agentprov.io.workers import (
    IsolationDegradedWarning,
    IsolationInsufficientError,
    Job,
    WorkerLimits,
    WorkerPool,
    get_calibration,
)

HOST = detect_host()
CAPS = HOST.caps
OK_12 = Calibration("ok", alloc_rate_bytes_per_s=12.0 * GIB, duration_s=0.02, bytes_touched=256 * MIB)


def synthetic(
    os_family: str = "linux",
    *,
    arch: str = "x86_64",
    cpus: int | None = 8,
    memory: int | None = 16 * GIB,
    sampler: str = "procfs",
    tree: str = "killpg",
    hard: str = "none",
    cpu_limit: str = "rlimit_cpu",
) -> HostProfile:
    def d(value, how="synthetic"):
        return Decided(value, how)

    caps = Capabilities(
        resource_module=d(cpu_limit != "none"),
        rlimits=d(("core", "cpu", "fsize", "nofile") if cpu_limit != "none" else ()),
        rlimit_as_enforced=d(hard == "rlimit_as"),
        rss_sampler=d(sampler),
        tree_kill=d(tree),
        hard_memory_cap=d(hard),
        cpu_limit=d(cpu_limit),
    )
    return HostProfile(
        os_family=os_family,
        os_release="0",
        arch=arch,
        machine=arch,
        python_implementation="CPython",
        python_version="3.14.8",
        cpu_count=cpus,
        memory_bytes=memory,
        memory_how="synthetic",
        page_size=4096,
        page_size_how="synthetic",
        caps=caps,
    )


LINUX_LIKE = synthetic("linux", hard="rlimit_as")
DARWIN_LIKE = synthetic("darwin", arch="arm64", sampler="libproc", hard="none", memory=32 * GIB, cpus=12)
WINDOWS_LIKE = synthetic("windows", sampler="psapi", tree="job_object", hard="job_object", cpu_limit="none")
DEGRADED = synthetic("plan9", arch="other", sampler="none", tree="none", hard="none")


# ---- constants_for: pure, keyed by capabilities ---------------------------------------------------------------


def test_constants_are_pure_and_deterministic():
    for profile in (LINUX_LIKE, DARWIN_LIKE, WINDOWS_LIKE, DEGRADED):
        before = repr(profile)
        a = constants_for(profile, OK_12, rss_cap_bytes=2 * GIB)
        b = constants_for(profile, OK_12, rss_cap_bytes=2 * GIB)
        assert a == b and repr(profile) == before
        assert json.dumps(a.to_record(), sort_keys=True) == json.dumps(b.to_record(), sort_keys=True)


def test_constants_do_not_depend_on_the_operating_system_label_or_architecture():
    base = constants_for(DARWIN_LIKE, OK_12)
    relabelled = dataclasses.replace(
        DARWIN_LIKE, os_family="somethingelse", arch="x86_64", os_release="9", machine="z"
    )
    assert constants_for(relabelled, OK_12) == base


def test_linux_like_has_hard_cap_slow_backstop_and_no_margin():
    c = constants_for(LINUX_LIKE)
    assert (c.hard_memory_cap, c.watchdog_interval_s, c.rate_source) == ("rlimit_as", 0.1, "not needed")
    assert c.margin_for(2 * GIB) == 0 and c.trigger_for(2 * GIB) == 2 * GIB
    assert (c.grade, c.grade_reasons) == ("enforced", ())


def test_windows_like_job_object_is_enforced():
    c = constants_for(WINDOWS_LIKE)
    assert (c.hard_memory_cap, c.grade, c.watchdog_interval_s) == ("job_object", "enforced", 0.1)


def test_darwin_like_polls_fast_and_keeps_a_calibrated_margin():
    c = constants_for(DARWIN_LIKE, OK_12, rss_cap_bytes=2 * GIB)
    assert c.hard_memory_cap == "none" and c.rate_source == "calibrated" and c.grade == "watchdog"
    assert c.watchdog_interval_s == 0.02
    margin = c.margin_for(2 * GIB)
    assert margin == int(12.0 * GIB * 0.02 * 2.0) and c.trigger_for(2 * GIB) == 2 * GIB - margin


def test_default_rate_is_used_without_calibration_and_grade_is_degraded():
    c = constants_for(DARWIN_LIKE, None)
    assert c.rate_source == "default" and c.alloc_rate_bytes_per_s == h.DEFAULT_ALLOC_RATE
    assert c.grade == "degraded" and "not calibrated" in c.grade_reasons[0]
    failed = constants_for(DARWIN_LIKE, Calibration("failed", detail="x"))
    assert failed.rate_source == "default" and failed.grade == "degraded"
    skipped = constants_for(DARWIN_LIKE, Calibration.skipped("why"))
    assert skipped.grade == "degraded"


def test_unknown_host_is_degraded_with_reasons():
    c = constants_for(DEGRADED, OK_12)
    assert c.grade == "degraded"
    assert "no process-tree kill" in c.grade_reasons
    assert any("no RSS sampler" in r for r in c.grade_reasons)
    assert c.default_workers >= 1


# ---- calibration margin clamping --------------------------------------------------------------------------------


def test_margin_has_a_floor_of_32_mib():
    slow = Calibration("ok", alloc_rate_bytes_per_s=1.0 * MIB)
    c = constants_for(DARWIN_LIKE, slow, rss_cap_bytes=2 * GIB)
    assert c.margin_for(2 * GIB) == 32 * MIB and c.watchdog_interval_s == 0.02


def test_margin_is_clamped_to_half_the_cap_and_the_interval_is_lowered_first():
    cap = 512 * MIB
    c = constants_for(DARWIN_LIKE, OK_12, rss_cap_bytes=cap)  # 12 GiB/s * 20 ms * 2 = 480 MiB > cap/2
    assert c.watchdog_interval_s == 0.01  # lowered to the floor
    assert c.margin_for(cap) <= cap // 2
    mid = Calibration("ok", alloc_rate_bytes_per_s=8.0 * GIB)
    m = constants_for(DARWIN_LIKE, mid, rss_cap_bytes=cap)
    assert m.watchdog_interval_s == 0.01 and m.margin_for(cap) == int(
        8 * GIB * 0.01 * 2
    )  # 164 MiB, no clamp needed


def test_interval_never_goes_below_ten_ms_and_margin_is_then_clamped():
    cap = 256 * MIB
    fast = Calibration("ok", alloc_rate_bytes_per_s=1024.0 * GIB)
    c = constants_for(DARWIN_LIKE, fast, rss_cap_bytes=cap)
    assert c.watchdog_interval_s == h.INTERVAL_FLOOR
    assert c.margin_for(cap) == cap // 2 and c.trigger_for(cap) == cap - cap // 2


def test_margin_for_another_cap_uses_the_same_interval_and_its_own_clamp():
    c = constants_for(DARWIN_LIKE, OK_12, rss_cap_bytes=2 * GIB)
    assert c.margin_for(100 * MIB) == 50 * MIB  # clamped to half of the smaller cap
    assert c.margin_for(8 * GIB) == int(12.0 * GIB * 0.02 * 2.0)


# ---- default worker count ---------------------------------------------------------------------------------------


def test_default_workers_is_min_of_cpus_and_usable_memory_over_cap():
    assert constants_for(synthetic(cpus=64, memory=16 * GIB)).default_workers == 6  # 0.75 * 16 / 2
    assert constants_for(synthetic(cpus=2, memory=256 * GIB)).default_workers == 2
    assert constants_for(synthetic(cpus=8, memory=GIB // 2)).default_workers == 1  # never below one
    assert constants_for(synthetic(cpus=8, memory=None)).default_workers == 8
    assert constants_for(synthetic(cpus=None, memory=None)).default_workers == 1


# ---- grade selection -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "calibration", "grade"),
    [
        (LINUX_LIKE, None, "enforced"),
        (WINDOWS_LIKE, None, "enforced"),
        (DARWIN_LIKE, OK_12, "watchdog"),
        (DARWIN_LIKE, None, "degraded"),
        (synthetic(sampler="none", hard="none"), OK_12, "degraded"),
        (synthetic(tree="none", hard="rlimit_as"), None, "degraded"),
        (synthetic(tree="none", hard="none"), OK_12, "degraded"),
        (DEGRADED, None, "degraded"),
    ],
)
def test_grade_selection(profile, calibration, grade):
    got, reasons = select_grade(profile, calibration)
    assert got == grade and (not reasons) == (grade != "degraded")


# ---- the pool: release refusal, warning, record -------------------------------------------------------------------


def test_release_mode_refuses_a_degraded_host_with_exit_3():
    pool = WorkerPool(release=True, host=DEGRADED, calibration=Calibration("failed", detail="x"))
    with pytest.raises(IsolationInsufficientError) as info:
        pool.prepare()
    assert info.value.code == "worker.isolation.insufficient" and info.value.exit_code == 3
    with pytest.raises(IsolationInsufficientError):
        pool.run([Job("a", "echo")])


def test_release_mode_accepts_watchdog_and_enforced_hosts_without_spawning():
    WorkerPool(release=True, host=DARWIN_LIKE, calibration=OK_12).prepare()
    WorkerPool(release=True, host=LINUX_LIKE).prepare()
    WorkerPool(release=True, host=WINDOWS_LIKE).prepare()


def test_dev_mode_warns_with_a_non_user_warning_and_records_the_grade():
    pool = WorkerPool(host=DEGRADED, calibration=Calibration.skipped("test"))
    with pytest.warns(IsolationDegradedWarning, match="degraded"):
        pool.prepare()
    assert not issubclass(IsolationDegradedWarning, UserWarning)
    assert pool.isolation["grade"] == "degraded"


def test_isolation_record_is_json_able_and_complete():
    pool = WorkerPool(host=DARWIN_LIKE, calibration=OK_12, watchdog_interval=None)
    record = pool.isolation
    json.dumps(record)
    assert record["mode"] == "worker" and record["grade"] == "watchdog" and record["release"] is False
    assert record["host"]["capabilities"]["rss_sampler"] == {"value": "libproc", "how": "synthetic"}
    assert record["host"]["os_family"] == "darwin" and record["host"]["arch"] == "arm64"
    assert record["constants"]["watchdog_interval_s"] == 0.02
    assert record["constants"]["rss_trigger_bytes"] < record["constants"]["rss_cap_bytes"]
    assert record["calibration"]["status"] == "ok"
    assert WorkerPool(in_process=True).isolation == {
        "mode": "in-process",
        "grade": None,
        "note": "no process isolation, limits or audit hook",
    }


def test_explicit_watchdog_interval_overrides_the_table():
    pool = WorkerPool(host=DARWIN_LIKE, calibration=OK_12, watchdog_interval=0.5)
    pool.prepare()
    assert pool.constants.watchdog_interval_s == 0.5


def test_no_warning_for_enforced_or_watchdog_grades():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        WorkerPool(host=LINUX_LIKE).prepare()
        WorkerPool(host=DARWIN_LIKE, calibration=OK_12).prepare()


# ---- spawn flags, environment ------------------------------------------------------------------------------------


def test_spawn_kwargs_follow_the_tree_kill_capability():
    assert spawn_kwargs(LINUX_LIKE) == {"start_new_session": True}
    flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    assert spawn_kwargs(WINDOWS_LIKE) == ({"creationflags": flag} if flag else {})
    assert spawn_kwargs(DEGRADED) == ({"creationflags": flag} if flag else {})


def test_minimal_environment_is_pure_and_explicit():
    posix = minimal_environment("/job", {"OPENAI_API_KEY": "x", "UV_CACHE_DIR": "/c"})
    assert posix == {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "HOME": "/job",
        "TMPDIR": "/job",
        "PATH": "/usr/bin:/bin",
    }
    loader = minimal_environment("J", {"SYSTEMROOT": "C:\\Windows", "OPENAI_API_KEY": "x"})
    assert (
        loader["SYSTEMROOT"] == "C:\\Windows"
        and loader["TEMP"] == loader["TMP"] == loader["USERPROFILE"] == "J"
    )
    assert "OPENAI_API_KEY" not in loader


# ---- detect_host on this machine ----------------------------------------------------------------------------------


def test_detect_host_returns_sane_facts():
    assert HOST.os_family and HOST.os_family == HOST.os_family.lower()
    assert HOST.arch in ("x86_64", "arm64", "other")
    assert HOST.python_implementation and HOST.python_version.startswith(f"{sys.version_info.major}.")
    assert HOST.cpu_count is None or HOST.cpu_count >= 1
    assert HOST.memory_bytes is None or HOST.memory_bytes > 256 * MIB
    assert HOST.page_size >= 4096 and HOST.page_size & (HOST.page_size - 1) == 0
    assert HOST.memory_how and HOST.page_size_how


def test_every_capability_records_how_it_was_decided():
    for field in dataclasses.fields(Capabilities):
        decided = getattr(CAPS, field.name)
        assert isinstance(decided, Decided) and decided.how, field.name
    json.dumps(HOST.to_record())
    assert CAPS.rss_sampler.value in ("procfs", "libproc", "psapi", "none")
    assert CAPS.tree_kill.value in ("killpg", "job_object", "none")
    assert CAPS.hard_memory_cap.value in ("rlimit_as", "job_object", "none")
    assert CAPS.rlimit_as_enforced.value in (True, False, None)


def test_capabilities_are_consistent_with_each_other():
    assert (CAPS.hard_memory_cap.value == "rlimit_as") == (CAPS.rlimit_as_enforced.value is True)
    if "as" not in CAPS.rlimits.value:
        assert CAPS.rlimit_as_enforced.value is False
    assert bool(CAPS.resource_module) == bool(CAPS.rlimits.value)


def test_detect_host_is_cached_per_process_and_refresh_redoes_it():
    assert detect_host() is HOST
    again = detect_host(refresh=True)
    # startup_vm_bytes is a measurement (VmPeak of a probe child) and varies by a few KiB between probes
    measured = ("startup_vm_bytes",)
    a = {k: v for k, v in again.to_record()["capabilities"].items() if k not in measured}
    b = {k: v for k, v in HOST.to_record()["capabilities"].items() if k not in measured}
    assert again is not HOST and a == b
    assert {k: v for k, v in again.to_record().items() if k != "capabilities"} == {
        k: v for k, v in HOST.to_record().items() if k != "capabilities"
    }
    assert detect_host() is again


def test_unprobed_profile_marks_rlimit_as_unknown_then_completes():
    unprobed = detect_host(refresh=True, probe=False)
    if "as" in unprobed.caps.rlimits.value:
        assert (
            unprobed.caps.rlimit_as_enforced.value is None
            and unprobed.caps.hard_memory_cap.value != "rlimit_as"
        )
    full = detect_host(probe=True)
    assert full.caps.rlimit_as_enforced.value in (True, False)


# ---- samplers, tree kill, calibration on this host ----------------------------------------------------------------


@pytest.mark.skipif(not CAPS.rss_sampler, reason="no RSS sampler on this host")
def test_the_chosen_sampler_reads_this_process_and_a_child():
    sample = make_rss_sampler(str(CAPS.rss_sampler.value))
    assert sample is not None
    own = sample(__import__("os").getpid())
    assert own is not None and 5 * MIB < own < 64 * GIB
    assert sample(2**22 + 12345) is None  # no such process


def test_unknown_sampler_kind_is_none():
    assert make_rss_sampler("none") is None and make_rss_sampler("ps") is None  # the `ps` subprocess is gone


@pytest.mark.skipif(not CAPS.tree_kill, reason="no process-tree kill on this host")
def test_tree_killer_ends_a_child_started_with_the_spawn_flags():
    proc = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(60)"], **spawn_kwargs(HOST)
    )
    killer = attach_tree_killer(HOST, proc, memory_limit_bytes=GIB)
    try:
        killer.kill()
        assert proc.wait(timeout=20) != 0
    finally:
        killer.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.slow
def test_calibration_runs_in_a_worker_and_is_cached_per_process():
    first = get_calibration(HOST)
    assert first.status == "ok", first
    assert first.alloc_rate_bytes_per_s and first.alloc_rate_bytes_per_s > 50 * MIB
    assert 8 * MIB <= first.bytes_touched <= 512 * MIB and first.duration_s < 5
    assert get_calibration(HOST) is first


def test_calibrate_job_is_bounded_and_always_touches_a_block():
    r = WorkerPool(in_process=True).run_one(Job("c", "calibrate", params={"budget_s": 0.0, "max_bytes": 1}))
    assert r.ok and r.json[0]["bytes"] == 8 * MIB
    r = WorkerPool(in_process=True).run_one(
        Job("c", "calibrate", params={"max_bytes": 10**12, "budget_s": 99})
    )
    assert r.json[0]["bytes"] <= 512 * MIB + 8 * MIB  # caps hold whatever the request says


def test_a_worker_pool_on_this_host_has_a_recorded_grade():
    pool = WorkerPool(limits=WorkerLimits())
    record = pool.isolation
    json.dumps(record)
    assert record["grade"] in ("enforced", "watchdog", "degraded")
    if CAPS.hard_memory_cap or (CAPS.rss_sampler and CAPS.tree_kill):
        assert record["grade"] != "degraded"


# ---- portable no-follow, POSIX permissions and the address-space floor (D-7; G.3.10, G.4.12) -----------------------


def with_caps(profile: HostProfile, **changes: Decided) -> HostProfile:
    return dataclasses.replace(profile, caps=dataclasses.replace(profile.caps, **changes))


def test_nofollow_capability_records_the_mechanism_ingest_selected():
    from agentprov.ingest import paths

    value, how = paths.describe_mechanism()
    assert (CAPS.nofollow.value, CAPS.nofollow.how) == (value, how)
    assert CAPS.nofollow.value in ("native", "verify_identity", "none") and how


def test_posix_permissions_is_probed_by_chmod_and_stat_not_by_name(monkeypatch):
    assert h._probe_posix_permissions().value in (True, False, None)
    monkeypatch.setattr(h.os, "chmod", lambda path, mode: None)  # a host where chmod bits do not stick
    decided = h._probe_posix_permissions()
    assert decided.value is False and "ACL" in decided.how


def test_new_capabilities_are_in_the_record():
    record = HOST.to_record()["capabilities"]
    for name in ("nofollow", "posix_permissions", "startup_vm_bytes"):
        assert set(record[name]) == {"value", "how"} and record[name]["how"]


def test_a_profile_built_without_the_new_capabilities_keeps_working():
    caps = dataclasses.replace(LINUX_LIKE.caps)
    assert caps.nofollow.value is None and caps.posix_permissions.value is None and caps.startup_vm_bytes.value is None
    assert constants_for(LINUX_LIKE).as_floor_bytes == 0


def test_the_address_space_floor_is_the_measured_footprint_plus_headroom():
    measured = with_caps(LINUX_LIKE, startup_vm_bytes=Decided(1_500 * MIB, "synthetic"))
    c = constants_for(measured)
    assert c.startup_vm_bytes == 1_500 * MIB and c.as_floor_bytes == 1_500 * MIB + h.AS_STARTUP_HEADROOM
    assert c.as_limit_for(1 * GIB) == c.as_floor_bytes  # a cap below the floor is raised, never kept
    assert c.as_limit_for(4 * GIB) == 4 * GIB  # a roomy cap is untouched
    assert c.as_limit_for(0) == 0  # 0 still disables the limit
    assert c.to_record()["as_floor_bytes"] == c.as_floor_bytes


def test_no_floor_without_an_enforced_address_space_cap_or_a_measurement():
    for profile in (DARWIN_LIKE, WINDOWS_LIKE):  # RLIMIT_AS is not the hard cap there
        c = constants_for(with_caps(profile, startup_vm_bytes=Decided(1 * GIB, "synthetic")))
        assert c.as_floor_bytes == 0 and c.as_limit_for(1 * MIB) == 1 * MIB
    unmeasured = with_caps(LINUX_LIKE, startup_vm_bytes=Decided(None, "synthetic"))
    assert constants_for(unmeasured).as_floor_bytes == 0


def test_the_floor_follows_the_measurement_whatever_the_os_label_or_architecture():
    measured = with_caps(LINUX_LIKE, startup_vm_bytes=Decided(2 * GIB, "synthetic"))
    relabelled = dataclasses.replace(measured, os_family="other", arch="arm64", page_size=65536)
    assert constants_for(relabelled).as_floor_bytes == constants_for(measured).as_floor_bytes


@pytest.mark.skipif(CAPS.hard_memory_cap.value != "rlimit_as", reason="the address-space probe runs where RLIMIT_AS is enforced")
def test_the_probe_child_reports_a_startup_footprint_where_the_host_has_one():
    enforced, startup = h._probe_rlimit_as()
    assert enforced.value is True
    assert startup.value is None or startup.value > 16 * MIB  # a bare interpreter maps tens of MiB at least
