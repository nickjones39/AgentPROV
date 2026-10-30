"""Windows 11 ARM64 in UTM for the G5 clean-machine tests (D-867): the unattended base, then per-run clones.

The base: ``autounattend.xml`` and ``firstlogon.ps1`` go on a small ISO (``hdiutil makehybrid``, no download). UTM
creates the VM by AppleScript with three USB CD drives (the user's Windows ISO, UTM's guest tools ISO, the unattend
ISO) and an NVMe disk. UTM's scripting dictionary has no TPM property and macOS keeps the driver out of UTM's container,
so **the user ticks "TPM 2.0 Device"** (QEMU, Tweaks) once. The VM gets a ``virtio-ramfb`` display and no serial port
(UTM's scripted default is a serial console only), and :func:`start_with_keys` answers the ISO's boot prompt. Windows installs
unattended and **unactivated** (the user's choice, 2026-10-28: "run unactivated within Microsoft's terms"; no product
key is handled). One local test account ``agentprov`` with a generated password kept under
``$AGENTPROV_HOME/vms/windows/`` (mode 0600, never printed) logs on automatically. At first logon the guest tools are
installed from their CD (virtio drivers, SPICE and the QEMU guest agent), which lets UTM's ``execute``, ``push`` and
``query ip`` reach the guest, so no OpenSSH is needed. The script writes ``C:\\agentprov-g5-base.json`` and shuts
down; the stopped VM is the base. LongPathsEnabled stays off (P-5's warning is tested).
"""

# ruff: noqa: S603, S607 - fixed host tools (hdiutil, osascript, git) with arguments this module builds

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import driver as d

ACCOUNT = "agentprov"
LANG = "en-US"
#: the edition installed from Microsoft's multi-edition ISO; without a key it stays unactivated
EDITION = "Windows 11 Pro"
MARKER = r"C:\agentprov-g5-base.json"


def password() -> str:
    """A test password for this VM's local account only (letters and digits: no XML or shell quoting issues)."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "G5-" + "".join(secrets.choice(alphabet) for _ in range(20))


def autounattend(pw: str, computer: str = "G5-WIN") -> str:
    p = escape(pw)
    arch = 'processorArchitecture="arm64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS"'
    intl = f"""<InputLocale>{LANG}</InputLocale><SystemLocale>{LANG}</SystemLocale><UILanguage>{LANG}</UILanguage>
      <UserLocale>{LANG}</UserLocale>"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- written by gui/tools/clean_machine/windows.py (D-867); a test VM only -->
