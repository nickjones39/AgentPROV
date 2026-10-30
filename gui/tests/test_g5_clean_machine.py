"""G5 clean-machine driver (D-860..D-867) without a VM: the pins, the Lima config's isolation, the image digest check,
the per-run deletion rule (D-862), the XWD screenshot conversion and the Linux bundle packing."""

from __future__ import annotations

import io
import json
import struct
import sys
import tarfile
import zlib
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI / "tools" / "clean_machine"))

import driver as d  # noqa: E402


def test_pins_are_complete_and_digest_pinned() -> None:
    pins = d.load_pins()
    pin = d.platform_pin(pins, "linux-arm64")
    assert pin["digest"].startswith("sha256:") and len(pin["digest"]) == 71
    assert pin["image"].startswith("https://cloud-images.ubuntu.com/releases/noble/release-")
    assert pins["tools"]["lima"] == "2.2.1"
    with pytest.raises(SystemExit):
        d.platform_pin(pins, "no-such-platform")


def test_pins_refuse_a_missing_field(tmp_path: Path) -> None:
    bad = tmp_path / "pins.toml"
    bad.write_text('[platform.x]\ntool = "lima"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="lacks"):
        d.load_pins(bad)


def test_lima_config_isolates_the_guest() -> None:
    pin = d.platform_pin(d.load_pins(), "linux-arm64")
    text = d.lima_config(pin, Path("/images/x.img"))
    for line in ("plain: true", "mounts: []", "portForwards: []", "loadDotSSHPubKeys: false", "forwardAgent: false",
                 "name: agentprov", f'digest: "{pin["digest"]}"', "vmType: vz"):
        assert line in text
    assert "[ -f /var/lib/agentprov-g5-base ] && exit 0" in text  # clones boot without the network
    for package in pin["prerequisites"] + pin["harness"]:
        assert package in text


def test_lima_config_refuses_odd_package_names() -> None:
    pin = d.platform_pin(d.load_pins(), "linux-arm64")
    pin["harness"] = ["xvfb; curl evil"]
    with pytest.raises(SystemExit, match="package name"):
        d.lima_config(pin, Path("/images/x.img"))


def _pin(data: bytes) -> dict[str, str]:
    import hashlib

    return {"image": "https://example.invalid/x.img", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}


def test_fetch_image_checks_the_digest(tmp_path: Path) -> None:
    data = b"image bytes" * 1000
    got = d.fetch_image(_pin(data), tmp_path, opener=lambda url: io.BytesIO(data))
    assert got.read_bytes() == data and got.name.endswith(".img")
    assert d.fetch_image(_pin(data), tmp_path, opener=lambda url: pytest.fail("downloaded twice")) == got


def test_fetch_image_refuses_a_mismatch(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not the pinned"):
        d.fetch_image(_pin(b"expected"), tmp_path, opener=lambda url: io.BytesIO(b"something else"))
    assert not list(tmp_path.glob("*.img"))  # only the .part stays, for a look


def test_fetch_image_refuses_a_non_https_pin(tmp_path: Path) -> None:
    pin = _pin(b"x") | {"image": "http://example.invalid/x.img"}
    with pytest.raises(SystemExit, match="https"):
        d.fetch_image(pin, tmp_path, opener=lambda url: io.BytesIO(b"x"))


def _marker(tmp_path: Path, vm: str, **doc: object) -> Path:
    path = tmp_path / vm / d.MARKER
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"name": vm, "tool": "agentprov-g5-driver"} | doc), encoding="utf-8")
    return path


def test_only_a_marked_per_run_clone_may_be_deleted(tmp_path: Path) -> None:
    name = d.vm_name("run", d.utc_now())
    assert d.may_delete(name, _marker(tmp_path, name))
    base = d.base_name("linux-arm64")
    assert not d.may_delete(base, _marker(tmp_path, base))  # a base, even with a marker
    assert not d.may_delete("default", _marker(tmp_path, "default"))  # not this tool's prefix
    other = d.vm_name("run", d.utc_now()) + "x"
    assert not d.may_delete(other, _marker(tmp_path, other, name="someone-else"))  # the marker names another VM
    assert not d.may_delete(name + "-y", tmp_path / "missing" / d.MARKER)  # no marker


