"""The verified upgrade of a package install (D-1130, amending D-1065): the release's own wheels, never PyPI.

``agentprov update download --package --allow-network`` stages, in ``$AGENTPROV_HOME/update/staging/package/`` (or
``--dir``), in this order: ``SHA256SUMS`` and ``SHA256SUMS.sig``, verified by :func:`agentprov.update.verify.
verify_release` exactly as for a bundle (a listed key needs a valid signature); then each wheel of the release's
version that this environment has, ``agentprov``, ``agentprov_capture`` and, when installed here, ``agentprov_zenodo``
(``<dist>-<version>-py3-none-any.whl``), whose size must be the listed one and whose sha256 must be the list's; then
each wheel's own metadata (:func:`wheel_metadata`): a zip of at most :data:`MAX_WHEEL_MEMBERS` members with no absolute
or ``..`` name, one ``<dist>-<version>.dist-info/METADATA`` naming that distribution and version. A failure removes
what was fetched.

``agentprov update install --package --confirm`` checks the staged files again and runs **this program's own
installer** on those exact files, with no dependency resolution and no index (:func:`installer_argv`):

* ``pip``: ``<this interpreter> -m pip install --isolated --no-deps --no-index --disable-pip-version-check
  --no-input [--user] WHEELS`` (``--user`` when this agentprov is installed in the user site: pip would otherwise write
  the base environment and leave the old copy first on ``sys.path``);
* ``uv-tool``: ``uv pip install --no-config --python <this interpreter> --no-deps --no-index WHEELS`` (the tool's
  receipt keeps naming ``agentprov``, so a later ``uv tool upgrade agentprov`` still works);
* ``pipx``: ``pipx runpip <venv> install --isolated --no-deps --no-index --disable-pip-version-check --no-input WHEELS``.

``--isolated`` and ``--no-config`` (D-1130 review): the installers read no configuration file, so nothing in a
``pip.conf`` or ``uv.toml`` (a target, a prefix, ``user = true``, an index) changes where or what they install.

Because nothing is resolved, the upgrade is refused (with the ordinary upgrade command shown instead) when the new
wheels need anything this environment may lack (:func:`dependency_problems`): every requirement of a new wheel that is
not one of the three siblings must be, text for text, one the installed version already declared (so it is already
satisfied), and every sibling requirement must pin the release's version (``==X.Y.Z``). The installer's output is kept
(its tail is reported); afterwards the installed versions are read again and must be the release's.

**The previous version is not kept.** A package manager installs over the old files, and the old wheels are not on
this machine. The result says so and names the command that goes back (from PyPI, as any other install would).

Outside every stage closure (class 0).
"""

from __future__ import annotations

import email.parser
import email.policy
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.update import ALLOWED_SIGNERS
from agentprov.update.releases import (
    CHECKSUM_ASSET,
    SIGNATURE_ASSET,
    Release,
    UpdateError,
    download,
    update_dir,
)
from agentprov.update.verify import SIG_MAX_BYTES, SUMS_MAX_BYTES, parse_sums, sha256_file, verify_release

__all__ = ["DISTS", "KINDS", "STAGED_FORMAT", "dependency_problems", "install_folders", "install_package", "installed",
           "installer_argv", "load_staged_package", "restore_command", "stage_package", "staging_dir",
           "user_site_install", "wheel_metadata", "wheel_name"]

STAGED_FORMAT: Final = "agentprov-update-staged-package/0.1"
#: the release's wheels in install order (the distribution name as a wheel file spells it, and as metadata does)
DISTS: Final = (("agentprov_capture", "agentprov-capture"), ("agentprov", "agentprov"),
                ("agentprov_zenodo", "agentprov-zenodo"))
#: the package-install kinds :func:`agentprov.update.install.package_install` reports that this module can upgrade
KINDS: Final = ("pip", "uv-tool", "pipx")
#: the distributions always upgraded together (``agentprov`` pins ``agentprov-capture==X``); the uploader only when here
REQUIRED: Final = frozenset({"agentprov", "agentprov-capture"})
SIBLINGS: Final = frozenset(m for _w, m in DISTS)
MAX_WHEEL_BYTES: Final = 64 * 1024 * 1024
MAX_WHEEL_MEMBERS: Final = 10_000
MAX_METADATA_BYTES: Final = 1024 * 1024
INSTALL_TIMEOUT_S: Final = 900
_MARKER: Final = ".agentprov-update-staging"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=64 * 1024, max_json_depth=8)
_REQ: Final = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([^;]*?)\s*(?:;\s*(.*))?\s*")
#: the environment the installer gets: this one without the variables that point pip or uv elsewhere
_DROP_ENV: Final = ("PIP_", "UV_", "PYTHON", "VIRTUAL_ENV", "CONDA_")

