"""D-1130: the verified upgrade of a package install from the release's own wheels (never PyPI), against a fake GitHub
and a fake installer: no socket is opened and nothing is installed."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import update_support as us  # noqa: E402

from agentprov.cli import update as update_cmd  # noqa: E402
from agentprov.cli.main import main  # noqa: E402
from agentprov.update import install as I  # noqa: E402
from agentprov.update import package as P  # noqa: E402
from agentprov.update import releases as R  # noqa: E402
from agentprov.update.releases import UpdateError  # noqa: E402
from agentprov.versions import __version__  # noqa: E402

NEW = "9.0.0"
TAG = f"v{NEW}"
SSH_KEYGEN = shutil.which("ssh-keygen")
needs_ssh_keygen = pytest.mark.skipif(SSH_KEYGEN is None, reason="OpenSSH ssh-keygen is not installed")


def requires(version: str) -> list[str]:
    """agentprov's Requires-Dist at ``version`` (the shape of the real one)."""
    return ["prov>=3.2.2", "rfc8785>=0.1.4", f"agentprov-capture=={version}", "psutil>=7.2,<9",
            f"agentprov-zenodo=={version} ; extra == 'zenodo'"]


class Run(NamedTuple):
    code: int
    out: str
    err: str


class Env:
    """The fake environment: the installed distributions, and the installer that "installs" the wheels it is given."""

    def __init__(self, *, zenodo: bool = False, kind: str = "pip") -> None:
        self.dists: dict[str, tuple[str, list[str]]] = {
            "agentprov": (__version__, requires(__version__)), "agentprov-capture": (__version__, ["rfc8785>=0.1.4"])}
        if zenodo:
            self.dists["agentprov-zenodo"] = (__version__, [f"agentprov=={__version__}"])
        self.kind = kind
        self.calls: list[list[str]] = []
        self.installer_code = 0
        self.installs = True

    def have(self, name: str) -> tuple[str, list[str]] | None:
        return self.dists.get(name)

    def run(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(argv))
        assert kw.get("check") is False and "PIP_INDEX_URL" not in kw["env"]
        if self.installer_code == 0 and self.installs:
            for path in (a for a in argv if a.endswith(".whl")):
                name = Path(path).name.split("-")[0].replace("_", "-")
                self.dists[name] = (NEW, list(self.dists[name][1]))
        return subprocess.CompletedProcess(argv, self.installer_code, b"", b"Successfully installed")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, no_keys: Path) -> Env:
    e = Env()
    monkeypatch.setattr(update_cmd, "SIGNERS", no_keys)
    monkeypatch.setattr(update_cmd, "KIND", lambda: {"kind": e.kind, "command": ["x"], "text": f"upgrade {e.kind}"})
    monkeypatch.setattr(update_cmd, "HAVE", e.have)
    monkeypatch.setattr(update_cmd, "WHICH", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(update_cmd, "HAS_PIP", lambda: True)
    monkeypatch.setattr(update_cmd, "INSTALL_RUN", e.run)
    return e


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv, "--progress", "off"])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _wheels(tmp_path: Path, *, zenodo: bool = False, ap_requires: list[str] | None = None,
            **ap: Any) -> dict[str, bytes]:
    d = tmp_path / "built"
    d.mkdir(exist_ok=True)
    files = {p.name: p.read_bytes() for p in (
        us.wheel(d, "agentprov_capture", NEW, ["rfc8785>=0.1.4"]),
        us.wheel(d, "agentprov", NEW, requires(NEW) if ap_requires is None else ap_requires, **ap),
        *((us.wheel(d, "agentprov_zenodo", NEW, [f"agentprov=={NEW}"]),) if zenodo else ()))}
    return files


def _github(files: dict[str, bytes], *, sums: bytes | None = None, sig: bytes | None = None,
            served: dict[str, bytes] | None = None) -> us.FakeTransport:
    """A fake GitHub release of ``files`` with their SHA256SUMS (``served`` replaces bytes after the list was made)."""
    listed = sums if sums is not None else "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n"
                                                   for n, b in sorted(files.items())).encode()
    body = {**files, **(served or {}), "SHA256SUMS": listed, **({"SHA256SUMS.sig": sig} if sig is not None else {})}
    routes: dict[str, Any] = {R.API_URL: us.answer(us.release(TAG, [(n, len(b)) for n, b in body.items()]))}
    routes.update({f"{us.REPO_DL}/{TAG}/{n}": b for n, b in body.items()})
    return us.FakeTransport(routes)


