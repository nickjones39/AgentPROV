"""The closed set of format ids (docs/architecture HL L.1.1, L.1.2; MN M.1.2).

Formats are closed: a reader MUST reject an id it does not know, including a newer minor or major version of a known
format (L.1.2, "fail closed"). :func:`require_supported` is that check; every corpus-layer reader calls it on the
``format`` member (or the version member) of what it opens before it trusts any other member.

The set is L.1.1's complete v0.1 list, plus the format ids the as-built code already writes (``agentprov-*/0.1``
documents of the validation summary, the progress stream, the semantic diff, the capture-quality report, the PROV and
artefact catalogues, the backend-environment marker, the stored split descriptor, the semantics profiles, the
reconciliation and inspect reports, the import artefact table and the fixture caps). They are listed separately so that the spec list stays
recognisable. ``agentprov-collection/0.1`` is reserved for the deferred collections (AD-10 row 6) and is **not** in the
set. The provenance spec ids (``agentprov-prov/0.1``, ``adprov-v2.3-compat``) are spec versions, not formats; they live
in :mod:`agentprov.versions` and in the PROV spec registry.

This module is L0: it imports nothing from AgentPROV but the error base.
"""

from __future__ import annotations

from typing import Final

from agentprov.errors import AgentProvError

__all__ = [
    "AS_BUILT_FORMATS",
    "CORPUS_LAYER_FORMATS",
    "FORMATS",
    "RECORD_FORMATS",
    "RESERVED_FORMATS",
    "SPEC_FORMATS",
    "UnsupportedFormatError",
    "is_supported",
    "require_supported",
]

