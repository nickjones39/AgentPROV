"""G5 packaging, statically (design §13, macos-design §8): no bundle is built here (gui/tools/build_bundle.py builds and
checks one). The licence texts are the canonical ones, the notices are current, the spec excludes what §13 lists, and
the frozen entry dispatches the two helper flags before Qt is imported."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI / "tools"))

import build_bundle  # noqa: E402
import gen_notices  # noqa: E402


def test_the_licence_texts_are_canonical() -> None:
    for name, digest in build_bundle.LICENCES.items():
        assert hashlib.sha256((GUI / "packaging" / "licenses" / name).read_bytes()).hexdigest() == digest, name


@pytest.mark.skipif(sys.platform != "darwin", reason="the notices are generated on macOS (platform-specific packages)")
def test_the_notices_are_current() -> None:
    assert gen_notices.main(["--check"]) == 0
    text = (GUI / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "LGPL-3.0-only" in text and "linked dynamically" in text and "Corresponding source" in text


def test_the_spec_excludes_what_the_design_bans() -> None:
    spec = (GUI / "packaging" / "agentprov-gui.spec").read_text(encoding="utf-8")
    for module in ("QtWebEngineCore", "QtQuick", "QtQml", "QtNetwork", "QtMultimedia", "Qt3DCore", "QtPdf"):
        assert f'"PySide6.{module}"' in spec, module
    assert "one-file" not in spec.replace("never one-file", "") and "COLLECT(" in spec  # one-folder (LGPL relinking)
    assert "entitlements_file=None" in spec and "codesign_identity=None" in spec


def test_the_excluded_check_catches_a_banned_library(tmp_path: Path) -> None:
    lib = tmp_path / "Contents" / "Frameworks" / "PySide6" / "Qt" / "lib" / "QtNetwork.framework"
    lib.mkdir(parents=True)
    (tmp_path / "Contents" / "Frameworks" / "QtCore.framework").mkdir()
    assert build_bundle.check_excluded(tmp_path) == ["Contents/Frameworks/PySide6/Qt/lib/QtNetwork.framework"]


def test_the_frozen_entry_dispatches_the_helpers(tmp_path: Path) -> None:
    entry = GUI / "packaging" / "entry.py"
    preview = subprocess.run([sys.executable, str(entry), "--preview-helper", str(tmp_path)], input=b"",
                             capture_output=True, timeout=60, check=False)
    assert preview.returncode == 0


def test_signing_is_ad_hoc_unless_an_identity_is_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """D-657: no Developer ID is bought; the signing step runs codesign only for an explicit --sign-identity."""
    calls: list[list[str]] = []
    monkeypatch.setattr(build_bundle, "_sh", lambda argv, **_k: calls.append(argv) or
                        subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(build_bundle.sys, "platform", "darwin")
    assert build_bundle.sign(tmp_path, None).startswith("ad hoc") and calls == []
    assert build_bundle.sign(tmp_path, "Developer ID Application: X") == "signed"
    assert calls[0][:2] == ["codesign", "--force"] and "runtime" in calls[0] and "Developer ID Application: X" in calls[0]