#: ``installed(name)``: ``(version, requires)`` of a distribution in this environment, or ``None``
Installed = Callable[[str], "tuple[str, list[str]] | None"]


def staging_dir(home: Path) -> Path:
    return update_dir(home) / "staging" / "package"


def wheel_name(dist: str, version: str) -> str:
    """The release's file of a pure-Python wheel: ``agentprov_capture-0.2.2-py3-none-any.whl``."""
    return f"{dist}-{version}-py3-none-any.whl"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def installed(name: str) -> tuple[str, list[str]] | None:
    """The version and ``Requires-Dist`` lines of an installed distribution (this interpreter's environment)."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    return str(dist.version), [str(r) for r in (dist.metadata.get_all("Requires-Dist") or [])]


def _requirement(text: str) -> tuple[str, str, str]:
    """``(name, extras + specifier, marker)``, each normalised (no white space, one quote style, lower case name)."""
    m = _REQ.fullmatch(text)
    if m is None:
        raise UpdateError("a wheel declares a requirement this client cannot read", code="update.package.metadata")
    name, extras, spec, marker = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4) or ""
    squash = lambda s: re.sub(r"\s+", "", s).replace('"', "'")  # noqa: E731
    return _norm(name), squash(extras + spec), squash(marker)


# --------------------------------------------------------------------------------------------------------------
# A wheel's own metadata
# --------------------------------------------------------------------------------------------------------------


def wheel_metadata(path: Path, dist: str, version: str) -> list[str]:
    """Check a verified wheel's members and its ``METADATA`` (name and version); its ``Requires-Dist`` lines. The wheel
    is read, never unpacked: pip or uv installs it."""
    wanted = f"{dist}-{version}.dist-info/METADATA"
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_WHEEL_MEMBERS:
                raise UpdateError(f"{path.name} has too many members", code="update.package.wheel")
            for info in infos:
                name = info.filename
                if (not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name
                        or ".." in name.split("/") or info.flag_bits & 0x1):
                    raise UpdateError(f"{path.name} has a member that is not a plain relative name",
                                      code="update.package.wheel")
            meta = next((i for i in infos if i.filename == wanted), None)
            if meta is None or meta.file_size > MAX_METADATA_BYTES:
                raise UpdateError(f"{path.name} has no {dist}-{version}.dist-info/METADATA", code="update.package.wheel")
            with zf.open(meta) as fh:
                data = fh.read(MAX_METADATA_BYTES + 1)
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        raise UpdateError(f"{path.name} is not a readable wheel", code="update.package.wheel") from None
    msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(data, headersonly=True)
    if _norm(str(msg.get("Name", ""))) != _norm(dist) or str(msg.get("Version", "")) != version:
        raise UpdateError(f"{path.name}'s metadata does not name {dist} {version}", code="update.package.wheel")
    return [str(r) for r in (msg.get_all("Requires-Dist") or [])]


def dependency_problems(new: Mapping[str, list[str]], version: str, *, have: Installed = installed) -> list[str]:
    """Why the new wheels cannot be installed without resolving anything (empty: they can). ``new`` maps each
    distribution (metadata name) to its new ``Requires-Dist`` lines."""
    problems: list[str] = []
    for dist, requires in new.items():
        old = have(dist)
        old_set = {_requirement(r) for r in old[1]} if old is not None else set()
        for text in requires:
            name, spec, marker = _requirement(text)
            if name in SIBLINGS:
                if spec != f"=={version}":
                    problems.append(f"{dist} {version} does not pin {name} to {version}")
                continue
            if (name, spec, marker) not in old_set:
                problems.append(f"{dist} {version} needs {name}{spec}{(' ; ' + marker) if marker else ''}, which "
                                "the installed version did not")
    return problems


# --------------------------------------------------------------------------------------------------------------
# Download and verify
# --------------------------------------------------------------------------------------------------------------


def _fresh(directory: Path) -> None:
    if directory.exists() or directory.is_symlink():
        if directory.is_symlink() or not directory.is_dir():
            raise UpdateError("the staging folder is not a folder", code="update.stage", exit_code=2)
        if any(directory.iterdir()) and not (directory / _MARKER).is_file():
            raise UpdateError("the staging folder is not empty and was not made by agentprov update",
                              code="update.stage", exit_code=2)
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    (directory / _MARKER).write_bytes(b"D-1130\n")


def _wanted(have: Installed) -> list[tuple[str, str]]:
    """The ``(wheel dist, metadata name)`` pairs to upgrade here: the required two, and the uploader when installed."""
    return [(w, m) for w, m in DISTS if m in REQUIRED or have(m) is not None]


def stage_package(transport: Any, release: Release, directory: Path, *, signers: Path = ALLOWED_SIGNERS,
                  ssh_keygen: str | None = None, run: Any = None, have: Installed = installed) -> dict[str, Any]:
    """Download and verify the release's wheels for this environment into ``directory``; the staged record."""
    sums = release.asset(CHECKSUM_ASSET)
    if sums is None:
        raise UpdateError(f"release {release.tag} publishes no {CHECKSUM_ASSET}: refused", code="update.verify.missing")
    wanted = _wanted(have)
    assets = {w: release.asset(wheel_name(w, release.version)) for w, _m in wanted}
    missing = [wheel_name(w, release.version) for w, a in assets.items() if a is None]
    if missing:
        raise UpdateError(f"release {release.tag} has no {', '.join(missing)}", code="update.download.missing")
    sig = release.asset(SIGNATURE_ASSET)
    _fresh(directory)
    wheels: list[dict[str, Any]] = []
    try:
        download(transport, sums, directory / CHECKSUM_ASSET, max_bytes=SUMS_MAX_BYTES)
        if sig is not None:
            download(transport, sig, directory / SIGNATURE_ASSET, max_bytes=SIG_MAX_BYTES)
        kw: dict[str, Any] = {"signers": signers, "ssh_keygen": ssh_keygen}
        if run is not None:
            kw["run"] = run
        verification = verify_release(directory / CHECKSUM_ASSET, directory / SIGNATURE_ASSET if sig else None, **kw)
        listed = parse_sums((directory / CHECKSUM_ASSET).read_bytes())
        for w, m in wanted:
            name = wheel_name(w, release.version)
            if name not in listed:
                raise UpdateError(f"{CHECKSUM_ASSET} does not list {name}: refused", code="update.verify.missing")
            asset = assets[w]
            assert asset is not None
            digest = download(transport, asset, directory / name, max_bytes=MAX_WHEEL_BYTES)
            if digest != listed[name]:
                raise UpdateError(f"{name}'s sha256 is not the one {CHECKSUM_ASSET} lists: refused",
                                  code="update.verify.sha256")
            requires = wheel_metadata(directory / name, w, release.version)
            wheels.append({"name": name, "dist": m, "size": asset.size, "sha256": digest, "requires": requires})
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    record = {"format": STAGED_FORMAT, "tag": release.tag, "version": release.version, "wheels": wheels,
              "checksum": {"name": CHECKSUM_ASSET, "sha256": sha256_file(directory / CHECKSUM_ASSET)},
              "signature": None if sig is None else {"name": SIGNATURE_ASSET,
                                                     "sha256": sha256_file(directory / SIGNATURE_ASSET)},
              **verification.to_json()}
    (directory / "staged.json").write_bytes(json.dumps(record, sort_keys=True, indent=1).encode("utf-8") + b"\n")
    return {**record, "dir": str(directory)}


