# Deferrals part D: the phase-13 gates (2026-10-12; first results)

All runs local, no network: the frozen baseline environment `~/.agentprov/baseline/venv-579a908` (CPython 3.12.14, the
wheel pinned in `migration/baseline.lock.json`, built offline earlier), the baseline checkout
`../AgentDojo-PROV-framework` @ `579a908` (read only), the AgentDojo fetch cache. Reports under `docs/reports/migration/`.
The core environment needs the locked `shacl` extra for C2 (`uv sync --extra shacl`, installed offline from the uv
cache).

| Gate | Result | Report | Tool |
|---|---|---|---|
| **R3** (field-level diff, J.4.3/J.4.4) | **passes**: 18,027 pairs (= gate R's comparable pairs), 0 `differs_unexpected`, 0 unexplained one-sided fields, lineage 18,027/18,027 `agree` (`migration.converted_v1_from_native@1`); 214 native logs unmatched (207 outcome-only, 7 Mixtral: R4/R5's sets); 0 crashes | `R3-full.json` (lineage records: `R3-lineage.jsonl`, 8.3 MB, kept in the work directory, sha256 `3a730afd…`; rerun 2026-10-13 on main with regen-batch items 17-19: one new `native_only` J.4.4 row, `system_prompt_variant`) | `tools/migration/r3_reconcile.py`, `agentprov.migration.reconcile` |
| **C2** (validators, J.3.4) | **passes**: 760 graphs (600 stratified + edge strata: 105 run errors, defended pipelines, DoS families, zero-tool and duplicated-id traces) and the audit fixture, 10,524 documents; **compat port: 0 verdict differences from the baseline** (all five `ProvValidator` checks and `validate_prov_document`); the generic checks differ only as registered (5 entries) | `C2.json` | `tools/migration/gate_c2.py`, `c2_mutations.py`, probe `c2` |
| **C3** (scoring, J.3.4) | **passes** (one register entry, D-215, user-approved 2026-10-13): all 35,691 traces mapped by the product mappers, 0 crashes; every scoring fact built from AER and SEM agrees with the baseline's except `rerun_detected` on 32 released traces (baseline `true`, AgentPROV unknown), which moves 30 verdicts' `rerun` flag and makes 2 traces scored instead of `rerun_not_reproduced`; `@2` adds no difference of its own on this corpus (F-60's DoS gating fires on no trace). Old side: release 17,496 scored, 162 unwinnable, 6 rerun not reproduced; converted 17,452 scored, 432 unwinnable, 106 abandoned, 30 account, 7 rerun | `C3.json` | `tools/migration/gate_c3.py`, `agentprov.migration.gate_c3`, probe `c3` |
| **C5** (converter on upstream samples, J.3.4) | **passes**: 16 samples (the 9 golden June-2024 logs, identical; the 7 head fixtures), one registered difference | `C5.json` | `tools/migration/gate_c5.py`, probe `c5` |
| C6 | passed 14/14 in phase 8 (D-21); not re-run (no change to what it exercises) | `C6.json`, `gate-c6.md` | |
| Release chain G0 → A → B → D → E (full scope, `--release`, commit `3523336`) | **G0 12/12, A 35,691/35,691, B 35,691/35,691 pass; D fails 17,664/17,664 on stale stored AERs; E refused until D passes (AD-07)**. D's failure is an input, not a defect: the stored `adprov-v1-release-p10` AERs were imported before regen-batch items 1-19, so they name the old `adprov-v1` profile digest (`00dc7981…`; shipped `59bf23b7…`) and the release-mode validator refuses every one (AER-V35); the native tree corpus was not given. D and E at full scope therefore run after the regeneration round, on corpora imported with the code they check | `release-chain-2026-10-13/` | `agentprov migrate gate G0|A|B|D|E --scope full --release` |

## R3 in detail

`project()` flattens every record but the seal, minus the members that differ by design (ids, origins, source key,
adapter, profile, rule citations, evidence metadata), keyed by record index per kind; actors are keyed by their id, which
both importers spell the same (`bench`, `user`, `agent`, `env`, `att`, `def<n>`). J.4.4's rows, as found:

| Category | Rows (count of fields over 18,027 pairs) |
|---|---|
| `equal` | 3,927,403 fields: messages (count, roles, order, text including `null`), parts, tool calls (function, args), results, fixtures, judgements with `origin`, the run-level error |
| `differs_expected` | `scope[*]/t/dur_s` rounding (\|Δ\| ≤ 0.0005 s), `attack_id` `null`→`"benign"`, and the `tool_filter` defence's attribution (`message`/`model_call` actor `def<n>` vs the v1 role; the filter's call `auxiliary` vs `agent`) |
| `native_only` | the pipeline/model/defence split (`defense_id`, the defence actor, the requested model), the no-calls encoding, tool-call id status, inferred passes, causal-order basis, and **the `repeat_user_prompt` copies' `copy_of` (774 messages): a J.4.4 row added from this run** |
| `v1_only` | the v1 importer's own `ext.adprov` record (lineage, model, meta keys), the converter actor `harness`, `ext.lex` hints, the tool timing stub `t.raw` |

## C2 in detail

