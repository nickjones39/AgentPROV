"""Host profile, probed capabilities and derived constants (L0; stdlib and ctypes only).

AgentPROV runs on Linux, macOS and Windows, on x86_64 and arm64. Nothing in the core chooses a code path by
operating-system name. Instead :func:`detect_host` records *facts* (operating-system family, architecture, CPU count,
physical memory, page size) and probes *capabilities* with feature tests. Each capability records how it was decided
(:class:`Decided`), so a corpus can state what isolation the producing host actually gave (G.4.3, G.4.11).

Capabilities (each decided by a probe, never by ``sys.platform``):

``resource_module``    the POSIX ``resource`` module imports.
``rlimits``            which of ``core, cpu, fsize, nofile, as`` exist and answer ``getrlimit``.
``rlimit_as_enforced`` a throwaway child sets a low ``RLIMIT_AS`` and tries to allocate above it. macOS accepts the
                       limit but does not enforce it, so only this probe decides. ``None`` means "not probed".
``rss_sampler``        first of ``procfs`` (``/proc/<pid>/statm``), ``libproc`` (``proc_pidinfo`` through ctypes),
                       ``psapi`` (``GetProcessMemoryInfo``), ``none`` that returns a plausible RSS for this process.
``tree_kill``          ``killpg`` (POSIX session + ``os.killpg``), ``job_object`` (Windows Job Object with
                       kill-on-close) or ``none``.
``hard_memory_cap``    ``rlimit_as`` where it is enforced, else ``job_object`` where the Job Object accepts
                       ``JOB_OBJECT_LIMIT_PROCESS_MEMORY``, else ``none``.
``cpu_limit``          ``rlimit_cpu`` or ``none`` (the parent's wall clock still applies).
``nofollow``           the no-follow open mechanism of ``agentprov.ingest.paths``: ``native`` (``dir_fd`` walk with the
                       no-follow flag), ``verify_identity`` (per-component ``lstat`` plus a post-open ``fstat``
                       identity check, for hosts without those primitives) or ``none`` (ingest fails closed). The
                       decision is the feature test of ``paths._probe``; this module only records it.
``posix_permissions``  a temporary file chmod-ed ``0o600`` and a directory chmod-ed ``0o700`` read back exactly. When
                       false, the private ``tmp`` and job directories rely on the user-profile ACL of the host
                       (a known gap, G.4.12).
``startup_vm_bytes``   the peak address space of a worker-like process after it imported the job table (``VmPeak``
                       from the probe child, where the host reports it). ``constants_for`` never lets ``RLIMIT_AS``
                       fall below it plus :data:`AS_STARTUP_HEADROOM`.

:func:`constants_for` is a pure function from a profile (and an optional calibration) to the watchdog interval, the
RSS trigger margin, the default worker count and the isolation grade. Its table is documented on the function.
Nothing here ever enters AER or PROV bytes; it is recorded only in the corpus ``producer`` block.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import dataclasses
import mmap
import os
import platform
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "AS_STARTUP_HEADROOM",
    "DEFAULT_ALLOC_RATE",
    "GRADES",
    "Calibration",
    "Capabilities",
    "Decided",
    "HostConstants",
    "HostProfile",
    "TreeKiller",
    "attach_tree_killer",
    "available_rlimits",
    "constants_for",
    "detect_host",
    "make_rss_sampler",
    "select_grade",
    "spawn_kwargs",
]

KIB: Final = 1 << 10
MIB: Final = 1 << 20
GIB: Final = 1 << 30

GRADES: Final = ("enforced", "watchdog", "degraded")  # best first

# ---- constants table (see constants_for) ---------------------------------------------------------------------
INTERVAL_HARD_CAP: Final = 0.1  # s: a hard memory cap is enforced, the watchdog is only a backstop (G.4.3)
INTERVAL_SOFT_CAP: Final = 0.02  # s: no hard cap: the sampler is the only memory control
INTERVAL_FLOOR: Final = 0.01  # s
MIN_MARGIN: Final = 32 * MIB
SAFETY_FACTOR: Final = 2.0
DEFAULT_ALLOC_RATE: Final = 4 * GIB  # bytes/s assumed when no calibration ran (see constants_for)
USABLE_MEMORY_FRACTION: Final = 0.75
DEFAULT_RSS_CAP: Final = 2 * GIB
#: Address space a worker may use beyond its measured start-up footprint before ``RLIMIT_AS`` bites (G.4.12). The start-up
#: footprint is host-dependent (arena reservations, page size), so a fixed absolute cap can be below what the interpreter
#: needs to start; the floor is ``startup_vm + AS_STARTUP_HEADROOM``.
AS_STARTUP_HEADROOM: Final = 256 * MIB

_RLIMIT_NAMES: Final = ("core", "cpu", "fsize", "nofile", "as")
_RSS_SAMPLER_ORDER: Final = ("procfs", "libproc", "psapi")


@dataclass(frozen=True)
class Decided:
    """A probed value and how it was decided (for the record)."""

    value: Any
    how: str

    def __bool__(self) -> bool:
        """True when the capability is present: not ``None``, ``False``, ``"none"`` or empty."""
        return self.value not in (None, False, "none", ())

    def to_record(self) -> dict[str, Any]:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {"value": value, "how": self.how}


@dataclass(frozen=True)
class Capabilities:
    resource_module: Decided
    rlimits: Decided
    rlimit_as_enforced: Decided
    rss_sampler: Decided
    tree_kill: Decided
    hard_memory_cap: Decided
    cpu_limit: Decided
    nofollow: Decided = field(default_factory=lambda: Decided(None, "not probed"))
    posix_permissions: Decided = field(default_factory=lambda: Decided(None, "not probed"))
    startup_vm_bytes: Decided = field(default_factory=lambda: Decided(None, "not probed"))

    def to_record(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name).to_record() for f in dataclasses.fields(self)}


@dataclass(frozen=True)
class HostProfile:
    os_family: str
    os_release: str
    arch: str  # x86_64 | arm64 | other
    machine: str  # as reported, for the record
    python_implementation: str
    python_version: str
    cpu_count: int | None
    memory_bytes: int | None
    memory_how: str
    page_size: int
    page_size_how: str
    caps: Capabilities

    def to_record(self) -> dict[str, Any]:
        facts = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.name != "caps"}
        return {**facts, "capabilities": self.caps.to_record()}


@dataclass(frozen=True)
class Calibration:
    """Outcome of the allocation-rate probe (run in a T1 worker, once per process; see ``io.workers``)."""

    status: str  # ok | skipped | failed
    alloc_rate_bytes_per_s: float | None = None
    duration_s: float | None = None
    bytes_touched: int | None = None
    detail: str = ""

    @classmethod
    def skipped(cls, reason: str) -> Calibration:
        return cls("skipped", detail=reason)

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------------------------------------------


def _import_resource() -> Any:
    try:
        import resource
    except ImportError:
        return None
    return resource


def available_rlimits() -> tuple[str, ...]:
    """The rlimits from ``core, cpu, fsize, nofile, as`` that exist here. Cheap: never spawns."""
    resource = _import_resource()
    if resource is None:
        return ()
    found = []
    for name in _RLIMIT_NAMES:
        const = getattr(resource, f"RLIMIT_{name.upper()}", None)
        if const is None:
            continue
        try:
            resource.getrlimit(const)
        except (ValueError, OSError):
            continue
        found.append(name)
    return tuple(found)


_AS_PROBE = """
import sys
vm = None
try:
    with open("/proc/self/status", "rb") as handle:
        for line in handle:
            if line.startswith((b"VmPeak:", b"VmSize:")) and vm is None:
                vm = int(line.split()[1]) * 1024
