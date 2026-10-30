# `agentdojo.suites@1` versus the v2.3 labels (phase 7, 2026-10-08)

`equivalence-v2.3.json` is written by `tools/agentdojo/sem_equivalence_scan.py`. The tool maps every baseline v1
transcript of AgentDojo-PROV @ `579a908` with the `adprov-v1` profile, and every native log of
`ethz-spylab/agentdojo@c274885` with `agentdojo-upstream` (`--native-cache`). It annotates each AER with the semantics
profile `agentdojo.suites@1` and compares, element by element, the profile's labels with the stored v2.3 graph
(`agentprov.testing.sem_v23`; a native log is compared with the graph of its converted pair). The compared labels are
`adprov:integrity` (every tool output, the user query, the agent), `adprov:role` (sink ⇔ any sink role),
`adprov:source_channel` and `adprov:contains_injection_marker`. The report holds numbers only.

| | Release | Converted | Native `2024-06` |
|---|---|---|---|
| Executions annotated / failures | 17,664 / 0 | 18,027 / 0 | 18,241 / 0 |
| Compared with a v2.3 graph | 17,664 | 18,027 | 18,027 (207 outcome-only and the 7 Mixtral logs have no converted pair) |
| Unexplained differences | 0 | 0 | 0 |
| Registered `unknown_tool_fail_closed` (integrity + role) | 98 = 2 × 49 tool turns | 24 = 2 × 12 | 24 = 2 × 12 |
| Registered `yaml_rejection_fallback` | 0 | 0 | 0 |
| Marker annotations present / absent / ambiguous / gap | 35,672 / 83,933 / 0 / 0 | 36,423 / 91,517 / 0 / 0 | 36,423 / 91,517 / 0 / 0 |

The unknown tool turns are exactly EF E.7.3 item 2's "49 released and 12 converted tool turns with unknown names":
v2.3 labelled them trusted and neutral, the profile labels them `unknown` (fail-closed). Every other label agrees. A
marker annotation is one (tool output, payload fixture) pair, so its counts are not v2.3's per-output attribute counts;
"present for some fixture" equals v2.3's `true` on every compared output. The `census` member of each tree gives every
annotation type × value × evidence class, including the outcome claims.

## Full imports with the SEM stage (phase 7, 2026-10-08)

`import-<part>.json` is written by `tools/sem/sem_import_report.py` from a working corpus that `agentprov import
--release --jobs 10` built with the SEM stage (the commands of `docs/reports/{agentdojo,adprov,inspect}/README.md`, into
fresh `*-p7` corpora), compared with the phase-6 corpus of the same snapshot. Numbers, codes and digests only.

| | `agentdojo` · `2024-06` | `adprov-v1` · `release` | survey AgentHarm |
|---|---|---|---|
| Executions annotated / SEM ok | 18,241 / 18,241 | 17,664 / 17,664 | 1,056 / 1,056 |
| Tier 3 (`SEM-V01…V12`) and tier 4 | all pass | all pass | all pass |
| AER digests equal to the phase-6 corpus | 18,241 / 18,241 | 17,664 / 17,664 | 1,056 / 1,056 |
| `apv:ContainsPayload` / `ExposedTo` / `PotentiallyInfluencedBy` | 36,423 / 73,254 / 37,074 | 35,672 / 71,757 / 41,392 | 0 / 23,231 / 0 (no taint policy) |
| Wall time (M2 Max, 10 workers) | 30 min (phase 6: 27 min) | 28 min (phase 6: 25 min) | 2 min |

Taint assessments are never fewer than v2.3's sink-taint pairs (EF E.7.3 item 2): released 41,392 against 41,066, and
the native import 37,074 against the converted tree's 36,687. The excess is the fail-closed unknown-tool pairs and the
never-executed sink requests (48 released, 153 converted), plus the 7 Mixtral logs natively; the exact per-tree
reconciliation is gate E at full scope (phase 13).

