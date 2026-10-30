"""K.11.1 over the parts of ``agentprov.ingest`` that ``tests/security/test_ingest_fuzz.py`` does not reach: input-tree
discovery and opening (``ingest.paths``) over random trees, and container sniffing (``ingest.streams``).

Discovery reads nothing, is deterministic and sorted, and every entry is either a valid label or a rejection with a
G.3.9 code; every discovered label opens (or fails typed) and the bytes are exactly the file's.
"""

from __future__ import annotations

from pathlib import Path

from fuzz_support import budget, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.errors import INGEST_CODES
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import logical_name
from agentprov.ingest.paths import discover, open_evidence
from agentprov.ingest.streams import sniff_container

LIMITS = IngestLimits().replace(max_artefact_bytes=4096)
# names a POSIX file system accepts; hostile ones included (controls, bidi, NFD, leading dots, case twins, long)
NAME = st.one_of(
    st.text(alphabet=st.characters(blacklist_characters="/\x00", blacklist_categories=("Cs",)), min_size=1, max_size=24),
    st.sampled_from([".hidden", "._x", "a\u202ebc", "e\u0301", "\u00e9", "E", "e", "CON", "a.", "x" * 200, "\x1b[31m",
                     "..x", "-n", "a\nb", "\u2028"]),
).filter(lambda n: n not in (".", "..") and len(n.encode("utf-8")) <= 255)
TREE = st.lists(st.tuples(st.lists(NAME, min_size=1, max_size=3), st.binary(max_size=64)), max_size=8)


@budget(60, deadline=None)
@given(TREE)
def test_discovery_of_a_random_tree_is_total_sorted_and_typed(tmp_path_factory, entries: list[tuple[list[str], bytes]]) -> None:
    root: Path = tmp_path_factory.mktemp("tree")
    written: dict[str, bytes] = {}
    for parts, data in entries:
        target = root.joinpath(*parts)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                continue
            target.write_bytes(data)
        except OSError:  # the host file system refused the name (APFS normalisation, length): not under test
            continue
        written[target.relative_to(root).as_posix()] = data
    found = discover(root, LIMITS)
    again = discover(root, LIMITS)
    assert [f.label for f in found.files] == [f.label for f in again.files] == sorted(f.label for f in found.files)
    assert all(r.code in INGEST_CODES for r in found.rejected)
    for item in found.files:
        logical_name(item.label, LIMITS, portable=False)  # a local label passes the non-portable name rules (G.3.6)
        result = outcome(lambda label=item.label: open_evidence(root, label, LIMITS).read())
        if result[0] == "ok":
            on_disk = (root / item.label).read_bytes() if (root / item.label).is_file() else None
            assert result[1] == on_disk


@budget(150)
@given(st.binary(max_size=16))
def test_container_sniffing_is_total_and_reads_only_the_head(head: bytes) -> None:
    kind = sniff_container(head)
    assert kind == sniff_container(head) and kind in ("zip", "document", "gzip", "bzip2", "xz", "zstd")
