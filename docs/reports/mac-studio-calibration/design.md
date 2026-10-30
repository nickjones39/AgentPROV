# Mac Studio calibration: design note (D-820..D-829)

Status: **approved 2026-10-28** by the user, relayed by the orchestrator ("approve all for me as recommended") and
confirmed in the calibration session's window. **`--tune-jobs` is built (D-820..D-823, D-826); no measurement has
run.** Answers:
- Q1: (b), D-827.
- Q2: Qwen3.5-4B-MLX-4bit and Qwen3.8-Flash-Next-UD-Q4_K_XL.
- Q3: calibrated presets run live.
- Q4: 24 cells.
- Q5: build the local time estimate now (D-826).

Built as written, except:
- a preset run defaults to `--llm-element gateway_compat` (explicit `native` is refused);
- the corpus record's floats are decimal strings (H.1.4(3));
- arm files live in `<out>/arms/`, outside the corpora;
- a sweep's `max_attempts` defaults to 2;
- the report lists `reused_arms`.

Branch `claude/mac-studio-calibration-9cbe8b`, from main `7ae72ef5`.

The roadmap's "Calibrate on the machine" list (`docs/roadmap.md`, the Mac Studio M5 Ultra entry) has four items:
1. the oMLX concurrency sweep `run --tune-jobs`, which bumps the `m5ultra` preset to a measured version (§1–§7);
2. the host capability probes (§8);
3. the memory-watchdog allocation-rate calibration (§9);
4. the estimate priors' time figures (§10).

## 0. Findings before design

| # | Finding | Effect |
|---|---|---|
| F1 | `run --tune-jobs` does not exist. `run --help` has no such option; `cli/run.py:1775` refuses every live run with `--preset`/`--m5ultra` ("deferred to the --tune-jobs calibration", exit 5). | Step 1 builds it (§1–§6). |
| F2 | The preset's `request_timeout_s = 900` is recorded by `preset_record` but never reaches a live run. The worker's gateway element uses `params.timeout_s` if given, else `LLM_TIMEOUT_S` (default 180 s; `backends/shared/.../_llm.py:194`, `runner.py:619`). T0 never sets `timeout_s`. The stock `native` element ignores it (SDK default). | A sweep without the fix would measure timeouts at 180 s, not at the preset's value. §3 wires it. |
| F3 | The oMLX server on `127.0.0.1:8000` (a Python process is listening) answers `GET /v1/models` with **HTTP 401**: it is set up with an API key. The hand-off says oMLX on loopback needs no key, and the `omlx` entry in `endpoints.toml` has no `api_key_env`. `agentprov models --endpoint omlx` exits 3 (`run.local.bad_listing`). | Blocked every measurement. **Resolved by D-827** (the user chose Q1 (b), 2026-10-28): an optional `OMLX_API_KEY`, built ahead of the rest. |
| F4 | `jobs` is not part of the configuration digest (`digest_input` in `_live_run_held`), so arms with different `jobs` in one corpus would count as the same configuration, and resume would skip the cells of the second arm. | Each arm writes its own working corpus (§2). |

## 1. Command

```bash
agentprov run agentdojo --m5ultra --tune-jobs 1,2,4,6,8,12 \
  --model omlx --model-id <ID> --model-dir <PATH> --model-display-name "Local model" \
  --tune-out <DIR> --containment sandbox-exec --i-consent-to-local-run
```

- `--tune-jobs N[,N...]` takes 1 to 12 distinct values, each ≥ 1 and at most the host maximum (`check_jobs`), in
  the order given. It needs a preset (the sweep calibrates one) and a `local` endpoint class (D-721). An `api` endpoint
  is refused (`cli.refused.tune_api`, exit 4): the sweep measures a local server, and an API sweep would be billed
  traffic with nothing to calibrate.
- `--tune-out DIR` replaces `--corpus` (exit 2 if both are given). Default:
  `$AGENTPROV_HOME/calibration/tune-jobs-<UTC stamp>/`. It must not overlap the environments or staging (the G2 guard
  of `_execute`).
- Refused with `--tune-jobs` (exit 2): `--jobs`, `--corpus`, `--campaign`, `--corpus-id`, `--limit`, `--preflight-only`,
  `--plan-json`, `--allow-mixed-config`, `--defence` other than `none`.