def load_staged_package(directory: Path, *, signers: Path = ALLOWED_SIGNERS, ssh_keygen: str | None = None,
                        run: Any = None, have: Installed = installed) -> dict[str, Any]:
    """The staged record, every file verified again (the signature, ``SHA256SUMS``, each wheel and its metadata). The
    wheels must still be those this environment needs (:func:`_wanted`): an uploader installed since the download
    would otherwise be left pinning the old ``agentprov``."""
    try:
        with open(directory / "staged.json", "rb") as fh:
            doc = strict_json_loads(fh.read(64 * 1024 + 1).rstrip(b"\n"), _LIMITS)
    except OSError:
        raise UpdateError("no package update is staged: run agentprov update download --package --allow-network "
                          "first", code="update.stage.none", exit_code=4) from None
    except IngestError:
        raise UpdateError("staged.json is not readable", code="update.stage") from None
    wheels = doc.get("wheels") if isinstance(doc, dict) else None
    version = doc.get("version") if isinstance(doc, dict) else None
    if (not isinstance(doc, dict) or doc.get("format") != STAGED_FORMAT or not isinstance(version, str)
            or not isinstance(wheels, list) or not wheels):
        raise UpdateError("the staged download is not a package update", code="update.stage")
    kw: dict[str, Any] = {"signers": signers, "ssh_keygen": ssh_keygen}
    if run is not None:
        kw["run"] = run
    sig = directory / SIGNATURE_ASSET
    verification = verify_release(directory / CHECKSUM_ASSET, sig if sig.is_file() else None, **kw)
    if sha256_file(directory / CHECKSUM_ASSET) != (doc.get("checksum") or {}).get("sha256"):
        raise UpdateError(f"the staged {CHECKSUM_ASSET} changed since it was downloaded", code="update.verify.sums")
    listed = parse_sums((directory / CHECKSUM_ASSET).read_bytes())
    by_dist = {m: w for w, m in DISTS}
    checked: list[dict[str, Any]] = []
    for entry in wheels:
        dist = entry.get("dist") if isinstance(entry, dict) else None
        if dist not in by_dist or entry.get("name") != wheel_name(by_dist[dist], version):
            raise UpdateError("the staged record names a file that is not one of the release's wheels",
                              code="update.stage")
        path = directory / entry["name"]
        digest = sha256_file(path) if path.is_file() and not path.is_symlink() else None
        if digest is None or digest != listed.get(entry["name"]) or digest != entry.get("sha256"):
            raise UpdateError(f"the staged {entry['name']} no longer matches {CHECKSUM_ASSET}: download it again",
                              code="update.verify.sha256")
        checked.append({**entry, "requires": wheel_metadata(path, by_dist[dist], version), "path": str(path)})
    if not REQUIRED <= {e["dist"] for e in checked}:
        raise UpdateError("the staged update lacks agentprov or agentprov-capture", code="update.stage")
    lacking = sorted({m for _w, m in _wanted(have)} - {e["dist"] for e in checked})
    if lacking:
        raise UpdateError(f"the staged update lacks {', '.join(lacking)}, installed here since the download: run "
                          "agentprov update download --package --allow-network again", code="update.stage")
    return {**doc, **verification.to_json(), "wheels": checked, "dir": str(directory)}


