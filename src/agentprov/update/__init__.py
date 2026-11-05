"""Check for Updates (D-1065): the newest release of the public repository, its verified download and the desktop
bundle's install with a one-step rollback. ``agentprov update`` is the one implementation; the desktop app runs it as
CLI jobs and keeps no network code (S11).

* :mod:`.releases`: the GitHub releases API of :data:`~.releases.REPOSITORY` (one https host, bounded, strict JSON,
  untrusted), the version order, this platform's bundle name and the cached check;
* :mod:`.verify`: ``SHA256SUMS`` (strict), each file's sha256, and the list's signature (``ssh-keygen -Y verify``
  against the project's ``data/allowed_signers``, shipped in the package);
* :mod:`.unpack`: a bundle archive's members checked (paths, types, links, sizes) and written only below a new
  directory: ``.tar.gz`` (Linux), ``.zip`` (Windows), and the ``.dmg`` (macOS) through ``hdiutil`` and ``ditto``;
* :mod:`.install`: the swap of the bundle folder with the previous one kept beside it (macOS and Linux at once; Windows
  after the app has quit, by :mod:`.apply`), the rollback, and the upgrade command of a package install.

Outside every stage closure (class 0): nothing here reads or writes a corpus.
"""

from pathlib import Path as _Path
from typing import Final as _Final

#: The public keys the release's ``SHA256SUMS.sig`` is checked against (``ssh-keygen`` allowed-signers format).
ALLOWED_SIGNERS: _Final = _Path(__file__).resolve().parent / "data" / "allowed_signers"
