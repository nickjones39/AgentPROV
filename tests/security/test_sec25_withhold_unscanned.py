"""D-450: ``chain`` reports a released stored archive the decoded scan cannot read (``withheld.unscanned``).

Sealing withholds such an archive unread (basis ``unscanned``, D-454; before it, the seal refused it), so a sealed tree
only releases one through a planner defect or an edit. Here the corpus of ``test_sec25_withhold_issue.py`` (one Inspect ``.eval``
container) is sealed with a byte rule that matches nothing, so the container is released and ``chain`` passes; then the
decoded scan is made to report it unreadable, as for a deferred codec or a nesting beyond the allowance. ``chain`` must
fail with its own code, never pass and never misreport it as a rule hit.
"""

from __future__ import annotations

import corpus_harness as harness
import verify_support as vs
from corpus_harness import verify
from test_sec25_withhold_issue import HEAD, _inject, _package, corpus, working_template  # noqa: F401

cli = harness.cli
NO_MATCH = '''
[[withhold.rules]]
id = "never-matches"
pattern = "QQZZ-[0-9]{12}"
scope = "object"
'''


def test_a_released_archive_the_decoded_scan_cannot_read_fails_chain(cli, corpus, monkeypatch):  # noqa: F811
    from agentprov.corpus import withhold_scan

    _inject(monkeypatch, HEAD + NO_MATCH)
    run = _package(cli, corpus)
    assert run.code == 0, run.err
    root = corpus["root"]
    pinned = vs.root_digest(root)
    assert verify(cli, root, "--level", "chain", "--release", "--root-digest", pinned).code == 0
    real = withhold_scan.scan_archives

    def unreadable(objects, stream, rules, **kwargs):
        found = real(objects, stream, rules, **kwargs)
        archives = {sha for sha, label in objects.items() if label.endswith((".eval", ".zip"))}
        assert archives  # the released .eval container
        return withhold_scan.DecodedScan(found.hits, {sha: "ingest.archive.format" for sha in archives})

    monkeypatch.setattr(withhold_scan, "scan_archives", unreadable)
    check = verify(cli, root, "--level", "chain", "--release", "--root-digest", pinned)
    codes = check.codes()
    assert check.code != 0 and "withheld.unscanned" in codes, codes
    assert "withheld.rule_hit" not in codes  # its own code, not the '<unscanned>' stand-in
