# Bug pass bugpass-new-families: proposals for the user

These findings were reproduced (see `findings.md` and `repro/`), but none of them is a plain bug fix. Each moves a stored
code digest (byte class 1) or changes the text of an approved decision.

**User decision 2026-10-21: regen items 115-131 approved, option (a) for item 130.** Items 115-127 and 131 are built by
this session on held branches, not pushed before the round. Items 128-130 (`adapters/runner/importer.py`) go to the
CLI robustness session, which owns the D-529 runner (orchestrator, 2026-10-21). P-1 and P-2: approved by the user 2026-10-21 and written as addenda to D-250, D-470 and D-474.

Numbers come from `tools/reserve_id.py`: regen-batch items 115-131.

None of the families below has a stored corpus today:
- memo-ozdincer and qwencode wait on their recipes (D-530 for qwencode);
- the D-529 runner changes affect sampled working corpora only.

So **no stored AER, SEM or PROV byte moves**. What moves is the `adapter_code_sha256` of the family (agentdojo,
qwencode, inspect), or the aer stage's `engine_code_sha256` for `adapters/runner/`. Those digests move for every import
made after the change. The "AER bytes" column says what the change would do to a first import of the pinned data.

## Regen-batch item proposals (byte class 1)

| item | NF | file | change | AER bytes at the pin |
|---|---|---|---|---|
| 115 | NF-5 | `adapters/agentdojo/results_mapper.py:829` | `outcome_imposed_by_runner` cites `self.cite.cite(R_EXCEPTION)` (the `_unverified` twin), as the generic mapper does (D.5.4, D-472). Test: the issue's rule equals the judgements' rule; the real-fixture test also walks `issues[].rule` | the rule of the issue on every exception row |
| 116 | NF-6 | `adapters/agentdojo/results_mapper.py:359` | with no `defense` key and no table defence, omit `task.defense_id`, set `unk /task/defense_id: not_recorded`, raise an info issue `rescont.defence_unrecorded` (catalogue entry; `rescont` catalogue version bump). Keep the class-I null only where the key is present with value null. A documented "no defence" (e.g. FULL_EVAL_RESULTS.md) can come in as a table field with its basis | the header of every row without a `defense` key |
| 117 | NF-7 | `adapters/agentdojo/results_mapper.py:873` | in `results_degenerate_header`, cite `/results/<i>/suite` when `suite` comes from the row | none (0 degenerate rows) |
| 118 | NF-8 | `adapters/agentdojo/results_mapper.py:806-829` | impose `harness_default` only on judgements whose logged value equals the quirk's declared param (as `capture_mapper.py:1825-1837` does); otherwise keep the checker origin and raise `rescont.exception_row_values_differ` (warning; catalogue bump) | none (all 1,038 rows hold false/true) |
| 119 | NF-13 | `adapters/agentdojo/results_mapper.py:296` | run the D-378 surrogate pass in `ResultsBuild` (`scrub_keys` on the row and the container fields, `surrogates(self, records, "agentdojo")` before the redaction pass); add `ResultsBuild` to D-378's list | none (no lone surrogate at the pin) |
| 120 | NF-14 | `adapters/qwencode/dialect.py:152-165` | salvage only a capture cut: output of exactly 65,536 bytes whose strict error is `ingest.json.syntax` at end of input. Every other strict failure re-raises, so the runner seals the D.2.8 case-3 degenerate AER. Align D.24.2 and the `qwencode.truncated_salvage@1` statement (catalogue bump) | none expected (needs a check over the 3,295 outputs before the round) |
| 121 | NF-15 | `adapters/qwencode/dialect.py:172-230` | bound salvage: a size cap before it, one forward pass for the element boundaries, one strict parse of the kept prefix. Cost test: an adversarial 64 KiB input finishes in under 1 s | none |
| 122 | NF-16 | `adapters/qwencode/mapper.py:51`, `ext.schema.json` | add `stats` to `_RESULT_FIELDS` (verbatim in `ext.qwencode.result`, O under the result locator). Correct the part-C census and D.24.3/D.24.4. Optional, needing a decision: a check of `stats` request counts against the blocks, to explain the 851 usage-excess runs from logged hidden-source calls | ext of every run (3,295 result messages) |
| 123 | NF-17 | `adapters/qwencode/dialect.py:297-307` | `sniff` matches every JSON array in the D.24.1 grammar. An unsupported version raises `UnsupportedVariant` and a wrong shape `MalformedArtefact`, so both are degenerate AERs, not `select.not_execution_artefact` | none expected (all pinned outputs are 0.21.x arrays) |
| 124 | NF-18 | `adapters/qwencode/mapper.py:~630,703,734,~676` | type guards: a non-string or absent tool name becomes `unk` (`not_recorded`/`ambiguous`) with the raw value in ext and an issue, never `str(None)`; a non-string user text becomes an `other` part with `qwencode.unmapped_message` | none |
| 125 | NF-19 | `adapters/qwencode/mapper.py:782-790` | a missing `score` sets no value (`unk not_recorded`, no `/score` pointer); a non-int or out-of-scale score (bool excluded) keeps the value and raises `qwencode.score_unrecognised` (catalogue bump). The openhands RedCode judge (`openhands/mapper.py:1259`) has the same gap: the openhands owner decides | none |
| 126 | NF-20 | `adapters/qwencode/mapper.py:566`, `_load_aux` | a second `result` message is mapped as a harness activity with an issue (e.g. `qwencode.extra_result_message`); a non-UTF-8 `execution_rules.md` raises `qwencode.sidecar_missing` (`rules: not UTF-8`) | none |
| 127 | NF-21 | `adapters/qwencode/semantics/tools.py:192-200`, `qwencode.tools-1/profile.toml` | `non_informative = [1]` in the semantics profile; any other integer score gets no annotation. The openhands sibling has the same catch-all: the openhands owner decides. This moves the qwencode sem engine digest | none (scores 0, 1, 3) |
| 128 | NF-34 | `adapters/runner/importer.py:2130` (`_plan_sample`) | keep resume-skipped whole files as candidates (their `label#` key), so a resumed sample draws the same set. Test: a credleak zip with a malformed member sampled twice; candidates, executions and `selection.sample` unchanged | none (sampled working corpora only) |
| 129 | NF-35 | `adapters/runner/importer.py:2095` | refuse `--sample-mode spread` for a reader without `sample_stratum` before any write (next to `_check_identity`). Test: no corpus.json on a fresh corpus; an existing corpus's corpus.json is byte-identical after the refusal | none |
| 130 | NF-36 | `adapters/runner/importer.py:2576`, `_check_identity` | **needs a choice:** (a) refuse a run whose selection differs from the recorded one for a listed snapshot, keep `partial` sticky, and record each snapshot's selection; or (b) record the selection per snapshot and derive `partial` from all of them. Either way `package._check_working` gets a class-0 backstop (refuse when a snapshot's counts show a partial import) | none |
| 131 | NF-37 | `adapters/inspect/dialect.py:140-143` | `sample_stratum` splits at the last `!/` and returns the head only when it ends in `.eval`, else `None`. Test: a nested-archive spread over three logs gives three strata | none (sampling only) |