The 13 mutations of audit/validation.md §6.3 are applied to every sampled graph that admits them; the constraint probes
a, b, c and e to the audit's 3-call fixture. The compat port (`prov/compat/adprov_v2_3/{validate,conformance}.py`, frozen)
reproduces the baseline's verdict for every check on every document. The generic tier-4 checks (structure without its two
AgentPROV-format checks, and constraints) differ in five registered ways, each a baseline defect the audit lists:

| Entry | Old (baseline) | New (generic) | Absorbed |
|---|---|---|---|
| `XD-C2-V1-totality` | raises `TypeError` on a scalar relation section | structure fails; constraints skip the section | 4,566 |
| `XD-C2-V2-closed-world` | a typo section and an unprefixed attribute pass | structure fails them | 1,455 |
| `XD-C2-V10-agent-shape` | a non-object agent and a dangling association pass `schema` | structure fails them | 828 |
| `XD-C2-V6-closed-world-typing` | "constraint 50" fails an undeclared endpoint | typing infers it (PROV-CONSTRAINTS) | 695 |
| `XD-C2-V8-builder-invariant` | `schema` holds the builder's one-generation policy (probe a) | valid PROV; no builder policy | 1 |

## C5 in detail

`convert_run` takes `model`, `model_id` and `pipeline_name` from its pipeline argument (the run directory); the native
view takes the log's own `pipeline_name`, which is `"local"` for the `v1.k14` local-model logs (the case J.3.4 predicts)
and another label for two repeat-prompt logs. `XD-C5-pipeline-label-source` absorbs these 15 observations on 5 of the 7
head samples. Versions and `evaluation_timestamp` show no difference: `render_converted` already re-applies those
converter rules.

## CI (`old-vs-new`, manual dispatch; AGENTS.md §8)

The register changed (C2 and C5 entries), which is a point where the manual dispatch is due (§8 item 4). The C2
(`--scope golden`: the baseline corpora are not in the public baseline repository) and C5 steps are in
`.github/workflows/ci.yml`'s `old-vs-new` job after C6 (added once phase 12b's CI changes were on main). The core
environment there now syncs the `shacl` extra, because C2 compares the compat port's SHACL verdicts. A manual dispatch
after this branch merges is the first CI run of both steps.

## C3 in detail

The new side maps each trace with the product mapper (the native June-2024 log for the converted tree, joined by the
converter's layout rule as in gate R; the released transcript with `adprov-v1` for the release tree), annotates it with
`agentdojo.suites@1` and builds the eight facts `score()` reads by their AgentPROV meaning
(`agentprov.migration.gate_c3`: run judgements, attempt scopes, injection-marker annotations, payload fixtures). The
outcome-replay row is the shared input (replay is deferred, AD-10 row 2). 438 s with 10 workers.

The one class of difference: the baseline marks 153 released traces as re-runs because `usage.n_llm_calls` exceeds the
assistant turns held (artefact C07 in `adapters/adprov/artefacts.toml`). AgentPROV agrees on 121, where
`model_config.finish_reasons` counts the same number of calls: the mapper records the lost earlier-pass calls
(`adprov.lost_calls_from_count@1`). On the other 32 the two counters disagree (no discarded attempts, no retry
counters, a final reply with content), so the mapper does not infer an earlier pass; the scored attempt's index is
`lost` and the seal reports `accounting_inconsistent`. A call count above the turns is not by itself evidence of a
pipeline re-run in this corpus: `_CompatLLM`'s retries also raise it (B.9 F-02). The scoring rules then read
`rerun_detected = None` as not re-run: 30 verdicts change only their `rerun` flag (all already scored or unscored for
another reason), and 2 important-instructions traces become scored instead of `rerun_not_reproduced` (one success,
one failure).

**D-215 (user-approved 2026-10-13):** register this as an expected difference (`XD-C3-rerun-inconsistent-counters`, max 9 observations
per trace, release tree only). The alternative, inferring a re-run from `n_llm_calls` alone when the counters disagree,
would assert an earlier pass the evidence does not establish (invariant 2).

## The release chain (2026-10-13)

Run from a scratch checkout at `3523336` (this branch), workers 10, reports under
`docs/reports/migration/release-chain-2026-10-13/` (D's per-execution JSONL, 7.9 MB, stays in the work directory). The
baseline is an APFS clone of `../AgentDojo-PROV-framework` at `579a908`, made clean: the user's checkout has uncommitted
README/CHANGELOG edits, which fail G0's `git.status_clean` in release mode, and the user chose the clone (2026-10-13)
over editing the checkout. Wall: G0 10 s, A 33 min, B 28 min, D 35 min.

Gate D's failure is expected at this point. It re-derives SEM and PROV from **stored** AERs and validates every D8
tier in release mode, and the stored corpora predate regen-batch items 1-19: their AERs carry the profile digests of
their import, so AER-V35 fails on each. Its J.3.5 invariants all hold (the table in `D.md`). Gate E needs a passing
D for the same commit and lock. **Next:** after the regeneration round (the user's separate approval), run D at full
scope with both trees (`--corpus` for `agentdojo-upstream-2024-06` and `adprov-v1-release`) and then E, at one commit.

## Open

- Gates D and E at full scope, after the regeneration round (see "The release chain").
- `agentprov migrate reconcile` (J.3's CLI name) is not added: R3 runs through the tool, as gate R does
  (`tools/agentdojo/import_scan.py`).
