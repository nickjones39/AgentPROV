"""BF-15 (D-461): a split archive at ``max_split_parts`` expands in a real worker, within its ``RLIMIT_NOFILE``.

The expand job holds every part open (D-243), and a worker may hold at most ``WorkerLimits().nofile`` descriptors (G.4.3).
``max_split_parts`` therefore stays under that limit with room for the worker's own descriptors. A job that still runs
out of descriptors reports ``worker.input.nofile``, never ``worker.input.missing``. Archives are built here.
"""

from __future__ import annotations

import io
import zipfile

from agentprov.ingest.limits import IngestLimits
from agentprov.io.workers import WorkerLimits, WorkerPool
from agentprov.raw.members import ContainerSpec, Selection, expand_containers, store_split_descriptor
from agentprov.raw.store import RawObjectStore

#: descriptors a worker holds besides the parts: stdio, the frame pipe, the split descriptor, store directories, imports
WORKER_RESERVE = 16


def _expand(tmp_path, n: int, limits: IngestLimits | None = None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("logs/a.json", b'{"k": 1}' + b" " * (n * 300))
    data = buf.getvalue()
    size = -(-len(data) // n)
    parts = [data[i : i + size] for i in range(0, len(data), size)]
    assert len(parts) == n
    store = RawObjectStore(tmp_path / "raw")
    declared = tuple((store.put(p, ext="bin").sha256, len(p)) for p in parts)
    sha = store_split_descriptor(store, declared)
    spec = ContainerSpec(sha, "snap", "logs.zip", (Selection(include=("logs/*",)),), parts=declared)
    return expand_containers(store, [spec], pool=WorkerPool(workers=1, store_root=store.objects_dir), limits=limits)


def test_the_part_limit_leaves_the_worker_room_under_its_open_file_limit():
    assert IngestLimits().max_split_parts + WORKER_RESERVE <= WorkerLimits().nofile


def test_a_split_archive_at_the_part_limit_expands_in_a_real_worker(tmp_path):
    out = _expand(tmp_path, IngestLimits().max_split_parts)
    assert [(r.label, r.disposition) for r in out.rows] == [("logs/a.json", "selected")], out.events


def test_running_out_of_descriptors_is_reported_as_such(tmp_path):
    n = WorkerLimits().nofile + 4  # only reachable with a raised part limit
    out = _expand(tmp_path, n, IngestLimits(max_split_parts=n))
    assert not out.rows
    (event,) = out.events
    assert event.code == "expand.failed" and "worker.input.nofile" in event.detail, event
