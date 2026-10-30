# Phase 10h routing note for the orchestrator

Items that phase 10h may not change itself (new files only; no mapper, schema, catalogue, core, runner, raw or ingest
change). Each item says what, why, the evidence and the digest impact. Nothing here is applied.

## R-H1: model-id and harness-text redaction (D-182): proposed regeneration-batch item

- **What:** `[[family.inspect.redact]]` in `adapters/inspect/family.schema.json` (closed: `id`, `scope` ∈ {`model_id`,
  `harness_text`}, `pattern`, `replacement` built from literal text, `{span12}` and `{leaf}`, optional `leaf`, `note`).
  Apply it in `adapters/inspect/mapper.py` (collect observed model ids that match; replace them wherever copied;
  apply `harness_text` rules to the copied sample `error`, error and logger events, `sample_metadata`, header
  `task_args`/`revision`/`model_generate_config`). Add a new rule `inspect.value_redacted@1` (class D) in
  `rules/inspect.rules.toml`, an `ext.inspect.redacted` list, the seal issue `inspect.value_redacted` (info) and an
  `artefacts.toml` entry. Then add the tables to the two phase-10h profiles (sketch in `redaction-design.md` §3).
- **Why:** D-146 (user-approved): the account names must not reach derived records. The census shows exactly where they
  go today (`redaction-design.md` §1).
- **Evidence:** `~/.agentprov/migration-work/phase10h/census/map-census.json` (pointer classes and counts);
  `tests/adapters/inspect/test_phase10h_agentharm.py` (one test pins today's verbatim copy, two strict xfails).
- **Impact:** moves the Inspect adapter code digest, so every Inspect corpus changes stage identity: ast-survey-agentharm,
  plus the whistlebench and phase-10h trial corpora. With a catalogue version bump, every Inspect AER header changes
  (`rules`) and the survey goldens move. AER bytes of corpora without `redact` tables change only through that header.
  memo-ozdincer (agentdojo family, D-146) needs the same table in the AgentDojo family schema; the shape is
  family-neutral.
- **Before packaging:** D-186 (raw objects with account paths in a public release) needs the user's decision.

## R-H2: unfinished Inspect logs (`_journal/` only)

- **What:** kexin's 2 unfinished logs (28 samples) hold `_journal/start.json`, `_journal/summaries/*.json` and complete
  sample members, but no `header.json`. The reader registers them `select.dialect_planned` ("no header.json member").
  Supporting them would read the eval spec from `_journal/start.json` (a reader change).
- **Why:** 28 samples (1% of kexin). Low priority. Recorded so that the count gap 2,825 → 2,797 is explained.

## R-H3: per-path attack declaration in the Inspect family (D-184)

- **What:** `[family.inspect]` has a profile-wide `no_attack` only. fragfuse mixes plain AgentHarm runs with memory-bank
  and carrier-injection experiments in one pin. A table keyed by path glob or `eval.task` (for example
  `attack = [{task = "tasks10_retrieve_test", attack_id = "memory_bank_injection"}, …]`) would let the profile state the
  arm as D-class data with a citable rule. Schema and mapper change, so it belongs with R-H1 or later.
- **Why:** `task.attack_id` is unrecorded for all 1,747 fragfuse samples, including the 140 attack runs.
- **Related:** the Inspect mapper does not declare `consumes_context`, so `[import] context_artefacts` is inert for the
  whole family (survey, WhistleBench, fragfuse). fragfuse's memory banks (136 `bank_*/*.jsonl`, 106 MB) and per-task
  `guardrail_decision.json` files are the attack material and a guardrail's verdicts; storing them needs the mapper to
  consume context (and a decision on how a guardrail verdict outside the log is cited).

## R-H4: issue counts seen in the trial imports

- `inspect.unmapped_event` for `logger` (196 kexin, 7 fragfuse events) and `error` events (25 and 34). The mapper keeps
  them in `ext`, and the code says only that they were not observed in the survey band. Inspect mapper owner: decide
  whether they join `_KEPT_OBSERVED`.
- `accounting_inconsistent` in 693 fragfuse samples is the known Inspect defect of **regen-batch item 16** (not a
  profile problem; no profile workaround): `execute_tools` gives every tool event of a parallel batch the first call's
  result `message_id`, so later results lose their generator. Measured from the logs (`scripts/parallel_calls.py`):
  0.3.154.dev37+g1289c1ad 802 parallel batches in 620 samples, 1,617 of 5,078 tool events name another call's result;
  0.3.159.dev20+g3ddd7997 87 batches in 73 samples, 155 of 567 events; 0.3.158 no parallel batch. The 620 + 73 affected
  samples are exactly the 693 `aer.acc.executions_have_results@1` samples. kexin (0.3.263): 1,551 batches in 1,059
  samples, every present `message_id` agrees with its call (110 events name no stored message: pruned results, seen as
  `missing_tool_result`), so it is not affected.
  **Resolved by item 16** (`2d11028`, on main at `bfa1951`; rule `inspect.tool_event_message_id_first_of_batch@1`,
  class D). Scratch trial import of fragfuse at `bfa1951` (2026-10-13, `--jobs 8`, scratch corpus `fragfuse-i16`):
  `accounting_inconsistent` 693 → 0, and those 693 samples move from `known_incomplete` to `verified_complete`
  (1,744 verified complete, 3 unverifiable). Against the pre-item-16 trial (`fragfuse-j8`), the AER and SEM digests
  change for exactly those 693 executions and no other. The PROV digest changes for all 1,747, and for the other 1,054
  the only change is the Inspect rule-catalogue digest (`rules:inspect.1`), which item 16 changed. Unchanged:
  `missing_tool_result` 23, `dangling_source_ref` 23, `inspect.sample_limit` 74, `inspect.unmapped_event` 24,
  `no_execution_observed` 3, `select.not_execution_artefact` 4. Status: 1,721 ok, 26 ok_with_issues (was 1,051 and
  696). derive --dry-run, validate --strict (tier 4, 1,747 passed, linkage 100%), recompute --dry-run (1,747
  identical) and verify --level chain all exit 0 (checksums unverified: a working tree).

## For AGENTS.md / spec (orchestrator-owned text)

- §D.3.2 lists the `planned` sources of phases 10d and 10f; `kexin-xu-01-agentharm` and `fragfuse-agentharm` (§D.9.8)
  belong in the same sentence.
