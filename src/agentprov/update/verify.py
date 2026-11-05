"""What makes a downloaded release file trusted (D-1065): its sha256 in ``SHA256SUMS``, and that list's signature.

``SHA256SUMS`` is the release's list of every file (``<64 hex>  <name>``, LF, sorted; the v0.1.0 and v0.1.1 format),
parsed strictly: ASCII only, one entry per line, no name twice, at most :data:`SUMS_MAX_BYTES`.

``SHA256SUMS.sig`` is an SSH signature (``ssh-keygen -Y sign -n file``). It is checked with
``ssh-keygen -Y verify -f allowed_signers -I PRINCIPAL -n file -s SHA256SUMS.sig < SHA256SUMS`` against the keys in the
package's ``agentprov/update/data/allowed_signers``, one principal at a time. OpenSSH's ``ssh-keygen`` comes with macOS,
Linux distributions and Windows 10 and later, so no library is added. The rule:

* the package lists a key: the release must publish ``SHA256SUMS.sig`` and it must verify under one of the keys, or the
  update is refused (``update.verify.unsigned``, ``update.verify.signature``); without ``ssh-keygen`` it is refused too
  (exit 3);
* the package lists no key: the files are checked against ``SHA256SUMS`` alone, which came over https from the same
  release; the result says ``"verification": "sha256"`` so nobody reads it as a signature.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.update import ALLOWED_SIGNERS
from agentprov.update.releases import UpdateError

__all__ = ["SIG_MAX_BYTES", "SUMS_MAX_BYTES", "Verification", "load_signers", "parse_sums", "sha256_file",
           "verify_release", "verify_signature"]

SUMS_MAX_BYTES: Final = 1024 * 1024
SIG_MAX_BYTES: Final = 64 * 1024
SIGNERS_MAX_BYTES: Final = 64 * 1024
_LINE: Final = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,199})")
_PRINCIPAL: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,99}")
_KEY_TYPES: Final = frozenset({"ssh-ed25519", "sk-ssh-ed25519@openssh.com", "ecdsa-sha2-nistp256",
                               "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521", "sk-ecdsa-sha2-nistp256@openssh.com",
                               "ssh-rsa", "rsa-sha2-256", "rsa-sha2-512"})
#: the namespace the release signs in (``-n file``, as the v0.1.0 and v0.1.1 signatures)
NAMESPACE: Final = "file"


@dataclass(frozen=True, slots=True)
class Verification:
    level: str  # "sha256+signature" or "sha256"
    principal: str | None  # the key's principal that verified, when signed

    def to_json(self) -> dict[str, Any]:
        return {"verification": self.level, "signed_by": self.principal}


def parse_sums(data: bytes) -> dict[str, str]:
    """``SHA256SUMS`` as ``{name: sha256}``; anything but the strict format refuses the whole list."""
    if len(data) > SUMS_MAX_BYTES:
        raise UpdateError("SHA256SUMS is larger than 1 MiB", code="update.verify.sums")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise UpdateError("SHA256SUMS is not ASCII", code="update.verify.sums") from None
    if not text.endswith("\n") or "\r" in text:
        raise UpdateError("SHA256SUMS is not LF-terminated lines", code="update.verify.sums")
    out: dict[str, str] = {}
    for line in text[:-1].split("\n"):
        m = _LINE.fullmatch(line)
        if m is None:
            raise UpdateError("SHA256SUMS has a line that is not '<sha256>  <name>'", code="update.verify.sums")
        if m.group(2) in out:
            raise UpdateError("SHA256SUMS lists a file twice", code="update.verify.sums")
        out[m.group(2)] = m.group(1)
    if not out:
        raise UpdateError("SHA256SUMS is empty", code="update.verify.sums")
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_signers(path: Path = ALLOWED_SIGNERS) -> list[str]:
    """The principals of the keys in an allowed-signers file (comments and blank lines skipped). A line that is not a
    public key entry, or any private-key text, refuses the file: it ships in the package and is read as trusted."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(SIGNERS_MAX_BYTES + 1)
    except OSError:
        return []
    if len(data) > SIGNERS_MAX_BYTES or b"PRIVATE KEY" in data:
        raise UpdateError("the package's allowed_signers file is not a list of public keys", code="update.verify.keys")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise UpdateError("the package's allowed_signers file is not ASCII", code="update.verify.keys") from None
    principals: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        names = fields[0].split(",")
        if len(fields) < 3 or not all(_PRINCIPAL.fullmatch(n) for n in names) or not any(
                f in _KEY_TYPES for f in fields[1:3]):
            raise UpdateError("the package's allowed_signers file has a line that is not a key entry",
                              code="update.verify.keys")
        principals.extend(n for n in names if n not in principals)
    return principals


def verify_signature(sums: Path, signature: Path, *, signers: Path = ALLOWED_SIGNERS, ssh_keygen: str | None = None,
                     run: Callable[..., Any] = subprocess.run) -> str:
    """The principal whose key signed ``sums`` (``ssh-keygen -Y verify``), or :class:`UpdateError`."""
    principals = load_signers(signers)
    if not principals:
        raise UpdateError("the package lists no release key", code="update.verify.keys")
    if signature.stat().st_size > SIG_MAX_BYTES:
        raise UpdateError("SHA256SUMS.sig is larger than 64 KiB", code="update.verify.signature")
    exe = ssh_keygen if ssh_keygen is not None else shutil.which("ssh-keygen")
    if exe is None:
        raise UpdateError("ssh-keygen (OpenSSH) is not installed, so the release's signature cannot be checked",
                          code="update.verify.tool", exit_code=3)
    for principal in principals:
        with open(sums, "rb") as fh:
            done = run([exe, "-Y", "verify", "-f", str(signers), "-I", principal, "-n", NAMESPACE, "-s",
                        str(signature)], stdin=fh, capture_output=True, timeout=60, check=False)
        if done.returncode == 0:
            return principal
    raise UpdateError("SHA256SUMS.sig is not a valid signature of SHA256SUMS by a release key of this package",
                      code="update.verify.signature")


def verify_release(sums: Path, signature: Path | None, *, signers: Path = ALLOWED_SIGNERS,
                   ssh_keygen: str | None = None, run: Callable[..., Any] = subprocess.run) -> Verification:
    """The module's rule: a listed key requires a valid signature; no listed key means ``SHA256SUMS`` alone."""
    if load_signers(signers):
        if signature is None:
            raise UpdateError("the release publishes no SHA256SUMS.sig, and this package lists release keys: refused",
                              code="update.verify.unsigned")
        return Verification("sha256+signature", verify_signature(sums, signature, signers=signers,
                                                                 ssh_keygen=ssh_keygen, run=run))
    return Verification("sha256", None)