#: Record and log formats (L.1.1 axes 2-4). ``aer/0.1`` and ``capture/0.1`` are frozen (AD-06).
RECORD_FORMATS: Final = frozenset({"aer/0.1", "aer/0.2", "sem/0.1", "capture/0.1"})
#: Corpus-layer formats (HL H.2, H.3, H.6, H.8, H.4.3, G.9.5, H.10).
CORPUS_LAYER_FORMATS: Final = frozenset(
    {
        "agentprov-corpus/0.1",
        "agentprov-corpus/0.2",
        "agentprov-index/0.1",
        "agentprov-register/0.1",
        "agentprov-derivation/0.1",
        "agentprov-raw-references/0.1",
        "agentprov-withheld/0.1",
        "agentprov-withheld/0.2",
        "agentprov-withheld/0.3",  # D-454: the basis unscanned
        "agentprov-withheld/0.4",  # D-810: the rule kind address
        "agentprov-withheld/0.5",  # D-964: the rule kind object
        "agentprov-deposit/0.1",
    }
)
#: The rest of L.1.1's list: the CLI summary (N.1.4), package resources (D.4, D.5), the transcript view (C.15.2), the
#: migration gate report (J.3), the worker protocols (G.4.6, D.11.3) and the live run plan (D.10.1).
SPEC_FORMATS: Final = frozenset(
    {
        "agentprov-cli-summary/0.1",
        "agentprov-source-profile/0.1",
        "agentprov-rule-catalogue/0.1",
        "agentprov-transcript/0.1",
        "agentprov-migration-gate/0.1",
        "agentprov-job/0.1",
        "agentprov-backend/0.1",
        "agentprov-run-plan/0.1",
    }
)
#: Format ids the as-built code writes that L.1.1 does not list (phase 11 records them here so that they are closed too).
AS_BUILT_FORMATS: Final = frozenset(
    {
        "agentprov-validation-summary/0.1",  # validation/summary.json (HL.R6(2))
        "agentprov-progress/0.2",  # the --progress-file / jsonl stream (cli/feedback.py; D-393, superset of 0.1)
        "agentprov-control/0.1",  # the --control-file request (cli/control.py; D-394)
        "agentprov-semdiff/0.1",  # migration semantic diff report (J.3.6)
        "agentprov-semdiff-map/0.1",  # its mapping table
        "agentprov-capture-quality/0.1",  # live capture-quality report
        "agentprov-prov-catalogue/0.1",  # the PROV rule catalogue resource (prov/specs.py)
        "agentprov-artefact-catalogue/0.1",  # the artefact detector catalogue (artefacts/catalogue.py)
        "agentprov-backend-env/0.1",  # the backend environment marker (cli/live/envs.py)
        "agentprov-stats/0.1",  # the agentprov stats report (stats/__init__.py; MN N.2.12)
        "agentprov-personas/0.1",  # a corpus spec's persona files (corpus/personas.py; D-810)
        "agentprov-deposit-manifest/0.1",  # DEPOSIT-MANIFEST.json of a deposit draft (release/builder.py; H.10.3, D-42)
        "agentprov-index-manifest/0.1",  # DEPOSIT-MANIFEST.json of an index deposit, kind "index" (release/index.py; H.10.7, D-947)
        "agentprov-collection-index/0.1",  # COLLECTION-INDEX.json of an index deposit (release/index.py; H.10.7, D-947, D-949)
        "agentprov-zenodo-draft-receipt/0.2",  # the uploader's draft receipt, read by release/index.py (agentprov-zenodo; D-870)
        "agentprov-zenodo-draft-receipt/0.1",  # superseded by 0.2 (D-870); release/index.py names it only to refuse it with a reason
        "agentprov-release-scan/0.1",  # <corpus>.release-scan.json (tools/release_scan.py; G.9.4)
        "agentprov-validation-report/0.1",  # validate --corpus --report (corpus/validation.py; N.2.5(5), D-40)
        "agentprov-split/0.1",  # the stored split descriptor raw object (raw/members.py; HL H.2.3, D-315)
        "agentprov-sem-profile/0.1",  # a semantics profile's profile.toml (adapters/<family>/semantics/)
        "agentprov-reconciliation/0.1",  # the R3 reconciliation report (migration/reconcile.py)
        "agentprov-inspect/0.1",  # agentprov inspect --json (cli/inspect.py)
        "agentprov-artefact-table/0.1",  # the import artefact table (cli/import_.py)
        "agentprov-run-dry-plan/0.1",  # run --dry-run --plan-json (cli/run.py; MN N.2.1 item 5, D-651)
        "agentprov-backend-catalogue/0.1",  # run SOURCE --catalogue, the worker op catalogue (cli/run.py; D-652)
        "agentprov-inspect-catalogue/0.1",  # the same for an Inspect backend (cli/live/inspect_catalogue.py; D-663)
        "agentprov-settings/0.1",  # $AGENTPROV_HOME/settings.json (settings.py; MN N.2.17, D-703)
        "agentprov-settings-schema/0.1",  # agentprov settings list --schema --format json (cli/settings_cmd.py; D-703)
        "agentprov-local-models/0.1",  # agentprov models --format json (cli/live/localmodels.py; MN N.2.18, D-691)
        "agentprov-local-model/0.1",  # superseded by 0.2 (D-736); held only by the live pilot's two Part L scratch corpora
        "agentprov-local-model/0.2",  # a local model's observed identity record (cli/live/localmodels.py; D-692, D-736)
        "agentprov-model-folders/0.1",  # models --find-folders: candidate model folders (cli/live/localmodels.py; D-828)
        "agentprov-tune-jobs/0.1",  # run --tune-jobs: the concurrency sweep's report (cli/live/tune.py; N.2.1a(4), D-821)
        "agentprov-tune-arm/0.1",  # one finished arm of a sweep, for resume (cli/live/tune.py; D-820)
        "agentprov-provider-models/0.1",  # an API provider's cached model list and models output (cli/live/providermodels.py; D-730)
        "agentprov-prices/0.1",  # the shipped price table and refreshed snapshots (estimate/prices.py; D-650, D-701)
        "agentprov-price-overrides/0.1",  # $AGENTPROV_HOME/prices/overrides.json (estimate/prices.py; D-701)
        "agentprov-prices-list/0.1",  # agentprov prices list --format json (cli/prices.py; D-701)
        "agentprov-estimate-priors/0.1",  # the shipped estimate priors (estimate/priors.py; D-653, D-701)
        "agentprov-estimate/0.1",  # agentprov estimate --format json (cli/estimate.py; D-701)
        "agentprov-job-record/0.1",  # $AGENTPROV_HOME/jobs/<id>/job.json (jobs/record.py; D-704)
        "agentprov-jobs-list/0.1",  # agentprov jobs list|prune --format json (cli/jobs.py; D-704)
        "agentprov-batch/0.1",  # $AGENTPROV_HOME/batches/<id>.json (jobs/batch.py; D-704)
        "agentprov-batches-list/0.1",  # agentprov batch list --format json (cli/batch.py; D-704)
        "agentprov-devrun/0.1",  # dev-runs/<stamp>/devrun.json (devrun/plan.py; D-705)
        "agentprov-devrun-plan/0.1",  # agentprov devrun plan --format json (cli/devrun.py; D-705)
        "agentprov-devrun-list/0.1",  # agentprov devrun list --format json (cli/devrun.py; D-705)
        "agentprov-fixture-caps/0.1",  # tests/FIXTURES.json (testing/fixture_caps.py)
        "agentprov-defence-registry/0.1",  # the live defence registry (backends/shared/.../defences.toml; D-670)
    }
)
#: Reserved ids that are deliberately **not** supported in v0.1.
RESERVED_FORMATS: Final = frozenset({"agentprov-collection/0.1"})
#: The closed set.
FORMATS: Final = RECORD_FORMATS | CORPUS_LAYER_FORMATS | SPEC_FORMATS | AS_BUILT_FORMATS


class UnsupportedFormatError(AgentProvError):
    """A document names a format id outside the closed set (L.1.2: readers reject unknown versions; exit 1)."""

    code = "format.unsupported"
    exit_code = 1


def is_supported(format_id: object) -> bool:
    """Whether ``format_id`` is a string in the closed set :data:`FORMATS`."""
    return isinstance(format_id, str) and format_id in FORMATS


def require_supported(format_id: object, *, expected: str | frozenset[str] | None = None) -> str:
    """Return ``format_id`` if it is in the closed set (and, with ``expected``, is that id or one of those ids).

    Raises :class:`UnsupportedFormatError` otherwise (fail closed, L.1.2). The message never repeats the value, which
    comes from a file and is untrusted; it says only whether it was a string and how long it was.
    """
    if not is_supported(format_id):
        what = f"a string of {len(format_id)} characters" if isinstance(format_id, str) else type(format_id).__name__
        raise UnsupportedFormatError(f"unsupported format id ({what}); readers fail closed on unknown formats (L.1.2)")
    assert isinstance(format_id, str)
    if expected is not None:
        allowed = frozenset({expected}) if isinstance(expected, str) else expected
        if format_id not in allowed:
            raise UnsupportedFormatError(
                "the format id is supported but not the one this reader expects", code="format.unexpected"
            )
    return format_id