def _serve(monkeypatch: pytest.MonkeyPatch, t: us.FakeTransport) -> us.FakeTransport:
    monkeypatch.setattr(update_cmd, "transport", lambda: t)
    return t


# ---------------------------------------------------------------------------------------------- download


def test_download_package_stages_the_wheels_after_the_checksum_list(cli, env: Env, monkeypatch, tmp_path: Path,
                                                                    home: Path) -> None:
    t = _serve(monkeypatch, _github(_wheels(tmp_path, zenodo=True)))
    run = cli("update", "download", "--package", "--allow-network", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    staged = home / "update" / "staging" / "package"
    assert (doc["format"], doc["kind"], doc["install_kind"]) == ("agentprov-update-download/0.1", "package", "pip")
    assert (doc["from_version"], doc["to_version"], doc["verification"]) == (__version__, NEW, "sha256")
    assert doc["installable"] is True and doc["problems"] == [] and doc["keeps_previous"] is False
    assert doc["restore_command"].endswith(f"agentprov=={__version__} agentprov-capture=={__version__}")
    names = [u.rsplit("/", 1)[-1] for u, _ in t.calls]
    assert names == ["releases?per_page=20", "SHA256SUMS", f"agentprov_capture-{NEW}-py3-none-any.whl",
                     f"agentprov-{NEW}-py3-none-any.whl"]  # the list first; the uploader is not installed here
    assert all(u.startswith(("https://api.github.com/", R.DOWNLOAD_BASE)) for u, _ in t.calls)  # never PyPI
    argv = doc["installer_argv"]
    assert argv[:8] == [sys.executable, "-m", "pip", "install", "--isolated", "--no-deps", "--no-index",
                        "--disable-pip-version-check"]
    assert [Path(a).parent for a in argv if a.endswith(".whl")] == [staged, staged]
    assert {p["dist"]: (p["from_version"], p["to_version"]) for p in doc["parts"]} == {
        "agentprov-capture": (__version__, NEW), "agentprov": (__version__, NEW)}


def test_the_uploader_wheel_comes_too_when_it_is_installed(cli, env: Env, monkeypatch, tmp_path: Path) -> None:
    env.dists["agentprov-zenodo"] = (__version__, [f"agentprov=={__version__}"])
    t = _serve(monkeypatch, _github(_wheels(tmp_path, zenodo=True)))
    doc = json.loads(cli("update", "download", "--package", "--allow-network", "--format", "json").out)
    assert [w["dist"] for w in doc["wheels"]] == ["agentprov-capture", "agentprov", "agentprov-zenodo"]
    assert t.calls[-1][0].endswith(f"agentprov_zenodo-{NEW}-py3-none-any.whl")


def test_download_package_needs_allow_network(cli, env: Env) -> None:
    assert cli("update", "download", "--package").code == 4


@pytest.mark.parametrize("kind", ["checkout", "bundle"])
def test_download_package_is_refused_for_a_checkout_or_the_bundles_own_agentprov(cli, env: Env, kind: str) -> None:
    env.kind = kind
    run = cli("update", "download", "--package", "--allow-network")
    assert run.code == 4 and "update.package.kind" in run.err


@pytest.mark.parametrize("case", ["tampered wheel", "not listed", "wrong metadata", "traversal", "missing wheel"])
def test_a_tampered_or_malformed_wheel_is_refused_and_nothing_is_kept(cli, env: Env, monkeypatch, tmp_path: Path,
                                                                     home: Path, case: str) -> None:
    files = _wheels(tmp_path, meta_version="9.0.1" if case == "wrong metadata" else None,
                    extra=[("../evil.py", b"x")] if case == "traversal" else ())
    ap = f"agentprov-{NEW}-py3-none-any.whl"
    flipped = bytearray(files[ap])
    flipped[len(flipped) // 2] ^= 0xFF
    served = {ap: bytes(flipped)} if case == "tampered wheel" else None
    sums = None
    if case == "not listed":
        sums = f"{hashlib.sha256(files[ap]).hexdigest()}  {ap}\n".encode()
    if case == "missing wheel":
        del files[f"agentprov_capture-{NEW}-py3-none-any.whl"]
    _serve(monkeypatch, _github(files, sums=sums, served=served))
    run = cli("update", "download", "--package", "--allow-network")
    code = {"tampered wheel": "update.verify.sha256", "not listed": "update.verify.missing",
            "wrong metadata": "update.package.wheel", "traversal": "update.package.wheel",
            "missing wheel": "update.download.missing"}[case]
    assert run.code == 1 and code in run.err, run.err
    assert not (home / "update" / "staging" / "package").exists()
    assert env.calls == []


# ---------------------------------------------------------------------------------------------- the signature


def _keypair(tmp_path: Path, name: str) -> tuple[Path, str]:
    key = tmp_path / name
    subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, key.with_suffix(".pub").read_text().strip()


@needs_ssh_keygen
@pytest.mark.parametrize("case", ["good", "tampered signature", "other key", "unsigned"])
def test_with_a_listed_key_the_wheels_need_a_valid_signature(cli, env: Env, monkeypatch, tmp_path: Path, home: Path,
                                                             case: str) -> None:
    key, pub = _keypair(tmp_path, "release")
    other, _ = _keypair(tmp_path, "other")
    signers = tmp_path / "allowed_signers"
    signers.write_text(f'agentprov-release namespaces="file" {pub}\n')
    monkeypatch.setattr(update_cmd, "SIGNERS", signers)
    files = _wheels(tmp_path)
    sums = tmp_path / "SHA256SUMS"
    sums.write_bytes("".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(files.items())).encode())
    signer = other if case == "other key" else key
    subprocess.run([SSH_KEYGEN, "-q", "-Y", "sign", "-f", str(signer), "-n", "file", str(sums)], check=True,
                   capture_output=True)
    sig = (tmp_path / "SHA256SUMS.sig").read_bytes()
    if case == "tampered signature":
        lines = sig.split(b"\n")
        lines[2] = lines[2][:-4] + (b"AAAA" if not lines[2].endswith(b"AAAA") else b"BBBB")
        sig = b"\n".join(lines)
    t = _serve(monkeypatch, _github(files, sums=sums.read_bytes(), sig=None if case == "unsigned" else sig))
    run = cli("update", "download", "--package", "--allow-network", "--format", "json")
    if case == "good":
        assert run.code == 0, run.err
        doc = json.loads(run.out)
        assert (doc["verification"], doc["signed_by"]) == ("sha256+signature", "agentprov-release")
        assert cli("update", "install", "--package", "--confirm").code == 0 and env.calls
        return
    code = "update.verify.unsigned" if case == "unsigned" else "update.verify.signature"
    assert run.code == 1 and code in run.err, run.err
    assert not any(u.endswith(".whl") for u, _ in t.calls)  # no wheel is fetched before the list is trusted
    assert not (home / "update" / "staging" / "package").exists() and env.calls == []


# ---------------------------------------------------------------------------------------------- install


def test_install_package_runs_the_installer_on_the_verified_files_only(cli, env: Env, monkeypatch, tmp_path: Path,
                                                                       home: Path) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    refused = cli("update", "install", "--package")
    assert refused.code == 4 and "--confirm" in refused.err and env.calls == []
    run = cli("update", "install", "--package", "--confirm", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert (doc["kind"], doc["action"], doc["from_version"], doc["to_version"]) == ("package", "installed",
                                                                                    __version__, NEW)
    assert doc["keeps_previous"] is False and doc["installed"] == {"agentprov-capture": NEW, "agentprov": NEW}
    (argv,) = env.calls
    staged = home / "update" / "staging" / "package"
    assert "--no-deps" in argv and "--no-index" in argv
    assert [a for a in argv if a.endswith(".whl")] == [str(staged / f"agentprov_capture-{NEW}-py3-none-any.whl"),
                                                       str(staged / f"agentprov-{NEW}-py3-none-any.whl")]
    record = json.loads((home / "update" / "package-installed.json").read_text())
    assert record["to_version"] == NEW and record["installer"] == "pip"
    assert any("previous version is not kept" in line for line in doc["lines"])


def test_a_wheel_changed_after_the_download_is_not_installed(cli, env: Env, monkeypatch, tmp_path: Path,
                                                             home: Path) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    path = home / "update" / "staging" / "package" / f"agentprov-{NEW}-py3-none-any.whl"
    path.write_bytes(path.read_bytes() + b"\0")
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 1 and "update.verify.sha256" in run.err and env.calls == []


def test_a_changed_checksum_list_after_the_download_is_not_installed(cli, env: Env, monkeypatch,
                                                                     tmp_path: Path, home: Path) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    sums = home / "update" / "staging" / "package" / "SHA256SUMS"
    sums.write_bytes(sums.read_bytes() + ("0" * 64 + "  extra.whl\n").encode())
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 1 and "update.verify.sums" in run.err and env.calls == []


@pytest.mark.parametrize(("ap_requires", "why"), [
    ([*requires(NEW), "numpy>=2"], "needs numpy>=2"),
    ([r.replace("psutil>=7.2,<9", "psutil>=8") for r in requires(NEW)], "needs psutil>=8"),
    ([r.replace(f"agentprov-capture=={NEW}", "agentprov-capture>=0.1") for r in requires(NEW)],
     f"does not pin agentprov-capture to {NEW}"),
])
def test_a_release_that_needs_another_dependency_is_not_installed(cli, env: Env, monkeypatch, tmp_path: Path,
                                                                  ap_requires: list[str], why: str) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path, ap_requires=ap_requires)))
    run = cli("update", "download", "--package", "--allow-network", "--format", "json")
    doc = json.loads(run.out)
    assert run.code == 0 and doc["installable"] is False and any(why in p for p in doc["problems"]), doc["problems"]
    refused = cli("update", "install", "--package", "--confirm")
    assert refused.code == 4 and "update.package.dependencies" in refused.err and "upgrade pip" in refused.err
    assert env.calls == []