except (OSError, ValueError, IndexError):
    vm = None
try:  # the footprint the worker needs to start: the interpreter plus every module of the closed job table
    from agentprov.io import workers
    workers.preload_job_kinds(workers.kind_table(test_kinds=False))
    with open("/proc/self/status", "rb") as handle:
        for line in handle:
            if line.startswith(b"VmPeak:"):
                vm = int(line.split()[1]) * 1024
except Exception:
    pass
if vm is not None:
    sys.stdout.write("VM %d\\n" % vm)
    sys.stdout.flush()
import resource
limit = 256 << 20
try:
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
except (ValueError, OSError):
    sys.exit(10)
try:
    block = bytearray(512 << 20)
except MemoryError:
    sys.exit(11)
sys.exit(12)
"""


def _probe_rlimit_as() -> tuple[Decided, Decided]:
    """Throwaway child: measure its start-up address space, then set a low ``RLIMIT_AS`` and allocate above it.

    Returns ``(rlimit_as_enforced, startup_vm_bytes)``. Exit 11 means the kernel enforced the limit. The start-up footprint
    is read from ``/proc/self/status`` where the host has it, else it is not decided.
    """
    env = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-B", "-c", _AS_PROBE],
            capture_output=True,
            timeout=30,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        failed = Decided(None, f"probe could not run: {type(exc).__name__}")
        return failed, failed
    vm = Decided(None, "the host reports no address-space figure for a process")
    for line in done.stdout.decode("ascii", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "VM" and parts[1].isdigit():
            vm = Decided(int(parts[1]), "VmPeak of the probe child after importing the job table")
    code = done.returncode
    if code == 11:
        return Decided(True, "child allocated 512 MiB under a 256 MiB RLIMIT_AS and got MemoryError"), vm
    if code == 12:
        return Decided(False, "child set RLIMIT_AS=256 MiB, allocated 512 MiB and was not stopped"), vm
    if code == 10:
        return Decided(False, "child could not set RLIMIT_AS (rejected by the OS)"), vm
    return Decided(None, f"probe ended with return code {code}"), vm


def _probe_posix_permissions() -> Decided:
    """Feature test: do ``chmod`` bits read back exactly? A file at ``0o600`` and a directory at ``0o700``."""
    try:
        with tempfile.TemporaryDirectory(prefix="agentprov-probe-") as scratch:
            file_path = os.path.join(scratch, "f")
            dir_path = os.path.join(scratch, "d")
            os.close(os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666))
            os.mkdir(dir_path)
            os.chmod(file_path, 0o600)
            os.chmod(dir_path, 0o700)
            got_file = stat.S_IMODE(os.stat(file_path).st_mode)
            got_dir = stat.S_IMODE(os.stat(dir_path).st_mode)
    except OSError as exc:
        return Decided(None, f"probe could not run: {type(exc).__name__}")
    if (got_file, got_dir) == (0o600, 0o700):
        return Decided(True, "chmod 0o600 on a file and 0o700 on a directory read back exactly")
    return Decided(
        False, f"chmod 0o600 and 0o700 read back as {got_file:#o} and {got_dir:#o}; access is governed by the host's ACLs"
    )


def _decide_nofollow() -> Decided:
    """The no-follow mechanism ``agentprov.ingest.paths`` selected (``native``, ``verify_identity`` or ``none``)."""
    from agentprov.ingest.paths import describe_mechanism  # noqa: PLC0415 - lazy: paths owns the feature test

    mechanism, how = describe_mechanism()
    return Decided(mechanism, how)


def _page_size() -> tuple[int, str]:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")), "os.sysconf(SC_PAGE_SIZE)"
    except (AttributeError, ValueError, OSError):
        return int(mmap.PAGESIZE), "mmap.PAGESIZE"


def _physical_memory() -> tuple[int | None, str]:
    try:
        total = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
        if total > 0:
            return total, "os.sysconf(SC_PHYS_PAGES*SC_PAGE_SIZE)"
    except (AttributeError, ValueError, OSError):
        pass
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "", use_errno=True)
        value, size = ctypes.c_uint64(0), ctypes.c_size_t(8)
        if libc.sysctlbyname(b"hw.memsize", ctypes.byref(value), ctypes.byref(size), None, 0) == 0 and value.value:
            return int(value.value), "sysctlbyname(hw.memsize) via ctypes"
    except (AttributeError, OSError, TypeError):
        pass
    try:
        total = _windows_total_phys()
        if total:
            return total, "GlobalMemoryStatusEx via ctypes"
    except (AttributeError, OSError):
        pass
    return None, "unavailable"


def _windows_total_phys() -> int:
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    win_dll: Any = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise AttributeError("no WinDLL")
    kernel32 = win_dll("kernel32", use_last_error=True)
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0
    return int(status.ullTotalPhys)


def _normalise_arch(machine: str) -> str:
    m = machine.lower()
    if m in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "other"


# ---- RSS samplers --------------------------------------------------------------------------------------------


def make_rss_sampler(kind: str) -> Callable[[int], int | None] | None:
    """A function ``pid -> resident bytes | None`` of the given kind, or None if its API cannot be resolved."""
    if kind == "procfs":
        page = _page_size()[0]

        def procfs(pid: int) -> int | None:
            try:
                with open(f"/proc/{pid}/statm", "rb") as handle:
                    return int(handle.read().split()[1]) * page
            except (OSError, ValueError, IndexError):
                return None

        return procfs
    if kind == "libproc":
        return _make_libproc_sampler()
    if kind == "psapi":
        return _make_psapi_sampler()
    return None


def _make_libproc_sampler() -> Callable[[int], int | None] | None:
    """``proc_pidinfo(PROC_PIDTASKINFO)``: the second 64-bit field of ``proc_taskinfo`` is the resident size."""
    name = ctypes.util.find_library("proc")
    if not name:
        return None
    try:
        lib = ctypes.CDLL(name, use_errno=True)
        func = lib.proc_pidinfo
    except (AttributeError, OSError):
        return None
    func.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    func.restype = ctypes.c_int
    proc_pidtaskinfo, size = 4, 96  # PROC_PIDTASKINFO, sizeof(struct proc_taskinfo)

    def libproc(pid: int) -> int | None:
        buffer = (ctypes.c_uint64 * (size // 8))()
        if func(pid, proc_pidtaskinfo, 0, buffer, size) != size:
            return None
        return int(buffer[1])

    return libproc


class _RusageInfoV4(ctypes.Structure):
    """``struct rusage_info_v4`` (``<sys/resource.h>``), field by field in the SDK's order (D-554)."""

    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16), *((name, ctypes.c_uint64) for name in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins", "ri_wired_size",
        "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime", "ri_proc_exit_abstime", "ri_child_user_time",
        "ri_child_system_time", "ri_child_pkg_idle_wkups", "ri_child_interrupt_wkups", "ri_child_pageins",
        "ri_child_elapsed_abstime", "ri_diskio_bytesread", "ri_diskio_byteswritten", "ri_cpu_time_qos_default",
        "ri_cpu_time_qos_maintenance", "ri_cpu_time_qos_background", "ri_cpu_time_qos_utility",
        "ri_cpu_time_qos_legacy", "ri_cpu_time_qos_user_initiated", "ri_cpu_time_qos_user_interactive",
        "ri_billed_system_time", "ri_serviced_system_time", "ri_logical_writes", "ri_lifetime_max_phys_footprint",
        "ri_instructions", "ri_cycles", "ri_billed_energy", "ri_serviced_energy", "ri_interval_max_phys_footprint",
        "ri_runnable_time"))]