- `--dry-run --tune-jobs ...` prints the sample, each arm's `jobs`, which arms would be skipped (§4) and the time
  estimate (§7). It makes no model call.
- `--llm-script` is allowed with `--tune-jobs` **for tests only**: the report is then `test_only: true`, and §6 refuses
  to use a `test_only` report as evidence.

## 2. The sample and the arms

- **Default sample** (`src/agentprov/presets/tune_sample.toml`, a committed run plan; the user can pass `--plan` or
  the selection flags instead): AgentDojo `v1.2.2`, the four suites (banking, slack, travel, workspace),
  `user_task_0`–`user_task_2`, each benign and with `important_instructions` × `injection_task_0`. That is
  **24 cells**, 2 × the largest arm, so the largest arm runs at least two waves. All four suites are in it because
  prompt length differs by suite (workspace is the longest), and prefill dominates these traces (N.2.1a(3)).
  A sample smaller than 2 × max N is a warning, recorded.
- **Same cells in every arm**, in the same order, with `repeats = 1`, `max_attempts = 2` and the preset's start stagger
  (1 s per worker).
- **One working corpus per arm** (F4): `<tune-out>/jobs-<N>/`, corpus id `<source>-tune-j<N>`. Each arm runs the full
  live pipeline (capture, map, derive), so the measured rate is what a capture campaign would see.
- **One consent and one preflight probe** for the whole sweep. The local model's identity is re-observed before every
  cell, as now (A14). A drift **stops the sweep** (`tune.model_drift`, exit 1): the arms would no longer compare the
  same model.
