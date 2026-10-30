# Phase 10k part A: census of Zenodo 22737462 (credential-leak study, v3)

Status: **census done; decisions taken** (2026-10-13). D-260 to D-268 were proposed here. On 2026-10-13 the user
delegated the decisions to the session ("make the decisions for me"), and the session took them as section 9 records
(session decisions under the user's delegation); the user then approved them as suggested, the same day, and they are
recorded in `docs/architecture/DECISIONS.md`. The user approved the v1/v2 download in chat (D-268).

**Source.** Record 22737462, version v3 (2026-09-13), concept record 21860162, licence CC-BY-4.0, one file
`p15b-run-data-v3-2026-09-13.zip` (11,060,394 bytes, md5 `d25b9b5c27f5f41689c62decb3e20ffc` per the record,
sha256 `7e5f7e40b86abfda45a951602188d979a26db9148cd2646e8a17a404c575082a` of the staged bytes). The bytes are
the file phase 10e staged under `~/.agentprov/staging/10e/zenodo_22737462/`, so no download was made. The zip was read
in memory through `agentprov.ingest` (`open_zip`, `iter_zip_members`, `strict_json_loads`) and nothing was extracted.
The scripts and their outputs are in `~/.agentprov/migration-work/phase10k/{scripts,census}/`.

**Secrets rule.** This report holds counts and field paths only. No planted value, fragment or hash of one is
recorded here. *Process note:* an early shape pass printed a few planted values to the session transcript, because
its filter keyed on secret shapes and the planted values use a tag convention. That scratch output was overwritten
at once. Every later pass prints values only from an allowlist of metadata paths, and never prints a string that
carries the tag in any case. No committed file holds a value.

Everything in the deposit is untrusted data: the runs carry injection payloads, poisoned `CLAUDE.md`/`AGENTS.md` rule
files (scenarios TRULES.1/.2) and agent output.

## 1. Members and layout

- **682 members**, all passing the G.3.5 gate (658 `.json`, 8 `.md`, 5 `.py`, 4 `.csv`, 3 `.jsonl`, 2 `.sarif`,
  2 `.mjs`).
- **643 run cells.** Each is a JSON object `{config, defence, model, runId, runs, scenario, summary, technique,
  timestamp}`, and 20 also have `__note`. They sit under `01-injection-map/`, `03-egress-axis/` and `04-hygiene/`, at
  `<section>/<channel>/<model>/<file>` (562 cells) or `<section>/<channel>/<excluded-models|_dir>/<model>/<file>` (81).
  - *Correction to card 3.10:* the card says 654 cells. The deposit has 643, and the 19,636 runs are confirmed.
- **14 non-run JSON members**: the T-EMIT audit and independent-scanner files.
- **One rejected member:** the collector log in `03-egress-axis/external-canary-collector-log/` (a `.json`). It fails
  the strict loader with `ingest.json.duplicate_key`, and it is not a cell.

Layout classes, read from the member label (`O`):

| Class | Cells | Runs | Deposit README / CHANGES says |
|---|---:|---:|---|
| roster `run__…` | 482 | 12,970 | primary cells |
| roster `archive-…` (five batch prefixes) | 50 | 2,904 | cells restored from batch archives (README "Completeness"; CHANGES v3) |
| roster `addendum-2026-09-13__…` | 6 | 600 | later harness build (CHANGES v3 addendum) |
| roster `extcanary__…` | 20 | 800 | scored at an external collector; in-harness counts read 0 by design |
| `_replication-wave-…/` | 2 | 160 | second T-EMIT wave, not pooled |
| `_fable-filter-probe-NOT-SCORABLE/` | 2 | 10 | "evidence, not a rate" |
| `excluded-models/` `run__…` | 73 | 2,180 | fable-5, glm-5, minimax-m2.5: outside the comparison |
| `excluded-models/` `archive-…` | 8 | 12 | as above |

`archive-*` cells hold 2,916 runs (904 + 640 + 320 + 120 + 920 + 12), which matches card 3.10.

## 2. Runs

- **19,636 runs** in `runs[]`, all content-distinct (the sha256 of each run's `turns` is unique). The tuple
  `(runId, model, scenario, technique, repetition)` is unique. `repetition` = index + 1 in every cell. `runId` is
  shared by several cells (211 distinct over 643), so it is a batch id, not a run id.
- **Turns.** 20,176 in total: 19,276 runs have one turn, 180 have two and 180 have three (the TDELAY delayed-trigger
  scenarios). A turn is `{turnNumber, userMessage, assistantResponse, toolCalls[], timestamp, canaryDetected,
  canariesFound[]}`, plus `durationMs` on 4,240 turns. There is **one** assistant text per turn, and its position
  relative to the turn's tool calls is not recorded.
- **Tool calls.** 83,619 in total. Each is `{tool, input, output, canaryInInput, canaryInOutput}`, plus `durationMs`
  on 19,347. `input` is an object (any keys, verbatim from the model). `output` is always a string (at most 10,006
  characters). Per turn there are 0 to 12+ calls; 1,619 turns have none.
- **Runs without any tool call:** 1,495. Of these, 59 have `invocationError`, and 100 also have an empty response
  (the provider-blocked Fable runs).

**Pairing.** No call or result ids exist. The input and output of a call are **fields of the same `toolCalls[]`
entry**, so the pairing is the record's own structure, not an order inference. The order of calls within a turn is
the array order. Nothing else orders them: there are no per-call timestamps, and `durationMs` is a duration.

**Tools.** 51 distinct names, as the model emitted them: Bash 36,540, Read 25,561, Glob 6,328, Edit 4,307,
WebFetch 3,222, McpToolCall 2,651, Write 2,409, Grep 1,382, ListMcpTools 657, WebSearch 280. The rest (about 290
calls) are malformed or variant names: channel-token leakage such as `Read<|channel|>commentary`, case variants,
typos, `""`, a command line used as a name, and one name the census suppressed as secret-shaped. Input key sets
number 94. Most are `command`, `file_path`, `pattern`, `url`, `{server, tool, args}`, and a few are malformed keys
(`" }"`, `"-i"`).

## 3. Models and identity

- **21 model strings.** `run.model == cell.model` holds for all 19,636 runs. The strings are the harness's labels
  (`gpt-5.5`, `nova-pro`, `qwen3-coder-480b`, ...). Three carry a Bedrock routing prefix
  (`eu.anthropic.claude-fable-5`, `global.anthropic.claude-fable-5`, `global.anthropic.claude-fable-5-1`).
  - Roster `run__` cells: 15 models. Archive cells add `gemini-3.1-pro-preview`. Excluded: `eu.anthropic.claude-fable-5`,
    `glm-5`, `minimax-m2.5`.
- **No served model id, provider, region or decoding parameter is recorded per run.** The README says only that the data
  came from "AWS Bedrock, Google Vertex AI, and direct vendor APIs".
- **The harness is not identified in the run files.** No name, build or version field exists. The CHANGES addendum
  names harness builds v0.1.790/793 for the 2026-09-13 waves only, in prose.
- **Judge and embedder.** `config.judgeModel` (three Bedrock ids), `embedModel`, `judgePrompt` "B7.1" and
  thresholds are recorded. However, `runs[].intentVerdicts[]` is `null` in all 20,176 entries, and the README
  describes an undefended baseline (`defence` = `C4-baseline` everywhere) with "no judge / filter". So no judge
  output exists.

## 4. Injection channels (techniques and scenarios)

15 techniques and 33 scenarios. `run.scenarioId == cell.scenario` holds for all runs, and each scenario has one
`scenarioName`. The channels are:
- file documents (T1.1-T1.4);
- HTTP responses, with the T4.1-T4.5 concealment sweep;
- web pages (TWEB);
- MCP responses and MCP tool descriptions (TMCP, TMCPDESC);
- poisoned rules files (TRULES.1 `CLAUDE.md`, TRULES.2 `AGENTS.md`);
- logs (TLOG), dependencies (TDEP) and command output (TCMD.1/.2);
- egress diversity through README or command output (TEGRESS.1-4, TEGRESSCMD.1-4);
- delayed triggers (TDELAY.1/.2);
- hygiene: execution (TSTAGE.1/.2), install (TSLOP.1) and output (TEMIT.1/.2).

## 5. Timestamps

- **Format.** Every turn timestamp, cell `timestamp` and `runId` has one shape (`YYYY-MM-DDTHH:MM:SS.mmmZ`;
  `runId` uses `-` for `:`). None is missing. Within a run, turn timestamps never decrease (540 of 540 pairs).
- **Turn timestamps cannot be classed as start or end.** Runs of one cell overlap: in 9,505 of 18,993 consecutive
  pairs, the next run's first turn starts before this run's `durationMs` has elapsed. The 30 multi-turn pairs with a
  turn duration split 13 (gap ≥ duration) to 17 (gap < duration).
- **Cell-level stamps.** The cell `timestamp` is at or after every turn in all 643 cells. The `runId` stamp is at or
  before the first turn in all 643 cells.
- No timestamp is missing and none would be invented.

## 6. Judging and outcome fields (harness detectors)

Per run (counts of `true` / present):
- `hijackSucceeded` 5,421; `exfiltrationDetected` 3,936, with `exfiltrationCount` (0-15), `exfiltrationPaths[]` and
  `egressChannel(s)` (http-post, git-push, tool-arg, http-get, dns; present in 11,096 runs);
- `agentDetected` 5,479; `displayedToUser` 1,260; `ges`/`gesDisplayed`/`gesExfil` (0, 33.3 or 100);
- `firstCanaryTurn`;
- `maliciousArtifactEmitted` 572 of 3,202 non-null, with `maliciousArtifactTags`;
- `scriptAudited` 124 of 1,815 non-null; `payloadDelivered` 2,840 of 3,566 non-null, with `payloadDeliveredBasis`;
- `taskEngaged`, `t0Completed`, `truncated`, `invocationError`, `errorDetail` and `missingTargetErrors`, on the 3,686
  newer-schema runs.

Per turn: `canaryDetected` and `canariesFound[]` (detector pattern labels). Per call: `canaryInInput` and
`canaryInOutput`.

Per the deposit's own CHANGES and README, the T-EMIT column was corrected after the fact. The run files keep the
pre-fix detector flag, and the corrected labels are in `05-temit-precision-audit/` (not run data).

## 7. Where the planted credentials occur (counts and field paths only)

The study tags every planted value with the literal tag `CANARY` (upper case, inside the value).

| Field (all inside `runs[].turns[]`) | `CANARY` tag occurrences |
|---|---:|
| `toolCalls[].output` | 50,094 |
| `canariesFound[]` (detector labels) | 21,767 |
| `toolCalls[].input.*` | 17,964 |
| `assistantResponse` | 5,505 |
| `userMessage`, `tool`, cell-level fields | 0 |

- **Shape matches** (phase 10e's patterns, counted disjointly over the cells):
  - AWS-like (`AKIA` + 16): 1,273, all carrying the tag inside the match;
  - Anthropic-like (`sk-ant-…`): 1,272, of which 1,270 carry the tag;
  - other `sk-…`: 15,927, of which 15,851 carry the tag.
  - *Correction to card 3.10:* phase 10e's OpenAI-like pattern also matches the Anthropic-like strings. Its 17,479
    also counted the non-cell members.
  - **78 secret-shaped strings carry no tag:** 76 `sk-…` and 2 `sk-ant-…`, in tool inputs and outputs and assistant
    text. 75 of them are delimited, and 3 are word-internal. They sit in 27 runs, and 26 of those also carry the tag.
- **Raw bytes match decoded strings.** The tag and shape counts over the raw member bytes equal the counts over the
  decoded strings (95,330 and 18,472), with no mismatching cell. So a byte scan, which is what sealing does, sees
  every occurrence.
- **Runs:**
  - 5,422 runs carry a tag or a secret shape in their content; **14,214 carry neither**.
  - The harness's own flags agree: 5,421 flagged runs carry a hit, and 1 unflagged run carries only an untagged shape.
  - The lower-case word `canary` without the tag (e.g. in prose) occurs in 1,256 strings. It is not a planted value.
- **Cells:** **318 cells are entirely clean (9,799 runs)**, 83 are entirely tagged, and 242 are mixed. The mixed and
  tagged cells hold 9,837 runs, of which 4,415 are clean.
- **Non-cell members:** the collector log, 5 audit files, 1 scanner file, the README and 3 scripts carry the tag (and
  the collector log also carries shapes).
- **AER stores content verbatim**, and aer/0.1 has no in-string redaction. So a run whose content carries a planted
  value would carry it into its AER (tool results, assistant text), into its PROV (tool-call args are emitted
  verbatim) and into views. Only corpus-level withholding (D-234, D-235) can keep the value out of a release.

## 8. Earlier versions

v1 (record 21860163, 2026-08-09, `p15b-run-data-2026-08-09.zip`, 10,634,809 bytes, md5 `1b44467e…`) and v2 (record
22729871, 2026-09-12, `p15b-run-data-v2-2026-09-12.zip`, 10,948,077 bytes, md5 `8fee73c2…`) were downloaded with the
user's yes, verified against the record checksums, logged in `~/.agentprov/cache/acquisitions.jsonl` and staged under
`~/.agentprov/staging/10k/v1|v2/`. They were compared with v3 in memory, by the sha256 of each run (counts only).

| | members | cells | runs |
|---|---:|---:|---:|
| v1 | 645 | 633 | 18,906 |
| v2 | 671 | 633 | 18,906 |
| v3 | 682 | 643 | 19,636 |

**Answer: neither v1 nor v2 holds a run that v3 lacks.**
- **v2 to v3:** all 18,906 runs of v2 are in v3, and v3 adds 730.
- **v1 to v3:** v1 has exactly one run that is not in v3: the Mistral T1.3 transcript (`01-injection-map/T1-file-document/mistral-large-3`).
  v2 redacted a 12-digit AWS account identifier in it (`<REDACTED_AWS_ACCOUNT_ID>`, 6 occurrences in v3), and v3 holds
  that redacted version.
- Every other v1 member is byte-identical in v3, apart from one non-run file.

This confirms the deposit's CHANGES. v1 is never stored in a raw store (D-268).

## 9. Decisions (proposed by the session; taken under the user's delegation, then user-approved, 2026-10-13)

Taken as proposed below, with these answers:
- **Q1:** no `model_call` records. Agent messages declare their generator `not_recorded` (`maxTurns` = 10 suggests
  several model calls per turn, so one call per turn would be false).
- **Q2:** object scope (D-265 as recommended).
- **Q3:** downloaded with the user's yes. Answered in section 8.
- **Q4:** lower-case prose stays outside the policy.

**Amendment to D-265 (2026-10-13, part C2).** Rule `canary-tag` is the bounded pattern `CANARY[^_]` (the tag
followed by any character but `_`), not the bare marker. Two not-selected collector-log member labels carry the tag
between underscores. `raw/members.jsonl` lists every label and is released (D-231), so with the bare marker the real
deposit's seal failed the `chain` backstop (`withheld.rule_hit`). The pattern still covers all 5,422 value-bearing runs:
each of the 5,421 tagged runs holds an occurrence it matches (census step 12). It matches no member label.
A second rule, `canary-tag-left` (`[^_/]CANARY`), was added after the C1 re-run. One hijacked run holds the tag only
once, after a lower-case letter and before `_`, and the AER does not copy the `canariesFound` labels that step 12 had
counted. On the content the AER holds, the two tag rules and the two shapes hit all 5,422 value-bearing runs, leave no
tag occurrence in any released run, and match no member label (census step 15).

### Proposals as written

- **D-260 (family and unit).** A new family `credleak`, with dialect and mapper `credleak.cell`, variant `p15b-v3`.
  - One execution per `runs[]` entry (19,636), with primary locator `{"p": "/runs/<i>"}` into the cell member.
  - **Selection:** the cell members under `01-injection-map/`, `03-egress-axis/` and `04-hygiene/`, so all 643 cells
    and every layout class of section 1 are imported. Non-cell members are `select.not_execution_artefact`. The
    collector log is out of the selection, so its strict-loader rejection never applies.
  - The layout class is recorded as an observed path facet in `ext.credleak`. Rate exclusions go in `rates.toml`
    (excluded models, the NOT-SCORABLE probe, the unpooled replication wave, and the collector-scored `extcanary`
    cells), not into the import.
  - Runs without tool calls (1,495) stay: they are agent executions in a tool-using harness. D-140 rules on sources,
    not runs.
  - *Rejected:* importing only the roster (drops 2,362 faithful runs the deposit keeps on purpose); one execution per
    cell (merges up to 160 runs).
- **D-261 (identity).**
  - `agent.model.requested` = the run's `model` string verbatim (`O`: the harness's own record of its
    configuration). `/model/served`, `/model/provider` and `/params` are `unk not_recorded`. Routing prefixes are kept,
    never normalised.
  - The harness identity is not recorded: `unk /instrumentation not_recorded`. The CHANGES prose about builds stays
    out of the AER.
  - No judge actor: `intentVerdicts` is all null and the baseline has no judge. `config` is kept verbatim in
    `ext.credleak.config`.
  - *Rejected:* mapping the labels to vendor model ids (invention); a judge actor from `judgeModel` (it produced
    nothing).
- **D-262 (turns, calls, pairing).** Per turn:
  - a `user` message (`O` text);
  - an `agent` message with one `tool_call` part per `toolCalls[]` entry in array order (`O`, `pos` order);
  - a `tool_execution` per call, `I` under `credleak.tool_entry_is_execution_unverified@1` (no harness code is
    verified);
  - a `tool` result message with `responds_to` linked **by co-location in the same entry**, `D` under
    `credleak.pair_same_entry@1`, a deterministic function of the record structure (no order inference);
  - the turn's `assistantResponse` as an agent text message ordered after the user message only. Its position relative
    to the calls is not recorded, so there is no edge to the tool results.
  - Model-call boundaries are not recorded, so no `model_call` is emitted. The agent messages' `generated_by` is
    `unk not_recorded` (Q1, decided).
  - Tool names and inputs are kept verbatim, malformed ones included. The semantics profile `credleak.tools@1` maps the
    10 canonical names, and every other name is `unknown`, with quirk counts.
- **D-263 (time).**
  - Each turn timestamp is kept verbatim in `t.raw`. The typed slots are `unk ambiguous` under
    `credleak.turn_timestamp_role_unverified@1`, because start and end cannot be told apart (section 5).
  - The cell `timestamp`, the `runId` and every `durationMs` go to `ext.credleak` and become no AER time.
  - Nothing is invented. This follows the DTap precedent (D.16.4 correction 1: an `I`-class typed time would emit a
    `prov:*Time` the validators refuse).
- **D-264 (harness signals).**
  - The run-level detector fields of section 6 become `judgement` records with actor `harness`, origin
    `harness_default`, and value `O` verbatim. Their `/t` and `/inputs` are `unk not_recorded`.
  - Policy readings go to the assessment bundle through the engine's rules only.
  - `canaryDetected`, `canaryInInput` and `canaryInOutput` are kept as booleans. `canariesFound[]` is kept as a count
    with a locator, because its labels are detector names that embed the tag.
  - *Rejected:* copying the labels (they add nothing to the booleans and would force escalation).
- **D-265 (withholding policy, profile `[withhold]`).** The profile declares:
  - `reason` = planted canary credentials (D-146), with a one-line `public_note`;
  - three rules, all **scope `object`**:
    - `canary-tag`: marker `CANARY`;
    - `aws-key-shape`: pattern `AKIA[0-9A-Z]{16}`;
    - `sk-key-shape`: pattern `sk-[A-Za-z0-9_\-]{20,256}`;
  - `scan_rules` naming the matching release-scan rule ids.
  - **Expected effect:**
    - The 325 tagged or shaped cell members are withheld at object level, and so is the deposit zip that contains them
      (basis `container`). The 318 clean members are released.
    - The derived files of the 5,422 value-bearing runs hit the rules (AER keeps content verbatim), so D-235 escalates
      them and they are withheld.
    - **14,214 executions are released.** For 4,415 of them, the raw cell object is withheld (`raw_withheld` in
      `chain`).
  - Part C must confirm two things. The withheld set equals the census set exactly. And no clean run's derived files
    hit, for example through an identifier that happens to contain `sk-` followed by 20 id characters, so no rule,
    record or PROV id may be named that way.
  - *Alternative (scope `executions`):* 9,799 released. Simpler, but it drops 4,415 executions that hold no value.
  - *Rejected:* in-string masking in the mapper (aer/0.1 cannot express it, and it would need a core change);
    withholding nothing (D-146).
  - **For the user to decide:** objects only, executions only, or both. The recommendation is the object-scope
    policy, which withholds every value-bearing object and execution and releases the clean executions.
- **D-266 (fixtures).**
  - Fixtures are whole clean cell members only (raw bytes are never edited; CC-BY-4.0 with attribution in `SOURCE.json`
    and `tests/fixtures/LICENSES/`). They are chosen among the 318 clean cells for small size and coverage: the layout
    classes, malformed tool names, `invocationError`, zero-tool runs, multi-turn TDELAY runs, the old and new run
    schemas, and `__note` cells.
  - The fixture builder re-checks each chosen member against all three rules and refuses any hit.
- **D-267 (end-to-end withholding test, D-234).**
  - It replaces the injection at `corpus.withhold.policy_of_profile` with the shipped profile. The chain is: import
    (the clean fixtures plus one cell **generated at test time** in a temporary directory, carrying test-made tagged
    sentinels assembled at run time, never committed) → seal in release mode → `verify` chain → deposit build.
  - Assertions: `WITHHELD.json` lists the generated cell object and exactly its sentinel-bearing executions; clean
    executions stay released; the deposit builder's rescan and the release secret scan find no rule hit in the sealed
    tree.
  - Test names and messages carry rule ids only.
- **D-268 (versions).** Only v3 is pinned and imported.
  - v1 is never stored in a raw store: it holds an unredacted account identifier.
  - Checking v1/v2 for runs missing from v3 needs the user's yes to download both (about 21.6 MB). If approved, they
    are read in memory only, compared by run content digest, and only counts are recorded.

**Open questions for the user.**
- **Q1:** one `model_call` per turn at `I`, or none, with agent messages' generator declared `not_recorded`?
- **Q2:** D-265 scope (object, the recommendation, or executions).
- **Q3:** the v1/v2 download for the completeness check.
- **Q4:** should the 1,256 lower-case `canary` prose strings stay outside the policy? (The proposal: yes. They are not
  planted values, and the marker is case-sensitive.)

## 10. Invariant 5

Nothing seen needs a change to `aer/`, `prov/`, `validate/` or `corpus/`. The withholding path exists (D-230 to
D-237), co-located pairing is expressible with existing rules and part fields, and typed time stays unknown.