<unattend xmlns="urn:schemas-microsoft-com:unattend" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE" {arch}>
      <SetupUILanguage><UILanguage>{LANG}</UILanguage></SetupUILanguage>
      {intl}
    </component>
    <component name="Microsoft-Windows-Setup" {arch}>
      <DiskConfiguration>
        <Disk wcm:action="add">
          <DiskID>0</DiskID>
          <WillWipeDisk>true</WillWipeDisk>
          <CreatePartitions>
            <CreatePartition wcm:action="add"><Order>1</Order><Type>EFI</Type><Size>260</Size></CreatePartition>
            <CreatePartition wcm:action="add"><Order>2</Order><Type>MSR</Type><Size>16</Size></CreatePartition>
            <CreatePartition wcm:action="add"><Order>3</Order><Type>Primary</Type><Extend>true</Extend></CreatePartition>
          </CreatePartitions>
          <ModifyPartitions>
            <ModifyPartition wcm:action="add"><Order>1</Order><PartitionID>1</PartitionID><Format>FAT32</Format>
              <Label>System</Label></ModifyPartition>
            <ModifyPartition wcm:action="add"><Order>2</Order><PartitionID>2</PartitionID></ModifyPartition>
            <ModifyPartition wcm:action="add"><Order>3</Order><PartitionID>3</PartitionID><Format>NTFS</Format>
              <Label>Windows</Label><Letter>C</Letter></ModifyPartition>
          </ModifyPartitions>
        </Disk>
      </DiskConfiguration>
      <ImageInstall>
        <OSImage>
          <InstallFrom><MetaData wcm:action="add"><Key>/IMAGE/NAME</Key><Value>{EDITION}</Value></MetaData></InstallFrom>
          <InstallTo><DiskID>0</DiskID><PartitionID>3</PartitionID></InstallTo>
        </OSImage>
      </ImageInstall>
      <UserData>
        <AcceptEula>true</AcceptEula>
        <ProductKey><Key></Key><WillShowUI>OnError</WillShowUI></ProductKey>
      </UserData>
    </component>
  </settings>
  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup" {arch}>
      <ComputerName>{computer}</ComputerName>
    </component>
    <component name="Microsoft-Windows-Deployment" {arch}>
      <RunSynchronous>
        <RunSynchronousCommand wcm:action="add"><Order>1</Order>
          <Path>reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\OOBE /v BypassNRO /t REG_DWORD /d 1 /f</Path>
        </RunSynchronousCommand>
      </RunSynchronous>
    </component>
  </settings>
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" {arch}>
      {intl}
    </component>
    <component name="Microsoft-Windows-Shell-Setup" {arch}>
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <ProtectYourPC>3</ProtectYourPC>
      </OOBE>
      <UserAccounts>
        <LocalAccounts>
          <LocalAccount wcm:action="add">
            <Name>{ACCOUNT}</Name><Group>Administrators</Group>
            <Password><Value>{p}</Value><PlainText>true</PlainText></Password>
          </LocalAccount>
        </LocalAccounts>
      </UserAccounts>
      <AutoLogon>
        <Username>{ACCOUNT}</Username><Enabled>true</Enabled><LogonCount>9999999</LogonCount>
        <Password><Value>{p}</Value><PlainText>true</PlainText></Password>
      </AutoLogon>
      <FirstLogonCommands>
        <SynchronousCommand wcm:action="add"><Order>1</Order>
          <CommandLine>cmd /c for %d in (D E F G H I) do if exist %d:\\firstlogon.ps1 powershell -NoProfile -ExecutionPolicy Bypass -File %d:\\firstlogon.ps1</CommandLine>
        </SynchronousCommand>
      </FirstLogonCommands>
    </component>
  </settings>
</unattend>
"""


FIRSTLOGON = r"""# written by gui/tools/clean_machine/windows.py (D-867): install UTM's guest tools, record the base, shut down
$ErrorActionPreference = 'Continue'
$log = 'C:\agentprov-g5-firstlogon.log'
Start-Transcript -Path $log -Append
$tools = Get-PSDrive -PSProvider FileSystem | ForEach-Object { Get-ChildItem "$($_.Root)utm-guest-tools-*.exe" -ErrorAction SilentlyContinue } | Select-Object -First 1
if ($tools) { Start-Process -FilePath $tools.FullName -ArgumentList '/S' -Wait }
$os = Get-CimInstance Win32_OperatingSystem
$facts = @{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber; arch = $env:PROCESSOR_ARCHITECTURE;
            guest_tools = if ($tools) { $tools.Name } else { $null };
            long_paths = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled }
$facts | ConvertTo-Json | Set-Content -Path 'C:\agentprov-g5-base.json' -Encoding utf8
Stop-Transcript
shutdown /s /t 20
"""


def unattend_iso(pw: str, dest: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-unattend-") as tmp:
        root = Path(tmp)
        (root / "autounattend.xml").write_text(autounattend(pw), encoding="utf-8")
        (root / "firstlogon.ps1").write_text(FIRSTLOGON, encoding="utf-8")
        if dest.exists():
            raise SystemExit(f"{dest} exists")
        subprocess.run(["hdiutil", "makehybrid", "-iso", "-joliet", "-default-volume-name", "AGENTPROV",
                        "-o", str(dest), str(root)], check=True, capture_output=True)
    return dest


def applescript_create(name: str, windows_iso: Path, tools_iso: Path, unattend: Path, cpus: int, memory_mib: int,
                       disk_mib: int) -> str:
    def f(p: Path) -> str:
        return f'POSIX file "{p}"'
    return f"""tell application "UTM"
  set vm to make new virtual machine with properties {{backend:qemu, configuration:{{name:"{name}", architecture:"aarch64", memory:{memory_mib}, cpu cores:{cpus}, uefi:true, hypervisor:true, drives:{{{{removable:true, interface:USB, source:({f(windows_iso)})}}, {{removable:true, interface:USB, source:({f(tools_iso)})}}, {{removable:true, interface:USB, source:({f(unattend)})}}, {{interface:NVMe, guest size:{disk_mib}}}}}, network interfaces:{{{{mode:shared}}}}, displays:{{{{hardware:"virtio-ramfb"}}}}}}}}
  set c to configuration of vm
  set «class SrPt» of c to {{}}
  update configuration vm with c
  return id of vm
