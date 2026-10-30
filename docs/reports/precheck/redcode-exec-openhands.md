# Pre-check dossier: `redcode-exec-openhands`

## 1. Header

| | |
|---|---|
| Corpus | `redcode-exec-openhands` (Zenodo 23168099, CC-BY-4.0, anonymous; RedCode dataset CC BY 4.0, vendored OpenHands MIT except `enterprise/`) |
| Parts | `redcode-exec-openhands · head` (1 part; L2 **blocked**: runner archive context tree; L1 only) |
| Family / profile | `openhands` / `redcode-exec-openhands@1` (dialect `openhands.events` variant `oh-1.5`, catalogue `openhands` v1, SEM `openhands.tools@1`) |
| Pin | 6 trajectory zips + `agent-execution-decisions-supp.zip` under `~/.agentprov/staging/10g/zenodo_23168099` |
| Code commit | L1 `d97d3a57` (batch `wave5`: l1 rc 0 in 31.4 s, l1_09 skipped, l1_10 rc 0); examiner scripts at `34fd4cbc` |
| Kind | wave 5, first examination; registry `planned`, never imported, no stored corpus, not in FA/E2 |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (all 7 confirmed, 4 with count or attribution corrections; PC-04 conditional S0 withdrawn) |
| Data | [`data/redcode-exec-openhands/`](data/redcode-exec-openhands/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `population.json`, `accounts.json`, `exam.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head`: **no `code-head.json`**: L2 never ran (blocked), so no engine or adapter digests were recorded. L1 ran at `d97d3a57` with profile sha256 `5b5e8bfa2fb7`. The only mapping evidence is the phase-10g map census, which ran at phase-10g code, not at the current code.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://zenodo.org/records/23168099 (concept 23107343; version 23107344 is a 7-byte placeholder) | the data; the deposit's own aggregates are the outcome reference |
| Paper | none public ("Which Orders Count?", anonymous; arXiv title search 0) | no author numbers apart from the deposit's aggregates |
| Benchmark | RedCode, https://arxiv.org/abs/2411.07781; https://github.com/AI-secure/RedCode (#2: score 3 = attack success) | requests and scorer codes 3/0/1 |
| Harness | OpenHands 1.5.0 `a77b0550` (CodeActAgent) | producer |

Data-versus-paper notes:
- The Zenodo description names one `trajectories.zip`. The record holds 7 zips (PC-07).
- Every deposit aggregate present equals the per-record scores (H-05). The 3 S1 arms have no `<S>_summary.json`, and the S1 scenario summaries carry a different key set (PC-07).

## 3. Expectations

Pre-registration: [`prereg/redcode-exec-openhands.md`](prereg/redcode-exec-openhands.md), written before any data check (wave 5). Amendment 2.3 (L1 only, archive context tree) applies. Classes follow [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H-01 | supported | 7/7 files match the profile on size, md5 and sha256 |
| H-02 | supported | 5,460 members; 5,460 (arm, scenario, payload) cells, 0 duplicates; 24 python and 19 bash scenarios per arm |
| H-03 | supported | `layout_mismatch` on 3,450 members = every S2/S3 member, 0 S1 (PC-03, R5) |
| H-04 | supported | score join 5,460/5,460, 1 entry per key, 0 orphans; all 24 arm × score counts equal section 4 |
| H-05 | supported (xlsx not tested) | csv scenario rows 182/182, average rows 8/8, risky-level subtotals 24/24, scenario summaries 182/182, arm summaries 5/5 with by_scenario 115/115 |
| H-06 | supported | score 1 on 137 runs (93 bash); score entries hold only `index`, `last_response_full`, `score` |
| H-07 | supported | `claude-sonnet-4-6` 11,789 entries, only in sonnet dirs; `qwen3-coder-30b-a3b-instruct` 20,417, only in qwen dirs |
| H-08 | supported in part | 1.5.0 and CodeActAgent in 5,460/5,460; tool set not re-counted |
| H-09 | supported | 67,312 naive timestamps, 0 parse failures, 2026-09-21..10-04, 0 non-monotone units |
| H-10 | trajectories: supported with caveats; supp zip: **refuted** | trajectories: 0 strict secret shapes, 0 `/Users`, 0 operator, 12 named `/home` artefacts, all sandbox, vendored or generic (PC-04). Supp zip: an HF token shape in 1 shell history, 2 lines (PC-01) |
| H-11 | supported | ids start at 0 and strictly increase; gaps in 5,460 files, 18,519 missing ids; 19,625 causes resolve to an earlier event; 3 uncaused errors |
| H-12 | supported | `finish` in 3,876 runs; the other last events match section 5; 5..16 events per run |
| H-13 | supported | all 4,421 later user messages have the `fixed_replies[0]` digest |
| H-14 | not tested | prompt join needs the map census (follow-up) |
| H-15 | refuted as worded | 0 byte or fingerprint duplicates, but the hash structure differs (PC-06) |
| H-16 | not tested | map census at current code is heavy (follow-up) |
| H-17 | supported in part | 5,460 / 3 / 137 confirmed; 144 not tested |
| H-18 | supported | the key-set variants follow arms (S1 vs S2/S3), as a partial re-summary would produce |
| H-19 | supported (desk) | recorded in PC-07 |

## 4. Level 1 (whole population)

Input: archive mode over the 6 trajectory zips (all verified). The batch never opened the supp zip (PC-02), so the examiner scripts read it directly through `agentprov.ingest` (extraction-free).

| Check | Result (denominator 5,460 artefacts = units) |
|---|---|
| L1-01 | 5,460 walked and selected = registry figure (census); 0 rejected or excluded; auxiliary scanned 0 (PC-02) |
| L1-02 | 5,460 ok; 0 failures of any strict class |
| L1-03 | 0 bidi, tag, zero-width or line-separator characters. Descriptive counts: `json_in_string` 5,460 (tool-call arguments), escaped newline 5,237, escaped unicode 1,136, variation selector 289 (model text) |
| L1-04 | 0 byte-identical files; 0 identical-trajectory groups (5,460 distinct fingerprints); 0 cross-corpus (`_cross/l1-xdup.json`). Case hashes: 2,730 values (PC-06) |
| L1-05 | 8 of 12 (model × target × language) cells present, 4 missing as pre-registered (sonnet bash ×3, qwen S3 bash), 0 extra. The L1 strata cover only S1 (PC-03); the examiner recount covers all 8 arms |
| L1-06 | strict token shapes 0. Generic credential assignment: 183 artefacts, which are RedCode payload content (PC-05). Named `/home/<x>/`: 12 artefacts, 4 digests, 3 real names after removing the `:` regex artefact (PC-04). 0 `/Users`, 0 operator. Supp zip: PC-01, PC-02 |
| L1-07 | `/*/timestamp` 67,312 naive; `model_response.created` 32,206 epoch; both 2026-09-21..10-04; 0 non-monotone |
| L1-08 | 0 empty or tiny files; min 5 events. Flags: `layout_mismatch` 3,450 (R5) plus the L1-06 flags |
| L1-09 / L1-10 | L1-09 skipped by the plan (0 metadata members); L1-10 screened 0 files (PC-02) |

## 5. Level 2

**Blocked** (amendment 2.3, plan `wave5.toml` `l2_blocked`). The profile has 6 same-role download pins, and the scores, prompts and dataset sit in the separate supp zip, which `auxiliary_for` and `ContextTree` cannot reach. A sampled import would leave every unit without its score. So there are no `l2-sample`, `l2` or `code` files, and no validation, recompute, determinism, A2/A3, identity, redaction or withholding results at the current code.

Substitute evidence, phase-10g map census only (phase-10g code, `~/.agentprov/migration-work/phase10g/mapcensus/redcode.json`):
- 5,460 mapped, 0 crash, accounting consistent 5,460.
- Issues: `filtered_events` 5,460, `join_after_rewrite` 144, `harness_error` 3.
- Outcomes: `attack_succeeded` true 3,803 / false 1,520, plus `non_informative` 137.
- Evidence classes: `tool_execution:D` 14,165, `model_call:O` 18,041 + `:I` 4,421, `fixture:D` 5,460, `message:O` 46,508.
- Tier-4 checks gave only not-applicable results. The j3 and j8 digests were identical.

Twin, native and mixed statement counts are not available. Withholding is not applicable to the trajectories (no `[withhold]` table). The redaction question for AER is PC-04.

CC-07 (#181/#161) does not apply: this is not an AgentDojo-format corpus.

## 6. Outcome comparison (whole population, L1, tolerance 0)

There are no paper numbers. The reference is the census `score_values_joined`, which equals the deposit's csv and summary JSON (H-05). Execution = score 3, refusal = score 0.

| Arm | n | execution % [Wilson 95] | refusal % | score 1 | reference execution % | gap | verdict |
|---|---:|---|---:|---:|---:|---:|---|
| sonnet / S1 / py | 720 | 74.58 [71.28, 77.63] | 25.14 | 2 | 74.58 | 0 | equal |
| sonnet / S2 / py | 720 | 54.86 [51.21, 58.46] | 44.72 | 3 | 54.86 | 0 | equal |
| sonnet / S3 / py | 720 | 51.25 [47.60, 54.88] | 46.94 | 13 | 51.25 | 0 | equal |
| qwen / S1 / py | 720 | 72.36 [68.98, 75.50] | 26.67 | 7 | 72.36 | 0 | equal |
| qwen / S1 / sh | 570 | 66.84 [62.88, 70.58] | 23.33 | 56 | 66.84 | 0 | equal |
| qwen / S2 / py | 720 | 81.67 [78.67, 84.32] | 17.08 | 9 | 81.67 | 0 | equal |
| qwen / S2 / sh | 570 | 82.11 [78.75, 85.03] | 11.40 | 37 | 82.11 | 0 | equal |
| qwen / S3 / py | 720 | 75.56 [72.29, 78.55] | 23.06 | 10 | 75.56 | 0 | equal |
| **total** | 5,460 | 3,803 | 1,520 | 137 | | | 0 flagged gaps |

Score 1 is ambiguous between Failure and the harness default (D-177, `score_one_ambiguous`). The mapped outcome recount at the current code is a follow-up (H-16).

## 7. Findings

| Id | Title | Class | Sev | Sec | Verdict |
|---|---|---|---|---|---|
| PC-01 | [CC-11 class] supp zip `environment/<seg>/.bash_history` (1 member; verifier correction from 2) holds the same Hugging Face token-shaped string on 2 identical `export HF_TOKEN=` lines (length withheld = `hf_` + length withheld, `<secret-C>`). No placeholder word; 0 in trajectories. Not selected by the profile, but inside a pinned file that enters the raw store | source-defect (CC-13 real-format secret of the source's own infrastructure; reclassified 2026-10-21 from S2) | S0 | **yes** | confirmed |
| PC-02 | [R5] The batch never opened the supp zip: L1-06 aux 0 files, L1-10 0 files, so PC-01 and 12 `environment/` home names were missed | analysis-artefact | S3 | no | confirmed |
| PC-03 | [R5] `_RC` requires the `_py`/`_sh` tag: 3,450 S2/S3 members get `layout_mismatch` and stratum `<none>`; there is no hook for supp-zip outcomes | analysis-artefact | S3 | no | confirmed |
| PC-04 | [CC-03] 12 trajectories hold a named `/home/<x>/`. 10 are the OpenHands sandbox user: 4 plain, and 6 (`<account-B>`) where the tool regex admits `:` and captured `openhands:` from a PATH list. 1 is a vendored OpenHands string (`environment/OpenHands`, not the RedCode dataset as first stated). 1 (`03924d78`) is `test_user:` from an agent `mkdir`. 0 operator, 0 workstation account. These reach AER content on import | expected-known | S3 | no | confirmed (conditional S0 withdrawn) |
| PC-05 | [R5] 183 "secret-like" artefacts come from the generic assignment rule on RedCode payload code: 1,665/1,783 matches are dataset strings, 17 distinct, 0 strict tokens | analysis-artefact | S3 | no | confirmed |
| PC-06 | [R4] Case-hash structure: qwen S2 bash shares the S2 python hash (570 triples), and 570 S1 bash hashes are unique. R10g line 200 is incomplete (omits the S2 bash sharing) and the prereg's 1,140 unique bash hashes is wrong. No join impact | documentation-mismatch | S3 | no | confirmed |
| PC-07 | [R3] Deposit documentation and layout: one-zip description vs 7 zips; 3 S1 arms without an arm summary; S1 scenario summaries with `jsonfile` (46 also with `duration_sec`, 21 without; verifier correction from 67) | documentation-mismatch | S3 | no | confirmed |

Proposed `artefacts.toml` entry (text only, to the openhands family owner):

```toml
# [[artefact]] id = "openhands.art.deposit_shell_history_token"   # PC-01
#   scope = { sources = ["redcode-exec-openhands"], parts = ["head"] }; unit = "members"; count = 1 (2 lines, 1 distinct token shape)
#   handling = withhold at seal, digests kept (CC-11 / D-345; member carving as D-315); basis "pre-check PC-redcode-exec-openhands-01"
```

AGENTS.md section 12 items:
- PC-01 security (S0 under CC-13, real-format secret, not a fixture): Zenodo 23168099 supp zip ships a shell history (1 member) with an HF-token-shaped string; withhold before any seal.
- (PC-04 item withdrawn by the verifier: `<account-B>` is the sandbox user `openhands` plus a `:` regex artefact.)

## 8. Recommendations and readiness

1. **PC-01: report to the orchestrator now** (README section 5). The user decides between withholding the 1 member (carved) and withholding the whole supp zip with a carved remainder, and whether the anonymous depositors or Zenodo are told. Never print the value.
2. PC-04: no private classification needed (verifier). Tool fix (R5): exclude `:` from the account-name class in `l1_scan`/`l1_context`, and add `openhands` and `test_user` to the generic account list.
3. Tool fixes before the post-check (R5): add the supp zip as an aux/context input in archive mode (PC-02); make the `_RC` language tag optional and add a redcode outcome hook (PC-03).
4. Run the map census at the current code through the queue (follow-ups), then L2 once the runner reaches the supp-zip auxiliaries.
5. Do not exclude any data. The 4 missing bash cells are a design property of the deposit.

**Readiness: `blocked`** (verifier: confirmed).
- The product import cannot attach scores (runner archive context tree), so the round cannot import this corpus as it stands.
- PC-01 (S0 security under CC-13) needs a withhold decision before any seal of this source; any release stays blocked until that decision.
- The raw data itself is clean: pins verified, 5,460/5,460 parse, scores join, every outcome count and deposit aggregate reproduces at tolerance 0, and there are no duplicates.

## 9. Reproduction

```bash
# batch (wave 5)
uv run python tools/precheck/l1_scan.py --source redcode-exec-openhands --part head --corpus-id redcode-exec-openhands --jobs 2 --emit-fp --input ~/.agentprov/staging/10g/zenodo_23168099
# l1_10 step (tools/precheck/l1_context.py via run_batch, plan wave5.toml): files_screened 0
# examiner (S = docs/reports/precheck/data/redcode-exec-openhands/exam-scripts, W = ~/.agentprov/migration-work/precheck/redcode-exec-openhands/exam)
uv run python -I S/pop.py    W/pop.json     # pins, arms, cells, ids, causes, models, fixed replies, join, outcomes, aggregates, account/secret scan
uv run python -I S/acct.py   W/acct.json    # account first-seen class, credential matches vs dataset, csv non-scenario rows, summary arms
uv run python -I S/acct2.py  W/acct2.json   # unresolved-name context classes; shell-history counts (PC-01)
uv run python -I S/envsec.py W/envsec.json  # strict token shapes in environment/ (shape stats only)
uv run python -I S/agg2.py   W/agg2.json    # H-18 key sets by arm; csv subtotals vs scenario rows
uv run python -I S/vpc01.py  W/verify-pc01.json   # verifier: hf_ shapes per member, line prefix words, trajectory recount (shape stats only)
uv run python -I S/vpc04.py                         # verifier: home-name shapes and contexts (':'-split digests computed inline, see findings.json PC-04)
python3 -c "import json,re,collections as C;g=C.defaultdict(list)
for l in open('$HOME/.agentprov/migration-work/precheck/redcode-exec-openhands/l1-units-head.jsonl'):
  m=re.search(r'OH/([^/]+)/(S\d)/(\w+)/.*-([0-9a-f]+)\.json',json.loads(l)['label']);g[m[4]].append(m[1][:6]+'/'+m[2]+'/'+m[3])
print(C.Counter('+'.join(sorted(v)) for v in g.values()))"   # PC-06
```

Follow-ups (not run):

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-redcode-exec-openhands -- \
  uv run python -I tools/openhands/map_census.py redcode --zips ~/.agentprov/staging/10g/zenodo_23168099 \
  --out ~/.agentprov/migration-work/precheck/redcode-exec-openhands/exam/mapcensus.json \
  --digests ~/.agentprov/migration-work/precheck/redcode-exec-openhands/exam/mc.j2.digests.jsonl --jobs 2   # H-14, H-16, H-17; repeat --jobs 1, compare digests
```
