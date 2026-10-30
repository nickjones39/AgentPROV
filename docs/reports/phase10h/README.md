# Phase 10h: profiles for the AgentHarm Inspect log sets of kexin-xu-01 and fragfuse

Branch `phase-10h-agentharm`, 2026-10-12. Decisions D-180–D-188 (`docs/architecture/DECISIONS.md`; proposals except D-185
and D-187, which are the user's decisions of 2026-10-12); spec §D.9.8. Inputs: the phase-10e verification
(`docs/reports/systematic-search/candidates/phase10e-candidates.md` §2 rank 4, §3.3, §3.4; D-144–D-146). Third-party data,
read in memory through `agentprov.ingest`; nothing in it was run, installed or followed.

**Account names.** Both sources record workstation account names in file paths. No account name, and no path that
contains one, appears in this report, the census files, the profiles, the tests or the commits. Paths are described by
structure (`/home/<account>/…`), and every committed or written file was checked against the account segments by digest
(`scripts/repo_guard.py` in the work directory). The single 6-letter `/Users/<name>/` string that models wrote in kexin's
outputs is a common English word, used elsewhere in this spec; it never occurs in a log header.

Files: `README.md` (this report), `redaction-design.md` (part B), `routing.md` (items for the orchestrator). Work
directory, outside Git: `~/.agentprov/migration-work/phase10h/` (`scripts/`, `census/`, trial corpora under `corpora/`).
Staging copies: `~/.agentprov/staging/10e/` (phase 10e's copies, checked again here).

## 1. Acquisition

- **Census input:** the 236 logs that phase 10e staged (68 + 168). Each matches its pinned tree entry by git blob id and
  size (the tree listings phase 10e saved at the pins; `census/staged-verify.json`), so the census needed no download.
- **Trial imports:** with the user's approval of 2026-10-12, a depth-1 fetch of each pinned commit through the
  framework's own `agentprov fetch` (the `Fetcher`: `transfer.fsckObjects`, every blob's SHA-1 recomputed). Both are
  logged in `~/.agentprov/cache/acquisitions.jsonl`:
  - `Kexin-xu-01/agentharm@859c34f4`, tree `logs/`: 68 blobs, 36,467,328 B.
  - `zixin22/fragfuse_agentharm@24cc8aea`, whole commit: 3,847 blobs, 318,827,530 B (the rest is the `inspect_evals`
    working copy; stored, never run).

  A blob-less partial clone was not used: seeding the fetch cache from one would let `upload-pack` fetch missing blobs
  lazily (phase 10d's R2).

## 2. Census (part A)

Every member of every log was read through `agentprov.ingest` (`open_zip`, `iter_zip_members`, `strict_json_loads`).
Scripts: `scripts/census.py`, `dups.py`, `secrets*.py`, `paths.py`, `account_logs.py`, `journal_scan.py`. Results:
`census/census.json` (per log and per sample: counts, codes, digests; model ids redacted),
`census/account-paths-by-log.json`.

| | kexin-xu-01/agentharm | zixin22/fragfuse_agentharm |
|---|---|---|
| Logs, samples | 68 logs, 2,825 samples | 168 logs, 1,759 samples (1,747 real-model) |
| Layout | `logs/` (26), `logs/patched-judge/` (20), `-v2/` (2), `-v3/` (20) | `logs_archive/` (26) and `logs_archive/agentharm_2025-12-30_run1/` (2); `src/inspect_evals/agentharm/tasks10_outputs/retrieve_test_logs_memory/task_<n>-<m>/` (136, one sample each); `…/Agentharm/carrier_inject_eval/task_[test_]<n>-<m>/` (4, one sample each) |
| Inspect | `inspect_ai` 0.3.263 and inspect_evals 0.20.0 (66 logs); 2 unfinished logs (`_journal/` only, no `header.json`, 28 samples) | 0.3.154.dev37+g1289c1ad (25), 0.3.158 (136), 0.3.159.dev20+g3ddd7997 (7); no inspect_evals version recorded |
| Log status | 63 success, 3 error, 2 unfinished | 148 success, 20 error |
| Tasks | `inspect_evals/agentharm` (34), `…/agentharm_benign` (32): AgentHarm harmful and benign test splits, 44 behaviours per log | `inspect_evals/agentharm` (12), `…_benign` (16), `tasks10_retrieve_test` (136), `task` (4, carrier) |
| Agent models | claude-sonnet-5 (10 logs), claude-sonnet-4-5-20250929 (1), gemini-2.5-pro (7), gemini-2.5-flash (6), gemini-2.5-flash-lite (6), gpt-4o-2024-08-06 (6), gpt-4o-mini (6), vllm/Qwen/Qwen3-14B (6), and three local Qwen3-14B checkpoints served by vLLM (18 logs: two merged fine-tunes and one LoRA; ids are workstation paths) | gpt-4o-2024-08-06 (151 logs), gpt-5-nano (7), claude-opus-4-1-20250805 (6), `none/none` (4: Inspect's no-model provider) |
| Judge | `combined_scorer` with semantic and refusal judge openai/gpt-4o-2024-08-06 in scorer spans (every finished log). For the six gpt-4o agent logs the judge model equals the agent model; spans separate them | the same in the 28 `logs_archive` logs; the 136 retrieve logs use `always_ok` (no judgement) |
| Solver plan | `setup_tools_from_metadata → system_prompt_based_on_model → prompt_template → set_tool_choice → generate` | as kexin (26); plus `mode_router`/`save_router` (3) and `pre_router`/`post_router` (3) variants; retrieve: `prepend_reference → … → inject_memory_from_bank → … → generate` (136) |
| Attacks | none (plain AgentHarm) | **memory retrieval** (136): memories drawn from a bank (`bank_<x>/bank_<n>-<m>.jsonl`) are injected before generation, with `masked_query` metadata; **carrier injection** (4): `carrier_query_path`, `carrier_host_id`, `prompt_kind` metadata. The repository also holds the attack pipeline's intermediate files (masking, carrier queries, guardrail decisions; not executions) |
| Tool calls | 11,036 calls of 34 tools; 2,043 samples with a tool call | 5,645 calls of 80 tools; 1,064 real samples with a tool call |
| Sample limits | 298 message limits | 74 message limits |
| Sample errors | 25 | 34 (12 of them `none/none`) |
| Secret-like strings | 33 matches, all inside longer tokens of AgentHarm's simulated terminal output | 166, all inside longer tokens: the terminal tool (2) and gpt-5-nano's encrypted `reasoning` parts (25 in messages, the rest their copies in events). None whole, none in a header (D-188) |

**Distinctness and overlap (D-181).** Every sample uuid and every message id is distinct in both sources, so the
`patched-judge*` directories hold new runs, not re-scorings (phase 10e's reading confirmed). Comparing message lists by
text only (role, text, tool calls; ids excluded), 230 kexin groups (2–9 samples each), 186 fragfuse groups and 49
cross-source groups are equal. These are short refusals (system, user, assistant), deterministic tool chains, and
samples that errored before any reply. They are independent runs and count separately. No sample of either source
equals one of the survey's 1,056 AgentHarm samples. The first user prompts do overlap, by design: the same AgentHarm
behaviours (kexin uses 89 distinct prompts, all of them in the survey and in fragfuse).

**Workstation account paths** (details in `redaction-design.md` §1). kexin: three checkpoint ids under
`/workspace/shared/outputs/<job>/…` (18 logs, 792 samples), and `/home/<account>/.cache/inspect_evals/…` in
`eval.dataset.location` of every log (two accounts). fragfuse: `/Users/<account>/…` in `dataset.location` (28 logs), the
memory-bank solver parameter (136), error tracebacks (20 logs; 34 samples) and `metadata.carrier_query_path` (4 samples,
a second account). The `/home/…` and `/Users/Downloads/…` paths inside prompts and tool outputs are AgentHarm's fiction.

**What the current mapper does with each log** (`scripts/map_census.py`: every log through the real in-process
pipeline, raw store in scratch, then release-mode AER validation; `census/map-census.json`):

| | kexin | fragfuse |
|---|---|---|
| Units | 2,797 (the 2 unfinished logs: `select.dialect_planned`, "no header.json member") | 1,759 (incl. the 12 `none/none` samples, mapped here only) |
| Crashes, degenerate, validation errors | 0, 0, 0 | 0, 0, 0 |
| Run status | 2,474 none recorded, 298 `limit`, 25 `error` | 1,651, 74 `limit`, 34 `error` |
| Samples by issue | `inspect.sample_limit` 298; `inspect.unmapped_event` 83 (`logger` 196 events, `error` 25); `missing_tool_result` and `dangling_source_ref` 51 | `accounting_inconsistent` 693 (all `aer.acc.executions_have_results@1`: some tool executions without a linked result; 620 under 0.3.154.dev37, 73 under 0.3.159.dev20, none under 0.3.158). This is the known Inspect parallel-tool-call defect, **regen-batch item 16**: the affected samples are exactly those whose tool events name another call's result `message_id` (routing R-H4); `sample_limit` 74; `unmapped_event` 36; `missing_tool_result`/`dangling_source_ref` 23; `no_execution_observed` 3 |
| Account path reaches the AER | in the 18 checkpoint-id logs: 9 pointer classes (`redaction-design.md` §1) | tracebacks in `ext` (34 samples), `carrier_query_path` in `ext` (4) |

## 3. Profiles, registry, fixtures, tests (part C)

- **Profiles** (new files): `src/agentprov/adapters/inspect/profiles/kexin-xu-01-agentharm.profile.toml` and
  `fragfuse-agentharm.profile.toml` (D-180). kexin: tree `logs/`, band 0.3.263, `no_attack`. fragfuse: whole commit,
  band 0.3.154.dev37/0.3.158/0.3.159.dev20, the four `none/none` logs excluded by exact path (D-183), attack not declared
  (D-184). Both: span roles `solver`/`scorer`, ground-truth metadata `target_functions`/`grading_function`, quirks with
  census counts. Neither carries a redaction table: the schema has none yet (D-182).
- **Registry:** two appended `SourceRegistration`s, part `logs`, `planned`, semantics `inspect.agentharm@1`, own
  restricted-use corpus each; `agentprov info` lists both as `include (restricted)`.
- **Fixtures (D-185):** none committed. The user chose "clean real logs plus synthetic", but no log is clean: the 2
  unfinished kexin logs also hold `/home/<account>/` in `_journal/start.json`. The tests build synthetic logs in code.
- **Tests:** `tests/adapters/inspect/test_phase10h_agentharm.py`, 29 cases. They cover profiles, the closed schema,
  quirk rules, the registry, fragfuse's selection and exclusion, band and off-band synthetic logs, the unfinished-log
  register row, the trial tool's local-path detection, today's verbatim copy of a local-path model id, and two strict
  xfails for D-182. When the pinned commits are in the fetch cache, they also check the pinned tree counts, the 18/2/48
  split of kexin's logs and a release-mode mapping of the smallest band log of each source (skipped otherwise; two are
  `slow`).
- **Spec:** §D.9.8 in `docs/architecture/D_adapters.md`.

## 4. Trial imports (part C; D-187)

`tools/inspect/phase10h_trial.py import` (release mode, through validation; bypasses the `planned` gate as phase 10d's
tool does), then `agentprov derive --dry-run`, `validate --strict`, `recompute --dry-run`, `verify --level chain` and a
summary. Corpora under `~/.agentprov/migration-work/phase10h/corpora/` only. Two runs per source compare determinism.

| | `kexin-xu-01-agentharm` | `fragfuse-agentharm` |
|---|---|---|
| Logs imported | 50 of 68 selected: the 18 checkpoint-path logs left out (D-182); the 2 unfinished logs registered `select.dialect_planned` | 164 selected; the 4 `none/none` logs registered `select.not_execution_artefact` |
| Executions (8 workers) | 2,005 mapped, sealed, annotated (SEM), derived (PROV), validated; 0 failed, 0 degenerate; 781 s | 1,747; 0 failed, 0 degenerate; 854 s |
| Status, completeness | 1,965 ok, 40 ok with issues; all `verified_complete` | 1,051 ok, 696 ok with issues; 1,051 `verified_complete`, 693 `known_incomplete` (accounting), 3 `unverifiable` (`no_execution_observed`); before item 16, which clears the 693 (routing R-H4) |
| Register (samples) | `inspect.sample_limit` 186, `inspect.unmapped_event` 47, `missing_tool_result` and `dangling_source_ref` 40 | `accounting_inconsistent` 693, `sample_limit` 74, `unmapped_event` 24, `missing_tool_result`/`dangling_source_ref` 23, `no_execution_observed` 3 |
| `derive --dry-run` | 2,005 identical, 0 unexplained | 1,747 identical, 0 unexplained |
| `validate --strict` | 2,005 passed, 0 failed, 0 skipped; linkage 2,005/2,005; stored results reproduced 2,005 | 1,747 passed, 0 failed, 0 skipped; linkage 1,747/1,747; reproduced 1,747 |
| `recompute --dry-run` (expand, aer, sem, prov, validation) | 2,005 identical, 0 unexplained | 1,747 identical, 0 unexplained |
| `verify --level chain` | 0 failed; 2,131 raw objects re-hashed, 2,081 members checked; 1 unverified: `checksums.absent` (a working tree has no `checksums.sha256` until sealing) | 0 failed; 2,075 raw re-hashed, 1,911 members; the same single `checksums.absent` |
| Validation checks failed (68 checks) | none | none |
| Second import | 3 workers, same 50 logs: 8,153 files, all byte-identical to the 8-worker import | every 5th log (33 logs, 36 samples), 3 workers: all 210 objects identical to the full import; and a full 3-worker import of all 164 logs: 7,323 files, all byte-identical to the 8-worker import |

**After rebasing on main** (phase 12b merged, then the D-28 I-class-time engine fix): a `recompute --dry-run` of all
five stages on both trial corpora with the rebased code gives 2,005 and 1,747 executions identical (AER, SEM, PROV,
validation). Its exit status is 1 for one corpus-level difference: every `raw/members.jsonl` row (2,479 and 2,075) changes
only its `fn_digest`. Member digests, labels, sizes, CRCs and dispositions are unchanged. This is the phase-12b
`expand` bundle exactly as predicted in `docs/reports/analysis/regen-batch.md`, not a phase-10h effect; any archive
corpus imported before that merge shows it until the regeneration round.

**Account paths in the trial corpora** (`scripts/corpus_account_scan.py`, by digest): kexin, none outside `raw/objects`
(the 18 checkpoint logs were not imported; `dataset.location` is not copied). fragfuse, 25 AER files carry an account
path in `ext` (22 traceback samples and 4 `carrier_query_path` samples, one sample having both), as predicted by the
census; SEM, PROV, index and register hold none. The raw objects of both corpora hold the originals (invariant 3).
The corpora are local and never committed (D-187).

**Context artefacts are inert** for the Inspect family: the mapper does not declare `consumes_context`, so fragfuse's
declared memory banks and guardrail decisions (like the survey's and WhistleBench's declarations) were not stored: the
raw store holds exactly 164 containers, 164 header members and 1,747 sample members (routing R-H3).

## 5. Open items

1. **D-182** redaction (routing R-H1, regeneration batch) and **D-186** (raw with account paths in a public release):
   the user decides before any packaging. The 18 kexin checkpoint logs (792 samples) wait for D-182.
2. **R-H2** unfinished logs (28 samples), **R-H3** per-path attack declaration and inert context artefacts, **R-H4**
   `unmapped_event` and `accounting_inconsistent` for the Inspect mapper owner.
3. D-180–D-184 and D-186–D-188 await the user. Full imports wait for the regeneration round and the user's approval;
   both registry parts stay `planned`.
