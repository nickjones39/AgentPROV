"""``Capability.sealed``: the sealed corpora holding a part, shown by the README, the user guide and ``info`` (display only)."""

from __future__ import annotations

from pathlib import Path

from agentprov.adapters.registry import REGISTRY

REPO = Path(__file__).resolve().parents[3]
#: The seal reports: round 1 and wave 2 (2026-10-29).
SEAL_REPORTS = ("docs/reports/release/pre-release-checks.md", "docs/reports/release/wave-2-pre-release-checks.md")


def _parts():
    return [(r.source_id, c) for r in REGISTRY for c in r.capabilities]


def test_every_supported_import_part_is_sealed():
    """In v0.1 a part reaches ``supported`` only through an import that was then sealed (round 1 or wave 2)."""
    assert [f"{s} · {c.part}" for s, c in _parts() if c.import_status == "supported" and not c.sealed] == []


def test_every_sealed_corpus_is_named_by_a_seal_report_and_by_the_caveat():
    reports = "".join((REPO / path).read_text(encoding="utf-8") for path in SEAL_REPORTS)
    for source_id, cap in _parts():
        for sealed in cap.sealed:
            assert f"`{sealed.corpus_id}`" in reports, (source_id, cap.part, sealed.corpus_id)
            assert sealed.version == "0.1.0"
            assert f"{sealed.corpus_id} {sealed.version}" in str(cap.caveat), (source_id, cap.part)
            assert sealed.tag == f"corpus/{sealed.corpus_id}/v{sealed.version}" and sealed.tag in str(cap.caveat)
            assert any(path in str(cap.caveat) for path in SEAL_REPORTS), (source_id, cap.part)


def test_sealed_parts_are_import_source_parts():
    for source_id, cap in _parts():
        if cap.sealed:
            assert cap.role == "source" and cap.import_status in ("supported", "partial") and cap.corpus_id, source_id