## Re-derivation after phase 8 (2026-10-08)

Phase 8 changed the `agentdojo` rule catalogue, whose digest is the `apv:sha256` value of its `rules:agentdojo.1`
catalogue entity in every PROV document: `8bf5140c…f006d` before, **`54b37cef…e83e8cb8`** after
(`sha256:54b37cefeaec1b32a50b2301b607f73642567a6fa1dd3cc32c288468e83e8cb8`). The corpora were re-imported with the
recorded commands (`--release --jobs 10`, offline, inputs read in place and pinned as above) into fresh `*-p8` working
corpora beside the phase-7 ones, at AgentPROV commit `b4fb72a` (`src/` clean, CPython 3.14.8, M2 Max, 10 workers). The
phase-7 corpora are kept as `*-p7.pre-phase8.partial`. The comparison is `executions.jsonl` row by row, then every PROV
document of the old corpus against its new counterpart as parsed JSON.

| | `adprov-v1` · `release` | survey AgentHarm | `agentdojo` · `2024-06` |
|---|---|---|---|
| Wall time (import) | 29 min 49 s (1,784.7 s) | 2 min 0 s (120.0 s) | 29 min 5 s |
| Executions / sealed clean / with issues / failed | 17,664 / 17,584 / 80 / 0 | 1,056 / 1,052 / 4 / 0 | 18,241 / 17,747 / 494 / 0 |
| Same execution set and same file paths | yes | yes | yes |
| AER digests unchanged | 17,664 / 17,664 | 1,056 / 1,056 | 18,241 / 18,241 |
| SEM digests unchanged | 17,664 / 17,664 | 1,056 / 1,056 | 18,241 / 18,241 |
| PROV digests changed | 17,664 / 17,664 | 0 / 1,056 | 18,241 / 18,241 |
| Nature of the PROV change | `apv:sha256` of the `agentdojo` catalogue entity only (one per document, `8bf5140c…` to `54b37cef…`); no other field | none: the `inspect` catalogue is unchanged | as adprov: the `agentdojo` catalogue `apv:sha256` only |
| Tier 3 / tier 4 (strict, release) | all pass | all pass | all pass |
| `apv:ContainsPayload` / `ExposedTo` / `PotentiallyInfluencedBy` | 35,672 / 71,757 / 41,392 (as phase 7) | 0 / 23,231 / 0 (as phase 7) | 36,423 / 73,254 / 37,074 (as phase 7) |

`import-adprov-release.json` and `import-agentharm.json` regenerated with `tools/sem/sem_import_report.py` from the new
corpora are byte-identical to the phase-7 reports above (they hold no PROV document digest). `derivation.json` differs
from phase 7 only in the code digests of the `aer` and `prov` stages (`engine_code_sha256`, `fn_digest`) and, for
adprov, in `rules_sha256.agentdojo`; the lockfile digest is equal. The AER rule-catalogue digest is a derivation
parameter and not part of any AER, so no AER changed.

AgentDojo `2024-06` was re-derived afterwards, on the user's go-ahead, at AgentPROV commit `bf1fe5a` with `agentprov import agentdojo --fetch --allow-network --release --jobs 10` (the pinned commit `c274885` came from the bare fetch cache; no acquisition was made). `import-agentdojo-2024-06.json` regenerated from the new corpus is byte-identical to the phase-7 report.

## Re-derivation after phase 9 (2026-10-09)

