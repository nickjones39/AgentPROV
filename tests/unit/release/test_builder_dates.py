"""CB-19: the deposit builder refuses a release date ZIP cannot record, before it writes anything (H.10.4).

ZIP member timestamps end at 2107. A release date after it used to fail mid-build with ``struct.error`` (exit 70) after
the corpora were opened and verified, leaving a ``.partial`` tree. The CLI refuses it too; this is the builder's own
backstop for callers of the library. The last day ZIP can hold still builds.
"""

from __future__ import annotations

import zipfile
from datetime import date

import pytest
import release_support as rs

from agentprov.release.builder import DepositRefusedError


def test_a_release_date_after_2107_is_refused_before_anything_is_written(tmp_path_factory, tmp_path):
    mit = rs.sealed(tmp_path_factory, tmp_path / "corpora", "mini-mit")
    out = tmp_path / "deposit"
    with pytest.raises(DepositRefusedError) as refused:
        rs.build([mit], out, release_date=date(2108, 1, 1))
    assert refused.value.code == "release.usage" and refused.value.exit_code == 2
    assert not out.exists() and not out.with_name(out.name + ".partial").exists()
    rs.build([mit], tmp_path / "last", release_date=date(2107, 12, 31))
    with zipfile.ZipFile(tmp_path / "last" / "mini-mit-v0.1.0.meta.zip") as zf:
        assert {i.date_time for i in zf.infolist()} == {(2107, 12, 31, 0, 0, 0)}