# --------------------------------------------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------------------------------------------


def _site(dist: str = "agentprov") -> Path | None:
    """The folder a distribution is installed in (its ``site-packages``), or ``None``."""
    try:
        return Path(os.path.realpath(str(metadata.distribution(dist).locate_file(""))))
    except (metadata.PackageNotFoundError, OSError, TypeError):
        return None


def user_site_install(*, location: Path | None = None, user_site: str | None = None) -> bool:
    """Whether this ``agentprov`` is installed in the user site (``pip install --user``)."""
    import site

    where = location if location is not None else _site()
    mine = user_site if user_site is not None else site.getusersitepackages()
    if where is None or not mine:
        return False
    return os.path.normcase(str(where)) == os.path.normcase(os.path.realpath(mine))


def install_folders(kind: str, *, prefix: str | None = None, which: Callable[[str], str | None] = shutil.which,
                    files: Callable[[], Sequence[Path]] | None = None) -> list[Path]:
    """What a package install's upgrade replaces (D-1130 review), for the running-job guard: the environment
    (``sys.prefix``), the folder the distributions are installed in (the user site of ``pip install --user`` is not
    in ``sys.prefix``), this distribution's own commands wherever its ``RECORD`` puts them (``~/.local/bin/agentprov``
    of a user install), and for a uv tool the ``agentprov`` found on ``PATH`` (on Windows uv copies the command there
    rather than linking it). ``files`` is a seam: the commands' paths."""
    out = [Path(sys.prefix if prefix is None else prefix)]
    for dist in ("agentprov", "agentprov-capture"):
        site_dir = _site(dist)
        if site_dir is not None:
            out.append(site_dir)
    out += list(files() if files is not None else _commands())
    if kind == "uv-tool":
        found = which("agentprov")
        if found:
            out.append(Path(found))
    seen: list[Path] = []
    for path in out:
        if path not in seen:
            seen.append(path)
    return seen


def _commands() -> list[Path]:
    """The ``agentprov`` commands this distribution's ``RECORD`` installed (``bin/agentprov``, ``Scripts\\agentprov.exe``)."""
    try:
        dist = metadata.distribution("agentprov")
    except metadata.PackageNotFoundError:
        return []
    out = []
    for file in dist.files or ():
        if file.name.lower() in ("agentprov", "agentprov.exe"):
            try:
                out.append(Path(os.path.abspath(str(file.locate()))))
            except (OSError, TypeError):
                continue
    return out