def test_a_failed_installer_or_a_version_that_did_not_change_is_reported(cli, env: Env, monkeypatch,
                                                                         tmp_path: Path) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    env.installer_code = 1
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 1 and "update.package.installer" in run.err
    env.installer_code, env.installs = 0, False
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 1 and "update.package.installed" in run.err


def test_the_same_version_is_current_and_an_older_one_refused(cli, env: Env, monkeypatch, tmp_path: Path) -> None:
    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    monkeypatch.setattr("agentprov.versions.__version__", NEW)
    doc = json.loads(cli("update", "install", "--package", "--confirm", "--format", "json").out)
    assert doc["action"] == "current" and env.calls == []
    monkeypatch.setattr("agentprov.versions.__version__", "9.1.0")
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 4 and "update.install.downgrade" in run.err and env.calls == []


def test_without_a_download_install_package_says_so(cli, env: Env) -> None:
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 4 and "update download --package" in run.err


def test_bundle_package_and_checkout_cannot_be_combined(cli, env: Env, tmp_path: Path) -> None:
    assert cli("update", "install", "--package", "--checkout", "--confirm").code == 2
    assert cli("update", "install", "--allow-network").code == 2


# ---------------------------------------------------------------------------------------------- the installers


@pytest.mark.parametrize(("kind", "pip", "tools", "head"), [
    ("pip", True, {}, ["/py", "-m", "pip", "install", "--isolated", "--no-deps", "--no-index"]),
    ("pip", False, {"uv": "/bin/uv"}, ["/bin/uv", "pip", "install", "--no-config", "--python", "/py", "--no-deps",
                                      "--no-index"]),
    ("pip", False, {}, None),
    ("uv-tool", True, {"uv": "/bin/uv"}, ["/bin/uv", "pip", "install", "--no-config", "--python", "/py", "--no-deps",
                                         "--no-index"]),
    ("uv-tool", True, {}, None),
    ("pipx", True, {"pipx": "/bin/pipx"}, ["/bin/pipx", "runpip", "agentprov", "install", "--isolated", "--no-deps",
                                          "--no-index"]),
    ("pipx", True, {}, None),
    ("checkout", True, {"uv": "/bin/uv"}, None),
])
def test_each_installer_installs_the_files_without_resolving(kind: str, pip: bool, tools: dict[str, str],
                                                             head: list[str] | None) -> None:
    argv, how = P.installer_argv(kind, ["/s/a.whl"], prefix="/home/u/.local/pipx/venvs/agentprov", executable="/py",
                                 which=tools.get, has_pip=lambda: pip, user=False)
    if head is None:
        assert argv is None and how
    else:
        assert argv is not None and argv[:len(head)] == head and argv[-1] == "/s/a.whl"