@dataclass(frozen=True)
class Footprint:
    """A process's memory as the D-554 admission controller counts it.

    ``current`` is ``phys_footprint`` on macOS (it keeps counting compressed pages, where the resident size falls when the
    host is short), else the resident size of the RSS sampler. ``lifetime_max`` is the kernel's lifetime maximum of
    ``phys_footprint`` (macOS), else ``None``. ``metric`` names what ``current`` is."""

    current: int
    lifetime_max: int | None
    metric: str


def footprint_reader(profile: HostProfile | None = None) -> Callable[[int], Footprint | None] | None:
    """The best per-process memory reader of this host for admission (D-554): ``proc_pid_rusage(RUSAGE_INFO_V4)`` on
    macOS, else the host's RSS sampler (``metric`` ``"resident"``). ``None`` when the host has neither."""
    name = ctypes.util.find_library("proc") if sys.platform == "darwin" else None
    if name:
        try:
            func = ctypes.CDLL(name, use_errno=True).proc_pid_rusage
        except (AttributeError, OSError):
            func = None
        if func is not None:
            func.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
            func.restype = ctypes.c_int
            rusage_info_v4 = 4

            def footprint(pid: int) -> Footprint | None:
                info = _RusageInfoV4()
                if func(pid, rusage_info_v4, ctypes.byref(info)) != 0:
                    return None
                return Footprint(int(info.ri_phys_footprint), int(info.ri_lifetime_max_phys_footprint), "phys_footprint")

            return footprint
    sampler = host_rss_sampler(profile) if profile is not None else None
    if sampler is None:
        return None

    def resident(pid: int) -> Footprint | None:
        value = sampler(pid)
        return None if value is None else Footprint(int(value), None, "resident")

    return resident


