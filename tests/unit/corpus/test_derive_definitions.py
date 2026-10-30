"""``corpus.derive`` re-implements the importer's stage definitions and code digests (D-30): pinned equal here.

``corpus/`` (L5) may not import ``adapters.runner`` (L6), so the ``sem``, ``prov`` and ``validation`` stage definitions and
``code_sha256`` exist twice; any drift would make ``recompute`` call a refactor a version change (or the reverse).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import importer
from agentprov.cli.derive import catalogues
from agentprov.corpus import derive
from agentprov.corpus.writer import CorpusWriter
from agentprov.ingest.limits import IngestLimits
from agentprov.progress import NULL_PROGRESS

DIR_SETS = [
    (["prov", "vocab"], ["prov/compat/"]),
    (["validate", "aer/validate.py", "aer/accounting.py", "sem/validate.py"], []),
    (["sem", "adapters/semantics_profiles.py", "adapters/agentdojo/semantics"], []),
    (["adapters/runner", "aer"], []),
    (["adapters/inspect"], []),
    (["views"], []),
]


@pytest.mark.parametrize(("dirs", "exclude"), DIR_SETS)
def test_code_sha256_equals_the_importers(dirs, exclude):
    assert derive.code_sha256(dirs, exclude) == importer.code_sha256(dirs, exclude)


def _pipeline(tmp: Path, *, source: str, profile: str, part: str, semantics: tuple[str, ...], mode: str, until: str):
    writer = CorpusWriter(tmp / f"c-{mode}-{until}-{len(semantics)}").open()
    pipeline = importer._Pipeline(
        source, None, writer, profile=load_profile(profile), part=part, snapshot_id=part, corpus_id=source,
        filters=importer.ImportFilters(), limit=None, mode=mode, until=until, prov_specs=(importer.SPEC_ID,), workers=1,
        in_process=mode == "dev", limits=IngestLimits(), retry_failed=False, progress=NULL_PROGRESS, pin_check=None,
        resume_index=None, batch_size=1, dry_run=True, semantics=semantics,
    )  # fmt: skip
    return writer, pipeline


CASES = [
    ("agentdojo", "agentdojo-upstream", "2024-06", ("agentdojo.suites@1",), "dev", "validation"),
    ("agentdojo", "agentdojo-upstream", "2024-06", ("agentdojo.suites@1",), "release", "validation"),
    ("agentdojo", "agentdojo-upstream", "2024-06", (), "dev", "validation"),
    ("agent-security-tools-survey", "survey-agentharm", "agentharm", ("inspect.agentharm@1",), "release", "validation"),
]


@pytest.mark.parametrize(("source", "profile", "part", "semantics", "mode", "until"), CASES)
def test_stage_definitions_equal_the_importers(tmp_path, source, profile, part, semantics, mode, until):
    writer, pipeline = _pipeline(tmp_path, source=source, profile=profile, part=part, semantics=semantics, mode=mode,
                                 until=until)
    try:
        expected = {s["stage"]: s for s in pipeline.stage_definitions(None)}
    finally:
        pipeline.close()
        writer.close()
    injected = catalogues()
    infos = [injected.semantics(ref) for ref in semantics]
    assert all(info is not None for info in infos)
    if semantics:
        assert derive.sem_stage_definition([i for i in infos if i is not None]) == expected["sem"]
    else:
        assert "sem" not in expected
    assert derive.prov_stage_definition() == expected["prov"]
    assert derive.validation_stage_definition(semantics, mode) == expected["validation"]


def test_with_digest_is_h82_and_idempotent():
    body = {"stage": "x", "fn": "f"}
    once = derive.with_digest(body)
    assert derive.with_digest(once) == once and once["fn_digest"].startswith("sha256:")


def test_declared_identity_ignores_code_digests_and_versioned_digests():
    base = {"stage": "aer", "adapter": "a@0.1.0", "adapter_code_sha256": "sha256:1", "engine_code_sha256": "sha256:2",
            "profile": "p@1", "profile_sha256": "sha256:3", "rules": {"a": 1}, "rules_sha256": {"a": "sha256:4"},
            "fn_digest": "sha256:5"}
    other = {**base, "adapter_code_sha256": "sha256:9", "engine_code_sha256": "sha256:9", "profile_sha256": "sha256:9",
             "rules_sha256": {"a": "sha256:9"}, "fn_digest": "sha256:9"}
    assert derive.declared_identity(base) == derive.declared_identity(other)
    assert derive.declared_identity(base) != derive.declared_identity({**base, "rules": {"a": 2}})
    prov = derive.prov_stage_definition()
    # D-640: with its aprov version recorded, the catalogue digest is not a declared version (D-31, as for aer) ...
    assert derive.declared_identity(prov) == derive.declared_identity({**prov, "rules_sha256": "sha256:0"})
    assert derive.declared_identity(prov) != derive.declared_identity({**prov, "rules": {"aprov": 1}})
    # ... and a definition recorded before D-640 (no rules) still declares it
    legacy = {k: v for k, v in prov.items() if k != "rules"}
    assert derive.declared_identity(legacy) != derive.declared_identity({**legacy, "rules_sha256": "sha256:0"})
    sem = {"stage": "sem", "profiles": {"x.y@1": "sha256:1"}}
    assert derive.declared_identity(sem) == derive.declared_identity({"stage": "sem", "profiles": {"x.y@1": "sha256:2"}})