def test_a_user_site_install_is_upgraded_in_the_user_site(tmp_path: Path) -> None:
    """D-1130 review: without --user, pip writes the base environment and the old user-site copy stays first."""
    argv, how = P.installer_argv("pip", ["/s/a.whl"], executable="/py", which={"uv": "/bin/uv"}.get,
                                 has_pip=lambda: True, user=True)
    assert argv is not None and "--user" in argv and argv[-1] == "/s/a.whl" and how == "pip"
    argv, how = P.installer_argv("pip", ["/s/a.whl"], executable="/py", which={"uv": "/bin/uv"}.get,
                                 has_pip=lambda: False, user=True)
    assert argv is None and "user site" in how  # uv pip has no user installs: never into the base environment
    site = tmp_path / "user-site"
    site.mkdir()
    assert P.user_site_install(location=site.resolve(), user_site=str(site))
    assert not P.user_site_install(location=tmp_path.resolve(), user_site=str(site))
    assert not P.user_site_install()  # this test environment is a virtual environment


def test_the_job_guard_covers_every_folder_a_package_upgrade_replaces(tmp_path: Path) -> None:
    """D-1130 review: a user-site install's files and its ~/.local/bin command are outside sys.prefix, and a uv tool's
    command on Windows is a copy outside the tool's environment."""
    bin_cmd = tmp_path / "bin" / "agentprov"
    folders = P.install_folders("uv-tool", prefix=str(tmp_path / "env"), which=lambda n: str(tmp_path / "copy.exe"),
                                files=lambda: [bin_cmd])
    assert folders[0] == tmp_path / "env" and bin_cmd in folders and tmp_path / "copy.exe" in folders
    assert tmp_path / "copy.exe" not in P.install_folders("pip", prefix=str(tmp_path / "env"),
                                                          which=lambda n: str(tmp_path / "copy.exe"), files=list)
    from importlib import metadata

    real = [f.resolve() for f in P.install_folders("pip")]
    assert Path(str(metadata.distribution("agentprov").locate_file(""))).resolve() in real  # its site-packages