def _make_psapi_sampler() -> Callable[[int], int | None] | None:
    """``OpenProcess`` + ``GetProcessMemoryInfo``: ``WorkingSetSize``."""
    win_dll: Any = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return None
    try:
        from ctypes import wintypes

        kernel32 = win_dll("kernel32", use_last_error=True)
        psapi = win_dll("psapi", use_last_error=True)
        get_info = getattr(psapi, "GetProcessMemoryInfo", None) or kernel32.K32GetProcessMemoryInfo
        open_process, close_handle = kernel32.OpenProcess, kernel32.CloseHandle
    except (AttributeError, OSError):
        return None

    class COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    open_process.restype = wintypes.HANDLE
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    close_handle.argtypes = [wintypes.HANDLE]
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(COUNTERS), wintypes.DWORD]
    query_limited = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION

    def psapi_sample(pid: int) -> int | None:
        handle = open_process(query_limited, False, pid)
        if not handle:
            return None
        try:
            counters = COUNTERS()
            counters.cb = ctypes.sizeof(COUNTERS)
            if not get_info(handle, ctypes.byref(counters), counters.cb):
                return None
            return int(counters.WorkingSetSize)
        finally:
            close_handle(handle)

    return psapi_sample


def _decide_rss_sampler() -> tuple[Decided, Callable[[int], int | None] | None]:
    for kind in _RSS_SAMPLER_ORDER:
        sampler = make_rss_sampler(kind)
        if sampler is None:
            continue
        own = sampler(os.getpid())
        if own is not None and own > MIB:
            return Decided(kind, f"{kind} returned a plausible RSS for this process"), sampler
    return Decided("none", "no procfs, libproc or psapi sampler returned a plausible RSS"), None


