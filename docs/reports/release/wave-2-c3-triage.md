# Wave-2 release-scan triage (C-3)

Date: 2026-10-30, Mac Studio. Code: branch `claude/c3-triage-wave2-ecbe12` from `main` `ed72bae9`, with the two class-0
changes to `tools/release_triage.py` described below. Python 3.14.8 (core venv), gitleaks 8.30.1. All heavy jobs went
through `tools/suite_queue.py --class import`.

**No sealed tree was written. Nothing was tagged, packaged, deposited or pushed.** This report holds rules, key names,
ordinals, counts and digests only: no value, address, account name, path or benchmark text. The evidence was computed
value-blind, with values and names held in memory only (scripts in the session scratchpad; see section 7).

## 1. Outcome

The 15 wave-2 trees whose seal-time scan exited 1 (712,538 untriaged findings) and DTap's `dtap-bench-w2c` now each have
`<tree>.release-triage.toml` beside the sealed tree. `tools/release_triage.py` wrote it from the decisions file in
[`wave-2-c3-triage/triage-decisions/`](wave-2-c3-triage/triage-decisions/) (one per corpus, value-blind, like round 1's).
For every tree the tool exited 0, with **0 findings left untriaged**. `tools/release_scan.py --triage` then scanned each
tree again. Every rescan has the sealed root digest and exactly the seal-time fingerprints, and holds **0 untriaged and
0 `real`** findings. **There are no STOP items**: no finding looked like a real secret, a real person's address or an
unexplained account path. Under the orchestrator's later account-path guidance, 27 ordinals in 3 trees (26 distinct
names, 417 findings) were STOP-candidates: names first seen in benchmark tool output and in no benchmark definition. The
user decided on 2026-10-30 to keep them as triaged (section 5, item 4).

| Tree | Untriaged before (gitleaks / account-path) | `synthetic-benchmark` | `model-generated` | `false-positive` | `pinned-account` | Left | Rescan |
|---|---:|---:|---:|---:|---:|---:|---|
| `agentdyn-b-w2` | 2,972 (1,252 / 1,720) | 1,379 | 1,124 | 469 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `agentdyn-c-w2` | 3,001 (1,244 / 1,757) | 1,391 | 1,118 | 492 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `code-agent-misalignment-w2` | 744 (744 / 0) | 630 | 0 | 114 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `controlarena-persistent-w2b` | 11 (11 / 0) | 0 | 0 | 11 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `credleak-p15b-w2b` | 10 (10 / 0) | 0 | 0 | 10 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `fragfuse-agentharm-w2` | 19,194 (355 / 18,839) | 18,873 | 277 | 44 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `kexin-xu-01-agentharm-w2` | 2,380 (1,174 / 1,206) | 1,571 | 748 | 61 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `llm-lock-agentdojo-w2` | 17 (4 / 13) | 15 | 0 | 2 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `mcphunt-w2b` | 25 (13 / 12) | 1 | 12 | 12 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `openagentsafety-w2` | 1,322 (1,263 / 59) | 724 | 576 | 4 | 18 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `redcode-exec-openhands-w2` | 372 (72 / 300) | 303 | 54 | 15 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `redcode-exec-qwencode-w2` | 133 (44 / 89) | 89 | 44 | 0 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `tacit-agentdojo-w2` | 143 (0 / 143) | 143 | 0 | 0 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `what-surrounds-w2` | 1,849 (0 / 1,849) | 1,849 | 0 | 0 | 0 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `whistlebench-w2` | 680,365 (10 / 680,355) | 679,446 | 8 | 550 | 361 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| `dtap-bench-w2c` | 160,007 (2,184 / 157,823) | 147,642 | 279 | 66 | 12,020 | 0 | same root digest and fingerprints; 0 untriaged, 0 `real` |
| **Total** | **872,545** (8,380 / 864,165) | **854,056** | **4,240** | **1,850** | **12,399** | **0** | |

