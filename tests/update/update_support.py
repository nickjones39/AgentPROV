"""Fakes for the D-1065 update tests: no socket is ever opened and no real disk image is attached.

* :class:`FakeTransport` answers the ``agentprov.raw.fetch.Transport`` seam from a URL table and records each request
  (URL and allow-list);
* :func:`release` builds a GitHub ``/releases`` entry; :func:`linux_tar`, :func:`windows_zip` and :func:`macos_app`
  build small bundle archives and trees; :func:`dmg_run` stands in for ``hdiutil`` and ``ditto``.
"""

from __future__ import annotations

import io
import json
import plistlib
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_DL = "https://github.com/nickjones39/AgentPROV/releases/download"


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, url: str = "", headers: Mapping[str, str] | None = None):
        self._buf = io.BytesIO(body)
        self.status = status
        self.url = url
        self.headers = dict(headers or {})
        self.closed = False

    def read(self, n: int = -1, /) -> bytes:
        return self._buf.read(n)

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeTransport:
    routes: dict[str, Any] = field(default_factory=dict)
    calls: list[tuple[str, frozenset[str]]] = field(default_factory=list)

    def open(self, url: str, *, headers: Mapping[str, str], unredirected: Mapping[str, str], timeout: float,
             allowed_hosts: frozenset[str]) -> FakeResponse:
        self.calls.append((url, allowed_hosts))
        assert "Authorization" not in headers and not unredirected, "no credential is ever sent"
        answer = self.routes.get(url)
        if answer is None:
            return FakeResponse(b"not found", status=404, url=url)
        if isinstance(answer, FakeResponse):
            answer._buf.seek(0)
            if not answer.url:
                answer.url = url
            return answer
        final = url.replace("https://github.com/", "https://release-assets.githubusercontent.com/") \
            if url.startswith(REPO_DL) else url  # the asset CDN, as GitHub redirects
        return FakeResponse(answer, url=final)


def release(tag: str, assets: Sequence[tuple[str, int]] = (), *, draft: bool = False, prerelease: bool = False,
            body: str | None = "Release notes.", published: str = "2026-11-04T01:02:03Z",
            url_for: Callable[[str, str], str] | None = None) -> dict[str, Any]:
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "published_at": published,
            "html_url": f"https://github.com/nickjones39/AgentPROV/releases/tag/{tag}", "body": body,
            "assets": [{"name": n, "size": s, "state": "uploaded", "content_type": "application/octet-stream",
                        "browser_download_url": (url_for or (lambda t, n: f"{REPO_DL}/{t}/{n}"))(tag, n)}
                       for n, s in assets]}


def answer(*releases: Mapping[str, Any]) -> bytes:
    return json.dumps(list(releases)).encode()


def _info(name: str, *, kind: bytes = tarfile.REGTYPE, size: int = 0, mode: int = 0o644,
          link: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type, info.size, info.mode, info.linkname = kind, size, mode, link
    return info


def linux_tar(path: Path, version: str = "0.1.2", *, extra: Sequence[tuple[tarfile.TarInfo, bytes]] = (),
              top: str = "AgentPROV") -> Path:
    """A Linux bundle archive: the executable (0755), a library, and a relative link to it."""
    with tarfile.open(path, "w:gz") as tf:
        tf.addfile(_info(top, kind=tarfile.DIRTYPE, mode=0o755))
        exe = f"#!/bin/sh\necho {version}\n".encode()
        tf.addfile(_info(f"{top}/AgentPROV", size=len(exe), mode=0o755), io.BytesIO(exe))
        tf.addfile(_info(f"{top}/_internal", kind=tarfile.DIRTYPE, mode=0o755))
        tf.addfile(_info(f"{top}/_internal/libx.so.1", size=3), io.BytesIO(b"lib"))
        tf.addfile(_info(f"{top}/_internal/libx.so", kind=tarfile.SYMTYPE, link="libx.so.1"))
        for info, data in extra:
            tf.addfile(info, io.BytesIO(data) if data else None)
    return path


def tar_entry(name: str, **kw: Any) -> tuple[tarfile.TarInfo, bytes]:
    data = kw.pop("data", b"")
    return _info(name, size=len(data), **kw), data


def windows_zip(path: Path, version: str = "0.1.2", *, extra: Sequence[tuple[zipfile.ZipInfo | str, bytes]] = ()) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AgentPROV/AgentPROV.exe", f"MZ {version}".encode())
        zf.writestr("AgentPROV/_internal/python314.dll", b"dll")
        for name, data in extra:
            zf.writestr(name, data)
    return path


def macos_app(root: Path, version: str = "0.1.2") -> Path:
    """An ``AgentPROV.app`` tree with ``Info.plist`` and a framework-style relative link."""
    app = root / "AgentPROV.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    (app / "Contents" / "Frameworks").mkdir()
    exe = app / "Contents" / "MacOS" / "AgentPROV"
    exe.write_bytes(f"macho {version}".encode())
    exe.chmod(0o755)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": version,
                                                                  "CFBundleIdentifier": "org.agentprov.gui"}))
    (app / "Contents" / "Resources" / "data.txt").write_bytes(b"data")
    (app / "Contents" / "Frameworks" / "data.txt").symlink_to("../Resources/data.txt")
    return app


def dmg_run(source_app: Path, log: list[list[str]] | None = None) -> Callable[..., subprocess.CompletedProcess[str]]:
    """``hdiutil attach`` copies ``source_app`` into the mount point; ``ditto`` copies a tree; ``detach`` empties it."""

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if log is not None:
            log.append(list(argv))
        if argv[:2] == ["hdiutil", "attach"]:
            mount = Path(argv[argv.index("-mountpoint") + 1])
            shutil.copytree(source_app, mount / source_app.name, symlinks=True)
        elif argv[0] == "ditto":
            shutil.copytree(argv[1], argv[2], symlinks=True)
        elif argv[:2] == ["hdiutil", "detach"]:
            mount = Path(argv[-1])
            for child in mount.iterdir():
                shutil.rmtree(child)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def wheel(directory: Path, dist: str, version: str, requires: Sequence[str] = (), *, name: str | None = None,
          meta_version: str | None = None, extra: Sequence[tuple[str, bytes]] = ()) -> Path:
    """A small pure-Python wheel (D-1130): a module, ``<dist>-<version>.dist-info/METADATA`` and ``WHEEL``."""
    path = directory / (name or f"{dist}-{version}-py3-none-any.whl")
    lines = ["Metadata-Version: 2.4", f"Name: {dist.replace('_', '-')}", f"Version: {meta_version or version}",
             *(f"Requires-Dist: {r}" for r in requires), "", ""]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{dist}/__init__.py", f"__version__ = {version!r}\n")
        zf.writestr(f"{dist}-{version}.dist-info/METADATA", "\n".join(lines))
        zf.writestr(f"{dist}-{version}.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n")
        for member, data in extra:
            zf.writestr(member, data)
    return path