- **Warm-up.** Before the first arm, one cell (the sample's first) runs at `jobs = 1` into `<tune-out>/warmup/`. It is
  not measured. It warms oMLX's prefix cache and loads the model, so the first arm does not pay the load time and the
  cold cache that later arms never see.
- **Order** is the order given (ascending by default) and is recorded. Prefix-cache state carries across arms, so the
  order is a run condition, not a neutral choice.
- **Resume.** A finished arm writes `<tune-out>/jobs-<N>/tune-arm.json`. Re-running the same command skips arms that
  have one and whose configuration digest matches. An unfinished arm is re-run from scratch into a fresh directory
  (the old one is renamed `jobs-<N>.interrupted-<stamp>`, never deleted), because its wall time is lost.

## 3. Request timeout (F2)

For a preset run (sweep or, after §6, a normal campaign), T0 puts the resolved `request_timeout_s` into the agent's
params as `timeout_s` (the field `runner.py:619` already reads). It then enters the configuration digest, and
`preset_record` records its source (`preset` or `flag`). A `native` LLM element with a preset is refused
(`cli.refused.native_timeout`, exit 2), because stock `OpenAILLM` would ignore the value. Runs without a preset do not
change (no new digest input), so existing corpora and their resume digests are untouched.

## 4. Arms that are skipped or flagged

- **Memory.** `local_concurrency` gives `J_memory` for the model. An arm above `J_memory` is **skipped**, recorded as
  `skipped: memory`. It could exhaust the GPU working set.
- **Server limit.** An arm above `J_server` (`--server-max-concurrency`, default 8 for oMLX) **runs** and is flagged
  `above_server_limit`. Its requests queue at the server, and measuring that confirms the limit. The 12 arm is above
  the default limit.
- **Stop rule.** After an arm with a request timeout or a failed cell, the higher arms are skipped
  (`skipped: after_timeouts`). More concurrency would only add load, and the rule never picks such an arm. A canary
  stop, a setup refusal (`config_stop`) or a model drift stops the whole sweep.

## 5. Metrics and the recommendation

Per arm, from T0's clock and the stored capture logs only (no prompt, reply or tool text is copied):

| Metric | Source |
|---|---|
| `wall_s` | T0 `time.monotonic()` from the arm's first spawn to the last ingest |
| cells planned, conclusive, inconclusive, inconsistent, failed | the campaign counters |
| `traces_per_hour` | conclusive cells ÷ `wall_s` × 3600 |
| calls kept, discarded, errors, retries | `session_quality` (existing) |
| `request_timeouts` | `llm.response` events whose `exception.type` is a client timeout (`APITimeoutError`, `ReadTimeout`, `TimeoutException`), plus cells killed at `--cell-timeout` |
| call latency p50, p90, max | `mono_ns` from each `llm.request` to its `llm.response`, per session |
| prompt and completion tokens; prompt tok/s and completion tok/s over `wall_s` | the kept replies' `usage` |

**Rule (N.2.1a(4)):** `peak` is the highest `traces_per_hour` of any arm that ran. The recommendation is the
**smallest N** whose arm has `traces_per_hour ≥ 0.9 × peak`, **no request timeout** and no failed cell. If no arm
qualifies, there is no recommendation and the exit code is 1. The report also prints, for comparison, what the
current preset table gives this model (`J_compute`, `J_memory`, `J_server`, the binding term).

## 6. What is recorded and committed

- `<tune-out>/tune-jobs.json`, format `agentprov-tune-jobs/0.1` (a new format id, registered in `versions.py`):
  - the software (`agentprov` version, git commit, `dirty` flag) and the preset (`name`, `version`, file digest);
  - the host profile (CPU counts, memory, OS) and the queue ticket label of the measurement;
  - the endpoint, the server kind and version, the local model's `identity_sha256`, and the model facts with their
    sources (A, W, KV geometry);
  - the sample's `plan_sha256` and cell keys, `repeats`, `max_attempts`, stagger, request timeout, `cell_timeout`,
    the order and the warm-up;
  - the per-arm metrics of §5, with skip reasons, and each arm corpus's id and `corpus.json` sha256;
  - the recommendation and the rule's parameters (0.9, timeouts 0), and `test_only`.
- `<tune-out>/tune-jobs.md`: the same as a table.
- **Committed** (step 4): each model's `tune-jobs.json` under `docs/reports/mac-studio-calibration/tune-jobs/` and a
  summary in `docs/reports/mac-studio-calibration/README.md`. The arm corpora are **not** committed (invariant 6). They
  stay under `$AGENTPROV_HOME/calibration/` until the user OKs moving them to the Trash. They are throughput evidence
  only, never results: the models' verdicts are not reported.
- **Research caveat (N.2.1a(4), unchanged):** batched inference is not batch-invariant, so `jobs`, the server limit and
  the preset version stay recorded run conditions (`live.jobs`, `producer.preset`).

## 7. Time estimate (shown before the yes)

`--dry-run` prints an estimate. Before any measurement it uses the D-653 priors' calls per cell and the live pilot's
rate (an 8B model on LM Studio: 25 kept calls in 7m56s at `jobs = 1`, 8 cells). That rate is labelled as from another
server and model. As a rough guide for 24 cells and arms 1, 2, 4, 6, 8, 12: about 45 cell-times in all (24 + 12 + 6 +
4 + 3 + 2 + 1 warm-up, if throughput scaled perfectly; less scaling means more). That is about 45–60 minutes for an
8B-class model, and several hours for a 70B-class dense model.

## 8. The preset bump (`m5ultra` version 2)

- `presets.toml`: `version = 2`; `calibrated = true`; `calibration = "docs/reports/mac-studio-calibration/README.md"`.
- `compute_caps` keeps its three active-parameter classes (≤ 15 B, 15–40 B, > 40 B). Each row gets
  `basis = "measured"` with the recommended N of the model measured in that class, or keeps its v1 value with
  `basis = "provisional"` if no model in that class was measured. One model per class is the minimum. Ask the user
  which models (Q2).
- `server_max_concurrency_default` stays 8 (oMLX's default) unless the user runs oMLX with another
  `--max-concurrent-requests`, in which case the measured setting is recorded as an evidence row, not as a new default.
- `request_timeout_s` stays 900 unless the measured p90 latency gets near it.
- New `[[presets.m5ultra.evidence]]` rows: one per measured model, `claim` = the measured rates and the
  recommendation, `source` = the committed report's path and sha256. The v1 rows stay as the prior.
- `presets.py` parses the new keys (`calibrated`, `calibration`, `basis`), and `preset_record` records `calibrated`.
- **Corpora keep the preset version they recorded:** `producer.preset{name, version, resolved}` is written per corpus,
  so the bump changes nothing stored. No corpus has recorded a preset yet, because preset live runs were refused.
- **Unlocking preset live runs (Q3):** the refusal at `cli/run.py:1775` is lifted for a preset with `calibrated = true`:
  `jobs` comes from the plan unless `--jobs` is given, and the stagger and request timeout come from the preset. v1
  (`calibrated` absent) stays refused, so nothing runs on unmeasured caps.

## 9. Host capability probes (D-824): nothing to build

- **What they are:** `detect_host()` (`host.py:703`) probes the host **live in every process**. It caches nothing on
  disk (D-7). `check_host` (`presets.py:263`) compares the live profile with the preset's `expected_host`.
- **Checked on the Studio** (`agentprov info`, 2026-10-28, no model, no network): `darwin 27.2.0 / arm64`, 36 CPUs,
  256.0 GiB; rlimits core, cpu, fsize, nofile, as; `rlimit_as_enforced` False; `rss_sampler` libproc; `tree_kill`
  killpg; `hard_memory_cap` none; isolation grade `watchdog`, calibration `ok`.
- `run agentdojo --m5ultra --dry-run --model-size-gb 18 --active-params-b 3` no longer prints a host mismatch
  (`J_compute 8, J_memory 35, J_server 8`). The roadmap item is therefore met by the move.
- **Proposed:** record these facts in the report (§6) and correct the roadmap line. No code changes.

## 10. Memory-watchdog allocation rate (D-825): nothing to build

- **What it is:** the allocation rate is **measured in every process** that starts a worker pool. `job_calibrate`
  (`io/workers.py:1004`) allocates 8 MiB blocks for at most 80 ms or 256 MiB, and `get_calibration` caches the result
  in memory only.
- **The default:** `DEFAULT_ALLOC_RATE = 4 GiB/s` (`host.py:86`) is used only when that probe fails. The measured rate
  sets the RSS kill margin, so each corpus's `producer.isolation` records it.
- **The roadmap is misleading here:** it says the rate "is a default until it is measured". There is no committed
  measured value to update.
- **Proposed:** in the quiet window, run the probe 20 times through the queue (a short stdlib loop over
  `get_calibration`, no model). Record min, median and max in the report. Update the figures in the `constants_for`
  docstring (`host.py:859`, which today says "11.9-12.3 GiB/s", the M2 Max) and in `G_security.md:985` with the
  Studio's, naming both machines.
- **Default:** the 4 GiB/s default changes only if the Studio's minimum is below it. A lower measured rate makes the
  default unsafe, while a higher one leaves it conservative.

## 11. Estimate priors' time figures (D-826): no rebuild needed

- **How they are built:** `tools/estimate/gen_estimate_priors.py` reads stored AER only. It uses no model and no
  network, and it does not import or derive. `seconds` is the AER run scope's `t.dur_s` (`estimate/usage.py:142`):
  the duration **recorded in the source logs**, not this machine's compute time.
- **Effect of a rebuild here:** corpus bytes are identical across machines (invariant 4), so a rebuild on the Studio
  from the same corpora gives the same rows; only `built_from.commit` changes. The roadmap's claim that "their time
  figures come from the M2 Max" is wrong.
- **Proposed:** correct the roadmap. Optionally (Q5), run the rebuild once through the queue as a check that the rows
  come out byte-identical, and don't commit it unless something differs.
- **What is actually missing:** a time basis for **local** runs. The estimate uses the default 45 s / 150 s per cell
  for oMLX (`estimate/cost.py:117`), and the local-LLM design note (§6) left "time: needs a measured throughput
  (--tune-jobs)" open.
- **Proposed follow-up (Q5, not in this build unless you say so):** per measured model, put the recommended arm's
  seconds per cell into `presets.toml` as `[[presets.m5ultra.cell_seconds]]` rows by active-parameter class. A local
  preset run's estimate would then use them, labelled `basis: tune-jobs`.

## 12. Downstream effects, tests, decisions, questions

**Downstream effects** (all class 0):
- Code: `cli/run.py`, a new `cli/live/tune.py`, `presets.py`, `presets.toml`, `versions.py` (the new format id) and
  the new `presets/tune_sample.toml`. None of these is in a stage digest. No AER, SEM, PROV or compat bytes change,
  and no stored corpus changes.
- `capture/` and `backends/` do not change, so no environment rebuild is needed (unless Q1 (b)).
- Preset runs, which none exist yet, get `timeout_s` in their configuration digest and `calibrated` in
  `producer.preset`.
- Tests that pin `m5ultra` version 1 are updated at the bump (step 4).
- Spec and docs: N.2.1a(4) (the sweep as built), N.2.1b(3) (the refusal becomes "uncalibrated preset"); D-820..D-826
  in `docs/architecture/decisions/`; an AGENTS.md fragment; the generated CLI page of the user guide; the roadmap
  corrections of §9–§11.
- Manuscript: the concurrency figure becomes measured. The batch-invariance caveat stays.

**Tests** (scripted, no real model):
- unit tests: the metric extraction on synthetic capture logs (timeouts, latency pairs, usage), the recommendation
  rule (table-driven: ties, all timed out, peak at the top arm), the skip and stop rules, `J_memory` skips, the
  report schema, and the `presets.toml` v2 parsing;
- CLI refusals: an `api` endpoint, `--jobs`, `--corpus`, no preset, `native` with a preset, and an uncalibrated preset
  live run;
- an integration test with the fake backend environment (the `test_run_spawn.py` pattern): `--llm-script --tune-jobs
  1,2` on 4 cells, covering the warm-up, the arm corpora, the report, and resume after an interrupted arm;
- the full suite through the queue (`-n 24`).

**Decisions** (reserved D-820..D-829):

| Id | Decision |
|---|---|
| D-820 | `run --tune-jobs`: one preset, a local endpoint, one corpus per arm, the default 24-cell sample, warm-up, order recorded, resume by arm (§1, §2, §4) |
| D-821 | Metrics, the recommendation rule (smallest N ≥ 0.9 × peak, no timeouts, no failed cell) and `agentprov-tune-jobs/0.1` (§5, §6) |
| D-822 | A preset's `request_timeout_s` reaches the worker as `timeout_s`; `native` with a preset is refused (§3) |
| D-823 | `m5ultra` v2 schema (`calibrated`, `basis`, evidence rows); calibrated presets may run live (§8) |
| D-824 | Host probes: nothing to build; Studio facts recorded (§9) |
| D-825 | Watchdog rate: measured per process; Studio figures recorded, default kept unless the minimum is below it (§10) |
| D-826 | Priors: host-independent, no rebuild; local-run time basis from the sweep offered (§11) |
| D-827 | **Built** (user's Q1 (b)): an optional key for a local endpoint, `OMLX_API_KEY` on `omlx`; CLI, discovery and GUI; never to a LAN address |
| D-828 | **Built** (user's request): a local model's facts as settings (`local_models.<endpoint>.<id>.*`, Settings › Local Models), flag > setting > folder > preset; GGUF sizes; `models --find-folders` |

**Questions for the user:**

- **Q1: the oMLX key (F3). Answered 2026-10-28: (b), built as D-827.** The options were:
  - (a) **Recommended:** turn off oMLX's API key for the loopback server. The registry entry stays keyless and nothing
    else changes.
  - (b) Add an optional `api_key_env = "OMLX_API_KEY"` to the `omlx` entry, with the key read from the Keychain
    (D-702). This changes the capture package, so the orchestrator rebuilds the four backend environments.
- **Q2: models.** Which oMLX models to sweep, ideally one per class (≤ 15 B active, 15–40 B, > 40 B).
  - **Served on 2026-10-28:** two DeepSeek-V4.1-Flash builds (319 GiB each, **over the 192 GiB budget**: the
    preset's memory rule refuses them, although oMLX serves them), two Qwen3.8-Flash-Next GGUF builds (104 GiB and
    158 GiB), and a 1.1 GiB DFlash2 draft model.
  - **Active parameters:** none of them states the count, so the user gives it, now as settings (D-828).
  - **DeepSeek-V4.1-Flash, out of scope (the user, 2026-10-28):** both 319 GiB builds exceed the preset's 192 GiB
    budget and the machine's 256 GiB of physical memory. They will not be used in AgentPROV, so the preset's memory
    refusal stays as it is.
- **Q3: preset live runs.** Should calibrated presets run live (recommended), or stay dry-run only?
- **Q4: sample size.** Choose one:
  - 24 cells (recommended);
  - 16 cells (two user tasks per suite), which is faster but makes the 12-job arm a single wave.
- **Q5: estimate and priors.** Should the sweep feed the local-run time estimate (§11)? And should the priors rebuild
  run as an identity check?