The other 36 sealed trees (28 of wave 2 and round 1's 8) already scan with 0 untriaged and need no triage file from this
step.

**Deposit builder.** The builder's per-corpus gates ran on all 52 sealed trees (`release.builder._open_corpus` with its
default verifier: the scan and triage checks, closed world, and the D-236 and D-964 withhold backstops; it writes
nothing). **All 52 pass.** At first `controlarena-persistent` and `credleak-p15b` were refused (`release.refused.withhold_scan`).
Their `[withhold]` policies list `generic-api-key` in `scan_rules`, and D-236 accepts a released finding of such a rule
only as `false-positive`. With the reviewer's approval those 20 findings were re-triaged (section 4a).

## 2. Inputs and method

* **Approved basis.** The rule-based classes are those of round 1's check 4b (user-approved 2026-10-28, item 2), which
  wave 2 adopted as decision 11 (`docs/reports/release/wave-2-pre-release-checks.md`, check 4b):
  * `upstream-data` and `benchmark-input` → `synthetic-benchmark`;
  * `model-generated` → `model-generated`.

  The verdicts on findings with no derivable origin are decision 11's secret review. For the 15 trees, that is
  `~/.agentprov/migration-work/wave-2/secret-review/decisions.toml`, made by the orchestrator under the user's
  delegation. For DTap, it is `secret-review-dtap/decisions.toml`, made under the DTap pre-approval. Account ordinals
  follow round 1's check 4c method (user-approved):
  * a name in the benchmark's own data, or one the benchmark supplies (first in a benchmark-input record) →
    `synthetic-benchmark`;
  * a path the model made up (first in model output, not in the benchmark data) → `false-positive`.

  Two further bases are user decisions already on record. D-604 item 7 (2026-10-21): raw residue that ships as pinned
  takes `pinned-account`. Decision 5 of the wave-2 checks covers what-surrounds' MCPTox quote.