# ---- process-tree kill and Windows Job Objects ---------------------------------------------------------------

_JOB_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA_TERMINATE = 0x0100 | 0x0001


def _job_api() -> dict[str, Any] | None:
    """Resolve the Job Object functions with typed signatures, or None."""
    win_dll: Any = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return None
    try:
        from ctypes import wintypes

        k = win_dll("kernel32", use_last_error=True)
        api = {
            "create": k.CreateJobObjectW,
            "set": k.SetInformationJobObject,
            "assign": k.AssignProcessToJobObject,
            "terminate": k.TerminateJobObject,
            "open": k.OpenProcess,
            "close": k.CloseHandle,
        }
    except (AttributeError, OSError):
        return None

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (n, ctypes.c_ulonglong)
            for n in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    api["create"].restype = wintypes.HANDLE
    api["create"].argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api["set"].argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api["assign"].argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api["terminate"].argtypes = [wintypes.HANDLE, wintypes.UINT]
    api["open"].restype = wintypes.HANDLE
    api["open"].argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api["close"].argtypes = [wintypes.HANDLE]
    api["Extended"] = Extended
    return api


def _decide_tree_kill() -> Decided:
    if hasattr(os, "killpg"):
        return Decided("killpg", "os.killpg exists; workers start in their own session")
    api = _job_api()
    if api is not None:
        job = api["create"](None, None)
        if job:
            api["close"](job)
            return Decided("job_object", "CreateJobObjectW works; workers are assigned to a kill-on-close job")
    return Decided("none", "neither os.killpg nor Job Objects are available")


def _decide_hard_cap(as_enforced: Decided, tree_kill: Decided) -> Decided:
    if as_enforced.value is True:
        return Decided("rlimit_as", "rlimit_as_enforced probe succeeded")
    if tree_kill.value == "job_object":
        return Decided("job_object", "Job Object JOB_OBJECT_LIMIT_PROCESS_MEMORY")
    return Decided("none", "RLIMIT_AS not enforced and no Job Object")


class TreeKiller:
    """Kills a worker and everything it started. ``kind`` is the ``tree_kill`` capability."""

    def __init__(self, kind: str, proc: subprocess.Popen[bytes], job: Any = None, api: Any = None) -> None:
        self.kind = kind
        self._proc = proc
        self._job = job
        self._api = api

    def kill(self) -> None:
        try:
            if self.kind == "killpg":
                os.killpg(self._proc.pid, signal.SIGKILL)
            elif self.kind == "job_object" and self._job:
                self._api["terminate"](self._job, 1)
            else:
                self._proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def close(self) -> None:
        if self._job and self._api is not None:
            self._api["close"](self._job)
            self._job = None


