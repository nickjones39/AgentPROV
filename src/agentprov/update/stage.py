"""The staged download (D-1065): ``agentprov update download`` fetches and verifies; ``install`` verifies again.

The staging folder (``$AGENTPROV_HOME/update/staging/<platform>/``, or ``--dir``) holds ``SHA256SUMS``, the signature
when the release publishes one, this platform's bundle archive and ``staged.json`` (``agentprov-update-staged/0.1``).
The order is fixed: the checksum list and its signature first (verified by :func:`agentprov.update.verify.verify_release`
before the bundle is fetched), then the bundle, whose sha256 must be the list's, then the archive's member checks
(:func:`agentprov.update.unpack.check_archive`). Nothing is unpacked here. A failure removes what was fetched.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
    bundle_asset_name,
    download,
    update_dir,
)
from agentprov.update.unpack import check_archive
from agentprov.update.verify import SIG_MAX_BYTES, SUMS_MAX_BYTES, parse_sums, sha256_file, verify_release

__all__ = ["STAGED_FORMAT", "load_staged", "stage_release", "staging_dir"]

STAGED_FORMAT: Final = "agentprov-update-staged/0.1"
_MARKER: Final = ".agentprov-update-staging"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=64 * 1024, max_json_depth=8)


def staging_dir(home: Path, label: str) -> Path:
    return update_dir(home) / "staging" / label


def _fresh(directory: Path) -> None:
    """Empty ``directory`` for a new download: only a folder this module made (its marker) is cleared."""
    if directory.exists() or directory.is_symlink():
        if directory.is_symlink() or not directory.is_dir():
            raise UpdateError("the staging folder is not a folder", code="update.stage", exit_code=2)
        if any(directory.iterdir()) and not (directory / _MARKER).is_file():
            raise UpdateError("the staging folder is not empty and was not made by agentprov update",
                              code="update.stage", exit_code=2)
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    (directory / _MARKER).write_bytes(b"D-1065\n")


def stage_release(transport: Any, release: Release, label: str, directory: Path, *,
                  signers: Path = ALLOWED_SIGNERS, ssh_keygen: str | None = None, run: Any = None) -> dict[str, Any]:
    """Download and verify this platform's bundle of ``release`` into ``directory``; the ``staged.json`` record."""
    name = bundle_asset_name(label)
    bundle, sums = release.asset(name), release.asset(CHECKSUM_ASSET)
    if bundle is None:
        raise UpdateError(f"release {release.tag} has no bundle for {label}", code="update.download.missing")
    if sums is None:
        raise UpdateError(f"release {release.tag} publishes no {CHECKSUM_ASSET}: refused",
                          code="update.verify.missing")
    sig = release.asset(SIGNATURE_ASSET)
    _fresh(directory)
    try:
        download(transport, sums, directory / CHECKSUM_ASSET, max_bytes=SUMS_MAX_BYTES)
        if sig is not None:
            download(transport, sig, directory / SIGNATURE_ASSET, max_bytes=SIG_MAX_BYTES)
        kw: dict[str, Any] = {"signers": signers, "ssh_keygen": ssh_keygen}
        if run is not None:
            kw["run"] = run
        verification = verify_release(directory / CHECKSUM_ASSET, directory / SIGNATURE_ASSET if sig else None, **kw)
        listed = parse_sums((directory / CHECKSUM_ASSET).read_bytes())
        if name not in listed:
            raise UpdateError(f"{CHECKSUM_ASSET} does not list {name}: refused", code="update.verify.missing")
        digest = download(transport, bundle, directory / name)
        if digest != listed[name]:
            raise UpdateError(f"{name}'s sha256 is not the one {CHECKSUM_ASSET} lists: refused",
                              code="update.verify.sha256")
        members = check_archive(directory / name, label)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    record = {"format": STAGED_FORMAT, "tag": release.tag, "version": release.version, "platform": label,
              "asset": {"name": name, "size": bundle.size, "sha256": digest},
              "checksum": {"name": CHECKSUM_ASSET, "sha256": sha256_file(directory / CHECKSUM_ASSET)},
              "signature": None if sig is None else {"name": SIGNATURE_ASSET,
                                                     "sha256": sha256_file(directory / SIGNATURE_ASSET)},
              **verification.to_json(), "members_checked": members}
    (directory / "staged.json").write_bytes(json.dumps(record, sort_keys=True, indent=1).encode("utf-8") + b"\n")
    return {**record, "dir": str(directory)}


def load_staged(directory: Path, label: str, *, signers: Path = ALLOWED_SIGNERS, ssh_keygen: str | None = None,
                run: Any = None) -> tuple[dict[str, Any], Path]:
    """The staged record and its archive, verified again (the files may have changed since ``download``)."""
    try:
        with open(directory / "staged.json", "rb") as fh:
            doc = strict_json_loads(fh.read(64 * 1024 + 1).rstrip(b"\n"), _LIMITS)
    except OSError:
        raise UpdateError("nothing is staged: run agentprov update download --allow-network first",
                          code="update.stage.none", exit_code=4) from None
    except IngestError:
        raise UpdateError("staged.json is not readable", code="update.stage") from None
    name = bundle_asset_name(label)
    asset = doc.get("asset") if isinstance(doc, dict) else None
    if (not isinstance(doc, dict) or doc.get("format") != STAGED_FORMAT or doc.get("platform") != label
            or not isinstance(asset, dict) or asset.get("name") != name or not isinstance(doc.get("version"), str)):
        raise UpdateError("the staged download is not this platform's bundle", code="update.stage")
    archive = directory / name
    kw: dict[str, Any] = {"signers": signers, "ssh_keygen": ssh_keygen}
    if run is not None:
        kw["run"] = run
    sig = directory / SIGNATURE_ASSET
    verification = verify_release(directory / CHECKSUM_ASSET, sig if sig.is_file() else None, **kw)
    listed = parse_sums((directory / CHECKSUM_ASSET).read_bytes())
    digest = sha256_file(archive) if archive.is_file() else None
    if digest is None or digest != listed.get(name) or digest != asset.get("sha256"):
        raise UpdateError(f"the staged {name} no longer matches {CHECKSUM_ASSET}: download it again",
                          code="update.verify.sha256")
    if hashlib.sha256((directory / CHECKSUM_ASSET).read_bytes()).hexdigest() != (doc.get("checksum") or {}).get(
            "sha256"):
        raise UpdateError(f"the staged {CHECKSUM_ASSET} changed since it was downloaded", code="update.verify.sums")
    return {**doc, **verification.to_json(), "dir": str(directory)}, archive