* **Suite data** (`--suites`, the origin rule's "benchmark's own suite data") are the same as the wave-2 forecast's, so
  the classes line up with decision 11's groups:
  * the AgentDojo package suites for every tree;
  * plus AgentDyn-main's suites for `agentdyn-c`;
  * the AgentHarm data for the two AgentHarm trees;
  * the DecodingTrust-Agent-Platform checkout at the pin for DTap.

  Wider benchmark definitions served only as evidence, never as an origin: AgentDyn's suites for `agentdyn-b`, and
  OpenAgentSafety's workspaces and servers.
* **Evidence for leftovers** (value-blind). For gitleaks values:
  * the value's shape and placeholder markers;
  * whether it occurs in the benchmark's definitions;
  * the first record of a citing execution's AER that holds it;
  * per-run value ordinals, to see which findings share a value;
  * for PEM keys, whether the body is a well-formed DER key and whether it equals a key of a D-964-withheld object.

  For account ordinals:
  * per execution, the kind of the first AER record that holds the path. Post-hoc judge text and the agent's final
    answer stored in the execution record are skipped (section 5);
  * the role and key of raw JSON strings that hold it;
  * name membership in the benchmark definitions;
  * the ordinal of the same name in round 1's corpora of the same benchmark (agentdyn-a, ast-survey-agentharm) and in
    the sibling wave-2 tree;
  * equality with a generic account an earlier pre-check names.

  All of these yield ordinals and booleans only.

### Two class-0 changes to `tools/release_triage.py`

1. **Archive members (D-491).** The tool skipped `account-path` findings in archive members (`<archive>#<locator>`), so
   45,560 of them could never be triaged: whistlebench 45,555, what-surrounds 4, kexin 1. It now reads those members
   decoded, exactly as the scan read them: `withhold_scan.scan_archives`, the same declared depth, and the same stored
   members skipped. The member's name counts as line 0, then its data. It numbers their names in the same
   first-appearance order, labels in sort order. Trees with no member findings, including all of round 1, number as
   before.
2. **`pinned-account` (D-604 item 7).** The scan and the deposit builder already accept this triage for a third-party
   account in `raw/` that ships as pinned. The tool could not write it. An `[[account]]` row may now give it, but only
   for an ordinal whose hits are all `raw-object`; anything else is refused. On a line with several ordinals it is
   chosen first.

Tests: `tests/unit/release/test_release_triage_tool.py` (25 pass, 4 new): a deflated zip member's ordinals match the
scan's fingerprints; `pinned-account` is refused outside raw-only ordinals and in `[[secret]]` rows; a shared line takes
it. Byte class 0: `tools/` only, outside every stage scope; no corpus byte changes.

## 3. Per tree: classes, rules and leftover verdicts

| Tree | gitleaks by origin (rule-based; in controlarena and credleak, D-236 makes the `generic-api-key` ones `false-positive`, section 4a) | Leftover classes (`unclassified`) and verdicts | Ordinals by triage |
|---|---|---|---|
| `agentdyn-b-w2` | benchmark-input 34, model-generated 24 | `generic-api-key` / `is` 4 → `synthetic-benchmark`; `generic-api-key` / `key` 4 → `synthetic-benchmark`; `generic-api-key` / `password` 1096 → `model-generated`; `generic-api-key` / `requested` 4 → `synthetic-benchmark`; `generic-api-key` / `token` 4 → `model-generated`; `private-key` / `(none)` 82 → `synthetic-benchmark` | `false-positive` 9, `synthetic-benchmark` 11 |
| `agentdyn-c-w2` | model-generated 12, upstream-data 123 | `generic-api-key` / `password` 1102 → `model-generated`; `generic-api-key` / `token` 4 → `model-generated`; `private-key` / `(none)` 3 → `false-positive` | `false-positive` 9, `synthetic-benchmark` 11 |
| `code-agent-misalignment-w2` | benchmark-input 630 | `generic-api-key` / `_api.py` 9 → `false-positive`; `generic-api-key` / `_tokenizer.py` 9 → `false-positive`; `generic-api-key` / `api.py` 21 → `false-positive`; `generic-api-key` / `api_jwk.py` 1 → `false-positive`; `generic-api-key` / `api_jws.py` 1 → `false-positive`; `generic-api-key` / `api_jwt.py` 1 → `false-positive`; `generic-api-key` / `auth.py` 31 → `false-positive`; `generic-api-key` / `keys.pyi` 1 → `false-positive`; `generic-api-key` / `keywrap.py` 1 → `false-positive`; `generic-api-key` / `python_api.py` 9 → `false-positive`; `generic-api-key` / `test_auth.py` 12 → `false-positive`; `generic-api-key` / `token.py` 18 → `false-positive` | none |
| `controlarena-persistent-w2b` | upstream-data 4 | `generic-api-key` / `API_KEY` 4 → `false-positive`; `generic-api-key` / `API_KEY+key` 2 → `false-positive`; `generic-api-key` / `key` 1 → `false-positive` | none |
| `credleak-p15b-w2b` | benchmark-input 2, model-generated 7 | `curl-auth-user` / `(none)` 1 → `false-positive` | none |
| `fragfuse-agentharm-w2` | benchmark-input 58, model-generated 277, upstream-data 9 | `generic-api-key` / `key` 11 → `synthetic-benchmark` | `false-positive` 7, `synthetic-benchmark` 11 |
| `kexin-xu-01-agentharm-w2` | benchmark-input 229, model-generated 748, upstream-data 197 | none | `false-positive` 7, `synthetic-benchmark` 5 |
| `llm-lock-agentdojo-w2` | upstream-data 4 | none | `false-positive` 1, `synthetic-benchmark` 1 |
| `mcphunt-w2b` | benchmark-input 1, model-generated 12 | none | `false-positive` 1 |
| `openagentsafety-w2` | benchmark-input 667, model-generated 576, upstream-data 14 | `generic-api-key` / `feed_token` 3 → `synthetic-benchmark`; `generic-api-key` / `requesttoken` 3 → `synthetic-benchmark` | `false-positive` 1, `pinned-account` 9, `synthetic-benchmark` 3 |
| `redcode-exec-openhands-w2` | benchmark-input 12, model-generated 54 | `generic-api-key` / `Key` 1 → `synthetic-benchmark`; `generic-api-key` / `Password` 1 → `false-positive`; `generic-api-key` / `key` 3 → `synthetic-benchmark`; `generic-api-key` / `password` 1 → `synthetic-benchmark` | `false-positive` 1, `synthetic-benchmark` 2 |
| `redcode-exec-qwencode-w2` | model-generated 44 | none | `synthetic-benchmark` 1 |
| `tacit-agentdojo-w2` | none | none | `synthetic-benchmark` 1 |
| `what-surrounds-w2` | none | none | `synthetic-benchmark` 1 |
| `whistlebench-w2` | benchmark-input 2, model-generated 8 | none | `false-positive` 10, `pinned-account` 1, `synthetic-benchmark` 1 |
| `dtap-bench-w2c` | benchmark-input 199, model-generated 279, upstream-data 1,704 | `generic-api-key` / `CUST1004` 2 → `synthetic-benchmark` | `false-positive` 13, `pinned-account` 5, `synthetic-benchmark` 48 |

Leftover gitleaks classes, with the evidence and the review group (decision 11) they apply:

* **agentdyn-b**
  * `password` 1,096 → `model-generated` (G01+G02, same count). The passwords sit in uncited raw run files, first as the
    model's own tool-call argument (round 1 item 6).
  * `private-key` 82 → `synthetic-benchmark` (G03; 88 in the forecast; the 3 objects D-964 withholds hold the other
    6, as gitleaks counts them there). All
    83 values are placeholder-marked or have a non-base64 body; none is a well-formed DER key; none equals one of the 5
    keys in the withheld objects.
  * `is`, `key`, `requested` 4 each → `synthetic-benchmark` (G04–G06): one value, which is in AgentDyn's suite data.
  * `token` 4 → `model-generated` (G07): a UUID in a URL the model composed.
* **agentdyn-c**
  * `password` 1,102 → `model-generated` (G08+G09, same count).
  * `token` 4 → `model-generated` (G10).
  * `private-key` 3 → `false-positive` (G11): placeholder-marked, not DER.
* **code-agent-misalignment.** 12 classes whose keys are library file names, 114 findings → `false-positive` (G13–G29,
  the file-to-SHA-256 manifest): every value is hex. C-3's pairing gave the review's other 179 an origin
  (`benchmark-input`, so `synthetic-benchmark` by rule).
* **controlarena-persistent.** `API_KEY` 4, `API_KEY+key` 2 and `key` 1 → `synthetic-benchmark` by G30, then `false-positive`
  under D-236 (section 4a). G30 is mock
  configuration in a traceback). The 7 findings hold 2 distinct values, both G30's. The 7th finding, which the forecast
  classed `model-generated`, holds one of them: the metadata-only seal withholds the AER the forecast had paired it
  with (D-344).