def spawn_kwargs(profile: HostProfile) -> dict[str, Any]:
    """``Popen`` keyword arguments that put the worker in its own killable tree, chosen by capability."""
    if profile.caps.tree_kill.value == "killpg":
        return {"start_new_session": True}
    flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": flag} if flag else {}


def attach_tree_killer(profile: HostProfile, proc: subprocess.Popen[bytes], *, memory_limit_bytes: int = 0) -> TreeKiller:
    """Create the kill handle for a started worker; for a Job Object also assign it and set the memory cap.

    The worker is assigned right after ``Popen`` returns. It reads nothing until the parent sends a job, so no
    untrusted input is processed before the assignment.
    """
    if profile.caps.tree_kill.value == "job_object":
        api = _job_api()
        if api is not None:
            job = api["create"](None, None)
            if job:
                info = api["Extended"]()
                flags = _JOB_LIMIT_KILL_ON_JOB_CLOSE
                if memory_limit_bytes > 0 and profile.caps.hard_memory_cap.value == "job_object":
                    flags |= _JOB_LIMIT_PROCESS_MEMORY
                    info.ProcessMemoryLimit = memory_limit_bytes
                info.BasicLimitInformation.LimitFlags = flags
                handle = api["open"](_PROCESS_SET_QUOTA_TERMINATE, False, proc.pid)
                ok = bool(
                    handle
                    and api["set"](job, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info))
                    and api["assign"](job, handle)
                )
                if handle:
                    api["close"](handle)
                if ok:
                    return TreeKiller("job_object", proc, job, api)
                api["close"](job)
        return TreeKiller("none", proc)
    return TreeKiller(str(profile.caps.tree_kill.value), proc)


# ---------------------------------------------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------------------------------------------

_LOCK = threading.Lock()
_CACHE: HostProfile | None = None
_SAMPLER: Callable[[int], int | None] | None = None


def detect_host(*, refresh: bool = False, probe: bool = True) -> HostProfile:
    """Detect the host once per process. ``probe=False`` skips the ``RLIMIT_AS`` child (``rlimit_as_enforced`` is
    then ``None``, "not probed"); a later ``probe=True`` call completes the profile. ``refresh=True`` redoes everything.
    """
    global _CACHE, _SAMPLER
    with _LOCK:
        if _CACHE is not None and not refresh and (_CACHE.caps.rlimit_as_enforced.value is not None or not probe):
            return _CACHE
        resource = _import_resource()
        rlimits = available_rlimits()
        startup_vm = Decided(None, "not probed")
        if "as" in rlimits and probe:
            as_enforced, startup_vm = _probe_rlimit_as()
        elif "as" in rlimits:
            as_enforced = Decided(None, "not probed")
        else:
            as_enforced = Decided(False, "RLIMIT_AS does not exist")
            startup_vm = Decided(None, "RLIMIT_AS does not exist, so no address-space floor is needed")
        sampler_decision, _SAMPLER = _decide_rss_sampler()
        tree = _decide_tree_kill()
        caps = Capabilities(
            resource_module=Decided(resource is not None, "import resource"),
            rlimits=Decided(rlimits, "hasattr(resource, RLIMIT_*) and getrlimit() answers"),
            rlimit_as_enforced=as_enforced,
            rss_sampler=sampler_decision,
            tree_kill=tree,
            hard_memory_cap=_decide_hard_cap(as_enforced, tree),
            cpu_limit=(
                Decided("rlimit_cpu", "RLIMIT_CPU exists")
                if "cpu" in rlimits
                else Decided("none", "no RLIMIT_CPU; the parent's wall clock still applies")
            ),
            nofollow=_decide_nofollow(),
            posix_permissions=_probe_posix_permissions(),
            startup_vm_bytes=startup_vm,
        )
        memory, memory_how = _physical_memory()
        page, page_how = _page_size()
        machine = platform.machine()
        _CACHE = HostProfile(
            os_family=platform.system().lower() or "unknown",
            os_release=platform.release(),
            arch=_normalise_arch(machine),
            machine=machine,
            python_implementation=platform.python_implementation(),
            python_version=platform.python_version(),
            cpu_count=os.process_cpu_count(),
            memory_bytes=memory,
            memory_how=memory_how,
            page_size=page,
            page_size_how=page_how,
            caps=caps,
        )
        return _CACHE


