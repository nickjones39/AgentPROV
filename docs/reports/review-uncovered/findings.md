# Review of the uncovered code: findings (2026-11-01)

Reviewed at `394ee707`. The scope is in [coverage.md](coverage.md): product code that no earlier review covered, plus
every file changed after the review that covered it. Eleven read-only reviewers ran in parallel, one per area, and each
finding is backed by an end-to-end code reading (**PLAUSIBLE**) or a repro that showed the defect (**CONFIRMED**).
Repros are kept outside the repository, in the session group's notes folder (`review-uncovered-repro/<area>/`); none used
the network, a real key or `~/.agentprov`.

**Status (pruned 2026-11-01, on `release/v0.1.1`).** 30 of the 47 findings are fixed on `release/v0.1.1`. Their
full write-ups are removed from this file. Each keeps a status row, and its fix and tests are in the fix tables below.
The full review text is in this file's history, at `d3974b23`. Still open:
- **16 findings that would change corpus results:** UC-2, UC-12, UC-16 to UC-22 and UC-37 to UC-43. They are recorded
  only, by the user's rule of 2026-11-01.
- **UC-44:** excluded from the fix batches.

## Status

| id | sev | area | finding | status |
|---|---|---|---|---|
| UC-1 | high | release | `export --onto` commits ignored files (e.g. `.env`); a second run hides the leaked commit behind a clean one | **fixed** `ba1849be` |
| UC-2 | high | backends | the gate recorder matches runtime calls to batch calls by name only, so a Mandate denial is recorded as an execution and the call that ran as never run | open: recorded only (affects corpus results) |
| UC-3 | high | trust | on Windows every T1 worker dies at start-up: the V-4 audit hook blocks the probe `import _posixsubprocess` it then expects to raise ImportError | **fixed** `61e7e258` (class 1: the `aer` stage digest moves on re-import; no record changes) |
| UC-4 | medium | live CLI | a remote `--defence-endpoint` (paid API) does not change the endpoint class: local consent, "no provider billing", optional caps | **fixed** `62d99d10` |
| UC-5 | medium | live CLI | the per-cell call bound (48) ignores defence calls, so a MELON cell can overrun `--max-calls` severalfold | **fixed** `a86e7419` |
| UC-6 | medium | live CLI | judge tables in an Inspect `--plan` file skip base-URL validation, so the agent's key can go to any host over plain http | **fixed** `07283db3` |
| UC-7 | medium | release | `--onto` accepts any clean clone on `main`, including the private development repository, and runs that clone's hooks | **fixed** `ba1849be` |
| UC-8 | medium | security (keys) | `keys set --stdin` with non-UTF-8 input prints the raw key in the UnicodeDecodeError (stderr under `-v`, and always in `--log-file`) | **fixed** `5c01256c` |
| UC-9 | medium | GUI | Run Live checks the dev-run cost cap, and builds the R2 consent text, from a stale estimate after the selection changes | **fixed** `6b337bc9` |
| UC-10 | medium | jobs | a Linux wall-clock step over 2 s makes every running job read as unobserved: prune deletes it, stop/kill refuse, the single-writer check lets a second writer in | **fixed** `6c5538c2` |
| UC-11 | medium | jobs | a stop or drain sent just after a job starts is silently dropped while `jobs stop` reports success (the only graceful stop on Windows) | **fixed** `74a5fb2c` |
| UC-12 | medium | adapters | a live capture whose model calls a deny-listed tool name (`none`, `-`, …) loses its whole AER; the three sibling mappers have the fix (CD-10, item 97, BF-22) | open: recorded only (affects corpus results) |
| UC-13 | medium | capture | `plan_ok` carries every cell in one protocol line; above about 4,500 cells it exceeds 1 MiB and the run cannot start, reported as `backend.unavailable` | **fixed** `5adb0118` |
| UC-14 | medium | assist | one assistant reply over 20,000 characters blocks every later GUI chat message until New Chat | **fixed** `32621242` |
| UC-15 | medium | GUI | `last_line` shows the CLI's `INFO … end command=…` log line instead of the error reason (10 call sites) | **fixed** `44dde982` |
| UC-16 | low | provenance | since D-930 an unk premise field can leave a statement with no method, and the whole derivation is refused (`prov.method_set_empty`) | open: recorded only (affects corpus results) |
| UC-17 | low | backends | a gate executor that raises mid-batch leaves the calls it already ran as dispatches with no `tool.result` | open: recorded only (affects corpus results) |
| UC-18 | low | backends | defence code and weights are hashed on one read and loaded on another; `refs/main` is never checked against the pinned revision | open: recorded only (affects corpus results) |
| UC-19 | low | capture | a lone surrogate in a provider reply, or tool arguments nested over 200 levels, make the capture writer raise into the benchmark run | open: recorded only (affects corpus results) |
| UC-20 | low | capture | writer-made events (a seq-1 flag note, an early `error`/`session.end`) break the fixed event order, and the verifier then reports a damaged chain | open: recorded only (affects corpus results) |
| UC-21 | low | capture | Anthropic with `thinking_budget_tokens`: the declared instrumentation (temperature not sent; max_tokens 4000) contradicts the wire (temperature 1; 6048) | open: recorded only (affects corpus results) |
| UC-22 | low | capture | T0's staging re-scan treats every parent variable matching the key-name pattern as a secret and over-quarantines | open: recorded only (affects corpus results) |
| UC-23 | low | live CLI | preflight probe calls are not gated by the caps and are lost from `live.caps` on resume | **fixed** `eee91365` |
| UC-24 | low | live CLI | the egress proxy's 64-tunnel cap is below the allowed `--jobs`; the 65th tunnel gets 503 | **fixed** `707ea41c` |
| UC-25 | low | live CLI | the defence endpoint's key ignores the keychain (D-702), and the refusal wrongly says ".env" | **fixed** `363db545` |
| UC-26 | low | jobs | a running batch step whose job directory was pruned stays running forever and holds the slot | **fixed** `38365c13` |
| UC-27 | low | jobs | `jobs start --meta k=1e999` exits 70 and leaves a job directory that cannot be listed or pruned | **fixed** `dfbc7c18` |
| UC-28 | low | jobs | `jobs follow` of an ended job prints at most about 2 MiB and exits 0 | **fixed** `6b20e934` |
| UC-29 | low | jobs | `devrun list` never reports step times (the atomic rewrite makes the difference negative) | **fixed** `3f983567` |
| UC-30 | low | jobs | Windows settings writes have no `os.replace` retry; the slot and single-writer checks are check-then-act | **fixed** `ddd58a78` |
| UC-31 | low | assist | JSON mode: a lone surrogate crashes it and C1/bidi characters pass raw; a bad port in `assistant.base_url` exits 70; text mode cuts reply lines at 1,000 characters | **fixed** `32621242` |
| UC-32 | low | GUI | the live dev-run call cap loses its count after a re-attach, and Resume drops the cap | **fixed** `2cbb9f45` |
| UC-33 | low | GUI | Settings › Keys "Delete Key" deletes a stored key with no confirmation (contrary to the D-654 note) | **fixed** `c37dcb0b` |
| UC-34 | low | GUI | "Copy Execution Id" copies an unvalidated id with control characters (S13) | **fixed** `7eb7a4ac` |
| UC-35 | low | GUI | a relative or dash-led DEPOSIT_DIR is resolved against the GUI's cwd, but the uploader runs in the checkout | **fixed** `299ffa2e` |
| UC-36 | low | GUI | several CLI calls (up to 120 s each) run on the UI thread | **fixed** `c3777292` |
| UC-37 | low | adapters | the D-607 redactor skips `$utf16`-encoded strings, so account paths in them survive (NF-10's flaw, in dtap) | open: recorded only (affects corpus results) |
| UC-38 | low | adapters | redaction followed by D-934 not-inlining leaves a dangling citation pointer; the run is sealed `adapter_defect` | open: recorded only (affects corpus results) |
| UC-39 | low | adapters | the D-1011 flaw class elsewhere: counts, durations and times outside the AER ranges reach typed fields, and the writer refuses the run | open: recorded only (affects corpus results) |
| UC-40 | low | adapters | the D-378 lone-surrogate pass is missing, so a lone surrogate in a typed text field makes the run degenerate | open: recorded only (affects corpus results) |
| UC-41 | low | adapters | no not-inlined path for strings over 1 MiB (the D-934 class) | open: recorded only (affects corpus results) |
| UC-42 | low | adapters | type confusion crashes the mapper, and Inspect copies non-conforming patches and deny-listed header strings into strict slots | open: recorded only (affects corpus results) |
| UC-43 | low | trust | `decode_members` accepts an escaped lone surrogate that `decode_origins` refuses; re-encoding then raises an untyped error | open: recorded only (affects corpus results) |
| UC-44 | low | trust | a stored zip entry is read up to its compressed size, past `max_member_bytes` | open: not fixed (excluded) |
| UC-45 | low | CI | publish checks out `inputs.tag` unqualified, so a branch with the tag's name wins; nothing checks the commit is the tag's | **fixed** `d207d7a5` |
| UC-46 | low | CI | if `CI_RUNNER` is set in the public repository, fork pull requests run on the self-hosted machine | **fixed** `618586c3` |
| UC-47 | low | CI | `persist-credentials` defaults to true; `pages: write`/`id-token: write` are granted to the build job too | **fixed** `0ab9937a` |

## Open findings: corpus-results impact (user rule, 2026-11-01)

**The rule:** "any bugs that would affect the corpus generation or results just record them in a md file rather than
fixing them if they would change results of the manuscript". A finding **affects corpus results** when its fix would
change, for a corpus generated with the fixed code, any of these:
- stored AER/SEM/PROV bytes;
- execution or issue counts;
- PROV statements;
- recorded stage or adapter code digests (`engine_code_sha256`, `adapter_code_sha256`).

Sealed corpora are reproduced at their building commit (the F-8 ruling), so no fix rewrites one.

**Scan of the 52 sealed corpora (2026-11-01, read-only):** none holds any of the following:
- an `adapter_defect` row;
- an AER write refusal (`aer.write`, `aer.sentinel`, `inline_limit`);
- a `prov.method_set_empty` refusal;
- a live capture execution;
- a `$utf16` value in the DTap AER;
- a lone-surrogate member label.

So no open finding's fix would change a count, a statement or a record byte of a sealed corpus. The "yes" rows move code
digests only, plus the AER of inputs that do not occur in the sealed corpora.

**Corpora per adapter (for the digest moves):**
- **agentdojo (`agentdojo.tracelogger`, including the DRIFT mapper), 35 corpora:**
  - agentdojo-upstream-2024-06-rg1, agentdojo-upstream-head-rg1;
  - agentdyn-a-rg1, agentdyn-b-w2, agentdyn-c-w2;
  - aiauthz, ast-survey-agentdojo-rg2, authority-caps, bookkeeper, ceferisbarov, craibench, dca-…-w2b;
  - drift-head-w2, drift1;
  - gate, geryon, glitch, hilarytorn-trajectory-poisoning, interbolt, ipi-defenses, kavach, kongminos, linyxus, llm-lock;
  - mandate-agentdojo-eval-rg1, melon, memo-ozdincer, menelaus29-ipi-multidomain, mohameduk, rope-rg1, seagent,
    sentry, shreeyavarma-llm-safety, tacit, yockcheng-prompt-injection-harness.
- **inspect, 6 corpora:**
  - ast-survey-agentharm-rg2, atia-benchmark-w2, fragfuse-agentharm-w2, kexin-xu-01-agentharm-w2, whistlebench-w2;
  - controlarena-persistent-w2b (0 released rows; all withheld).
- **One corpus each:**
  - adprov: adprov-v1-release-rg2
  - dtap: dtap-bench-w2c
  - mcphunt: mcphunt-w2b
  - agentops: agentops-bench-w2
  - qwencode: redcode-exec-qwencode-w2
  - credleak: credleak-p15b-w2b
  - autogen: autogen-guard-placement-w2
  - geminicli: code-agent-misalignment-w2
  - wirelog: what-surrounds-w2
- **openhands, 2 corpora:** openagentsafety-w2, redcode-exec-openhands-w2.

| id | affects corpus results | what a fix would change |
|---|---|---|
| UC-2 | **yes (future live corpora only)** | AER of live AgentDojo captures under Mandate-style gates: tool results and denials, hence ASR and denial counts. No sealed corpus holds live captures; `mandate-agentdojo-eval-rg1` is an imported TraceLogger corpus and is unaffected |
| UC-12 | **yes (digests; future live corpora)** | `adapter_code_sha256` of the agentdojo family moves (35 corpora). Live sessions with a deny-listed tool name would get a full AER instead of a degenerate one. No sealed corpus holds capture sessions |
| UC-16 | **yes (digests only)** | `prov/rules/assess.py` is in the `prov` stage scope, so the prov `engine_code_sha256` of every corpus moves. PROV statements change only for executions refused with `prov.method_set_empty`, and none of the 52 corpora has one |
| UC-17, UC-18 | **yes (future live corpora only)** | AER of live captures with gate defences (UC-17), and the recorded code and weights pins (UC-18) |
| UC-19, UC-20, UC-21, UC-22 | **yes (future live corpora only)** | capture/0.1 logs and instrumentation items (UC-21 is a false harness claim), and quarantine decisions (UC-22). Live sessions only; none is sealed |
| UC-37, UC-38 | **yes (digests only)** | dtap `adapter_code_sha256` moves (dtap-bench-w2c). No DTap AER holds `$utf16` (UC-37), and no row is `adapter_defect` (UC-38) |
| UC-39 | **yes (digests only)** | `adapter_code_sha256` of mcphunt, qwencode, agentops, inspect, agentdojo, adprov, openhands, autogen and wirelog (the corpora listed above). 0 `adapter_defect` rows, so no count changes |
| UC-40 | **yes (digests only)** | the nine newer families gain a `lone_surrogate_replaced` rule. This is a catalogue change (a D-31 bump) plus adapter digests. No affected row exists |
| UC-41 | **yes (digests only)** | agentops, qwencode, credleak, autogen, geminicli, wirelog adapter digests; also a catalogue rule (D-934 pattern). No affected row exists |
| UC-42 | **yes (digests only)** | inspect and agentdojo adapter digests. No affected row exists |
| UC-43 | **yes (digests only)** | `raw/members.py` is in `AER_CLOSURE`, so the `aer` stage digest moves for all 52 corpora. No member label has a lone surrogate |
| UC-44 | no (not verified for crafted archives) | `corpus/zip_local.py` lies outside every stage scope. A fix only makes the decoded withhold scan refuse an over-long stored member. A sealed corpus holding such a forged header would get a different scan outcome; I did not scan for one |

UC-3, also a "yes" row (digests only), was fixed on the release branch in `61e7e258`. A re-import at that code moves the
`aer` stage `engine_code_sha256` of every family; no record bytes change.

Every open "yes" row goes, if fixed at all, through the regen-batch process: `tools/reserve_id.py`, a user decision, and
D-31 version bumps where a catalogue changes. It is not fixed on a release branch.

## Open findings: details

### UC-2 (high) The Mandate gate recorder can invert a denial
- **Where:** `backends/shared/src/agentprov_backend/defences.py:737-747`. `_GateContext.begin` binds a runtime call to the first unmatched batch call with the same function name.
- **What goes wrong:**
  - The pinned Mandate executor skips a declined call and runs the later ones.
  - In a batch `[send_money(attacker), send_money(legit)]` where Mandate declines the first call, the legitimate call that ran is bound to the attacker call's dispatch.
  - The capture then records:
    - the attacker transfer as `tool.result ok`, with the legitimate call's `args_effective` and return value;
    - the legitimate call as an unclassified non-execution;
    - and the denial (`status: denied, decided_by: def0`) is lost.
  - The defence's effect is inverted in AER/PROV, so denial counts and ASR are wrong. No test covers two calls with the same name.
- **Evidence:** CONFIRMED (`backends/repro/gate_same_name.py`, scripted transport): `tool.result o0 ok args_effective.recipient=US1330…` and `note defence_unclassified_non_execution {'occ': 'o1'}`.
- **Fix:**
  - Pass the call's kwargs to `begin` and match on identity (`tc.args is kwargs`, which Mandate passes through), then on equality.
  - Fall back to the name only when exactly one candidate is left; otherwise record a note and do not bind.
  - Add a two-same-name test.
- **Class:** 0 for stored corpora, since no sealed corpus holds Mandate captures. It changes future capture bytes.

### UC-12 (medium) Capture mapper: a deny-listed tool name loses the whole AER
- **Where:** `src/agentprov/adapters/agentdojo/capture_mapper.py:585-612`. `_Live.run` never calls `_ambiguous_tool_names`, which the TraceLogger (CD-10, item 87), DRIFT (item 97) and Inspect (BF-22) mappers do. The names are written at 1663, 1730, 1878 and 2093.
- **What goes wrong:**
  - A model calls a tool named `none` or `-`; the executor mirror records "Invalid tool none provided."
  - The name is copied into tool_call parts and the tool_execution `name` without `unk ambiguous`, so the writer refuses it (AER-V17).
  - The session becomes a degenerate `adapter_defect` AER: every call, message and judgement is lost.
  - Hallucinated tool names come from model behaviour, so the loss is correlated with outcomes.
- **Evidence:** CONFIRMED (`adapters1/repro_capture_none_tool.py`): `[('aer.sentinel', '/parts/1/name')]`; the control case seals 19 records.
- **Fix:** call `_ambiguous_tool_names(records)` in `_Live.run` before `_native_check`, and add a capture test.
- **Class:** 1 (agentdojo aer scope). No stored corpus holds capture sessions.

### Low

- **UC-16 (provenance; class 1).** Since D-930, `premises()` drops a premise field its record declares `unk` (`prov/rules/assess.py:184-188`).
  - If that field was the only I-class contributor, `sem_class` returns `(I, {})` (155-169), and `_combine` raises `prov.method_set_empty` (`prov/engine.py:558-566`).
  - The AER and SEM documents are both valid, yet derivation of the whole execution is refused.
  - Fix: keep that field's I methods as the statement's method set when the field is dropped, or refuse that annotation with a counted reason.
  - Repro: `provcore/tests/test_d930_methods.py`.
- **UC-17 (backends).** `_Gate.query` writes results only after the delegated query returns (`defences.py:666-709`).
  - Mandate's `float(args.get("amount"))` raises on a model-supplied `"$5"`.
  - Calls already run are left as dispatches without `tool.result`, while the environment snapshot shows their effect.
  - Fix: write each result in `_GateContext.end`, or in a `finally`.
- **UC-18 (backends, PLAUSIBLE).** Defence code and weights are not tied to their pins at load time.
  - `load_provisioned` hashes the file, then `exec_module` re-reads it from disk (`defences.py:843-858`).
  - The worker checks only weight sizes, and the stock detector loads `refs/main`, which nobody compares with the pinned revision.
  - The recorded `defence_code_provisioned@1` and `defence_weights_offline@1` pins may name bytes that did not run.
  - Fix: exec the verified bytes, and check `refs/main == revision`.
- **UC-19 (capture).** Raw reply strings are written without `encode_value`: `gateway.py:89-97`, `messages.py:164-165,217-219`, `session.py:346-363`.
  - A provider-sent lone surrogate makes `LlmSpan.__exit__` raise `CaptureWriteError`, and `llm.response` is never written.
  - Tool arguments nested over 200 levels make `tool_dispatch` raise before the tool runs, so the observer changes the run.
  - Hooks should record a marker and a note, never raise into benchmark code.
- **UC-20 (capture).** Two writer-made sequences break the fixed event order:
  - A key-shaped string in `session.start` content puts a `secret_pattern` note at seq 1 (`log.py:296-301`), so the next `instrumentation` is refused, the worker sends `fatal` and every cell aborts.
  - A worker that dies after `session.start` leaves `error` or `session.end` at seq 1 (`log.py:445-468,484-536`).
  - Either way, `verify.py:221-225` reports `cap.chain.bad_second_event` instead of an early end.
  - Fix: hold seq-0 notes until after `instrumentation`, and accept a terminal event at seq 1.
- **UC-21 (capture).** With `thinking_budget_tokens`, the stock `AnthropicLLM` forces `temperature=1` and `max_tokens + budget`.
  - The declared items `agentdojo.temperature_not_transmitted@1` and `anthropic_max_tokens@1` (`runner.py:679-681,895-905`) say otherwise: these are false provenance claims about the harness.
  - It is latent for `agentprov run`, which has no such flag.
  - Fix: derive both items from the built element.
- **UC-22 (capture).** `secrets_from_environ(ctx.env)` at `run.py:2185` scans the whole parent environment. G.6.4 says only the `.env` values should be scanned.
  - Public values become secrets, e.g. `OPENAI_API_VERSION` or `HF_HUB_CACHE`.
  - A tool output containing the same text then quarantines the session.
- **UC-37 (adapters; class 1).** `dtap/redact.py:187-205` walks finished records, where a string with a lone surrogate is already `$utf16`. A listed account inside it is not redacted and not counted. The openhands, agentops and credleak copies handle the case.
- **UC-38 (adapters; class 1).** `_not_inlined` (`dtap/mapper.py:472-496`) moves `/parts/0/text` to `/parts/0/value`, but remaps only `evf`. The `dtap.value_redacted@1` citation and the `ext.dtap.redacted` pointer dangle, AER-V14 refuses the record, and the run is sealed `adapter_defect`.
- **UC-39 (adapters; class 1).** The flaw D-1011 fixed for adprov, out-of-range values reaching typed AER fields, exists elsewhere. The writer refuses the run, and it becomes `adapter_defect`.
  - **Counts:** `mcphunt/mapper.py:607-609`, `qwencode/mapper.py:607-616` and `agentops/mapper.py:579-580` (including negative values and floats), and Inspect usage (`inspect/mapper.py:1263-1269`).
  - **Durations:** Inspect `total_time` (940-944), the TraceLogger `duration` (`agentdojo/mapper.py:178-180`), and adprov `meta.wall_clock_s` (`adprov/mapper.py:649-657`, negative or ≥ 2^53).
  - **Times:** Inspect accepts `Z`/`+00:00` timestamps without a calendar check (`inspect/mapper.py:56,211-228`), and `t.raw.start` can be a non-string (`agentops/mapper.py:679`).
  - **PLAUSIBLE, same pattern:** openhands 1325-1327, autogen 938-943, wirelog `wire.py:238`.
- **UC-40 (adapters; class 1).** `surrogates.scrub_record` (D-378) is used only by agentdojo, adprov and inspect.
  - In the nine newer families, a lone surrogate in a typed text field becomes `$utf16`, the writer refuses it, and the run is `adapter_defect`.
  - Confirmed for mcphunt, qwencode and agentops.
- **UC-41 (adapters; class 1).** There is no D-934 not-inlined path for strings over 1 MiB.
  - CONFIRMED for agentops and qwencode (`aer.string.inline_limit`).
  - PLAUSIBLE for credleak, autogen, geminicli and wirelog.
- **UC-42 (adapters; class 1).** Unchecked types and values in the Inspect and capture mappers. Each error makes the whole unit `adapter_defect` or degenerate.
  - **Type confusion:** a set-membership test on a list or dict raises `TypeError` (`inspect/mapper.py:983,1327`; `capture_mapper.py:521,713,942,1382,2319`). So do non-list `tool_calls` or content (`capture_mapper.py:1151,1155,1653`; `messages_wire.py:363,376`).
  - **Patches:** Inspect copies state `changes` into `patch` without a shape check (1596-1601).
  - **Header strings:** deny-listed header strings such as `task_version = "none"` are accepted (815-818).
- **UC-43 (trust).** `raw/members.py:545-556` accepts an escaped lone surrogate in `label`, which `decode_origins` now refuses (D-1011). `encode_members` in `derive.py:2113` then raises `rfc8785` `CanonicalizationError`, which is not an `AgentProvError`. The same check is probably needed in `corpus/index.py:720` and `register.py:295` (not tested).
- **UC-44 (trust).** For a stored entry, `zip_local.py:160-165` checks the header's uncompressed size against `max_member_bytes` but reads up to the compressed size.
  - A forged header (`usize=1`, `csize=50000`) yields a 50,000-byte member under a 1,000-byte limit.
  - It stays bounded by the object size and the worker RSS cap.

## Fixes

Each fix is class 0 (except UC-3, which the release session fixed), with tests that fail before it. No file in a stage
scope was edited by these batches.
- **Batch 1:** cherry-picked onto `release/v0.1.1`, so the SHAs below are the release branch's. The `review-uncovered`
  originals are `19493f4a`, `55062f3d`, `82605dcb` and `5e0f288a`.
- **Batches 2-4:** merged in `78e4b0fa`.

### Batch 1

| id | commit | fix | tests |
|---|---|---|---|
| UC-1 | `ba1849be` | `--onto` refuses untracked or ignored files (`status --porcelain --ignored --untracked-files=all`); the equality proof runs on the index (`write-tree`) before the commit; any refusal after the tree is written resets and cleans the clone | `tests/unit/release/test_public_export.py`: `test_onto_refuses_an_ignored_file_and_commits_nothing`, `test_a_refusal_after_the_tree_is_written_leaves_the_clone_as_it_was` |
| UC-7 | `ba1849be` | `--onto` needs a history with exactly one root commit whose message is an export's (`ROOT_MESSAGE`); `add` and `commit` run with `core.hooksPath=/dev/null` and `core.autocrlf=false` in both modes | `test_onto_refuses_the_development_repository`, `test_onto_runs_no_hook_of_the_clone` |
| UC-8 | `5c01256c` | a value on stdin that is not UTF-8 is a usage error (exit 2) raised `from None`, so the raw line never reaches stderr or the log | `tests/cli/test_keys_cmd.py::test_a_value_that_is_not_utf8_is_refused_without_showing_it` (UTF-16 with BOM, and a stray `\xff`) |
| UC-15 | `44dde982` | `last_line` skips the CLI's `INFO`/`DEBUG agentprov...:` log lines (all ten call sites) | `gui/tests/test_live_cli_last_line.py` |
| UC-14 | `32621242` | `parse_request` cuts an assistant turn over 20,000 characters (`CUT_MARK`) instead of refusing it, while a user turn over the limit is still refused. The Assistant page's `request_bytes` cuts earlier replies and drops the oldest turns until the request fits in 40 messages and 1 MiB. `max_tokens` is still not sent for `openai_chat`: OpenAI's newer models refuse that parameter (they take `max_completion_tokens`), and the cut makes the bound unnecessary for this defect | `tests/cli/test_assist_cmd.py::test_a_long_earlier_reply_is_cut_never_refused`, `gui/tests/test_help_request_limits.py` |
| UC-31 | `32621242` | the JSON reply is ASCII-escaped (no crash on a lone surrogate; no raw C1/bidi/OSC characters). Text mode and `--show-context` escape each line without the 1,000-character cut. A base URL whose port is not 1..65535 is refused by the settings check (`local_base_url`) and by `target`/`local_target` (exit 2) | `test_the_json_reply_is_ascii_so_hostile_characters_never_reach_a_terminal_raw`, `test_text_mode_shows_a_long_line_whole`, `test_a_base_url_with_a_bad_port_is_refused_not_a_crash` |

### Batches 2-4

Three fixes take a narrower route than the review proposed, and one needs a repository setting:
- **UC-5:** a cost cap is refused for a defence endpoint off loopback, because the caps have one price pair. So MELON
  with a remote embedding endpoint cannot run live until defence prices exist (for example
  `--defence-price-in`/`--defence-price-out`). A loopback embedding server still runs.
- **UC-13:** only the clear `plan_refused`. Chunked or count-only `plan_ok` is not built.
- **UC-30:** `io/atomic.py` is in `AER_CLOSURE` and unchanged. The retry is in `io/replace_retry.py`.
- **UC-45:** the `pypi` environment's `v*` tag limit is a repository setting (`public-repo-plan.md` step 15).

| id | commit | fix | tests |
|---|---|---|---|
| UC-4 | `62d99d10` | a defence endpoint off loopback makes a local-agent run an `api` run (`_class_with_defence`): API consent, both caps (refused before any key source is read when the entry is not local), and the consent text names the defence endpoint, its host and its key variable | `tests/cli/test_live_defence_endpoint.py::test_a_remote_defence_endpoint_makes_a_local_agent_run_an_api_run`, `test_a_local_agent_without_a_defence_endpoint_stays_local` |
| UC-5 | `a86e7419` | `policy.defence_cell_calls`: the cell bound is 48 plus each `*_per_step` cost at every model step of every pass (3 × 16) and each `*_per_pass` cost at every pass (MELON 192, `tool_filter` 51); an unusable `cost` member refuses caps; a cost cap is refused when the defence calls an endpoint off loopback, which has no prices of its own | `test_the_cell_bound_counts_the_defence_s_declared_calls`, `test_a_melon_cell_is_not_admitted_when_its_calls_do_not_fit_the_cap`, `test_a_cost_cap_is_refused_when_the_defence_endpoint_has_no_prices_of_its_own` |
| UC-6 | `07283db3` | `_plan_judges`: a `--plan` judge table is rebuilt from the agent table plus its `model_requested`; one that sets any other member (endpoint, base URL, key variable, transport) to a value other than the agent's is refused (exit 2) | `tests/cli/test_inspect_live_t0.py::test_plan_file_judges_use_the_agent_s_endpoint_and_key` |
| UC-23 | `eee91365` | `_probe` checks `Budget.probe_refusal()` before each probe call against the campaign's prior spend (`_prior_budget`: the working corpus's stored logs plus its recorded probes); `live.caps.probe_calls` keeps the probe count, which a resumed campaign charges again | `tests/cli/test_live_policy.py::test_no_probe_call_is_sent_at_the_caps_and_probes_are_kept_across_resume`, `test_the_prior_spend_of_a_working_corpus_includes_its_recorded_probes`, `test_a_probe_must_fit_the_cost_cap` |
| UC-24 | `707ea41c` | `egress.tunnel_cap(jobs, targets, connections)`: never below 64, else 2 tunnels per concurrent connection; sized from `--jobs` (the sweep's largest arm), the allowed endpoints and an Inspect plan's `max_connections` | `tests/cli/test_egress_proxy.py::test_the_tunnel_cap_grows_with_the_campaign_s_concurrency` |
| UC-25 | `363db545` | `_defence_key`: the defence endpoint's key follows the run's key source (`--env-file`/`--env-stdin` only, `--keychain` only, else keychain then `.env`), and a missing key names the places looked in | `test_the_defence_key_comes_from_the_keychain_first`, `test_the_defence_key_falls_back_to_dotenv_and_a_missing_key_names_both_places`, `test_the_defence_key_follows_an_explicit_key_source` |
| UC-9 | `6b337bc9` | Run Live keys `estimate_result` to the estimate argv it was computed for (`current_estimate`); a failed estimate clears it; Start for a real model waits for this selection's estimate (Preflight Only… does not) | `gui/tests/test_g3_live.py::test_a_changed_selection_never_gates_on_the_previous_estimate` (and the preflight test now waits for the estimate) |
| UC-32 | `2cbb9f45` | `ProgressState.step_count`: the last heartbeat's `done + failed` plus the steps after it (`steps_since_heartbeat`), used by `_enforce_call_cap`; `_resume_extra` keeps `call_cap` and the `steps` progress level | `test_the_call_cap_counts_from_the_heartbeat_after_a_reattach_and_survives_resume` |
| UC-10 | `6c5538c2` | on Linux the supervisor records `supervisor_start_ticks` and `pid_start_ticks` (`/proc/<pid>/stat` field 22), and `same_process` compares them exactly; `observe` reads a job as running while its CLI passes its own identity check (`same_cli`) | `tests/jobs/test_jobs.py::test_a_linux_wall_clock_step_keeps_a_job_running` (simulated Linux, a 30 s step), `test_start_ticks_reads_this_process_s_start` (Linux only); `gui/tests/test_jobs.py::test_kill_needs_the_identity` now breaks both identities |
| UC-11 | `74a5fb2c` | a request already in the control file when the watcher starts is acted on when its `issued` time is not earlier than this process's start (`jobs.record.process_start_time`; psutil stays inside `jobs/`) | `tests/cli/test_control_file.py::test_a_request_issued_after_this_process_started_is_acted_on_although_it_predates_the_watcher` |
| UC-26 | `38365c13` | a running batch step whose job record no longer exists fails with `GONE_NOTE` (exit unknown); `devrun prune` no longer reads such a step as busy | `tests/jobs/test_batch.py::test_a_running_step_whose_job_was_pruned_does_not_stay_running`, `test_a_stopped_batch_s_pruned_running_step_does_not_keep_its_dev_run_busy` |
| UC-27 | `dfbc7c18` | a non-finite `--meta` number is kept as its text; `atomic_write_json` writes with `allow_nan=False` (a ValueError, so `spawn` removes the directory) | `tests/cli/test_jobs_cmd.py::test_a_non_finite_meta_number_is_kept_as_text_and_the_job_stays_listable` |
| UC-28 | `6b20e934` | `jobs follow` of an ended job reads to the end of the file, one 1 MiB read at a time | `test_follow_of_an_ended_job_prints_its_whole_file` (3.3 MiB appended) |
| UC-29 | `3f983567` | a step's time runs from the job's recorded `created` (whole seconds) to `ended.json`'s mtime | `tests/devrun/test_devrun.py::test_the_summary_reports_each_step_s_time` |
| UC-30 | `ddd58a78` | `io/replace_retry.atomic_write_bytes_retrying` (outside every scope; `io/atomic.py` is in `AER_CLOSURE` and unchanged) retries the Windows rename race for `settings` (the call site only), the price overrides and snapshots, and `job.json` (`atomic_write_json` now uses it); `spawn` runs `check()` and the new `job.json` under `jobs.spawn.lock` (retried up to 10 s, then `jobs.spawn.busy`) | `tests/jobs/test_jobs_windows_paths.py::test_settings_and_price_writes_retry_while_a_reader_holds_the_file_on_windows`, `tests/jobs/test_jobs.py::test_two_concurrent_starts_of_one_slot_cannot_both_pass_the_check` |
| UC-33 | `c37dcb0b` | Delete Key asks first (Cancel is the default) and reports a failed delete | `gui/tests/test_g5_portability.py::test_delete_key_asks_first_and_reports_a_failure` |
| UC-34 | `7eb7a4ac` | Copy Execution Id (tab and row menus) copies only an id matching `EXECUTION_ID` (the GUI's copy of `aer.ids.EXECUTION_ID_RE`, which is not on the GUI allowlist; a test pins the two) | `gui/tests/test_g2_pages.py::test_copy_execution_id_copies_only_a_well_formed_id` |
| UC-35 | `299ffa2e` | a deposit list's DEPOSIT_DIR must be absolute (or start with `~`); a relative or dash-led one is a ValueError naming the line | `gui/tests/test_zenodo.py::test_a_relative_or_dash_led_deposit_dir_is_refused` |
| UC-36 | `c3777292` | `worker.run_off_ui`: the call runs in the pool while a local event loop keeps painting; the page is disabled meanwhile. Used for Tune, `options_for` (`--help` probes), `dev_settings`, `devrun plan`/`start` and `_zenodo_settings` | `gui/tests/test_g3_live.py::test_slow_cli_calls_run_off_the_ui_thread` |
| UC-13 | `5adb0118` | `worker.plan_reply`: a `plan_ok` that exceeds one 1 MiB protocol line is answered `plan_refused` (`PlanTooLarge`, "plan too large: N cells …; split it"), which T0 reports as a usage error with that reason | `backends/shared/tests/test_units.py::test_a_plan_too_large_for_one_line_is_refused_with_that_reason` |
| UC-45 | `d207d7a5` | `pypi.yml` checks the tag name before any checkout, checks out `refs/tags/<tag>`, and asserts `HEAD` is the tag's commit (`rev-parse` and `describe --exact-match`) | `tests/repo/test_pypi_workflow.py` |
| UC-46 | `618586c3` | every `runs-on` that reads `CI_RUNNER`, and the core matrix, carry the same-repository guard, so a fork's pull request always runs GitHub-hosted | `tests/repo/test_repository_hygiene.py::test_a_fork_pull_request_never_reaches_the_self_hosted_runner` (and the updated `test_ci_runner_variable_never_moves_the_windows_leg`) |
| UC-47 | `0ab9937a` | every checkout in `ci.yml` and `pages.yml` sets `persist-credentials: false` (`pypi.yml` and `bundles.yml` already did); `pages: write` and `id-token: write` move to the Pages `deploy` job | `tests/repo/test_pages_workflow.py::test_pages_has_exactly_the_pages_permissions`, `test_every_checkout_drops_its_credentials` |

**Side effects to know:**
- **UC-23:** `live.caps` gains `probe_calls` when a probe was charged (absent otherwise, so scripted manifests are
  unchanged).
- **UC-6:** a plan file whose judges repeated the agent's members gets the full agent table. Its live configuration
  digest can then differ from an earlier invocation, and resume treats it as another configuration.
- **UC-10:** `job.json` gains `pid_start_ticks` and `supervisor_start_ticks` (null off Linux).
- **UC-13:** a rebuilt backend environment carries the new worker. An environment built before this commit keeps the
  old behaviour until `agentprov backends build`.

**Checks run (targeted; no full suite):**
- Batch 1: `tests/cli` and the export, keys, assist and GUI help tests.
- Batches 2-4, on the merge into `release/v0.1.1` (`78e4b0fa`):
  - core targeted set: 1,761 passed;
  - the whole GUI suite: 784 passed;
  - `backends/shared`: 97 passed;
  - `ruff`, `mypy` (core and gui), `check_unicode` and `gen_docs --check`: all clean.

## Checked and sound (highlights)

- **Assist egress:**
  - It contacts only the registry host, over HTTPS with default TLS, through no proxy and following no redirects. The body is bounded at 4 MiB and parsed strictly.
  - A provider needs `--allow-network`. Local servers are loopback-only, with userinfo and `@`/`#` tricks refused.
  - No key is in argv. Each key goes to its own host, and is registered for redaction before the request.
  - No corpus data is sent, there is no tool use, and the conversation is never stored.
  - The GUI does no network I/O (S11). `DocView` opens no links and loads images only from under the guide (S1/S2).
- **Live CLI:**
  - `exclude-newer-package` (741c019a) reproduces all four backend locks (`uv lock --check --offline`).
  - The egress proxy (CONNECT allowlist, forward-mode header hygiene) is sound.
  - The local-model peer check happens before any key header is sent, and a LAN key is refused.
  - API caps are checked before any key is read, and `--env-stdin` is bounded and strict.
- **Live capture:**
  - The capture/0.1 hash chain and verifier (gaps, reordering, edits, tails, `after_end`) are sound, and `append_terminal` never invents a `mono_ns`.
  - The redactor, the header allow/deny lists and the worker protocol (nonce, 1 MiB lines, identity cross-check, private fd) are sound.
  - So are the worker environment allowlist and attack-cache staging.
- **Defences:**
  - Registry validation, refusals, guarded `from_config` and the output-filter recorder are sound.
  - The MELON port matches the pinned `pi_detector.py`.
  - The Inspect worker keeps the key out of model_args and records no headers.
- **Jobs:**
  - `kill`'s identity check comes before the tree snapshot, and `delete` never follows symlinks.
  - `resolve_tool` refuses `..`, absolute paths and symlinks.
  - The spawn environment allowlist is sound, and batch steps are re-parsed with their tier recomputed.
  - `stage_scopes` closures and digests are deterministic.
- **GUI:**
  - Option injection is refused (`-` prefixes, `allow_abbrev=False`).
  - Every subprocess gets the allowlisted environment.
  - The new widgets are plain-text (S1/S3), and no reviewed file imports a network module (S11).
  - The viewer's read path is strict.
- **Release:**
  - Every action is pinned by SHA, there is no `pull_request_target` and no expression injection, and the publish job has only `id-token`.
  - `public_export --out` is sound: 6,359 files, 119 excluded.
  - The Zenodo tool has no publish, edit or delete path, and needs a typed confirmation.
  - The release scans fail closed, and `release/index.py` binds receipts by digest.
- **Provenance core:**
  - The D-31 archives are byte-exact, and v2 corpora report drift.
  - The `Ctx.rel(merge=True)` merge key is complete, and Tier 4 linkage is sound.
  - The D-1001 limit overrides are rebuilt only on a `limits_sha256` match.
- **Trust boundary:**
  - `artefacts/` (reviewed in full) is pure and bounded, with linear regexes.
  - `raw/fetch.py`, purge, rawtree and withhold are sound, as are the ingest and io diffs.
  - The adprov D-1011 fixes fabricate no lost-call evidence and leave valid inputs' bytes unchanged.
- **Adapters:**
  - The credleak, agentops and openhands redactors are sound, and so are the qwencode salvage and mcphunt carving.
  - Only `strict_json_loads` / `open_json_stream` read untrusted bytes, and no new times are invented.
  - The TraceLogger structured fuzz found no `adapter.defect`.