* **credleak-p15b.** `curl-auth-user` 1 → `false-positive` (G31, placeholder). Its 9 rule-based `generic-api-key`
  findings are `false-positive` under D-236 (section 4a).
* **fragfuse-agentharm.** `key` 11 → `synthetic-benchmark` (G32+G37). One value, first in the citing execution's own
  execution record. The review's other fragfuse groups and all of kexin's (G33–G42) now have an origin by C-3's pairing.
* **openagentsafety**
  * `feed_token` 3 and `requesttoken` 3 → `synthetic-benchmark` (G53, G54, same counts): the benchmark's GitLab service
    tokens, first in tool output.
  * G51, G58 and G69 (withheld by D-964) are not in the sealed tree.
* **redcode-exec-openhands**
  * `key` 3, `Key` 1 and `password` 1 → `synthetic-benchmark` (G70, G71, G73).
  * `Password` 1 → `false-positive` (G72, placeholder).
* **dtap-bench.** `CUST1004` 2 → `synthetic-benchmark` (DTap G02: the customer-service fixture credential, first in tool
  output). G01's gatewayToken is in no released file (the 3 withheld executions), and G03–G06 now have an origin by rule.

Account ordinals (by tree; "round-1 name" means the same name, compared value-blind, in a round-1 corpus of the same
benchmark, with its user-approved class):