def installer_argv(kind: str, wheels: Sequence[str], *, prefix: str | None = None, executable: str | None = None,
                   which: Callable[[str], str | None] = shutil.which,
                   has_pip: Callable[[], bool] | None = None, user: bool | None = None
                   ) -> tuple[list[str] | None, str]:
    """The installer command for ``kind`` on the verified ``wheels`` (no resolver, no index, no configuration file),
    or ``None`` and why there is none here. ``user``: this agentprov is a user-site install (default: looked up)."""
    python = executable if executable is not None else sys.executable
    pip_found = has_pip() if has_pip is not None else _has_pip()
    in_user_site = user if user is not None else (kind == "pip" and user_site_install())
    if kind == "pip":
        if pip_found:
            return [python, "-m", "pip", "install", "--isolated", "--no-deps", "--no-index",
                    "--disable-pip-version-check", "--no-input", *(["--user"] if in_user_site else []), *wheels], "pip"
        if in_user_site:
            return None, "this agentprov is installed in the user site and this interpreter has no pip (uv pip has no user installs)"
        uv = which("uv")
        if uv is not None:  # a virtual environment made by uv has no pip
            return [uv, "pip", "install", "--no-config", "--python", python, "--no-deps", "--no-index", *wheels], \
                "uv pip"
        return None, "this environment has no pip and uv is not on PATH"
    if kind == "uv-tool":
        uv = which("uv")
        if uv is None:
            return None, "uv is not on PATH"
        return [uv, "pip", "install", "--no-config", "--python", python, "--no-deps", "--no-index", *wheels], "uv pip"
    if kind == "pipx":
        pipx = which("pipx")
        if pipx is None:
            return None, "pipx is not on PATH"
        venv = Path(sys.prefix if prefix is None else prefix).name
        return [pipx, "runpip", venv, "install", "--isolated", "--no-deps", "--no-index",
                "--disable-pip-version-check", "--no-input", *wheels], "pipx runpip"
    return None, f"a {kind} install is not upgraded from wheels"


def _has_pip() -> bool:
    from importlib.util import find_spec

    return find_spec("pip") is not None


def restore_command(kind: str, version: str | None, *, executable: str | None = None,
                    have: Installed = installed, user: bool | None = None) -> str | None:
    """The command that goes back to ``version`` (from PyPI): the previous version is not kept on this machine. With
    the uploader installed here, it goes back too (``agentprov-zenodo`` pins ``agentprov``). Every word is quoted for
    the shell (zsh reads an unquoted ``agentprov[zenodo]`` as a glob). ``user``: this agentprov is a user-site install
    (default: looked up), whose restore goes back into the user site with ``--user``, as the installer does."""
    if version is None:
        return None
    zenodo = have("agentprov-zenodo") is not None
    package = f"agentprov{'[zenodo]' if zenodo else ''}=={version}"
    if kind == "uv-tool":
        argv = ["uv", "tool", "install", "--force", package]
    elif kind == "pipx":
        argv = ["pipx", "install", "--force", package]
    else:
        python = executable if executable is not None else sys.executable
        in_user_site = user if user is not None else (kind == "pip" and user_site_install())
        argv = [python, "-m", "pip", "install", *(["--user"] if in_user_site else []), f"agentprov=={version}",
                f"agentprov-capture=={version}", *([f"agentprov-zenodo=={version}"] if zenodo else [])]
    return subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(_quote(a) for a in argv)


def _quote(arg: str) -> str:
    import shlex

    return shlex.quote(arg)


def installer_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """This environment without the variables that would point pip or uv at an index, a config or a Python path."""
    source = os.environ if environ is None else environ
    return {k: v for k, v in source.items() if not k.upper().startswith(_DROP_ENV)}


def install_package(staged: Mapping[str, Any], argv: list[str], *, run: Callable[..., Any] = subprocess.run,
                    have: Installed = installed) -> dict[str, Any]:
    """Run the installer ``argv`` (already holding the verified wheel paths) and read the installed versions again."""
    try:
        done = run(argv, capture_output=True, timeout=INSTALL_TIMEOUT_S, check=False, env=installer_env(),
                   stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError(f"the installer could not be run ({type(exc).__name__})", code="update.package.installer",
                          exit_code=3) from None
    tail = (done.stderr or b"")[-2000:].decode("utf-8", "replace") if isinstance(done.stderr, bytes) else ""
    if done.returncode != 0:
        raise UpdateError(f"the installer failed (exit {done.returncode}); the installed version is unchanged or "
                          "partly changed: see its output", code="update.package.installer")
    found = {e["dist"]: (have(e["dist"]) or ("?", []))[0] for e in staged["wheels"]}
    wrong = sorted(d for d, v in found.items() if v != staged["version"])
    if wrong:
        raise UpdateError(f"after the install, {', '.join(wrong)} is not at {staged['version']}",
                          code="update.package.installed")
    return {"installed": found, "installer_tail": tail}
