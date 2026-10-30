"""D-554: the per-process memory reader of the admission controller (``host.footprint_reader``).

On macOS it reads ``proc_pid_rusage(RUSAGE_INFO_V4)``: the structure is declared field by field, so its size is the
SDK's 296 bytes, and a live child that allocates and touches 200 MiB shows it in ``phys_footprint`` and keeps it in the
lifetime maximum after freeing it. (Whether the current footprint falls after a free is the allocator's choice: macOS's
malloc often keeps the pages, which is why the controller counts idle workers at their sampled footprint.)
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time

import pytest

from agentprov import host

MIB = 1 << 20
CHILD = (
    "import sys, time\n"
    "b = bytearray(200 * 1024 * 1024)\n"
    "for i in range(0, len(b), 4096): b[i] = 1\n"
    "print('held', flush=True); sys.stdin.readline()\n"
    "del b\n"
    "print('freed', flush=True); sys.stdin.readline()\n"
)


def test_the_rusage_structure_has_the_sdk_layout() -> None:
    assert ctypes.sizeof(host._RusageInfoV4) == 16 + 35 * 8
    names = [name for name, _ in host._RusageInfoV4._fields_]
    assert names.index("ri_phys_footprint") - 1 == 7  # uint64 index after the 16-byte uuid
    assert names.index("ri_lifetime_max_phys_footprint") - 1 == 28
    assert names.index("ri_interval_max_phys_footprint") - 1 == 33


@pytest.mark.skipif(sys.platform != "darwin", reason="phys_footprint is a macOS counter")
def test_a_live_child_shows_its_footprint_and_keeps_its_lifetime_max() -> None:
    read = host.footprint_reader()
    assert read is not None
    child = subprocess.Popen([sys.executable, "-c", CHILD], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdin is not None
        assert child.stdout.readline().strip() == "held"
        held = read(child.pid)
        assert held is not None and held.metric == "phys_footprint"
        assert held.current >= 190 * MIB and held.lifetime_max is not None and held.lifetime_max >= held.current
        child.stdin.write("\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "freed"
        time.sleep(0.2)
        freed = read(child.pid)
        assert freed is not None and freed.lifetime_max is not None and freed.lifetime_max >= 190 * MIB
        assert freed.current <= freed.lifetime_max
        child.stdin.write("\n")
        child.stdin.flush()
    finally:
        child.wait(timeout=30)
    assert read(child.pid) is None  # a process that is gone reads as None