* **agentdyn-b and agentdyn-c**, 20 ordinals each. Each tree's 20 names are exactly agentdyn-a's 20 (round 1, check 4c
  and item 6), and each takes agentdyn-a's class: 11 `synthetic-benchmark` and 9 `false-positive` per tree. The
  AgentDyn suite data agrees in all 40: every `synthetic-benchmark` name is in it and no `false-positive` one is. #7–#20
  sit only in uncited raw run files of other AgentDyn parts (as round 1's #18–#20).
* **fragfuse-agentharm**, 18 ordinals:
  * 10 are round-1 ast-survey-agentharm names and take their class. #1–#9 are `synthetic-benchmark` (#1–#3 and #8 are also
    in the AgentHarm data); #14 is `false-positive`.
  * #17 (first in scripted tool output; also kexin #4) and #18 (first in the attack harness's own logged plan and the
    user turns) → `synthetic-benchmark`.
  * #10–#13, #15 and #16 are first in model output in every execution → `false-positive`.

  Pre-check fragfuse CC-03 already judged the `/home/` names benchmark content. The two real `/Users/` accounts were
  withheld with the raw logs (D-604, 164 logs).
* **kexin-xu-01-agentharm**, 12 ordinals:
  * #1, #2 and #10 → `synthetic-benchmark`, as round-1 names (#10 is also in the prompt and the AgentHarm data).
  * #8 → `synthetic-benchmark` (in the AgentHarm data).
  * #4 → `synthetic-benchmark` (scripted tool output; also fragfuse #17).
  * #6 → `false-positive`, as a round-1 name.
  * #3, #5, #7, #9, #11 and #12 → `false-positive` (first in model output).
* **llm-lock.** #1 is in the AgentDojo suite data → `synthetic-benchmark`; #2 is first in model output →
  `false-positive`.
* **mcphunt.** #1 → `false-positive`. It is first in assistant text in each of its 4 executions, and it equals the
  generic container account pre-check mcphunt L1-06 names ("all generic").
* **openagentsafety**, 13 ordinals:
  * #1, #3 and #4 are in OpenAgentSafety's own workspaces and servers → `synthetic-benchmark`.
  * #2 is first in model output → `false-positive`.
  * #5–#13 are raw-only, D-606's 9 raw-only names → `pinned-account` (D-604 item 7: raw trajectories and state files
    ship as pinned).
* **redcode-exec-qwencode** #1 and **redcode-exec-openhands** #2 are the same name, first in the RedCode-Exec task
  fixture in every execution → `synthetic-benchmark`.
* **redcode-exec-openhands**, other ordinals:
  * #1 → `synthetic-benchmark`: the OpenHands sandbox user (pre-check PC-04), first in sandbox tool output in 7 of 8
    executions.
  * #3 → `false-positive`: first in model output; PC-04's name from an agent `mkdir`.
* **tacit-agentdojo.** #1 is the AgentDojo banking persona's first name (pre-check PC-05) → `synthetic-benchmark`.
* **what-surrounds.** #1, all 1,849 findings → `synthetic-benchmark` (decision 5, the MCPTox quote).
* **whistlebench**, 12 ordinals:
  * #1, the scenario user of all 8,800 high-agency samples (first in the scenario fixture), → `synthetic-benchmark`.
  * #2–#11 are first in model output in every execution; the name appears only later in user turns and judge
    records →
    `false-positive`.
  * #12 is D-601's workstation account in the `error_retries` tracebacks of 260 raw samples. Its AER copies are
    redacted → `pinned-account` (D-604 item 7).
* **dtap-bench**, 66 ordinals:
  * 23 are in DTap's task configurations at the pin → `synthetic-benchmark`. That is the forecast's count.
  * 25 are first in tool output or sandbox state in at least one execution → `synthetic-benchmark`. D-607's pre-check
    judged these benchmark or model content.
  * 13 are first in model output in every execution (the agent's text, or once a judgement quoting it) →
    `false-positive`.
  * #62–#66 are D-607's five harness-host accounts, raw only (the AER holds `acct-` labels) → `pinned-account` (D-604
    item 7; statement `dtap-host-accounts-redacted`).

## 4. DTap

`dtap-bench-w2c` (sealed from `3000b220`; 651,821 scan findings, 160,007 untriaged: gitleaks 2,184, account-path
157,823).

