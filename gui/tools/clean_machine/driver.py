"""G5 clean-machine tests: fresh VMs from pinned images run the §3 test plan of ``g5-cross-platform.md`` (D-860..D-867).

    uv run --project gui python gui/tools/clean_machine/driver.py base linux-arm64
    uv run --project gui python gui/tools/clean_machine/driver.py build linux-arm64 [--checkout REF]
    uv run --project gui python gui/tools/clean_machine/driver.py run linux-arm64 --bundle AgentPROV-linux-aarch64.tar.gz

Run both through ``tools/suite_queue.py --class import --cpu N --mem-gib M --`` on a shared machine (D-862).

**Base** (once per pin): downloads the pinned image into ``$AGENTPROV_HOME/vms/images/`` (checked against its sha256),
creates the VM with no host mount, no port forwarding and none of the host's SSH keys, installs the prerequisite and
harness packages, records their versions, and stops it. An existing base is never replaced: moving it to the Trash is
the user's call.

**Run** (one per test): clones the base to ``agentprov-g5-<platform>-<UTC>``, writes a marker file into the clone's
directory, copies in the bundle, the three-execution mini corpus and the guest script (``limactl copy``; never a key, a
``.env`` or a host directory), runs the steps, copies the results to ``$AGENTPROV_HOME/vms/results/<run>/`` and then
deletes the clone, even on failure (the user approved this per-run deletion, D-862). Only a VM with this tool's name
prefix, not a base, and with a marker naming it is deleted. ``--keep`` leaves it.

**Build** (D-865): builds the platform's bundle in a fresh clone (deleted afterwards like a run's) from a ``git archive``
of ``--checkout``, as ``.github/workflows/bundles.yml`` does on a runner; the package and its ``bundle-report.json``
land in ``$AGENTPROV_HOME/vms/builds/<build>/guest/``.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, BinaryIO

HERE = Path(__file__).resolve().parent
GUI = HERE.parent.parent
REPO = GUI.parent
PINS = HERE / "pins.toml"
PREFIX = "agentprov-g5-"
MARKER = "agentprov-g5-run.json"
GUEST_IN = "/tmp/g5-in"  # noqa: S108 - a path inside the throwaway guest, not on the host
GUEST_OUT = "/tmp/g5-out"  # noqa: S108 - likewise
_CHUNK = 1 << 20


def agentprov_home() -> Path:
    return Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")).expanduser()


def vms_dir() -> Path:
    return agentprov_home() / "vms"


def lima_home() -> Path:
    return vms_dir() / "lima"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def load_pins(path: Path = PINS) -> dict[str, Any]:
    pins = tomllib.loads(path.read_text(encoding="utf-8"))
    for name, pin in pins.get("platform", {}).items():
        missing = {"tool", "arch", "image", "digest", "cpus", "memory_gib", "disk_gib"} - pin.keys()
        if missing:
            raise SystemExit(f"pins.toml: platform {name} lacks {sorted(missing)}")
        if not str(pin["digest"]).startswith("sha256:") or len(pin["digest"]) != 71:
            raise SystemExit(f"pins.toml: platform {name}: digest is sha256:<64 hex>")
    return pins


def platform_pin(pins: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        return dict(pins["platform"][name])
    except KeyError:
        raise SystemExit(f"no pin for platform {name!r} (pins.toml)") from None


def base_name(platform: str) -> str:
    return f"{PREFIX}base-{platform}"


def vm_name(kind: str, now: dt.datetime) -> str:
    """A per-run clone's name: short, because Lima's SSH socket path (``$LIMA_HOME/<name>/ssh.sock.<16 digits>``)
    must stay under the 104-byte UNIX socket limit; the platform is in the marker and the results folder's name."""
    return f"{PREFIX}{ {'build': 'b', 'run': 'r'}[kind] }{now:%m%d%H%M%S}"


def label(platform: str, now: dt.datetime) -> str:
    """The results or builds folder of one run: ``<platform>-<UTC>``."""
    return f"{platform}-{now:%Y%m%dT%H%M%SZ}"