def test_the_restore_command_takes_the_uploader_back_too() -> None:
    zenodo = lambda name: ("0.2.1", []) if name == "agentprov-zenodo" else None  # noqa: E731
    posix = os.name != "nt"
    with_extra = "'agentprov[zenodo]==0.2.1'" if posix else "agentprov[zenodo]==0.2.1"
    assert P.restore_command("uv-tool", "0.2.1", have=zenodo) == f"uv tool install --force {with_extra}"
    assert P.restore_command("pipx", "0.2.1", have=lambda n: None) == "pipx install --force agentprov==0.2.1"
    assert P.restore_command("pip", "0.2.1", executable="/py", have=zenodo, user=False).endswith(
        "agentprov-zenodo==0.2.1")


@pytest.mark.skipif(os.name == "nt", reason="a POSIX shell's words")
def test_the_restore_command_pastes_into_a_shell_as_its_words() -> None:
    """zsh (the macOS default shell) reads an unquoted [zenodo] as a glob and refuses the line ("no matches found")."""
    import shlex

    zenodo = lambda name: ("0.2.1", []) if name == "agentprov-zenodo" else None  # noqa: E731
    for kind, words in (("uv-tool", ["uv", "tool", "install", "--force", "agentprov[zenodo]==0.2.1"]),
                        ("pipx", ["pipx", "install", "--force", "agentprov[zenodo]==0.2.1"])):
        assert shlex.split(P.restore_command(kind, "0.2.1", have=zenodo) or "") == words


