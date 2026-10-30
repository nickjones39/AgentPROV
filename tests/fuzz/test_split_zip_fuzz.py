"""K.11.1 over zips stored as byte parts (D-243): random cut points, part permutations and mutated parts give a typed
outcome only, and an intact declaration in the original order reads exactly the unsplit zip's members (F-1, F-2, F-3)."""

from __future__ import annotations

import io
import zipfile

from format_support import zip_bytes
from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.ingest.archives import iter_zip_members, open_split_zip
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits().replace(max_member_bytes=1 << 16, max_total_bytes=1 << 18, max_members=64, max_split_parts=16,
                                max_split_bytes=1 << 20)  # fmt: skip
MEMBERS = [("a/1.json", b'{"a": 1}' * 40), ("a/2.eval", bytes(range(256)) * 4), ("b.txt", b"x")]
ZIP = zip_bytes(MEMBERS, zipfile.ZIP_DEFLATED)


def _read(parts: list[bytes]) -> list[tuple[str | None, bytes | None]]:
    handles = [io.BytesIO(p) for p in parts]
    with open_split_zip(handles, [len(p) for p in parts], LIMITS, release=False) as z:
        return [(m.label, z.read_member(m) if m.disposition == "selected" else None)
                for m in iter_zip_members(z, None, LIMITS)]  # fmt: skip


def _cut(data: bytes, points: list[int]) -> list[bytes]:
    cuts = sorted({p % len(data) for p in points} - {0})
    return [data[a:b] for a, b in zip([0, *cuts], [*cuts, len(data)], strict=True)]


@budget(150)
@given(st.lists(st.integers(1, 1 << 16), min_size=1, max_size=10))
def test_any_cut_in_order_reads_the_unsplit_members(points: list[int]) -> None:
    parts = _cut(ZIP, points)
    if len(parts) < 2:
        return
    assert _read(parts) == [(n, d) for n, d in MEMBERS]


@budget(150)
@given(st.lists(st.integers(1, 1 << 16), min_size=1, max_size=6), st.randoms(use_true_random=False))
def test_permuted_parts_give_a_typed_outcome(points: list[int], rnd) -> None:
    parts = _cut(ZIP, points)
    rnd.shuffle(parts)
    kind, value = outcome(lambda: _read(parts))
    assert kind in ("ok", "ingest")
    if kind == "ok":  # only the identity order (or an order of identical parts) reads, and then exactly
        assert value == [(n, d) for n, d in MEMBERS]


@budget(150)
@given(byte_mutations(ZIP, max_ops=3), st.integers(1, 4096))
def test_mutated_parts_give_a_typed_outcome(mutated: bytes, size: int) -> None:
    parts = [mutated[i : i + size] for i in range(0, len(mutated), size)] or [b""]
    kind, _ = outcome(lambda: _read(parts))
    assert kind in ("ok", "ingest")