#: macOS's ``sun_path`` size; Lima refuses an instance whose ``ssh.sock.<16 digits>`` path reaches it
UNIX_PATH_MAX = 104


def check_name_length(name: str) -> None:
    sock = lima_home() / name / ("ssh.sock." + "0" * 16)
    if len(str(sock).encode()) >= UNIX_PATH_MAX:
        raise SystemExit(f"VM name {name!r} is too long for Lima's SSH socket under {lima_home()} "
                         f"({len(str(sock).encode())} of fewer than {UNIX_PATH_MAX} bytes); use a shorter AGENTPROV_HOME")


# -- images ---------------------------------------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _urlopen(url: str) -> BinaryIO:
    return urllib.request.urlopen(url, timeout=60)  # type: ignore[no-any-return]  # noqa: S310 - pinned https URL


def fetch_image(pin: dict[str, Any], dest: Path, opener: Callable[[str], BinaryIO] = _urlopen) -> Path:
    """The pinned image under ``dest``, named by its digest; downloaded once and refused unless the sha256 matches."""
    return fetch_pinned(pin["image"], pin["digest"], dest, ".img", opener)


def fetch_pinned(url: str, digest: str, dest: Path, suffix: str, opener: Callable[[str], BinaryIO] = _urlopen) -> Path:
    """A pinned download under ``dest``, named by its digest (``<sha256><suffix>``)."""
    want = digest.removeprefix("sha256:")
    target = dest / f"{want}{suffix}"
    if target.is_file():
        if _sha256(target) != want:
            raise SystemExit(f"{target} does not match its pinned digest; it is left as it is (look at it)")
        return target
    if not str(url).startswith("https://"):
        raise SystemExit("pins.toml: a download is an https URL")
    dest.mkdir(parents=True, exist_ok=True)
    part = dest / f"{want}.part"
    h = hashlib.sha256()
    with opener(url) as src, open(part, "wb") as out:
        while chunk := src.read(_CHUNK):
            h.update(chunk)
            out.write(chunk)
    if h.hexdigest() != want:
        raise SystemExit(f"downloaded image sha256 {h.hexdigest()} is not the pinned {want}; kept as {part}")
    os.replace(part, target)
    return target


# -- Lima -----------------------------------------------------------------------------------------------------------

def lima_config(pin: dict[str, Any], image: Path) -> str:
    """The base VM's Lima config: plain mode (no mounts, port forwards or containerd), the guest user ``agentprov``, no
    host SSH keys, and a provision script that installs the packages once (later boots of a clone stay offline)."""
    packages = " ".join(sorted({*pin.get("prerequisites", []), *pin.get("harness", [])}))
    if any(not p.replace("-", "").replace(".", "").replace("+", "").isalnum() for p in packages.split()):
        raise SystemExit("pins.toml: a package name has characters outside [A-Za-z0-9.+-]")
    return f"""# written by gui/tools/clean_machine/driver.py (D-862); do not edit
vmType: {pin.get("vm_type", "vz")}
arch: {pin["arch"]}
plain: true
images:
- location: {json.dumps(str(image))}
  arch: {pin["arch"]}
  digest: {json.dumps(pin["digest"])}
cpus: {int(pin["cpus"])}
memory: {int(pin["memory_gib"])}GiB
disk: {int(pin["disk_gib"])}GiB
mounts: []
portForwards: []
containerd:
  system: false
  user: false
ssh:
  loadDotSSHPubKeys: false
  forwardAgent: false
  forwardX11: false
user:
  name: agentprov
provision:
- mode: system
  script: |
    #!/bin/sh
    set -eu
    [ -f /var/lib/agentprov-g5-base ] && exit 0
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends {packages}
    touch /var/lib/agentprov-g5-base
"""


#: an emulated guest (``vm_type = "qemu"`` with another architecture) is several times slower; its pin's
#: ``timeout_factor`` stretches every limactl timeout (set by each command from the platform's pin)
TIMEOUT_FACTOR = 1.0


