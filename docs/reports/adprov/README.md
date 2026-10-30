# AgentDojo-PROV `transcript/v1` release import (phase 6, 2026-10-08)

`import-cli-release.json` records the full import of the released AgentDojo-PROV v2.3 transcript tree through
`agentprov import`, written by `tools/import_report.py` from the working corpus and the command's `--summary-json`. It
holds numbers, codes and digests only; the corpus (outside the repository) and the baseline tree are not in Git.

```bash
uv run agentprov import adprov-v1 --input ../AgentDojo-PROV-framework/corpus/corpus-prov --verify-against-pin \
    --release --jobs 10 --corpus ~/.agentprov/corpora/adprov-v1-release --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/adprov-v1-release.partial --summary <summary> \
    --out docs/reports/adprov/import-cli-release.json --compare-scan docs/reports/prov/derive-scan.json \
    --compare-gate docs/reports/migration/A-full.json --tree release
```

The input is the released tree of the frozen baseline (`../AgentDojo-PROV-framework` @ `579a908`, the location the
phase-4 gates read through `AGENTPROV_BASELINE_CORPUS`), read in place. The tree is git-ignored at the pinned commit, so
the profile pin `release` names it by its J.1.4 listing digest: `--verify-against-pin` recomputed the digest over the
17,664 `*.transcript.json` candidates, found `46273b01…` equal to the pin, and recorded every object with the
frozen-corpus origin `corpus {AgentDojo-PROV, 2.3, producer_commit 579a908, path corpus-prov/…}` (the origin the
migration gates record). AgentPROV source at commit `61b39d3` (`src/` clean), CPython 3.14.8, M2 Max, 10 T1 workers,
**release mode**.

| `agentprov import adprov-v1` (part `release`) | |
|---|---|
| Exit code / wall time | 0 / 1,475.6 s |
| Candidates / mapped / sealed clean / with issues / degenerate / failed | 17,664 / 17,664 / 17,584 / 80 / 0 / 0 |
| Registered / duplicates / excluded / filtered | 0 / 0 / 0 / 0 |
| Pin check (listing digest) | verified 17,664, unverified 0 |
| Variant / unit | `v1` 17,664 / `agent_execution` 17,664 |
| AER execution digests equal to the index / AER validator pass (release) | 17,664 / 17,664 |
| `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 17,664 / 17,664 / 17,664 |
| Accounting | `consistent` 14,688, `inconsistent` 32, `unverifiable` 2,944 |
| Completeness (index) | `verified_complete` 14,688, `known_incomplete` 32, `unverifiable` 2,944 |

| Seal issue (files = issues) | |
|---|---|
| `earlier_attempts_unobservable` | 3,097 |
| `accounting_unverifiable` | 2,944 |
| `unexecuted_tool_call` | 47 |
| `accounting_inconsistent` | 32 (the `adprov.art.reported_calls_exceed` artefact, D.15.6) |
| `adprov.tool_timing_overwritten` | 1 |

**Equal to the earlier records** (`comparison` in the report, 5 of 5 keys): the accounting verdicts of gate A
(`docs/reports/migration/A-full.json`, release tree) and, for the release tree of the phase-5 derive scan
(`docs/reports/prov/derive-scan.json`), the number derived, degenerate (0), the PROV statements by rule and the bundles.

Determinism: a second full import with `--jobs 6` (1,649.5 s) into another working corpus gave a byte-identical tree:
53,000 of 53,000 files, `corpus.json` and `derivation.json` included (`determinism` in the report,
`tools/import_compare.py --whole`).

Not covered here: the converted tree (`converted-legacy`, role `compat_oracle`) is not imported as a corpus; gates A1,
A2 and B over both trees are the phase-4 reports in `docs/reports/migration/`.
