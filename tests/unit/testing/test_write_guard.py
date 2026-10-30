"""The D-402 write guard of ``tests/conftest.py``: a write outside the test's temporary directories is refused and the
test fails; ``AGENTPROV_TEST_WRITE_ALLOW`` lets a deliberate run write exactly the paths it names (regenerators).

The probe runs in a child pytest with its own basetemp and private TMPDIR, so this test's ``tmp_path`` is outside the
child's temporary directories."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).with_name("guard_probe_case.py")


def _probe(tmp_path: Path, target: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environ = {k: v for k, v in os.environ.items() if k != "AGENTPROV_TEST_WRITE_ALLOW"}
    environ.update(GUARD_PROBE_TARGET=str(target), AGENTPROV_TEST_WRITE_GUARD="enforce", **env)
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
                           "--basetemp", str(tmp_path / "child-basetemp"), str(PROBE)],
                          cwd=REPO, env=environ, capture_output=True, text=True, timeout=300)


def test_a_write_outside_the_temporary_directories_is_refused_and_fails(tmp_path: Path) -> None:
    target = tmp_path / "outside" / "pin.txt"
    target.parent.mkdir()
    done = _probe(tmp_path, target)
    assert done.returncode == 1, done.stdout[-2000:]
    assert "D-402" in done.stdout and not target.exists()


def test_write_allow_admits_exactly_the_named_path(tmp_path: Path) -> None:
    target = tmp_path / "outside" / "pin.txt"
    target.parent.mkdir()
    done = _probe(tmp_path, target, AGENTPROV_TEST_WRITE_ALLOW=str(target))
    assert done.returncode == 0, done.stdout[-2000:]
    assert target.read_text(encoding="utf-8") == "probe"
    sibling = tmp_path / "outside" / "other.txt"  # the allowance is the named file only
    done = _probe(tmp_path, sibling, AGENTPROV_TEST_WRITE_ALLOW=str(target))
    assert done.returncode == 1 and not sibling.exists()


def test_an_allowed_file_admits_its_atomic_write_temporaries_only(tmp_path: Path) -> None:
    """``<file>.<anything>`` (the temporary of a write-then-replace) is admitted with ``<file>``; ``<file>X`` is not."""
    allowed = tmp_path / "outside" / "pin.txt"
    allowed.parent.mkdir()
    temporary = allowed.with_name("pin.txt.tmp-4711")
    done = _probe(tmp_path, temporary, AGENTPROV_TEST_WRITE_ALLOW=str(allowed))
    assert done.returncode == 0 and temporary.read_text(encoding="utf-8") == "probe", done.stdout[-2000:]
    lookalike = allowed.with_name("pin.txtX")
    done = _probe(tmp_path, lookalike, AGENTPROV_TEST_WRITE_ALLOW=str(allowed))
    assert done.returncode == 1 and not lookalike.exists()


def test_bf3_a_symlink_inside_the_temporary_directory_does_not_let_a_write_out(tmp_path: Path) -> None:
    """The guard checks the path the write really reaches, not the path as written."""
    target = tmp_path / "outside" / "pin.txt"
    target.parent.mkdir()
    done = _probe(tmp_path, target, GUARD_PROBE_MODE="through-symlink")
    assert done.returncode == 1 and "D-402" in done.stdout and not target.exists(), done.stdout[-2000:]


def test_removing_a_symlink_inside_the_temporary_directory_is_not_a_write_outside(tmp_path: Path) -> None:
    """Removing, renaming or creating a directory entry resolves only its parent: the link's target is untouched."""
    target = tmp_path / "outside" / "pin.txt"
    target.parent.mkdir()
    target.write_text("keep", encoding="utf-8")
    done = _probe(tmp_path, target, GUARD_PROBE_MODE="remove-symlink")
    assert done.returncode == 0, done.stdout[-2000:]
    assert target.read_text(encoding="utf-8") == "keep"


def test_bf4_an_allowed_files_parents_may_be_made_existing_or_not(tmp_path: Path) -> None:
    existing = tmp_path / "outside" / "pin.txt"
    existing.parent.mkdir()
    done = _probe(tmp_path, existing, GUARD_PROBE_MODE="mkdir-parents", AGENTPROV_TEST_WRITE_ALLOW=str(existing))
    assert done.returncode == 0 and existing.read_text(encoding="utf-8") == "probe", done.stdout[-2000:]
    nested = tmp_path / "outside" / "new" / "deeper" / "pin.txt"
    done = _probe(tmp_path, nested, GUARD_PROBE_MODE="mkdir-parents", AGENTPROV_TEST_WRITE_ALLOW=str(nested))
    assert done.returncode == 0 and nested.read_text(encoding="utf-8") == "probe", done.stdout[-2000:]
    sibling_dir = tmp_path / "outside" / "elsewhere" / "pin.txt"  # parents of a file that is not allowed: refused
    done = _probe(tmp_path, sibling_dir, GUARD_PROBE_MODE="mkdir-parents", AGENTPROV_TEST_WRITE_ALLOW=str(nested))
    assert done.returncode == 1 and not sibling_dir.parent.exists()
