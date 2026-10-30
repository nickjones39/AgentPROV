# Mandate-AgentDojo-Eval: full import (phase 10, recorded 2026-10-09, refreshed 2026-10-11)

`import-cli-mandate.json` records the import of the 396 AgentDojo logs of `jwilliamsc/mandate-agentdojo-eval` (source
`mandate-agentdojo-eval`, part `head`, profile `mandate-agentdojo-eval`, corpus `mandate-agentdojo-eval`) through
`agentprov import`, written by `tools/import_report.py`. It holds numbers, codes and digests only; log text (which holds
prompt-injection payloads by design) is never printed. The corpus is outside the repository. The licence basis is recorded
verbatim in the registry and the profile: **MIT as declared; publisher unverified**.

**Refreshed on the integrated code (2026-10-11).** The first report (2026-10-09) was written from an import on the wave-2
branch code. The five phase-10 branches were then integrated on `main` (`afe7038`) and the source was imported again as step
`mandate` of the phase-10 run script (`--release --jobs 10`; corpus `mandate-agentdojo-eval-p10`). Every figure below is from that
import and equals the branch report's: 396 of 396, the same census, the same cross-checks, the same seal issues. What differs is the
code digests of the derivation stages, the worker count (10) and the wall time (58 s). The branch import's corpora are kept as
`mandate-agentdojo-eval-p10.pre-integration.partial` and `-p10-b.pre-integration.partial`; against the first of them the integrated
corpus has **396 of 396 AER documents and 396 of 396 SEM documents byte-identical**, and every PROV document differs in exactly one
value, the `apv:sha256` of the `agentdojo` rule-catalogue entity (the D.6.16 history rules were added to the catalogue, version
unchanged). `docs/reports/sem/import-mandate.json` is the SEM-stage report of the same corpus.

```bash
uv run agentprov import mandate-agentdojo-eval --snapshot head --input <clone> --verify-against-pin --release --jobs 10 \
    --corpus ~/.agentprov/corpora/mandate-agentdojo-eval-p10 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/mandate-agentdojo-eval-p10.partial --summary <summary> \
    --out docs/reports/mandate/import-cli-mandate.json --extra <determinism, pin check, census, cross-checks>
uv run python tools/agentdojo/profile_census.py --profile mandate-agentdojo-eval --part head
uv run python tools/agentdojo/source_checks.py --source mandate --corpus ~/.agentprov/corpora/mandate-agentdojo-eval-p10.partial
```

**Origin.** The input is the local shallow clone at the pinned commit `fa62a977…` (untrusted third-party data, read through
`agentprov.ingest.paths`). `--verify-against-pin` needs the pin's tree listing in the fetch cache; it was seeded offline from
the clone (`tools/seed_git_cache.py`, git `file://` remote; the 40-hex commit id and `transfer.fsckObjects` authenticate every
object; logged in `~/.agentprov/cache/acquisitions.jsonl`). The pin covers the repository root (401 files, 3,137,054 bytes) so
that the four context artefacts are vouched for by the same listing as the logs. All 400 files read (396 logs and the 4
context artefacts `agentdojo_mandate_eval.py`, `README.md`, `requirements.txt`, `LICENSE`) matched their tree entries and carry
the pinned `git` origin (`pinned_snapshot_check`). The profile's `corpus_digest` (`a8f4a9d7…`, the verify report's recipe over
the 396 files of `runs/`) is recomputed from the pinned tree by `tests/adapters/agentdojo/test_mandate.py` (marker
`full_corpus`).

AgentPROV source at the integrated `main` `afe7038` (`src/` unchanged for the run), CPython 3.14.8, M2 Max, 10 T1 workers,
**release mode**.

| `agentprov import mandate-agentdojo-eval` | |
|---|---|
| Exit code / wall time | 0 / 58 s (branch code, 4 workers: 165.5 s; second branch import, `--jobs 3`: 237.3 s) |
| Candidates / mapped / sealed clean / with issues / degenerate / failed / registered | 396 / 396 / 396 / 0 / 0 / 0 / 0 |
| Variant / unit | `v1.k14` 396 / `agent_execution` 396 |
| Origins | `git` 396 |
| AER execution digests equal to the index / AER validator pass (release) | 396 / 396 |
| SEM annotated / `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 396 / 396 / 396 / 396 |
| Accounting | `unverifiable` 396 (TraceLogger records no model call) |

Seal issues (all "sealed clean": the two are info-level facts every TraceLogger log has): `accounting_unverifiable` 396,
`earlier_attempts_unobservable` 396. No adapter issue code fired: no `identity_unresolved`, `path_field_mismatch` or
`undeclared_quirk`.

**Census** (`profile_census`, reproduces every `observed` count of the profile, `differences: []`): `declines` **240** and
solvability pre-pass `files` **27** are the investigation's figures; `allowed_inferred` 143 equals the verify report's derived
allows (6 envelope + 137 intent); `args_mutated_in_place` 391 is 396 minus the 5 tool-free runs; `placeholder_args` 1,390 is the
verify report's tool-call count; the benign constant applies to the 27 pre-pass runs.

**Cross-checks against the investigation** (`source_checks`, all equal): the outcome table of verify §3.4 reproduces from the
AERs cell by cell (runs, `security` true, `utility` true, decline messages per pipeline and attack: baseline 108/144, intent
2/144, envelope 3/27, held-out 0/27, ...), declines by mode 49 envelope + 191 intent, derived allows 6 + 137, 5 tool-free runs,
message totals (396 system, 396 user, 1,621 assistant, 1,390 tool). For all 240 declines the AER holds a `deny` decision citing
`mandate.decline_prefix@1` on the declined `tool_call` part, no execution for it, the error verbatim as the reason, and a tool
the mode gates.

Determinism: on the branch code, a second import with `--jobs 3` into another working corpus gave a byte-identical tree to the
first (`--jobs 4`; 1,596 files, `corpus.json` and `derivation.json` included). That check is carried into the refreshed report as
recorded (`determinism.result`, marked `run_on_pre_integration_code`); the integrated import is not a second import, so no whole-tree
comparison exists for the integrated code. Its independent re-import comparison is the one stated above.

What this does not show: the allow decisions and the gate's inputs are not logged (the 143 allows are inferred, class I), and
the publisher of the repository is unverified.