def host_rss_sampler(profile: HostProfile) -> Callable[[int], int | None] | None:
    """The sampler chosen for ``profile`` (None when the capability is ``none``)."""
    kind = str(profile.caps.rss_sampler.value)
    if kind == "none":
        return None
    return make_rss_sampler(kind)


# ---------------------------------------------------------------------------------------------------------------
# Constants and grade (pure)
# ---------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HostConstants:
    """Everything the pool derives from a profile. ``margin_for`` and ``trigger_for`` are pure."""

    hard_memory_cap: str
    watchdog_interval_s: float
    alloc_rate_bytes_per_s: float
    rate_source: str  # calibrated | default | not needed
    safety_factor: float
    default_workers: int
    rss_cap_bytes: int
    grade: str
    grade_reasons: tuple[str, ...]
    startup_vm_bytes: int | None = None  # measured worker start-up address space (None: not measured or not needed)
    as_floor_bytes: int = 0  # the lowest RLIMIT_AS a worker may be given (0: no floor)

    def as_limit_for(self, requested: int) -> int:
        """The ``RLIMIT_AS`` actually given for a requested one: ``0`` stays ``0`` (disabled); otherwise never below the
        floor (``startup_vm + AS_STARTUP_HEADROOM``), so a worker cannot be killed by a cap that is under what the
        interpreter needs to start on this host."""
        return max(requested, self.as_floor_bytes) if requested > 0 else 0

    def margin_for(self, cap: int) -> int:
        """Bytes below ``cap`` at which the watchdog kills: ``rate * interval * safety``, clamped to
        ``[32 MiB, cap / 2]``; zero when a hard cap is enforced (the watchdog is then only a backstop at the cap).
        """
        if self.hard_memory_cap != "none":
            return 0
        raw = self.alloc_rate_bytes_per_s * self.watchdog_interval_s * self.safety_factor
        return int(min(max(raw, MIN_MARGIN), cap // 2))

    def trigger_for(self, cap: int) -> int:
        return cap - self.margin_for(cap)

    def to_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["grade_reasons"] = list(self.grade_reasons)
        record["rss_margin_bytes"] = self.margin_for(self.rss_cap_bytes)
        record["rss_trigger_bytes"] = self.trigger_for(self.rss_cap_bytes)
        return record


def select_grade(profile: HostProfile, calibration: Calibration | None) -> tuple[str, tuple[str, ...]]:
    """Isolation grade and the reasons it is not better.

    ``enforced``: a hard memory cap and tree kill (the parent's wall clock always applies).
    ``watchdog``: an RSS sampler, tree kill and a calibration that ran.
    ``degraded``: anything less.
    """
    caps = profile.caps
    tree = caps.tree_kill.value != "none"
    hard = caps.hard_memory_cap.value != "none"
    if tree and hard:
        return "enforced", ()
    reasons: list[str] = []
    if not tree:
        reasons.append("no process-tree kill")
    if not hard:
        if caps.rss_sampler.value == "none":
            reasons.append("no hard memory cap and no RSS sampler")
        elif calibration is None or calibration.status != "ok":
            reasons.append(f"watchdog not calibrated ({'not run' if calibration is None else calibration.status})")
    if not reasons:
        return "watchdog", ()
    return "degraded", tuple(reasons)


def constants_for(
    profile: HostProfile,
    calibration: Calibration | None = None,
    *,
    rss_cap_bytes: int = DEFAULT_RSS_CAP,
) -> HostConstants:
    """Derive the constants from capabilities. Pure and deterministic; no operating-system names.

    ===========================  ========================================  =====================================
    constant                     rule                                      rationale (measured, arm64 macOS)
    ===========================  ========================================  =====================================
    watchdog interval            0.1 s if ``hard_memory_cap`` is not       with a hard cap the sampler only
                                 ``none``; else 0.02 s                     backstops; without one the polling
                                                                           period bounds the overshoot (native
                                                                           libproc sampler, 12 GiB/s hog, trigger
                                                                           256 MiB): sample over trigger ~1.05
                                                                           GiB at 100 ms, ~85 MiB at 20 ms; a
                                                                           1.3 GiB/s hog ~62 MiB at 100 ms, ~24
                                                                           MiB at 20 ms (spawned-``ps`` sampler,
                                                                           now removed: ~146 / ~44 MiB)
    allocation rate              calibrated rate, else 4 GiB/s             calibration measured 11.9-12.3 GiB/s
                                                                           (M2 Max) and 15.8-16.8 GiB/s (M5 Ultra,
                                                                           D-825), arm64 macOS, 256 MiB in ~15-20 ms
    safety factor                2.0                                       sampling latency and rate variance
    margin                       0 with a hard cap; else                   trigger = cap - margin keeps the
                                 clamp(rate*interval*safety,               transient peak under the cap
                                 32 MiB, cap/2)
    interval lowering            while margin > cap/2 and interval > 10 ms  a slow-cap, fast-allocation host
                                 halve the interval (floor 10 ms)           polls faster instead of killing at
                                                                           half the cap
    default workers              min(cpus, floor(0.75*memory/cap)), >= 1   N watchdog caps must not together
                                                                           exhaust the host (G.4.3)
    RLIMIT_AS floor              startup_vm + 256 MiB when ``rlimit_as``    a fixed cap can sit under what the
                                 is the hard cap and ``startup_vm_bytes``   interpreter needs to start (observed:
                                 was measured, else none                    1 GiB too low on arm64 Linux, G.4.12)
    ===========================  ========================================  =====================================
    """
    hard = str(profile.caps.hard_memory_cap.value)
    interval: float = INTERVAL_HARD_CAP if hard != "none" else INTERVAL_SOFT_CAP
    rate: float
    if hard != "none":
        rate, source = float(DEFAULT_ALLOC_RATE), "not needed"
    elif calibration is not None and calibration.status == "ok" and calibration.alloc_rate_bytes_per_s:
        rate, source = float(calibration.alloc_rate_bytes_per_s), "calibrated"
    else:
        rate, source = float(DEFAULT_ALLOC_RATE), "default"
    if hard == "none":
        while rate * interval * SAFETY_FACTOR > rss_cap_bytes // 2 and interval > INTERVAL_FLOOR:
            interval = max(INTERVAL_FLOOR, interval / 2)
    cpus = profile.cpu_count or 1
    if profile.memory_bytes:
        by_memory = int(USABLE_MEMORY_FRACTION * profile.memory_bytes) // max(rss_cap_bytes, 1)
        workers = min(cpus, by_memory)
    else:
        workers = cpus
    grade, reasons = select_grade(profile, calibration)
    startup_vm = profile.caps.startup_vm_bytes.value
    vm = startup_vm if isinstance(startup_vm, int) and not isinstance(startup_vm, bool) and startup_vm > 0 else None
    as_floor = vm + AS_STARTUP_HEADROOM if vm is not None and profile.caps.hard_memory_cap.value == "rlimit_as" else 0
    return HostConstants(
        hard_memory_cap=hard,
        watchdog_interval_s=interval,
        alloc_rate_bytes_per_s=rate,
        rate_source=source,
        safety_factor=SAFETY_FACTOR,
        default_workers=max(1, workers),
        rss_cap_bytes=rss_cap_bytes,
        grade=grade,
        grade_reasons=reasons,
        startup_vm_bytes=vm,
        as_floor_bytes=as_floor,
    )


def minimal_environment(job_dir: str, parent_environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The explicit environment of a child process (G.4.2). Nothing is inherited.

    ``SYSTEMROOT`` is copied only if the parent has it (the Windows loader needs it); on such hosts ``TEMP``,
    ``TMP`` and ``USERPROFILE`` are redirected to the private directory as well.
    """
    parent = os.environ if parent_environ is None else parent_environ
    env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "HOME": job_dir, "TMPDIR": job_dir}
    system_root = parent.get("SYSTEMROOT")
    if system_root:
        env["SYSTEMROOT"] = system_root
        env["PATH"] = os.path.join(system_root, "System32")
        env.update({"TEMP": job_dir, "TMP": job_dir, "USERPROFILE": job_dir})
    else:
        env["PATH"] = "/usr/bin:/bin"
    return env
