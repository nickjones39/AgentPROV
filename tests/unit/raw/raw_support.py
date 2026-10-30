"""Deterministic zip builders shared by the raw-store and corpus tests (imported as ``raw_support``)."""

from __future__ import annotations

import io
import stat
import warnings
import zipfile


def build_zip(members, *, method: int = zipfile.ZIP_DEFLATED) -> bytes:
    """A deterministic zip: ``members`` is a list of ``(name_or_ZipInfo, bytes)``; dates are fixed."""
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in members:
                info = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.filename = info.orig_filename.split("\0", 1)[0]  # ZipInfo rewrites os.sep to "/" on some hosts
                if info.compress_type == zipfile.ZIP_STORED and not isinstance(name, zipfile.ZipInfo):
                    info.compress_type = method
                z.writestr(info, data)
    return buf.getvalue()


def symlink_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info
