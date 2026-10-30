"""The `defence` rule catalogue's home lands before the regeneration round (D-677; regen-batch item 167, option taken:
the `CATALOGUE_HOMES` line and the catalogue file pre-round, the rest of the defence core after it).

Byte-neutral on its own: the catalogue resolves and self-tests, and nothing committed cites it yet (only defended live
sessions will, once the live profiles v2 land after the round).
"""

from __future__ import annotations

from pathlib import Path

from agentprov.aer.rules import CATALOGUE_HOMES, load_catalogue

REPO = Path(__file__).resolve().parents[2]
RULE_IDS = ("defence.message_by_defence", "defence.denial_declared_text")


def test_the_defence_catalogue_resolves_from_its_home():
    assert CATALOGUE_HOMES["defence"] == "agentprov.adapters.agentdojo"
    catalogue = load_catalogue("defence")
    assert catalogue.version == 1
    for rule_id in RULE_IDS:
        entry = catalogue.get(f"{rule_id}@1")
        assert entry is not None and entry.citable


def test_nothing_committed_cites_the_defence_catalogue_yet():
    needles = [rule_id.encode("ascii") + b"@" for rule_id in RULE_IDS]
    roots = [REPO / "tests" / "fixtures", REPO / "tests" / "golden", REPO / "docs" / "architecture" / "examples"]
    hits = []
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in (".jsonl", ".json", ".ttl")):
            data = path.read_bytes()
            if any(needle in data for needle in needles):
                hits.append(path.relative_to(REPO).as_posix())
    assert hits == []
