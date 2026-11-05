"""D-1065: SHA256SUMS, the signature rule (``ssh-keygen -Y verify``), and the bundle extractor's refusals."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import update_support as us  # noqa: E402

from agentprov.update import ALLOWED_SIGNERS  # noqa: E402
from agentprov.update import unpack as U  # noqa: E402
from agentprov.update import verify as V  # noqa: E402
from agentprov.update.releases import UpdateError  # noqa: E402

SSH_KEYGEN = shutil.which("ssh-keygen")
needs_ssh_keygen = pytest.mark.skipif(SSH_KEYGEN is None, reason="OpenSSH ssh-keygen is not installed")
#: A Linux or macOS bundle's modes (the executable bit, a cleared setuid bit) exist only on a POSIX file system: Windows
#: reports 0o666/0o444 by the read-only attribute and executability by extension, and installs only its own zip bundle.
posix_modes = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes; Windows installs its zip bundle")


# ---------------------------------------------------------------------------------------------- SHA256SUMS


def test_sha256sums_in_the_release_format() -> None:
    a, b = "a" * 64, "b" * 64
    assert V.parse_sums(f"{a}  AgentPROV-macos-arm64.dmg\n{b}  SHA256SUMS.sig\n".encode()) == {
        "AgentPROV-macos-arm64.dmg": a, "SHA256SUMS.sig": b}


@pytest.mark.parametrize("data", [
    b"", b"\n", ("a" * 64 + "  x").encode(), ("a" * 64 + " x\n").encode(), ("A" * 64 + "  x\n").encode(),
    ("a" * 64 + "  x\r\n").encode(), ("a" * 64 + "  ../x\n").encode(), ("a" * 64 + "  x\n" + "b" * 64 + "  x\n").encode(),
    ("a" * 64 + "  x\u00e9\n").encode(), b"x" * (V.SUMS_MAX_BYTES + 1),
])
def test_a_malformed_checksum_list_is_refused(data: bytes) -> None:
    with pytest.raises(UpdateError) as exc:
        V.parse_sums(data)
    assert exc.value.code == "update.verify.sums"


def test_the_shipped_allowed_signers_holds_public_keys_only() -> None:
    text = ALLOWED_SIGNERS.read_text(encoding="ascii")
    assert "PRIVATE KEY" not in text
    V.load_signers()  # parses (a key line that is not a key entry would raise)


def test_an_allowed_signers_file_with_private_key_text_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "signers"
    bad.write_text("-----BEGIN OPENSSH " + "PRIVATE KEY-----\n")  # split: no key-shaped literal in the repository
    with pytest.raises(UpdateError):
        V.load_signers(bad)
    bad.write_text("someone not-a-key\n")
    with pytest.raises(UpdateError):
        V.load_signers(bad)


def test_without_a_listed_key_the_check_is_the_checksum_alone(tmp_path: Path, no_keys: Path) -> None:
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("a" * 64 + "  x\n")
    got = V.verify_release(sums, None, signers=no_keys)
    assert got.to_json() == {"verification": "sha256", "signed_by": None}


def test_with_a_listed_key_an_unsigned_release_is_refused(tmp_path: Path) -> None:
    signers = tmp_path / "signers"
    signers.write_text('rel namespaces="file" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample rel\n')
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("a" * 64 + "  x\n")
    with pytest.raises(UpdateError) as exc:
        V.verify_release(sums, None, signers=signers)
    assert exc.value.code == "update.verify.unsigned"


def test_without_ssh_keygen_a_signed_check_is_an_environment_error(tmp_path: Path) -> None:
    signers = tmp_path / "signers"
    signers.write_text("rel ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample\n")
    (tmp_path / "s").write_text("x")
    (tmp_path / "s.sig").write_text("x")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(V.shutil, "which", lambda _name: None)
        with pytest.raises(UpdateError) as exc:
            V.verify_signature(tmp_path / "s", tmp_path / "s.sig", signers=signers)
    assert exc.value.exit_code == 3


def test_the_verify_argv_is_fixed(tmp_path: Path) -> None:
    signers = tmp_path / "signers"
    signers.write_text("first,second ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample\n")
    (tmp_path / "s").write_text("x")
    (tmp_path / "s.sig").write_text("x")
    calls: list[list[str]] = []

    def run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kw["stdin"] is not None and kw["check"] is False
        return subprocess.CompletedProcess(argv, 0 if "second" in argv else 255)

    assert V.verify_signature(tmp_path / "s", tmp_path / "s.sig", signers=signers, ssh_keygen="ssh-keygen",
                              run=run) == "second"
    assert calls[0] == ["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", "first", "-n", "file", "-s",
                        str(tmp_path / "s.sig")]


def _keypair(tmp_path: Path, name: str) -> tuple[Path, str]:
    key = tmp_path / name
    subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, key.with_suffix(".pub").read_text().strip()


def _sign(key: Path, sums: Path) -> Path:
    subprocess.run([SSH_KEYGEN, "-q", "-Y", "sign", "-f", str(key), "-n", "file", str(sums)], check=True,
                   capture_output=True)
    return sums.with_name(sums.name + ".sig")


@needs_ssh_keygen
def test_a_real_signature_verifies_and_a_wrong_one_is_refused(tmp_path: Path) -> None:
    key, pub = _keypair(tmp_path, "release")
    other, _ = _keypair(tmp_path, "other")
    signers = tmp_path / "allowed_signers"
    signers.write_text(f'agentprov-release namespaces="file" {pub}\n')
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("a" * 64 + "  AgentPROV-linux-x86_64.tar.gz\n")
    sig = _sign(key, sums)
    assert V.verify_release(sums, sig, signers=signers).to_json() == {"verification": "sha256+signature",
                                                                      "signed_by": "agentprov-release"}
    sums.write_text("b" * 64 + "  AgentPROV-linux-x86_64.tar.gz\n")  # the list changed after signing
    with pytest.raises(UpdateError) as exc:
        V.verify_release(sums, sig, signers=signers)
    assert exc.value.code == "update.verify.signature"
    sig.unlink()
    with pytest.raises(UpdateError):
        V.verify_release(sums, _sign(other, sums), signers=signers)  # signed, but not by a listed key


# ---------------------------------------------------------------------------------------------- the extractor


@posix_modes
def test_a_linux_bundle_unpacks_with_its_executable_bit_and_relative_link(tmp_path: Path) -> None:
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz")
    assert U.check_archive(archive, "linux-x86_64") == 5
    top = U.unpack(archive, tmp_path / "out", "linux-x86_64")
    exe = top / "AgentPROV"
    assert top == tmp_path / "out" / "AgentPROV" and exe.read_bytes().endswith(b"0.1.2\n")
    assert os.stat(exe).st_mode & 0o111 and not os.stat(top / "_internal" / "libx.so.1").st_mode & 0o111
    assert os.readlink(top / "_internal" / "libx.so") == "libx.so.1"


@pytest.mark.parametrize(("entry", "why"), [
    (us.tar_entry("AgentPROV/../../escape", data=b"x"), "'..'"),
    (us.tar_entry("/etc/passwd", data=b"x"), "absolute"),
    (us.tar_entry("C:/x", data=b"x"), "absolute"),
    (us.tar_entry("Elsewhere/x", data=b"x"), "outside the bundle folder"),
    (us.tar_entry("AgentPROV/a\\b", data=b"x"), "character"),
    (us.tar_entry("AgentPROV/hard", kind=tarfile.LNKTYPE, link="AgentPROV/AgentPROV"), "hard link"),
    (us.tar_entry("AgentPROV/fifo", kind=tarfile.FIFOTYPE), "hard link, device or FIFO"),
    (us.tar_entry("AgentPROV/agentprov", data=b"x"), "twice"),  # a case-insensitive file system collision
    (us.tar_entry("AgentPROV/abs", kind=tarfile.SYMTYPE, link="/etc/passwd"), "absolute"),
])
def test_a_hostile_tar_member_is_refused_before_anything_is_written(tmp_path: Path, entry, why: str) -> None:  # noqa: ANN001
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", extra=[entry])
    with pytest.raises(UpdateError, match=why):
        U.check_archive(archive, "linux-x86_64")
    with pytest.raises(UpdateError):
        U.unpack(archive, tmp_path / "out", "linux-x86_64")
    assert not (tmp_path / "out").exists() and not (tmp_path / "escape").exists()


def test_a_link_that_leaves_the_bundle_is_refused_and_nothing_is_left(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    extra = [us.tar_entry("AgentPROV/up", kind=tarfile.SYMTYPE, link="../.."),
             us.tar_entry("AgentPROV/_internal/chain", kind=tarfile.SYMTYPE, link="../up/outside")]
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", extra=extra)
    U.check_archive(archive, "linux-x86_64")  # the names are fine; where links lead is checked on disk
    with pytest.raises(UpdateError, match="outside"):
        U.unpack(archive, tmp_path / "out", "linux-x86_64")
    assert not (tmp_path / "out").exists() and outside.is_dir()


def test_a_member_below_a_link_is_refused(tmp_path: Path) -> None:
    extra = [us.tar_entry("AgentPROV/lnk", kind=tarfile.SYMTYPE, link="_internal"),
             us.tar_entry("AgentPROV/lnk/x", data=b"x")]
    with pytest.raises(UpdateError, match="below a link"):
        U.check_archive(us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", extra=extra), "linux-x86_64")


@posix_modes
def test_setuid_bits_are_never_kept(tmp_path: Path) -> None:
    extra = [us.tar_entry("AgentPROV/suid", data=b"x", mode=0o4755)]
    top = U.unpack(us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", extra=extra), tmp_path / "out",
                   "linux-x86_64")
    assert stat.S_IMODE(os.stat(top / "suid").st_mode) == 0o755


def test_a_windows_zip_unpacks_and_hostile_members_are_refused(tmp_path: Path) -> None:
    good = us.windows_zip(tmp_path / "AgentPROV-windows-x64.zip")
    top = U.unpack(good, tmp_path / "out", "windows-x64")
    assert (top / "AgentPROV.exe").read_bytes() == b"MZ 0.1.2"
    link = zipfile.ZipInfo("AgentPROV/link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    cases = [([(link, b"../../x")], "link"), ([("AgentPROV/../evil", b"x")], "'..'"),
             ([("Other/x", b"x")], "outside"), ([("AgentPROV/a:b", b"x")], "character")]
    for n, (extra, why) in enumerate(cases):
        (tmp_path / str(n)).mkdir()
        bad = us.windows_zip(tmp_path / str(n) / "AgentPROV-windows-x64.zip", extra=extra)
        with pytest.raises(UpdateError, match=why):
            U.check_archive(bad, "windows-x64")


def test_the_archive_must_be_this_platform_s_format(tmp_path: Path) -> None:
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz")
    with pytest.raises(UpdateError, match="format"):
        U.check_archive(archive, "windows-x64")
    with pytest.raises(UpdateError, match="format"):
        U.unpack(archive, tmp_path / "out", "macos-arm64")


def test_unpack_never_writes_into_an_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    with pytest.raises(FileExistsError):
        U.unpack(us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz"), tmp_path / "out", "linux-x86_64")


def test_a_disk_image_is_attached_read_only_copied_with_ditto_and_detached(tmp_path: Path) -> None:
    app = us.macos_app(tmp_path / "src")
    log: list[list[str]] = []
    dmg = tmp_path / "AgentPROV-macos-arm64.dmg"
    dmg.write_bytes(b"dmg")
    top = U.unpack(dmg, tmp_path / "out", "macos-arm64", run=us.dmg_run(app, log))
    assert (top / "Contents" / "MacOS" / "AgentPROV").is_file()
    assert os.readlink(top / "Contents" / "Frameworks" / "data.txt") == "../Resources/data.txt"
    assert [a[:2] for a in log] == [["hdiutil", "attach"], ["ditto", log[1][1]], ["hdiutil", "detach"]]
    assert "-readonly" in log[0] and "-nobrowse" in log[0]
    assert not (tmp_path / "out" / ".mnt").exists()


def test_a_disk_image_whose_app_links_outside_is_refused_and_detached(tmp_path: Path) -> None:
    app = us.macos_app(tmp_path / "src")
    (app / "Contents" / "evil").symlink_to("../../../elsewhere")  # leaves the app (inside the test folder)
    log: list[list[str]] = []
    dmg = tmp_path / "AgentPROV-macos-arm64.dmg"
    dmg.write_bytes(b"dmg")
    with pytest.raises(UpdateError, match="outside"):
        U.unpack(dmg, tmp_path / "out", "macos-arm64", run=us.dmg_run(app, log))
    assert log[-1][:2] == ["hdiutil", "detach"] and not any(a[0] == "ditto" for a in log)
    assert not (tmp_path / "out").exists()


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    p = tmp_path / "f"
    p.write_bytes(b"abc" * 1000)
    assert V.sha256_file(p) == hashlib.sha256(b"abc" * 1000).hexdigest()