end tell
"""


def start_with_keys(vid: str, seconds: int = 30) -> None:
    """Start the VM and press a key once a second: the Windows ISO's "Press any key to boot from CD or DVD" prompt
    otherwise times out and the VM idles in the firmware with an empty disk (the first base attempt, 2026-10-28)."""
    start(vid)
    for _ in range(seconds):
        time.sleep(1)
        with contextlib.suppress(SystemExit):
            jxa("utm.inputKeystroke(utm.virtualMachines.byId(A.id), {text: ' '}); return '';", {"id": vid}, timeout=30)


def osascript(script: str, timeout: float = 120) -> str:
    done = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=timeout,
                          check=False)
    if done.returncode != 0:
        raise SystemExit(f"osascript failed: {done.stderr.strip()[:400]}")
    return done.stdout.strip()


# ------------------------------------------------------------------------------------------------ UTM by JXA
#: UTM's scripting dictionary (``UTM.sdef``) driven by JavaScript for Automation: arguments go in as one JSON argv
_JXA = "function run(argv) { const utm = Application('UTM'); const A = JSON.parse(argv[0]); %s }"


def jxa(body: str, args: dict[str, object] | None = None, timeout: float = 300) -> object:
    done = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA % body, json.dumps(args or {})],
                          capture_output=True, text=True, timeout=timeout, check=False)
    if done.returncode != 0:
        raise SystemExit(f"UTM scripting failed: {done.stderr.strip()[:400]}")
    out = done.stdout.strip()
    return json.loads(out) if out else None


def vms() -> list[dict[str, str]]:
    found = jxa("return JSON.stringify(utm.virtualMachines().map(v => ({id: v.id(), name: v.name(), "
                "status: v.status(), notes: v.configuration().notes || ''})));")
    return found if isinstance(found, list) else []


def vm_id(name: str) -> str | None:
    return next((v["id"] for v in vms() if v["name"] == name), None)


def status(vid: str) -> str:
    return str(jxa("return JSON.stringify(utm.virtualMachines.byId(A.id).status());", {"id": vid}))


def duplicate(base: str, name: str, notes: str) -> str:
    """A per-run copy of the stopped base, named ``name``, with the run marker in its notes (D-862). AppleScript, not
    JXA: JXA cannot hand UTM's configuration record back ("Can't convert types")."""
    q = json.dumps  # an AppleScript string literal is a JSON string without escapes beyond \" and \\
    osascript(f"""tell application "UTM"
  set vm to virtual machine id {q(base)}
  set c to configuration of vm
  set name of c to {q(name)}
  set «class NoTe» of c to {q(notes)}
  duplicate vm with properties {{configuration:c}}
end tell
""", timeout=1800)
    new = vm_id(name)
    if new is None:
        raise SystemExit(f"UTM did not create {name}")
    return new


def start(vid: str) -> None:
    jxa("utm.start(utm.virtualMachines.byId(A.id)); return '';", {"id": vid})


def stop(vid: str) -> None:
    jxa("utm.stop(utm.virtualMachines.byId(A.id), {by: 'force'}); return '';", {"id": vid})


def delete(vid: str) -> None:
    jxa("utm.delete(utm.virtualMachines.byId(A.id)); return '';", {"id": vid}, timeout=600)