def limactl(*args: str, timeout: float = 1800, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LIMA_HOME": str(lima_home())}
    return subprocess.run(["limactl", *args], env=env, text=True, capture_output=capture, check=False,  # noqa: S603, S607 - fixed tool
                          timeout=timeout * TIMEOUT_FACTOR)


def _ok(done: subprocess.CompletedProcess[str], what: str) -> subprocess.CompletedProcess[str]:
    if done.returncode != 0:
        raise SystemExit(f"{what} failed (exit {done.returncode}): {(done.stderr or '')[-1500:]}")
    return done


def instances() -> dict[str, str]:
    """Instance name → status."""
    done = limactl("list", "--format", "{{.Name}} {{.Status}}")
    return dict(line.split(" ", 1) for line in done.stdout.splitlines() if " " in line) if done.returncode == 0 else {}


def marker_path(name: str) -> Path:
    return lima_home() / name / MARKER


def may_delete(name: str, marker: Path | None = None) -> bool:
    """D-862: only a per-run clone this tool created: the prefix, not a base, and a marker that names it."""
    if not name.startswith(PREFIX) or name.startswith(PREFIX + "base-"):
        return False
    marker = marker_path(name) if marker is None else marker
    try:
        doc = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("name") == name and doc.get("tool") == "agentprov-g5-driver"


def destroy(name: str) -> str:
    if not may_delete(name):
        return f"kept {name}: not a marked per-run clone"
    limactl("stop", "--force", name, timeout=300)
    done = limactl("delete", "--force", name, timeout=300)
    return f"deleted {name}" if done.returncode == 0 else f"delete of {name} failed: {done.stderr[-300:]}"


def package_versions(name: str, packages: list[str]) -> dict[str, str]:
    done = _ok(limactl("shell", name, "dpkg-query", "-W", "-f", "${Package} ${Version}\\n", *packages, timeout=120),
               "dpkg-query")
    return dict(line.split(" ", 1) for line in done.stdout.splitlines() if " " in line)


def cmd_base(args: argparse.Namespace) -> int:
    pin = platform_pin(load_pins(), args.platform)
    name = base_name(args.platform)
    if name in instances():
        raise SystemExit(f"{name} exists; a new base needs the user's OK to move the old one to the Trash first")
    check_name_length(name)
    image = fetch_image(pin, vms_dir() / "images")
    configs = vms_dir() / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    config = configs / f"{name}.yaml"
    config.write_text(lima_config(pin, image), encoding="utf-8")
    _ok(limactl("create", "--name", name, "--tty=false", str(config)), "limactl create")
    _ok(limactl("start", "--tty=false", f"--timeout={int(10 * TIMEOUT_FACTOR)}m", name, timeout=3600), "limactl start")
    packages = sorted({*pin.get("prerequisites", []), *pin.get("harness", [])})
    record = {"name": name, "platform": args.platform, "image": pin["image"], "digest": pin["digest"],
              "created_utc": utc_now().isoformat(), "lima": limactl("--version").stdout.strip(),
              "packages": package_versions(name, packages), "prerequisites": pin.get("prerequisites", []),
              "harness": pin.get("harness", [])}
    _ok(limactl("stop", name, timeout=600), "limactl stop")
    bases = vms_dir() / "bases"
    bases.mkdir(parents=True, exist_ok=True)
    (bases / f"{name}.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# -- inputs ---------------------------------------------------------------------------------------------------------

def mini_corpus_tar(dest: Path) -> Path:
    """The GUI tests' three-execution working corpus (the core's ``seal_support`` helper), as ``mini.tar.gz``."""
    support = REPO / "tests" / "unit" / "corpus"
    if str(support) not in sys.path:
        sys.path.insert(0, str(support))
    import seal_support

    class _Factory:
        def mktemp(self, name: str) -> Path:
            return Path(tempfile.mkdtemp(prefix=name, dir=dest))

    final = seal_support.working_corpus(_Factory(), dest / "corpus" / "mini")
    partial = final.with_name(final.name + ".partial")
    target = dest / "mini.tar.gz"
    with tarfile.open(target, "w:gz") as tf:
        tf.add(partial, arcname=partial.name)
    return target


def bundle_tar(bundle: Path, dest: Path) -> Path:
    """A Linux bundle as the user downloads it: the ``.tar.gz`` itself, or a ``AgentPROV`` folder packed into one."""
    if bundle.is_file() and bundle.name.endswith(".tar.gz"):
        return bundle
    if bundle.is_dir() and (bundle / "AgentPROV").is_file():
        target = dest / "AgentPROV-linux.tar.gz"
        with tarfile.open(target, "w:gz") as tf:
            tf.add(bundle, arcname="AgentPROV")
        return target
    raise SystemExit(f"{bundle}: not a Linux bundle (.tar.gz, or an AgentPROV folder with its executable)")


# -- screenshots ----------------------------------------------------------------------------------------------------

def _png(width: int, height: int, rgb_rows: list[bytes]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rgb_rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def xwd_to_png(data: bytes) -> bytes:
    """An ``xwd -root`` dump (ZPixmap, 24 or 32 bits per pixel, 8-bit channels) as a PNG; nothing else is accepted."""
    if len(data) < 100:
        raise ValueError("xwd: too short")
    h = struct.unpack(">25I", data[:100])
    header_size, version, fmt, _depth, width, height = h[0], h[1], h[2], h[3], h[4], h[5]
    byte_order, bpp, bytes_per_line, masks, ncolors = h[7], h[11], h[12], h[14:17], h[19]
    if version != 7 or fmt != 2 or bpp not in (24, 32) or not (0 < width <= 16384 and 0 < height <= 16384):
        raise ValueError(f"xwd: unsupported (version {version}, format {fmt}, {bpp} bpp, {width}x{height})")
    step = bpp // 8
    index = []
    for mask in masks:
        shift = (mask & -mask).bit_length() - 1
        if mask >> shift != 0xFF or shift % 8:
            raise ValueError(f"xwd: channel mask {mask:#x} is not one byte")
        index.append(shift // 8 if byte_order == 0 else step - 1 - shift // 8)
    start = header_size + ncolors * 12
    if len(data) < start + bytes_per_line * height:
        raise ValueError("xwd: truncated image")
    rows = []
    for y in range(height):
        row = data[start + y * bytes_per_line: start + y * bytes_per_line + width * step]
        rgb = bytearray(width * 3)
        for c in range(3):
            rgb[c::3] = row[index[c]::step]
        rows.append(bytes(rgb))
    return _png(width, height, rows)


# -- runs -----------------------------------------------------------------------------------------------------------

def _stopped_base(platform: str) -> str:
    base = base_name(platform)
    status = instances().get(base)
    if status is None:
        raise SystemExit(f"no base {base}: run `driver.py base {platform}` first")
    if status != "Stopped":
        raise SystemExit(f"{base} is {status}; a base must be stopped to be cloned")
    return base


@contextlib.contextmanager
def fresh_clone(base: str, name: str, now: dt.datetime, keep: bool, record: dict[str, Any]) -> Iterator[str]:
    """Clone ``base`` to ``name``, mark it as this tool's, start it and make the guest's in/out folders; afterwards
    delete it (D-862), even on failure, unless ``keep``. ``record["vm"]`` says what happened to it."""
    check_name_length(name)
    _ok(limactl("clone", "--tty=false", base, name, timeout=1800), "limactl clone")
    try:
        marker_path(name).write_text(json.dumps({"name": name, "tool": "agentprov-g5-driver",
                                                 "created_utc": now.isoformat()}), encoding="utf-8")
        _ok(limactl("start", "--tty=false", f"--timeout={int(10 * TIMEOUT_FACTOR)}m", name, timeout=1800),
            "limactl start")
        _ok(limactl("shell", name, "mkdir", "-p", GUEST_IN, GUEST_OUT), "mkdir")
        yield name
    finally:
        record["vm"] = destroy(name) if not keep else f"kept {name} (--keep)"


def copy_in(name: str, *files: Path) -> None:
    for src in files:
        _ok(limactl("copy", str(src), f"{name}:{GUEST_IN}/{src.name}", timeout=900), f"copy {src.name}")


def copy_out(name: str, dest: Path) -> None:
    _ok(limactl("copy", "--recursive", f"{name}:{GUEST_OUT}/", str(dest), timeout=900), "copy results")


def cmd_build(args: argparse.Namespace) -> int:
    """Build the platform's bundle in a fresh clone from a ``git archive`` of ``--checkout`` (D-865)."""
    pins = load_pins()
    pin = platform_pin(pins, args.platform)
    build = pin.get("build")
    if not isinstance(build, dict):
        raise SystemExit(f"pins.toml: platform {args.platform} has no [build] table")
    base = _stopped_base(args.platform)
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", args.checkout + "^{commit}"],  # noqa: S603, S607
                            capture_output=True, text=True, check=True).stdout.strip()
    now = utc_now()
    name = vm_name("build", now)
    out = vms_dir() / "builds" / label(args.platform, now)
    out.mkdir(parents=True)
    record: dict[str, Any] = {"build": name, "platform": args.platform, "commit": commit, "started_utc": now.isoformat(),
                              "digest": pin["digest"], "uv": build["uv_version"], "tools": pins.get("tools", {})}
    uv = fetch_pinned(build["uv_url"], build["uv_digest"], vms_dir() / "downloads", ".tar.gz")
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-build-") as tmp:
        staging = Path(tmp)
        shutil.copyfile(uv, staging / "uv.tar.gz")
        with open(staging / "checkout.tar.gz", "wb") as fh:
            subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar.gz", commit], stdout=fh, check=True)  # noqa: S603, S607
        script = HERE / "guest" / "linux_build.sh"
        with fresh_clone(base, name, now, args.keep, record):
            copy_in(name, staging / "uv.tar.gz", staging / "checkout.tar.gz", script)
            done = limactl("shell", name, "sh", f"{GUEST_IN}/{script.name}", GUEST_IN, GUEST_OUT,
                           str(pin.get("glibc_floor", "2.35")), *build.get("packages", []), timeout=7200)
            (out / "harness.log").write_text(done.stdout + done.stderr, encoding="utf-8")
            record["exit"] = done.returncode
            copy_out(name, out / "guest")
    packages = sorted((out / "guest").glob("AgentPROV-linux-*.tar.gz"))
    record["package"] = {"file": str(packages[0]), "sha256": _sha256(packages[0])} if packages else None
    record["ok"] = record["exit"] == 0 and bool(packages)
    record["ended_utc"] = utc_now().isoformat()
    (out / "build.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if record["ok"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    pins = load_pins()
    pin = platform_pin(pins, args.platform)
    base = _stopped_base(args.platform)
    now = utc_now()
    name = vm_name("run", now)
    results = vms_dir() / "results" / label(args.platform, now)
    results.mkdir(parents=True)
    run: dict[str, Any] = {"run": name, "platform": args.platform, "level": args.level, "started_utc": now.isoformat(),
                           "image": pin["image"], "digest": pin["digest"], "tools": pins.get("tools", {})}
    base_record = vms_dir() / "bases" / f"{base}.json"
    if base_record.is_file():
        run["base"] = json.loads(base_record.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-in-") as tmp:
        staging = Path(tmp)
        bundle = bundle_tar(args.bundle.resolve(), staging)
        run["bundle"] = {"file": bundle.name, "sha256": _sha256(bundle)}
        corpus = mini_corpus_tar(staging)
        extra: list[Path] = []
        if args.level == "W":  # steps 4-9 need uv and the checkout (design §6 row 4: the guest downloads the rest)
            build = pin.get("build")
            if not isinstance(build, dict):
                raise SystemExit(f"pins.toml: platform {args.platform} has no [build] table (level W needs its uv)")
            run["commit"] = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify",  # noqa: S603, S607
                                            args.checkout + "^{commit}"], capture_output=True, text=True,
                                           check=True).stdout.strip()
            run["uv"] = build["uv_version"]
            shutil.copyfile(fetch_pinned(build["uv_url"], build["uv_digest"], vms_dir() / "downloads", ".tar.gz"),
                            staging / "uv.tar.gz")
            with open(staging / "checkout.tar.gz", "wb") as fh:
                subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar.gz", run["commit"]],  # noqa: S603, S607
                               stdout=fh, check=True)
            extra = [staging / "uv.tar.gz", staging / "checkout.tar.gz", HERE / "guest" / "linux_w_steps.py"]
        with fresh_clone(base, name, now, args.keep, run):
            copy_in(name, bundle, corpus, HERE / "guest" / "linux_steps.py", *extra)
            steps = limactl("shell", name, "python3", f"{GUEST_IN}/linux_steps.py", "--bundle",
                            f"{GUEST_IN}/{bundle.name}", "--corpus", f"{GUEST_IN}/{corpus.name}", "--out", GUEST_OUT,
                            timeout=3600)
            log = steps.stdout + steps.stderr
            if args.level == "W":
                w = limactl("shell", name, "python3", f"{GUEST_IN}/linux_w_steps.py", "--uv", f"{GUEST_IN}/uv.tar.gz",
                            "--checkout", f"{GUEST_IN}/checkout.tar.gz", "--out", GUEST_OUT, timeout=4 * 3600)
                log += w.stdout + w.stderr
            (results / "harness.log").write_text(log, encoding="utf-8")
            copy_out(name, results / "guest")
    shot = results / "guest" / "screenshot.xwd"
    if shot.is_file():
        try:
            (results / "screenshot.png").write_bytes(xwd_to_png(shot.read_bytes()))
        except ValueError as exc:
            run["screenshot_error"] = str(exc)
    lines = (results / "guest" / "steps.jsonl")
    run["steps"] = [json.loads(line) for line in lines.read_text(encoding="utf-8").splitlines()] if lines.is_file() else []
    run["ok"] = bool(run["steps"]) and all(s.get("pass") for s in run["steps"])
    run["ended_utc"] = utc_now().isoformat()
    (results / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    if args.report is not None:
        report = json.loads(args.report.read_text(encoding="utf-8")) if args.report.is_file() else {}
        report.setdefault("clean_machine", []).append({k: run[k] for k in (
            "run", "platform", "level", "started_utc", "digest", "tools", "bundle", "steps", "ok")})
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: run[k] for k in ("run", "ok", "vm")} | {"results": str(results),
                     "steps": [(s["step"], s["pass"]) for s in run["steps"]]}, indent=2))
    return 0 if run["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("base", help="build a platform's base VM from its pin (once)")
    b.add_argument("platform")
    r = sub.add_parser("run", help="run the §3 steps in a fresh clone of the base")
    r.add_argument("platform")
    r.add_argument("--bundle", type=Path, required=True)
    r.add_argument("--level", choices=("V", "W"), default="V", help="V: steps 1-3 (bundle only); W: also 4-9")
    r.add_argument("--checkout", default="HEAD", help="level W: the commit whose git archive steps 4-9 use")
    r.add_argument("--report", type=Path, help="a bundle-report.json to append the run to (D-863)")
    r.add_argument("--keep", action="store_true", help="leave the clone for inspection")
    c = sub.add_parser("build", help="build the platform's bundle in a fresh clone of the base")
    c.add_argument("platform")
    c.add_argument("--checkout", default="HEAD", help="the commit to build (a git archive of it is copied in)")
    c.add_argument("--keep", action="store_true", help="leave the clone for inspection")
    args = ap.parse_args(argv)
    if args.platform.startswith("windows-"):  # UTM, not Lima (D-867)
        import windows

        return {"base": windows.cmd_base, "run": windows.cmd_run, "build": windows.cmd_build}[args.command](args)
    if shutil.which("limactl") is None:
        raise SystemExit("limactl not found (brew install lima)")
    global TIMEOUT_FACTOR
    TIMEOUT_FACTOR = float(platform_pin(load_pins(), args.platform).get("timeout_factor", 1))
    return {"base": cmd_base, "run": cmd_run, "build": cmd_build}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