def test_the_restore_command_of_a_user_site_install_goes_back_into_the_user_site() -> None:
    """Without --user, pip installs the old version into a writable base site-packages, and the newer copy in the user
    site stays first on sys.path: nothing goes back (the installer passes --user for the same reason)."""
    none = lambda n: None  # noqa: E731
    assert " install --user agentprov==0.2.1 " in P.restore_command("pip", "0.2.1", executable="/py", have=none,
                                                                     user=True) or ""
    assert "--user" not in (P.restore_command("pip", "0.2.1", executable="/py", have=none, user=False) or "")


def test_the_installer_environment_drops_what_points_pip_or_uv_elsewhere() -> None:
    env = P.installer_env({"PATH": "/bin", "PIP_INDEX_URL": "https://evil", "UV_INDEX_URL": "x", "PYTHONPATH": "/p",
                           "HOME": "/h", "VIRTUAL_ENV": "/v"})
    assert env == {"PATH": "/bin", "HOME": "/h"}


def test_wheel_metadata_reads_the_requirements(tmp_path: Path) -> None:
    path = us.wheel(tmp_path, "agentprov", NEW, requires(NEW))
    assert P.wheel_metadata(path, "agentprov", NEW) == requires(NEW)
    with pytest.raises(UpdateError):
        P.wheel_metadata(path, "agentprov", "9.0.1")
    (tmp_path / "x.whl").write_bytes(b"not a zip")
    with pytest.raises(UpdateError):
        P.wheel_metadata(tmp_path / "x.whl", "agentprov", NEW)


# ---------------------------------------------------------------------------------------------- the plan command


def test_install_without_flags_says_which_automatic_path_applies(cli, env: Env, monkeypatch) -> None:
    doc = json.loads(cli("update", "install", "--format", "json").out)
    assert doc["action"] == "command" and doc["automatic"]["how"] == "package"
    assert doc["automatic"]["available"] is True and doc["automatic"]["installer"] == "pip"
    env.kind = "uv-tool"
    monkeypatch.setattr(update_cmd, "WHICH", lambda n: None)
    doc = json.loads(cli("update", "install", "--format", "json").out)
    assert doc["automatic"] == {"how": "package", "available": False, "why": "uv is not on PATH", "installer": None,
                                "argv": ["update", "download", "--package", "--allow-network"]}
    assert any("cannot do it here: uv is not on PATH" in line for line in doc["lines"])


def test_the_bundles_own_agentprov_is_updated_with_the_app() -> None:
    got = I.package_install(frozen=True)
    assert got["kind"] == "bundle" and got["command"] is None and "updated with the app" in got["text"]


def test_a_package_install_is_not_upgraded_under_a_running_job(cli, env: Env, monkeypatch, tmp_path: Path) -> None:
    class Job:
        job_id, state, command, record = "job-1", "running", "import", {"label": "import"}
        argv = [str(Path(sys.prefix) / "bin" / "python"), "-I", "-m", "agentprov"]

    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    monkeypatch.setattr(update_cmd, "JOBS", lambda _h: [Job()])
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 4 and "update.install.busy" in run.err and env.calls == []


def test_a_job_run_from_a_user_site_command_also_blocks_the_upgrade(cli, env: Env, monkeypatch, tmp_path: Path) -> None:
    """D-1130 review: ~/.local/bin/agentprov of a pip --user install is not in sys.prefix, and was not seen."""
    user_bin = tmp_path / "home" / ".local" / "bin" / "agentprov"

    class Job:
        job_id, state, command, record = "job-2", "running", "derive", {"label": "derive"}
        argv = [str(user_bin), "derive", "--corpus", "c"]

    _serve(monkeypatch, _github(_wheels(tmp_path)))
    assert cli("update", "download", "--package", "--allow-network").code == 0
    monkeypatch.setattr(update_cmd, "JOBS", lambda _h: [Job()])
    monkeypatch.setattr(update_cmd, "FOLDERS", lambda kind: [Path(sys.prefix), user_bin])
    run = cli("update", "install", "--package", "--confirm")
    assert run.code == 4 and "update.install.busy" in run.err and "job-2" in run.err and env.calls == []