def guest_exec(vid: str, exe: str, args: list[str], timeout: float = 600) -> dict[str, object]:
    """Run ``exe`` in the guest through UTM's guest agent (as SYSTEM); waits up to ``timeout`` seconds."""
    body = ("const vm = utm.virtualMachines.byId(A.id); "
            "const p = utm.execute(vm, {at: A.exe, withArguments: A.args, outputCapturing: true}); "
            "const end = Date.now() + A.timeout * 1000; let r = utm.getResult(p); "
            "while (!r.exited && Date.now() < end) { delay(1); r = utm.getResult(p); } "
            "return JSON.stringify({exited: r.exited, code: r.exitCode, out: r.outputText || '', "
            "err: r.errorText || ''});")
    result = jxa(body, {"id": vid, "exe": exe, "args": args, "timeout": timeout}, timeout=timeout + 60)
    return result if isinstance(result, dict) else {"exited": False}


def wait_agent(vid: str, timeout: float = 900) -> bool:
    """Until the guest agent answers (the guest tools are installed in the base)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if guest_exec(vid, "cmd.exe", ["/c", "echo", "ready"], timeout=30).get("code") == 0:
                return True
        except SystemExit:
            pass
        time.sleep(10)
    return False


def push(vid: str, host: Path, guest: str) -> None:
    jxa("const vm = utm.virtualMachines.byId(A.id); const f = utm.openFile(vm, {at: A.guest, for: 'writing'}); "
        "utm.push(f, {from: Path(A.host)}); return '';", {"id": vid, "host": str(host), "guest": guest}, timeout=1800)


def pull(vid: str, guest: str, host: Path) -> None:
    """One guest file to ``host``; UTM writes only into a host file that already exists, so it is created first."""
    host.parent.mkdir(parents=True, exist_ok=True)
    host.touch()
    jxa("const vm = utm.virtualMachines.byId(A.id); const f = utm.openFile(vm, {at: A.guest}); "
        "utm.pull(f, {to: Path(A.host)}); return '';", {"id": vid, "host": str(host), "guest": guest}, timeout=1800)


def pull_dir(vid: str, guest_dir: str, host: Path) -> dict[str, str]:
    """Every file under ``guest_dir``, by name; a file that fails to copy is listed with its error, and the rest are
    still copied (the clone is deleted afterwards, so nothing is left to retry from)."""
    listing = guest_exec(vid, "cmd.exe", ["/c", "dir", "/s", "/b", "/a-d", guest_dir], timeout=60)
    names = [line.strip() for line in str(listing.get("out", "")).splitlines() if line.strip()]
    failed: dict[str, str] = {}
    for name in names:
        rel = name[len(guest_dir):].lstrip("\\")
        try:
            pull(vid, name, host / Path(*rel.split("\\")))
        except SystemExit as exc:
            failed[rel] = str(exc)[:300]
    return failed


def user_task(vid: str, script: str, args: list[str], done: str, timeout: float) -> bool:
    """Run a guest PowerShell script in the auto-logged-on user's session (a scheduled task with ``/IT``), which the
    window, the screenshot and the user's Credential Manager need; waits until it writes ``done``."""
    command = f'powershell -NoProfile -ExecutionPolicy Bypass -File {script} ' + " ".join(args)
    guest_exec(vid, "schtasks.exe", ["/Create", "/TN", "agentprov-g5", "/TR", command, "/SC", "ONCE", "/ST", "23:59",
                                     "/RU", ACCOUNT, "/IT", "/RL", "HIGHEST", "/F"], timeout=60)
    guest_exec(vid, "schtasks.exe", ["/Run", "/TN", "agentprov-g5"], timeout=60)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if str(guest_exec(vid, "cmd.exe", ["/c", "if", "exist", done, "echo", "done"], timeout=60).get("out", "")).strip():
            return True
        time.sleep(15)
    return False


# ------------------------------------------------------------------------------------------------ base, build, run
BASE = "agentprov-g5-base-windows"
IN, OUT = r"C:\g5\in", r"C:\g5\out"


def run_marker(name: str, now: str) -> str:
    return json.dumps({"name": name, "tool": "agentprov-g5-driver", "created_utc": now}, sort_keys=True)


def may_delete_utm(name: str, notes: str) -> bool:
    """D-862 for UTM: the marker lives in the clone's notes (the driver cannot write into UTM's container)."""
    if not name.startswith(d.PREFIX) or name.startswith(d.PREFIX + "base-"):
        return False
    try:
        doc = json.loads(notes)
    except ValueError:
        return False
    return isinstance(doc, dict) and doc.get("name") == name and doc.get("tool") == "agentprov-g5-driver"