* **gitleaks:** 2,182 by rule and 2 leftovers.
  * By rule: upstream-data 1,704 (DTap's own repository at the pin as suite data) and benchmark-input 199 →
    `synthetic-benchmark`; model-generated 279 → `model-generated`.
  * The 2 leftovers, `CUST1004`, → `synthetic-benchmark` (DTap review G02).
  * DTap review G01's gatewayToken is in no released file.
* **account-path:**
  * 145,737 findings → `synthetic-benchmark`: 48 ordinals (the 23 task-configuration names and the 25 environment
    names).
  * 66 → `false-positive`: 13 ordinals.
  * 12,020 → `pinned-account`: #62–#66, in raw trajectories only.
* **Result:** 160,007 triage entries, 0 left untriaged; triaged as `synthetic-benchmark` 147,642, `model-generated` 279,
  `false-positive` 66, `pinned-account` 12,020. Decisions file sha256 `24387521…87ef`, recorded in the triage file's
  header.
* **Rescan:** same root digest and fingerprints as the seal-time scan; 0 untriaged, 0 `real`. The builder's gates pass (section 1).

## 4a. D-236: the 20 re-triaged findings

The reviewer approved this (the orchestrator, applying D-236, which the user approved on 2026-10-13; no new rule).
Each reason keeps the earlier class and its basis, then gives the value-blind evidence:
* controlarena: 5 distinct values, each weak-worded or placeholder-marked;
* credleak: 2 values, both model-first, one placeholder-marked;
* in both trees, 0 hits for the policy's canary and byte rules in released files.

All 20 fit that evidence. Both trees were rescanned (same root digest and fingerprints, 0 untriaged, 0 `real`), and the
builder's gates pass for both.

| Tree | Fingerprint | Rule / key | Earlier class (basis) | New class |
|---|---|---|---|---|
| `controlarena-persistent-w2b` | `raw/objects/0d/0d8271eb80fd8efec8ac4cadf5f5fc383811f7facb14eb4ad2b4f258f141d96b.json:generic-api-key:334` | `generic-api-key` / `API_KEY` | `synthetic-benchmark` (upstream-data rule) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/30/30e3022963a71e02a637e8cf6542b21c4e3e4b35dcb1232b74b2fc6920ba4472.json:generic-api-key:333` | `generic-api-key` / `API_KEY` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/30/30e3022963a71e02a637e8cf6542b21c4e3e4b35dcb1232b74b2fc6920ba4472.json:generic-api-key:334` | `generic-api-key` / `API_KEY` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/48/484580f1f46ff09123f3acf81288b9f19a9090cb0dc0ff0facdd02245d4c0f7f.json:generic-api-key:336` | `generic-api-key` / `API_KEY` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/48/484580f1f46ff09123f3acf81288b9f19a9090cb0dc0ff0facdd02245d4c0f7f.json:generic-api-key:337` | `generic-api-key` / `API_KEY` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/6d/6de4bc0001d6c3e4cd291e31f3d3e99f5ddc4f1a17fbfd5fe0db111ac7f2787c.json:generic-api-key:332` | `generic-api-key` / `key` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/6d/6de4bc0001d6c3e4cd291e31f3d3e99f5ddc4f1a17fbfd5fe0db111ac7f2787c.json:generic-api-key:333` | `generic-api-key` / `API_KEY+key` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/6d/6de4bc0001d6c3e4cd291e31f3d3e99f5ddc4f1a17fbfd5fe0db111ac7f2787c.json:generic-api-key:334` | `generic-api-key` / `API_KEY+key` | `synthetic-benchmark` (decision 11, G30) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/c3/c3b58f17787ea70277b09cffc2165537069636399dd31f9b55a349ff276a4184.json:generic-api-key:335` | `generic-api-key` / `api_key_value` | `synthetic-benchmark` (upstream-data rule) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/e0/e096e3c27d9bdbd9ded2c84fbc1b61b810e4430350216887f2ed2c8383eef97c.json:generic-api-key:336` | `generic-api-key` / `test_api_key` | `synthetic-benchmark` (upstream-data rule) | `false-positive` |
| `controlarena-persistent-w2b` | `raw/objects/e0/e096e3c27d9bdbd9ded2c84fbc1b61b810e4430350216887f2ed2c8383eef97c.json:generic-api-key:337` | `generic-api-key` / `mtest_api_key` | `synthetic-benchmark` (upstream-data rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/0b/ex_bss4o2ahymyslamrqlos5ecrw7.aer.jsonl:generic-api-key:19` | `generic-api-key` / `localhost` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/29/ex_rstpk7vqmmret4yyrrkfbjch5m.aer.jsonl:generic-api-key:19` | `generic-api-key` / `localhost` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:37` | `generic-api-key` / `nAPI_KEY` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:38` | `generic-api-key` / `nAPI_KEY` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:42` | `generic-api-key` / `nAPI_KEY` | `synthetic-benchmark` (benchmark-input rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:52` | `generic-api-key` / `nAPI_KEY` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:53` | `generic-api-key` / `nAPI_KEY` | `model-generated` (model-generated rule) | `false-positive` |
| `credleak-p15b-w2b` | `aer/37/ex_snanhiqbsy23he3oo3mwf5hhhm.aer.jsonl:generic-api-key:57` | `generic-api-key` / `nAPI_KEY` | `synthetic-benchmark` (benchmark-input rule) | `false-positive` |
| `credleak-p15b-w2b` | `raw/objects/d4/d4ed3beb9954a503ce527cb6994569f9f15e8c154d7720726665867bf71c8c6c.json:generic-api-key:1` | `generic-api-key` / `localhost` | `model-generated` (model-generated rule) | `false-positive` |

## 5. For the reviewer (decision 11's reviewer, the orchestrator)

None of these changes a released byte or needs a re-seal. Items 1, 2 and 4 move findings between triages that the deposit
accepts alike.

1. **Counts that differ from the review's groups** (the review pack says such a group "comes back to the reviewer"). In
   every case below, C-3's finer pairing of copies gave part of a group an origin, so the C-3 class is the group's
   remainder and takes the group's verdict. The one count that went up is controlarena's G30: 6 → 7, and the extra
   finding holds a G30 value.

   | Corpus | Group(s) | Review count | C-3 `unclassified` |
   |---|---|---:|---:|
   | `agentdyn-b` | G03 | 88 | 82 (the other 6 are in the 3 D-964-withheld objects) |
   | `code-agent-misalignment` | G13–G29 | 293 | 114 |
   | `controlarena-persistent` | G30 | 6 | 7 |
   | `fragfuse-agentharm` | G32+G37; G33–G36, G38 | 103; 69 | 11; 0 |
   | `kexin-xu-01-agentharm` | G39–G42 | 54 | 0 |
   | `openagentsafety` | the 22 groups other than G53, G54 and the D-964 ones | 113 | 0 |
   | `redcode-exec-openhands` | G70; G71; G72; G73 | 6; 2; 2; 2 | 3; 1; 1; 1 |
   | `whistlebench` | G75+G76 | 5 | 0 |
   | `dtap-bench` | G02; G03–G06 | 6; 10 | 2; 0 |

2. **Method points** (choices within round 1's check 4c method, not new classes):
   * The first-appearance test skips text that quotes the model after the fact:
     * the AgentHarm refusal judge's `refusal_explanations` and DTap's `final_response`, both stored in the execution
       record;
     * score and judge fields.

     Without the skip, 5 ordinals would read "first in the execution record" and move from `false-positive` to
     `synthetic-benchmark`: kexin #7 and #9, fragfuse #10 and dtap #59, plus kexin #6, which round 1's class
     (ast-survey-agentharm #11) supports anyway.
   * Cross-corpus name identity (agentdyn-a for agentdyn-b and -c; ast-survey-agentharm for the AgentHarm trees) carries
     round 1's approved class to the same name. The benchmark data agrees wherever it was checked.
   * The DTap names first seen in sandbox tool output (25) are taken as the benchmark environment's accounts,
     `synthetic-benchmark`, as D-607's note on its 137 other named accounts does. A few look like full environments:
     #13 (`miniconda3`, `workspace`) and #49 (`.claude`, `anaconda3`), first in tool output; #8 and #14 are Windows
     profiles in desktop-state output. They are none of the five harness accounts, which the AER redacts.

3. **D-236** is resolved (section 4a). A related point stays: for controlarena and openagentsafety, "upstream-data" (4 and
   14 findings) came from matching the AgentDojo suites, as in the forecast. Those are not their benchmarks' own data,
   so the rule says little there. controlarena's 4 are now `false-positive` under D-236; openagentsafety's 14 stay
   `synthetic-benchmark`, and the deposit accepts them alike.
4. **Account paths first seen in tool output** (the orchestrator's account-path guidance arrived after the triage was written). Each tree's names were grouped by
ordinal and count only, and each group has a basis in section 3:
* a name in the benchmark's own definitions;
* a round-1 name;
* a generic sandbox or container account an earlier pre-check names;
* a path first written by the model;
* raw-only residue that ships as pinned under D-604 item 7, D-601, D-606 and D-607.

One kind of group rests only on the by-origin "benchmark-input" class: names first seen in benchmark tool output or
environment state that are in no benchmark definition and match no round-1 name. Under the guidance they are
**STOP-candidates**. They are now triaged `synthetic-benchmark` (decision 11's by-origin classes; for DTap, D-607's note
that its other named accounts are benchmark or model content):

| Tree | Ordinals (findings) | First seen | Class an approved rule would need |
|---|---|---|---|
| `dtap-bench-w2c` | #4 (8), #6 (2), #8 (80), #10 (2), #11 (41), #13 (15), #14 (44), #15 (2), #23 (2), #24 (2), #25 (2), #27 (2), #29 (4), #30 (2), #32 (2), #35 (59), #36 (2), #37 (2), #44 (2), #48 (2), #49 (81), #51 (4), #54 (2), #55 (2), #57 (2): 25 ordinals, 368 findings | tool output or desktop state of the sandbox VMs (19 of them Windows profiles); none of D-607's five harness accounts | "an account of the benchmark's sandbox environment, shown in its tool output" |
| `fragfuse-agentharm-w2`, `kexin-xu-01-agentharm-w2` | fragfuse #17 (32) = kexin #4 (17), one name | AgentHarm's scripted tool output | the same, or "a name in AgentHarm's scripted tool output" (pre-check fragfuse CC-03 judged the `/home/` names benchmark content) |

**User decision (2026-10-30, relayed by the orchestrator from its window):** "Keep the 27 account-path ordinals as
triaged (synthetic benchmark, decision 11)". They stay `synthetic-benchmark`, so no triage file, scan or corpus byte
changes.

## 6. Not done here

* Nothing more on the trees. The rescans were written to the session scratchpad first. Each was checked (same root
  digest, same fingerprints, 0 untriaged, 0 `real`, the triage file's sha256 recorded) and then put beside its tree as
  `<tree>.release-scan.json`, as round 1 did. Each seal-time document was kept first, digest-checked, in
  `~/.agentprov/migration-work/wave-2/c3-triage/seal-time-scans/`.
* The deposit itself, any tag or push: not touched.

## 7. Reproduction

Scratch scripts, all in the session scratchpad, run with the core venv's `python -I`:

| Script | What it does |
|---|---|
| `evidence.py` | the C-3 classes (`release_triage.gather`), per-class gitleaks evidence and per-ordinal account evidence |
| `acct_detail.py` | the first record kind per execution, raw JSON context, cross-corpus ordinals |
| `first_aer.py`, `scope_events.py` | first appearance with judge text skipped; Inspect event types |
| `value_check.py` | the PEM checks (DER, placeholder, equality with D-964-withheld keys) |
| `make_decisions.py` | evidence + reviewed overrides → the decisions files |
| `apply.sh` | `release_triage.py --decisions`, then `release_scan.py --triage` into the scratchpad |
| `summarise.py`, `tables.py` | this report's tables |

The decisions files are in [`wave-2-c3-triage/triage-decisions/`](wave-2-c3-triage/triage-decisions/). Each triage file
records its decisions file's sha256 in its header.
