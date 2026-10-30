"""BF-19 (D-461): ``chain`` re-checks the AD-12 container closure of withheld members (HL H.4.5; D-232).

An archive holds its members' bytes, so the seal withholds every container of a withheld member. A sealed tree in which
such a container is put back, and dropped from ``WITHHELD.json``, must fail ``verify --level chain --release``
(``withheld.container``). The container is deflated, so the rule rescan alone cannot see the member's bytes in it. The
corpus is the synthetic one of ``test_sec25_withhold_issue.py`` (one Inspect ``.eval`` container, one flagged sample).
"""

from __future__ import annotations

import io
import shutil
import zipfile

import corpus_harness as harness
import verify_support as vs
from corpus_harness import verify
from test_sec25_withhold_issue import HEAD, ISSUE_RULE, _hits, _inject, _package, corpus, working_template  # noqa: F401

cli = harness.cli


def test_a_released_container_of_a_withheld_member_fails_chain(cli, corpus, monkeypatch):  # noqa: F811 - fixtures
    from agentprov.corpus.withheld import WithheldDocument, decode_withheld, encode_withheld

    _inject(monkeypatch, HEAD + ISSUE_RULE)
    run = _package(cli, corpus)
    assert run.code == 0, run.err
    root = corpus["root"]
    assert verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root)).code == 0
    doc = decode_withheld((root / "WITHHELD.json").read_bytes())
    container = next(e for e in doc.entries if e.basis == "container")
    members_left = [e for e in doc.entries if e.sha256 != container.sha256]
    assert members_left  # the withheld member stays listed
    side = root.with_name("c.withheld")
    src = next(p for p in (side / "raw" / "objects").rglob(container.sha256 + "*"))
    dst = root / src.relative_to(side)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    (root / "WITHHELD.json").write_bytes(encode_withheld(WithheldDocument(tuple(members_left), doc.executions,
                                                                          doc.policies)))
    vs.reforge(root)
    archive = zipfile.ZipFile(io.BytesIO(dst.read_bytes()))
    assert sum(_hits(archive.read(n)) for n in archive.namelist()) > 0  # it really holds the withheld bytes
    check = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert check.code != 0 and "withheld.container" in check.codes(), check.codes()