@contextlib.contextmanager
def fresh_clone(kind: str, now: dt.datetime, keep: bool, record: dict[str, Any]) -> Iterator[str]:
    base = vm_id(BASE)
    if base is None or status(base) != "stopped":
        raise SystemExit(f"{BASE} is missing or not stopped (create it with driver.py base windows)")
    name = d.vm_name(kind, now)
    vid = duplicate(base, name, run_marker(name, now.isoformat()))
    record["vm"] = name
    try:
        start(vid)
        if not wait_agent(vid):
            raise SystemExit(f"{name}: the guest agent did not answer within 15 minutes")
        guest_exec(vid, "cmd.exe", ["/c", "mkdir", IN, OUT], timeout=60)
        yield vid
    finally:
        if keep:
            record["vm"] = f"kept {name}"
        else:
            notes = next((v["notes"] for v in vms() if v["id"] == vid), "")
            if may_delete_utm(name, notes):
                with contextlib.suppress(SystemExit):
                    stop(vid)
                time.sleep(5)
                delete(vid)
                record["vm"] = f"deleted {name}"
            else:
                record["vm"] = f"left {name} (no matching marker)"


def _uv_zip(pin: dict[str, Any], staging: Path) -> Path:
    build = pin["build"]
    target = staging / "uv.zip"
    shutil.copyfile(d.fetch_pinned(build["uv_url"], build["uv_digest"], d.vms_dir() / "downloads", ".zip"), target)
    return target