def _xwd(width: int, height: int, pixels: list[tuple[int, int, int]], byte_order: int) -> bytes:
    name = b"root\x00"
    header_size = 100 + len(name)
    bytes_per_line = width * 4
    header = struct.pack(">25I", header_size, 7, 2, 24, width, height, 0, byte_order, 32, byte_order, 32, 32,
                         bytes_per_line, 4, 0xFF0000, 0x00FF00, 0x0000FF, 8, 256, 0, width, height, 0, 0, 0)
    body = b"".join((struct.pack("<I" if byte_order == 0 else ">I", (r << 16) | (g << 8) | b)) for r, g, b in pixels)
    return header + name + body


def _png_pixels(png: bytes) -> tuple[int, int, bytes]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    idat = png.index(b"IDAT")
    length = struct.unpack(">I", png[idat - 4:idat])[0]
    raw = zlib.decompress(png[idat + 4: idat + 4 + length])
    rows = [raw[y * (width * 3 + 1) + 1:(y + 1) * (width * 3 + 1)] for y in range(height)]
    return width, height, b"".join(rows)


@pytest.mark.parametrize("byte_order", [0, 1])
def test_xwd_to_png(byte_order: int) -> None:
    pixels = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]
    w, h, rgb = _png_pixels(d.xwd_to_png(_xwd(2, 2, pixels, byte_order)))
    assert (w, h) == (2, 2)
    assert rgb == bytes(c for p in pixels for c in p)


def test_xwd_refuses_other_formats() -> None:
    data = bytearray(_xwd(1, 1, [(1, 2, 3)], 0))
    data[8:12] = struct.pack(">I", 1)  # XYPixmap
    with pytest.raises(ValueError, match="unsupported"):
        d.xwd_to_png(bytes(data))
    with pytest.raises(ValueError, match="truncated"):
        d.xwd_to_png(_xwd(4, 4, [(0, 0, 0)], 0))


def test_bundle_tar_packs_a_folder_and_passes_a_tarball(tmp_path: Path) -> None:
    folder = tmp_path / "dist" / "AgentPROV"
    (folder / "_internal").mkdir(parents=True)
    exe = folder / "AgentPROV"
    exe.write_bytes(b"\x7fELF")
    exe.chmod(0o755)
    packed = d.bundle_tar(folder, tmp_path)
    with tarfile.open(packed) as tf:
        member = tf.getmember("AgentPROV/AgentPROV")
        assert member.mode & 0o111
    assert d.bundle_tar(packed, tmp_path / "unused") == packed
    with pytest.raises(SystemExit, match="not a Linux bundle"):
        d.bundle_tar(tmp_path / "dist", tmp_path)


def test_a_build_clone_is_a_per_run_clone(tmp_path: Path) -> None:
    name = d.vm_name("build", d.utc_now())
    assert d.may_delete(name, _marker(tmp_path, name))


def test_fetch_pinned_names_by_digest_and_suffix(tmp_path: Path) -> None:
    data = b"uv binary"
    pin = _pin(data)
    got = d.fetch_pinned(pin["image"], pin["digest"], tmp_path, ".tar.gz", opener=lambda url: io.BytesIO(data))
    assert got.name == pin["digest"].removeprefix("sha256:") + ".tar.gz"


def test_build_pins_point_at_a_pinned_uv() -> None:
    build = d.platform_pin(d.load_pins(), "linux-arm64")["build"]
    assert build["uv_url"].startswith("https://github.com/astral-sh/uv/releases/download/" + build["uv_version"] + "/")
    assert build["uv_digest"].startswith("sha256:") and len(build["uv_digest"]) == 71