**Merge notes.**
- Items 128-130 edit `adapters/runner/importer.py`. Six branches already queue on that file, so the orchestrator orders
  the merge (after D-414).
- Item 131 edits a file the D-529 hook branch created.
- Items 115-119 edit `results_mapper.py`, which no in-flight branch touches.
- The redaction fixes (NF-10..12) are not given items here. They are routed to regen-items with item 105, which is wiring
  the same module (`routing.md`).

## Decision text (byte class 0, needs the user because the decisions are approved)

- **P-1 (NF-3), an addendum to D-250 and census §2/§9.** "As built, the identity table is keyed by pipeline directory
  (`model_from = "pipeline_dir"`; the directory equals the logged `pipeline_name`). The experiment path is not a key,
  because the 3,260 re-packed byte copies span experiments; the experiment stays visible in each origin path."
  - The `(exp5; …)` notes in `tables/authority_caps_pipeline_dirs.toml` also name the wrong experiment for two
    autoconfirm rows (pilot also holds `claude-haiku-4-5-20251001-autoconfirm`; the distinct `gpt-6-sol-autoconfirm` logs
    are in `current_models`).
  - That table is class 1 (it is under the adapter digest). It can ride with any later agentdojo table bump.
- **P-2 (NF-9), addenda to D-470 and D-474.**
  - D-470: "As built, the located item's value is the whole parsed container (aggregate included); the row is selected
    by the locator `/results/<i>`; `ext.rescont.container` keeps only the listed fields (D.6.20 items 1 and 4)."
  - D-474: "`identity_conflict` is raised on the 5,369 runs of that path and on the five LoRA served names on the same
    checkpoint (`cb`, `cb_banking`, `cb_slack`, `cb_workspace`, `mse4`): 6,306 in the census and trial."
  - The same correction goes into `docs/reports/phase10q/README.md` §5.
