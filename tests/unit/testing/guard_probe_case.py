"""Not collected by the suite (no ``test_`` prefix): run by ``test_write_guard.py`` in a child pytest, so that the
repository's ``tests/conftest.py`` write guard (D-402) applies to it. ``GUARD_PROBE_MODE`` picks the operation."""

import os
from pathlib import Path


def test_probe_writes_its_target(tmp_path):
    target = Path(os.environ["GUARD_PROBE_TARGET"])
    mode = os.environ.get("GUARD_PROBE_MODE", "write")
    if mode == "write":
        target.write_text("probe", encoding="utf-8")
    elif mode == "through-symlink":  # BF-3: a symlink inside the test's tmp pointing at the target's directory
        link = tmp_path / "link"
        link.symlink_to(target.parent, target_is_directory=True)
        (link / target.name).write_text("probe", encoding="utf-8")
    elif mode == "mkdir-parents":  # BF-4: a regenerator makes its output's directory first
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("probe", encoding="utf-8")
    elif mode == "remove-symlink":  # removing a symlink in tmp that points outside touches only the link
        link = tmp_path / "link"
        link.symlink_to(target)
        link.unlink()
        assert target.exists()
    else:
        raise AssertionError(mode)