def _checkout(ref: str, staging: Path) -> tuple[str, Path]:
    commit = subprocess.run(["git", "-C", str(d.REPO), "rev-parse", "--verify", ref + "^{commit}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    target = staging / "checkout.tar.gz"
    with open(target, "wb") as fh:
        subprocess.run(["git", "-C", str(d.REPO), "archive", "--format=tar.gz", commit], stdout=fh, check=True)
    return commit, target


def cmd_base(args: argparse.Namespace) -> int:
    """Create the Windows base VM (once): the unattend ISO, the UTM VM, then the user ticks TPM 2.0 and the driver
    starts the unattended install, which shuts the VM down when first logon has finished."""
    pin = d.platform_pin(d.load_pins(), "windows-arm64")
    if vm_id(BASE) is not None:
        raise SystemExit(f"{BASE} exists; a new base needs the user's OK to remove the old one first")
    home = d.vms_dir() / "windows"
    home.mkdir(parents=True, exist_ok=True)
    secret = home / f"{BASE}.account.json"
    pw = password()
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"vm": BASE, "account": ACCOUNT, "password": pw, "note": "test value for this VM only (D-867)"}, fh)
    unattend = unattend_iso(pw, home / f"{BASE}-unattend.iso")
    unattend.chmod(0o600)
    images = d.vms_dir() / "images"
    windows_iso = images / (pin["digest"].removeprefix("sha256:") + ".iso")
    tools_iso = images / (pin["guest_tools_digest"].removeprefix("sha256:") + ".iso")
    for iso in (windows_iso, tools_iso):
        if not iso.is_file():
            raise SystemExit(f"{iso} missing: the Windows ISO is the user's download, the guest tools ISO is pinned")
    vid = osascript(applescript_create(BASE, windows_iso, tools_iso, unattend, int(pin["cpus"]),
                                       int(pin["memory_gib"]) * 1024, int(pin["disk_gib"]) * 1024))
    print(json.dumps({"base": BASE, "id": vid, "next": "tick TPM 2.0 Device in UTM (QEMU, Tweaks), save, then start "
                      "it through the queue with windows.start_with_keys; first logon shuts it down"}, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build the Windows bundle in a fresh clone of the base (D-867), as the Linux build does (D-865): ARM64 natively, or
    x86_64 with the x64 uv under Windows 11 ARM64's x64 emulation (``windows-x64``)."""
    pins = d.load_pins()
    pin = d.platform_pin(pins, args.platform)
    now = d.utc_now()
    out = d.vms_dir() / "builds" / d.label(args.platform, now)
    out.mkdir(parents=True)
    record: dict[str, Any] = {"platform": args.platform, "started_utc": now.isoformat(), "uv": pin["build"]["uv_version"],
                              "tools": pins.get("tools", {})}
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-wbuild-") as tmp:
        staging = Path(tmp)
        record["commit"], checkout = _checkout(args.checkout, staging)
        files = [_uv_zip(pin, staging), checkout, d.HERE / "guest" / "win_build.ps1"]
        with fresh_clone("build", now, args.keep, record) as vid:
            for f in files:
                push(vid, f, f"{IN}\\{f.name}")
            done = guest_exec(vid, "powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                                      f"{IN}\\win_build.ps1", IN, OUT], timeout=3 * 3600)
            record["exit"] = done.get("code")
            record["copy_failures"] = pull_dir(vid, OUT, out / "guest")
    packages = sorted((out / "guest").glob("AgentPROV-windows-*.zip"))
    record["package"] = {"file": str(packages[0]), "sha256": d._sha256(packages[0])} if packages else None
    record["ok"] = record.get("exit") == 0 and bool(packages)
    record["ended_utc"] = d.utc_now().isoformat()
    (out / "build.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if record["ok"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Steps 1-3 (level V) or 1-9 (level W) in a fresh clone, as the auto-logged-on user (D-867)."""
    pins = d.load_pins()
    pin = d.platform_pin(pins, args.platform)
    now = d.utc_now()
    results = d.vms_dir() / "results" / d.label(args.platform, now)
    results.mkdir(parents=True)
    run: dict[str, Any] = {"platform": args.platform, "level": args.level, "started_utc": now.isoformat(),
                           "digest": pin["digest"], "tools": pins.get("tools", {})}
    bundle = args.bundle.resolve()
    if not bundle.name.startswith("AgentPROV-windows-") or bundle.suffix != ".zip":
        raise SystemExit(f"{bundle} is not a Windows bundle zip")
    run["bundle"] = {"file": bundle.name, "sha256": d._sha256(bundle)}
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-win-") as tmp:
        staging = Path(tmp)
        files = [bundle, d.mini_corpus_tar(staging), d.HERE / "guest" / "win_steps.ps1"]
        if args.level == "W":
            run["commit"], checkout = _checkout(args.checkout, staging)
            run["uv"] = pin["build"]["uv_version"]
            files += [_uv_zip(pin, staging), checkout]
        with fresh_clone("run", now, args.keep, run) as vid:
            for f in files:
                push(vid, f, f"{IN}\\{f.name}")
            arch = "x64" if args.platform == "windows-x64" else "arm64"
            run["finished"] = user_task(vid, f"{IN}\\win_steps.ps1", ["-Level", args.level, "-Arch", arch, "-InDir", IN,
                                                                     "-OutDir", OUT],
                                        f"{OUT}\\done.txt", timeout=4 * 3600)
            run["copy_failures"] = pull_dir(vid, OUT, results / "guest")
    lines = results / "guest" / "steps.jsonl"
    run["steps"] = ([json.loads(line) for line in lines.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                    if lines.is_file() else [])
    expected = 9 if args.level == "W" else 3
    # D-863 counts the applicable steps; D-867 (user decision 2026-10-28) marks 7-8 not applicable on Windows ARM64
    run["ok"] = len(run["steps"]) == expected and all(s.get("pass") for s in run["steps"] if s.get("applicable", True))
    run["not_applicable"] = [s.get("step") for s in run["steps"] if s.get("applicable", True) is False]
    run["ended_utc"] = d.utc_now().isoformat()
    (results / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    if args.report is not None:
        report = json.loads(args.report.read_text(encoding="utf-8")) if args.report.is_file() else {}
        report.setdefault("clean_machine", []).append({k: run.get(k) for k in (
            "vm", "platform", "level", "started_utc", "digest", "tools", "bundle", "steps", "ok")})
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: run.get(k) for k in ("vm", "ok")} | {"results": str(results),
                     "steps": [(s.get("step"), s.get("pass")) for s in run["steps"]]}, indent=2))
    return 0 if run["ok"] else 1
