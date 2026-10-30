# A per-cell call bound for Inspect runs under the D-725 caps

Status: **approved, implemented** (D-740). The user approved option (a) on 2026-10-22 and gave the separate typed yes
for the D-667 probe with it; the probe runs after the regeneration round (orchestrator ordering, 2026-10-22). This
note was first written as a proposal at `e4bcfe05`. Its section 2 digest is corrected here: an earlier draft quoted the
`task_files_sha256` test vector, not the digest of the real package.

## 1. The problem

D-725's caps decide whether a cell may start by reserving the cell's worst case: `CELL_CALL_BOUND` billed calls, each
at the per-call token bound. The token bound is 32,000 input tokens, or the largest seen, and the transmitted
`max_tokens` or 4,096 output tokens, or the largest seen. `CELL_CALL_BOUND` is the AgentDojo cell's 48 (3 passes × 16
calls).

An Inspect cell is one `eval()` over `cell_size` samples × `epochs`, and each sample makes agent and judge calls. The
48 calls do not bound that. Since the train 2 merge (`887b12d0`, on main at `31ee942d`), a real Inspect run with caps
active is therefore refused (`cli.refused.api_caps`, `cli/run.py` `_refuse_unbounded_caps`; D-667 addendum). Every
API endpoint run has its caps active.

## 2. What bounds an Inspect sample's calls (inspect_ai 0.3.263, inspect_evals 0.20.0, read from the pinned wheels)

- **Agent calls ≤ `message_limit` − 1.** `Model.generate` calls `check_message_limit(len(input),
  raise_for_equal=True)` before every generate (`inspect_ai/model/_model.py`). So a generate is refused when the
  conversation is at the limit. Each agent turn adds at least one message, and a sample starts with at least one (the
  default agent has a system and a user message). AgentHarm's solvers make no model call outside `generate`.
  `default_agent`'s optional `tool_calls="single"` step is an ordinary generate, and `refusal_agent` makes none.
- **Refusal-judge calls ≤ agent calls.** `combined_scorer` calls `RefusalJudgeLLM.check_refusal` once per assistant
  message with text, and stops at the first refusal.
- **Semantic-judge calls ≤ 3 per sample.** An AST count over `harmful_grading_functions.py` and
  `benign_grading_functions.py` found:
  - at most 3 `semantic_judge` call sites per grading function;
  - none inside a loop or comprehension;
  - no indirect calls through another module function;
  - one `generate` per `semantic_judge`.

  The count belongs to this exact code, which `task_files_sha256` pins (`sha256:4ba500be…`, computed by T0 from a built `inspect-agentharm` environment).
- **Retries can bill.** Inspect retries an empty 200 stream (`NoStreamDataError`) and any attempt or stream-idle
  timeout. With `max_retries` unset, the retries are bounded only by the timeout. D-725 counts every 2xx
  `llm.response` as billed, and the harness does not set `max_retries` today. So without a fixed retry count there is
  no bound at all.

## 3. Proposal

1. **The harness fixes the retries for capped runs.** The worker sets `GenerateConfig(max_retries=K)` for the agent
   and every judge, with K = 1 by default. Each logical call is then at most 1 + K billed responses. This is a harness
   setting the plan cannot change, so the `inspect.harness_settings` instrumentation item moves to `@2`, with K in
   its detail. A scripted run is unaffected.
2. **The per-cell call bound is computed in T0 from the plan.** For an Inspect cell of n samples, E epochs and message
   limit M:

   `C = n × E × ((M − 1) + (M − 1) + J) × (1 + K)`

   - (M − 1) agent calls;
   - (M − 1) refusal-judge calls;
   - J semantic-judge calls (3 for AgentHarm).

   J comes from a per-task table in the backend kind (`cli/live/envs.py` `BACKEND_KINDS`), keyed by task and
   `task_files_sha256`. A task or digest without an entry keeps the refusal of §1, so a new inspect_evals version
   needs its count re-derived. A test re-derives J by the same AST count over the pinned files.
3. **`Budget` takes the cell's bound instead of the constant.** The constant becomes the AgentDojo-family value of the
   same parameter, so AgentDojo runs are unchanged. Two existing checks use it:
   - the start check, which reserves C at the per-call token bound for each in-flight cell;
   - the `cap_bound_exceeded` stop, for an attempt that billed more than C calls.

   The parent-kill extra call stays as D-725 has it.
4. **Judges are priced like the agent.** The caps have one price pair, so a capped run is refused unless every judge
   uses the agent's model (D-667 already puts them at the agent's endpoint and key). The alternative is per-role price
   flags, which can come later if a run needs a different judge model.
5. **Small cells for capped runs.** The start check reserves a whole cell's worst case, but the spend is charged from
   recorded usage. With `--cell-size 1` the reservation is one sample's worst case, and the actual spend decides
   whether the next cell starts. Proposal: under caps, `run` defaults `--cell-size` to 1 for an Inspect backend, and
   the consent text shows C and its USD bound.

## 4. Worked figures (gpt-4o-mini, $0.15 in / $0.60 out per million tokens; per-call bound $0.00726; E = 1, J = 3)

| M | K | n = 1: calls, USD | n = 4: calls, USD |
|---|---|---|---|
| 20 | 0 | 41, $0.298 | 164, $1.190 |
| 20 | 1 | 82, $0.595 | 328, $2.380 |
| 20 | 2 | 123, $0.893 | 492, $3.571 |
| 10 | 0 | 21, $0.152 | 84, $0.610 |
| 10 | 1 | 42, $0.305 | 168, $1.219 |
| 10 | 2 | 63, $0.457 | 252, $1.829 |

The D-667 probe was "4 samples, agent and judge gpt-4o-mini, capped at $0.50". As one cell its worst case exceeds the
cap in every row, so it would never start. Two options for the user:

- **(a) Recommended:** `--cell-size 1`, `--message-limit 10`, K = 1. Each cell reserves $0.305. The survey priors for
  one AgentHarm sample (about 4.4k input and 1.0k output agent tokens, and about 1.5 judge calls) put its expected spend
  near $0.002. So all four cells start under the $0.50 cap, and if they ever cost more, the cap stops the run between
  samples.
- **(b)** Keep `--message-limit 20` and raise the probe cap to $1.00 with `--cell-size 1` (a reservation of $0.595
  per cell).

## 5. Possible tightening (not proposed now)

Inspect's `token_limit` bounds the agent's tokens per sample. A token-based USD bound (`token_limit` plus one call's
overshoot, priced at the higher of the two prices, plus the judges at their per-call bound) can be much smaller than
the call-count bound. Using it needs a check of what Inspect 0.3.263 counts against `token_limit` (judges or not, and
the last call's overshoot). Proposal: ship the call-count bound (§3), and add the token bound only after that check.

## 6. Effects

- **Code (when approved):**
  - `cli/live/policy.py` (a cell-bound parameter);
  - `cli/run.py` (the bound, the judge-model check, the cell-size default, the consent text);
  - `cli/live/envs.py` (the J table);
  - `backends/inspect` (`max_retries`, the instrumentation `@2`).

  All of these are class 0 (no stage digest). The held core's `agentharm-live` profile lists the instrumentation id,
  so it moves to `inspect.harness_settings@2` before it lands.
- **No corpus byte changes.**
- **D-725's AgentDojo behaviour is unchanged.**
