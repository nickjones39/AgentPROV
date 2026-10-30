"""An archive stored as byte parts, read as one logical file in the declared order (docs/architecture G.3.5; D-243).

Some deposits cut one zip into fixed-size byte parts (``split -b``; for example ``x.zip.part-0000`` ...). The parts are
stored as separate raw objects, each pinned by its own digest. :class:`PartsView` presents them as one read-only,
seekable binary file **in the order the caller declares**, which comes from the profile or pin with each part's digest
and size; nothing here derives an order from names, and nothing is copied or written: reads go to the parts' handles.

:func:`check_split_declaration` is the declaration gate (``ingest.archive.parts``): at least two and at most
``max_split_parts`` parts, no empty part, each handle exactly its declared size, and a logical size of at most
``max_split_bytes``. A part that is reordered, missing, repeated by mistake or truncated passes this gate only if the sizes
still agree; the zip structure checks of :mod:`agentprov.ingest.archives` then refuse the logical bytes, and the container
identity (the split descriptor of :mod:`agentprov.raw.members`) differs in any case.
"""

from __future__ import annotations

import bisect
import io
from collections.abc import Sequence
from typing import IO

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

__all__ = ["PartsView", "check_split_declaration"]


def _parts_error(reason: str, **kwargs: int) -> IngestError:
    return IngestError("ingest.archive.parts", reason, **kwargs)


def check_split_declaration(parts: Sequence[IO[bytes]], sizes: Sequence[int], limits: IngestLimits) -> None:
    """Refuse a malformed part declaration before any part is read (``ingest.archive.parts``)."""
    if len(parts) != len(sizes):
        raise ValueError("one declared size per part")
    if len(parts) < 2:
        raise _parts_error("a split archive has at least two parts")
    if len(parts) > limits.max_split_parts:
        raise _parts_error(f"{len(parts)} parts exceed the limit", limit=limits.max_split_parts)
    total = 0
    for index, (handle, size) in enumerate(zip(parts, sizes, strict=True)):
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise _parts_error(f"part {index} has no positive declared size")
        actual = handle.seek(0, io.SEEK_END)
        if actual != size:
            raise _parts_error(f"part {index} is {actual} bytes, declared {size}")
        total += size
        if total > limits.max_split_bytes:
            raise _parts_error("the parts exceed max_split_bytes", limit=limits.max_split_bytes)


class PartsView(io.RawIOBase):
    """The concatenation of ``parts`` in the given order, read-only and seekable; the handles stay the caller's.

    ``read(n)`` returns ``n`` bytes unless the end is reached (a read that crosses a part boundary continues in the next
    part), so ``zipfile`` sees an ordinary file. A part that returns fewer bytes than its declared size is
    ``ingest.stream.truncated`` (the declaration gate checked the sizes; this catches a part that changes after it).
    """

    def __init__(self, parts: Sequence[IO[bytes]], sizes: Sequence[int]) -> None:
        super().__init__()
        if len(parts) != len(sizes) or not parts:
            raise ValueError("one declared size per part, at least one part")
        self._parts = tuple(parts)
        self._starts: list[int] = []
        total = 0
        for size in sizes:
            self._starts.append(total)
            total += size
        self._sizes = tuple(sizes)
        self._size = total
        self._pos = 0

    @property
    def size(self) -> int:
        return self._size

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self._pos + offset
        elif whence == io.SEEK_END:
            pos = self._size + offset
        else:
            raise ValueError("invalid whence")
        if pos < 0:
            raise ValueError("negative seek position")
        self._pos = pos
        return pos

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        view = memoryview(buffer).cast("B")
        done = 0
        while done < len(view) and self._pos < self._size:
            index = bisect.bisect_right(self._starts, self._pos) - 1
            within = self._pos - self._starts[index]
            want = min(len(view) - done, self._sizes[index] - within)
            handle = self._parts[index]
            handle.seek(within)
            got = handle.readinto(view[done : done + want])  # type: ignore[attr-defined]
            if not got:
                raise IngestError("ingest.stream.truncated", f"part {index} is shorter than declared")
            done += got
            self._pos += got
        return done

    def read(self, size: int | None = -1) -> bytes:
        if size is None or size < 0:
            size = max(self._size - self._pos, 0)
        buffer = bytearray(min(size, max(self._size - self._pos, 0)))
        n = self.readinto(buffer)
        return bytes(buffer[:n])

    def readall(self) -> bytes:
        return self.read(-1)