Phase 9 changed the `agentdojo` rule catalogue again (`capture_backend_identity` added; `run_error_imposed_outcome`
restated with the profile quirk's values): `54b37cef…e83e8cb8` before, **`30ad0b8d…10ae89f5`** after
(`sha256:30ad0b8dc1813691cc1959e7ed4b4323318a5de155c7a2ad619eae1410ae89f5`). `adprov-v1` · `release` (26 min 2 s) and
`agentdojo` · `2024-06` (28 min 3 s) were re-imported with the same commands at AgentPROV commit `b2eadcc` into
`*-p9` working corpora; the `*-p8` ones are kept as `*-p8.pre-phase9.partial`. Against phase 8: the same execution
sets and paths, every AER and SEM digest equal (17,664 and 18,241), the same seal statuses (17,584 + 80 and
17,747 + 494, 0 failed), every PROV digest changed, and the only difference in every PROV document is the
`apv:sha256` of the `agentdojo` catalogue entity. The survey AgentHarm corpus uses the `inspect` catalogue and was not
re-imported (`ast-survey-agentharm-p8.partial` stays current).

## Re-derivation after phase 10 (2026-10-11)

Phase 10 changed what feeds the three corpora that predate it. The `agentdojo` rule catalogue gained the phase-10 rules (the
hook, source-profile and D.6.16 history rules; version still 1): the digest of its `rules:agentdojo.1` entity is
**`acd77579…d062`** (`sha256:acd77579e522fe9fb7101784a3d4d85af56c4e8f6ec8d3c3cda2eb04d364d062`), was `30ad0b8d…89f5` after phase 9
and `05e580ce…b83f` on the wave branches. The profile `agentdojo-upstream` gained the pin of the D.6.16 history table
(`9d77aefe…aa95` in the phase-9 AERs, `a13b76ba…57fe` now). The three corpora were re-imported as steps `d2024`, `adprov` and
`agentharm` of the phase-10 run script (`--release --jobs 10`, offline, `main` `afe7038`, CPython 3.14.8, M2 Max; 2,564 s,
2,713 s and 134 s) into `*-p10` working corpora beside their phase-9 copies (`agentdojo-upstream-2024-06-p9`, `adprov-v1-release-p9`,
`ast-survey-agentharm-p8`, which stay). The pinned `2024-06` commit came from the bare fetch cache; no acquisition was logged after
2026-10-09. The comparison is `executions.jsonl` row by row, every AER and SEM file path by path, and every PROV document as parsed
JSON (scratch tools, numbers and paths only).

| | `adprov-v1` · `release` | survey AgentHarm | `agentdojo` · `2024-06` |
|---|---|---|---|
| Executions / sealed clean / with issues / failed | 17,664 / 17,584 / 80 / 0 | 1,056 / 1,052 / 4 / 0 | 18,241 / 17,747 / 494 / 0 |
| Same execution set, same file paths | yes | yes | yes |
| AER digests unchanged | 17,664 / 17,664 | 1,056 / 1,056 | **0 / 18,241** |
| SEM digests unchanged | 17,664 / 17,664 | 1,056 / 1,056 | **0 / 18,241** |
| PROV digests changed | 17,664 / 17,664 | 0 / 1,056 | 18,241 / 18,241 |
| Tier 3 / tier 4 (strict, release) | all pass | all pass | all pass |
| `apv:ContainsPayload` / `ExposedTo` / `PotentiallyInfluencedBy` | 35,672 / 71,757 / 41,392 | 0 / 23,231 / 0 | 36,423 / 73,254 / 37,074 |

**`adprov-v1` · `release` and survey AgentHarm: unchanged apart from the catalogue digest.** For adprov, every AER and SEM
document is byte-identical to phase 9 (the `adprov-v1` profile is unchanged), and the only difference in every PROV document is
the `apv:sha256` of the `agentdojo` catalogue entity (`30ad0b8d…` to `acd77579…`, 17,664 of 17,664; no other field).
For AgentHarm every AER, SEM and PROV document is byte-identical (the `inspect` catalogue and the Inspect profile are unchanged),
and `import-agentharm.json` regenerated from the new corpus is byte-identical to the phase-7 report. `import-adprov-release-p10.json`
differs from `import-adprov-release.json` only in `sem_stage.engine_code_sha256` and `fn_digest` (the code of the `agentdojo.suites@1`
engine changed in phase 10 without changing any output on these inputs: the SEM set digest and every assessment count are equal).

**`agentdojo` · `2024-06`: every AER changed, in exactly the fields of the history mechanism.** Path by path over all 18,241
AERs, the differences are the same nine header paths in every file and nothing else (no record changed, no line count changed):

| AER path | Files | Change |
|---|---|---|
| `execution.profile.sha256` | 18,241 | `9d77aefe…aa95` to `a13b76ba…57fe` (the history-table pin) |
| `artifacts[0].origin.introduced_in_commit` | 18,241 | absent to the introducing commit (D.6.16 item 4) |
| `ext.agentdojo.committed_no_later_than` | 18,241 | absent to the commit's date (class D) |
| `ext.agentdojo.benchmark_era` | 18,241 | absent to `pre_versioning` / candidate `v1` / next `v1.1` (class I) |
| `evf` for the two ext members | 18,241 | two entries added (`D`, `I`) |
| `rule` list | 18,241 | 2 to 4 entries (the two history rules) |
| `src` list | 18,241 | 5 to 6 entries (the origin locator) |
| `seal.records_sha256` | 18,241 | follows |

The expected `execution.profile.sha256` and the two history fields are there; the origin member, the two `evf` entries and the two
list entries are the same mechanism's own bookkeeping (D.6.16 items 4 and 6), not a further change. The values reproduce D.6.16 item 9
over the whole snapshot: 35 distinct introducing commits, 2024-06-02T12:26:48Z to 2024-06-05T11:21:57Z, all 18,241 logs
pre-versioning. The SEM documents differ only in `aer_digest` and `records_sha256` (18,241 each), and the SEM annotations are
unchanged (`import-agentdojo-2024-06-p10.json`: the same assessment counts; the SEM set digest differs because it is over the
documents' digests). The PROV documents of all 18,241 executions are **equal once identifiers and values derived from the AER
digest are set aside**: bundle, activity, mention and relation identifiers, derivation keys, the AER entity's name (it holds
the AER digest) and the catalogue's `apv:sha256`. No other value differs, so the
history fields do not reach PROV in v0.1. This is a statement about the comparison, not about the engine: the renaming treats
every dot- or hyphen-prefixed base-32 token of 12 to 26 characters and every 64-hex string as a digest-derived value.

**Head (new in phase 10, no phase-9 copy).** Compared with its wave-1 branch import the head corpus shows the same pattern (the
history fields on 36,679 logs, the era on the 24,914 `v0.k11` ones, equal SEM and PROV modulo digest-derived values): see
`docs/reports/agentdojo/README.md`. `import-agentdojo-head.json` (regenerated: the wave-1 version predates the history fields), `import-rope.json`,
`import-agentdyn.json`, `import-mandate.json` and `import-survey-agentdojo-runs.json` are the SEM-stage reports of the five new corpora (all tier-3 checks `SEM-V01…V12` and tier 4
pass for every execution). The Mandate and survey ones compare with the branch copies (AER digests equal 396 / 396 and 3,243 / 3,243).

| New corpus | Executions annotated / SEM ok | `apv:ContainsPayload` / `ExposedTo` / `PotentiallyInfluencedBy` |
|---|---|---|
| `agentdojo` · `head` | 36,679 | 73,580 / 168,387 / 74,101 |
| `rope` · `head` | 10,791 | 32,996 / 331,413 / 309,454 |
| `agentdyn` · `a` | 38,281 | 70,231 / 939,916 / 939,913 |
| `mandate-agentdojo-eval` | 396 | 361 / 1,237 / 1,146 |
| `agent-security-tools-survey` · `agentdojo-runs` | 3,243 | 5,633 / 15,752 / 10,975 |

The rope and AgentDyn figures include the fail-closed assessments of tools with no table (`docs/reports/{rope,agentdyn}/sem-unknown-tools.json`).

**Findings.** None beyond the above: no difference outside the expected mechanisms was found in the three corpora.