def test_vm_names_fit_lima_socket_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Lima puts ``ssh.sock.<16 digits>`` in the instance folder, and a UNIX socket path has fewer than 104 bytes."""
    monkeypatch.setenv("AGENTPROV_HOME", "/Users/" + "u" * 20 + "/.agentprov")
    now = d.utc_now()
    for name in (d.vm_name("build", now), d.vm_name("run", now), d.base_name("linux-arm64")):
        d.check_name_length(name)
    monkeypatch.setenv("AGENTPROV_HOME", "/Users/" + "x" * 60 + "/.agentprov")
    with pytest.raises(SystemExit, match="too long"):
        d.check_name_length(d.vm_name("build", now))


def test_level_w_parses_the_keyring_script_output() -> None:
    sys.path.insert(0, str(GUI / "tools" / "clean_machine" / "guest"))
    import linux_w_steps as w

    out = '== status\n{"allowed": true}\n== exit 0\n== set\n== exit 0\n== list\n{"keys": []}\n== exit 2\nstray\n'
    assert w._sections(out) == [("status", '{"allowed": true}', "0"), ("set", "", "0"), ("list", '{"keys": []}', "2")]
    assert "not-a-key" in w.DUMMY and w.SCRIPT[-1]["reply"] == "text"


def test_level_w_is_a_run_option() -> None:
    with pytest.raises(SystemExit):
        d.main(["run", "linux-arm64", "--bundle", "x", "--level", "X"])


def _windows():  # type: ignore[no-untyped-def]
    import windows

    return windows


def test_windows_unattend_is_unactivated_and_escapes_the_password() -> None:
    import xml.dom.minidom

    w = _windows()
    text = w.autounattend("G5-a<b&c")
    doc = xml.dom.minidom.parseString(text)
    keys = doc.getElementsByTagName("Key")
    product = [k for k in keys if k.parentNode.tagName == "ProductKey"]
    assert product and all(not k.firstChild for k in product)  # no product key: unactivated (the user's choice)
    assert "<AcceptEula>true</AcceptEula>" in text and "G5-a&lt;b&amp;c" in text
    assert 'processorArchitecture="arm64"' in text and "BypassNRO" in text
    assert "LongPathsEnabled" not in text  # P-5's warning is tested
    pw = w.password()
    assert pw.startswith("G5-") and len(pw) == 23 and pw[3:].isalnum()


def test_windows_clone_deletion_needs_the_marker_in_its_notes() -> None:
    w = _windows()
    name = d.vm_name("run", d.utc_now())
    assert w.may_delete_utm(name, w.run_marker(name, "2026-10-28T00:00:00+00:00"))
    assert not w.may_delete_utm(w.BASE, w.run_marker(w.BASE, "x"))
    assert not w.may_delete_utm(name, "")
    assert not w.may_delete_utm(name, w.run_marker(name + "x", "x"))
    assert not w.may_delete_utm("Windows 11", w.run_marker("Windows 11", "x"))


def test_windows_pins_and_the_create_script() -> None:
    w = _windows()
    pin = d.platform_pin(d.load_pins(), "windows-arm64")
    assert pin["tool"] == "utm" and pin["digest"].startswith("sha256:") and len(pin["guest_tools_digest"]) == 71
    assert pin["build"]["uv_url"].endswith("uv-aarch64-pc-windows-msvc.zip")
    script = w.applescript_create("n", Path("/a.iso"), Path("/b.iso"), Path("/c.iso"), 6, 12288, 65536)
    assert 'architecture:"aarch64"' in script and "uefi:true" in script and "interface:NVMe" in script
    assert script.count("interface:USB") == 3 and 'hardware:"virtio-ramfb"' in script and "«class SrPt»" in script


def test_windows_steps_follow_the_d867_decisions() -> None:
    """User decision 2026-10-28 (D-867): steps 7-8 not applicable on Windows ARM64, step 6 on info and kill."""
    text = (GUI / "tools" / "clean_machine" / "guest" / "win_steps.ps1").read_text(encoding="utf-8")
    assert "applicable = $false" in text and "if (-not $LiveRuns)" in text  # 2026-10-29: x64 too
    assert "'jobs' 'follow'" not in text  # a job does not start jobs (jobs.argv.recursive)
    assert "$null = $proc.Handle" in text  # Start-Process reports the exit code only with the handle cached


def test_windows_x64_runs_on_the_same_base_with_the_x64_uv() -> None:
    pins = d.load_pins()
    x64, arm = d.platform_pin(pins, "windows-x64"), d.platform_pin(pins, "windows-arm64")
    assert x64["digest"] == arm["digest"]  # one base VM: x64 is Windows 11 ARM64's own emulation
    assert x64["build"]["uv_url"].endswith("uv-x86_64-pc-windows-msvc.zip") and "emulated" in x64["arch"]


def test_linux_x86_64_is_an_emulated_qemu_guest_on_the_22_04_floor() -> None:
    pin = d.platform_pin(d.load_pins(), "linux-x86_64")
    text = d.lima_config(pin, Path("/images/x.img"))
    assert "vmType: qemu" in text and "arch: x86_64" in text
    assert pin["glibc_floor"] == "2.35" and "jammy" in pin["image"] and float(pin["timeout_factor"]) > 1
    assert "vmType: vz" in d.lima_config(d.platform_pin(d.load_pins(), "linux-arm64"), Path("/images/y.img"))
