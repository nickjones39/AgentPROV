# Live gates pilot: local models, then capped OpenRouter and Anthropic runs (design note)

Status: **design, for decision.** No code, no inference and no key use yet. Session "live gates pilot (local
models)", own worktree on main `32c89f96`, 2026-10-22. Decisions D-720..D-729 are reserved (`tools/reserve_id.py`).

**Scope.** It started as local models only (user decision 2026-10-22). Later on 2026-10-22 the orchestrator relayed
two additions from the user. Together they replace "API runs stay refused":

1. **One small, capped OpenRouter run** after the local part (§5.3).
2. **One small, capped Anthropic run** through the direct `anthropic` endpoint (D-656) after OpenRouter (§5.3a). The
   D-656 session's separately approved preflight probe runs first and exactly once (§5.3a).

The order is local, then OpenRouter, then Anthropic.

**Conditions on the API runs.** Each API run happens only after the user's typed yes in this window, given against
the exact plan, the cost estimate, a cost cap and a call cap. The user has added `OPENROUTER_API_KEY` and
`ANTHROPIC_API_KEY` to the repo `.env` (also relayed). This session never reads `.env`. Key presence is checked only
through the CLI's own resolution path (§5.3 step A0).

Everything below was read from main `32c89f96`, `rebuild-window-2026-10-22` (R), the local-endpoints branch
`claude/agentprov-local-endpoints-ea6a44` (L, which contains R), `agentdyn-backend` and `agentdyn-backend-core`, and
the defence branches. Citations are `branch:path:line` where the line matters.

---

## 1. Findings that shape the design

| # | Finding | Where |
|---|---|---|
| F1 | **There is no `gated` status, and there cannot be one.** The live vocabulary is closed (`supported`, `partial`, `planned`, `not_possible`), and the registry "MUST NOT invent other status strings" (R-15). "Gated" in the registry comments means "the value its gate supports", not a value of its own. | D.3.2; I.5 rule 1 (`I_matrix.md:1299`); `registry/__init__.py:43` |
| F2 | **The `planned` gate is the only thing that refuses real runs.** `_live_capability` refuses any non-scripted run of a `planned` part (exit 5). Any other status lets every real endpoint through, local or API, subject only to consent, containment and keys. | `main:src/agentprov/cli/run.py:388-415`; `L:run.py:500-529` |
| F3 | **A live part becomes `supported` on scripted evidence alone.** The gate is: backend implemented, CI drives a real benchmark task end to end through the worker (scripted transport allowed), identity guards active. The real-model pilot changes the **caveat**, not the status: "its caveat stays until a real-model pilot is sealed and approved (U-10)". | D.3.2 (`D_adapters.md:835`); I.5 rule 2 (`I_matrix.md:1301-1307`) |
| F4 | **A live corpus cannot be sealed in this build.** `package` refuses every non-import row (`package.unsupported.live`, exit 5), and `run --spec` is refused ("arrive with corpus sealing (phase 11)"). The phrase "sealed, non-`test_only` live corpus" (U-18, NC-LIVE-02) therefore cannot be met by any pilot until live sealing exists. | `src/agentprov/corpus/package.py:604-606`; `run.py:1072`; HL H.1.5, row `agentdojo-live-<campaign>` (`HL_corpus_versioning.md:850`) |
| F5 | **`validate --release` cannot pass on any corpus today.** It also requests `shacl` (not built). A requested tier that does not run counts as skipped, and skipped fails under `--release`. `--strict` gives the release-mode validators over the tiers that exist. That is what `package` requires ("the validation stage ran strict"). | `src/agentprov/cli/checks.py:13-17` |
| F6 | **"CI" means local CI (D-462).** GitHub Actions has not started jobs since 2026-10-09. D-462 made `tools/ci_local.py` the default gate. Its live jobs `live-run` and `backend-autodojo` build backends with `--allow-network` (they need a yes); `backend-agentdojo` runs offline. No CI run of a live job is recorded anywhere. All live evidence so far is local. | DECISIONS D-462; `tools/ci_local.py:135-182`; AGENTS.md:1232 |
| F7 | **Nothing distinguishes a local endpoint from an API endpoint at the status gate.** `endpoints.toml` marks entries `local = true` (loopback-only, keyless, `server` named). But `_live_capability` never looks at the endpoint. On L, `LOCAL_ENDPOINT_NAMES` is hard-coded in `run.py:46` rather than derived from `endpoints.toml`. | `L:capture/src/agentprov_capture/endpoints.py:198-217`; `L:run.py:46` |
| F8 | **The CLI has no cost cap and no call cap.** The cost estimate (D-650 prices, D-653 formula) is GUI-only. The transport retries up to 8 wire attempts per call (429, connection error, 5xx). AgentDojo's tool loop allows 15 iterations. The only stops are `--max-attempts` (per cell), `--cell-timeout` and the canary. | `R:backends/shared/src/agentprov_backend/_llm.py:129`; DECISIONS D-650, D-653 |
| F9 | **All three installed local models are "abliterated" Qwen3 variants**: their refusal behaviour has been removed. That is fine for a capture-path gate. It would be misleading as a security result (attack success on a model with its refusals stripped). | `~/.lmstudio/models/` (8B mxfp4 4.1 GB, 14B 6-bit 12 GB, 35B-A3B 4-bit 23 GB) |
| F10 | **Identity and canary gaps on L.** (a) The LM Studio version is not recorded (`detect_server` returns `version None`). (b) The canary covers only the first `--canary N` cells (default 10); later conditions are notices. (c) The D.10.9 canary paragraph does not list A12 or A14. (d) The L design note's header still says "proposed, nothing built". | `L:src/agentprov/cli/live/localmodels.py:307`; `L:campaign.py:463-471`; `L:D_adapters.md:4806-4808` |
| F11 | **What already works on a real server.** The local-endpoints session's direct probe of LM Studio, `qwen3-8b-abliterated-v2`: HTTP 200 in 23.9 s including the model load; served model equal to the requested one (A12 holds); a structured tool call (A4 `structured`, A9 `accepted`); 137 of 166 completion tokens were reasoning. | `L:docs/reports/local-llm/design.md:294-306` |

---

## 2. The gates, per live part

Legend: **S** = scripted evidence is enough; **R** = needs a real (local or API) model; ✓ = passed with recorded
evidence; ◐ = passes locally, not as specified; ✗ = missing; ⏳ = waits on the rebuild window or a held branch.

### 2.1 Status gate (planned → `partial`/`supported`, D.3.2 rule 1, I.5 rule 2)

| Gate | Kind | `agentdojo · live` | `autodojo · live` | `agentdyn · live` |
|---|---|---|---|---|
| G1 Backend implemented; registered environment with T0 identity and `--offline-check` | S | ✓ `agentdojo-79922295` (`docs/reports/backends/agentdojo-env.md`, 2026-10-22) | ✓ `autodojo-aa458794` (2026-10-08) | ⏳ built only in a scratch home (`agentdyn-5353cf76`); the registered env is built from main after its branches land |
| G2 A real benchmark task end to end through the worker, scripted ("CI": local CI per D-462) | S | ◐ 4-cell banking run (agentdojo-env.md); `tests/integration/test_run_live_agentdojo.py` (7). `ci_local --only live-run` not recorded | ◐ `docs/reports/live/autodojo-phase9.md`; `test_run_live_autodojo.py` (7); phase 9b. `ci_local --only backend-autodojo` not recorded | ◐ scripted S1–S4 (scratch); T1–T6 tests on its branch |
| G3 Identity guards active (D.10.6: lock, RECORD, PEP 610, guarded sources, `hello.expect`) | S | ✓ | ✓ | ✓ on its branch |
| G4 Executor-mirror differential (D.10.6, K.9.4) and live-vs-native differential (K.8.5, K.9.1) | S | ✓ (AGENTS.md phase 8; D-292) | ✓ (all 17 suites) | ✓ on its branch |
| G5 sandbox-exec probe passed **for the profile digest in force** (G.4.10; `_containment`) | S | ⏳ the D-664 profile changes the digest, so the window rebuild must re-probe | ⏳ same | ⏳ same |
| G6 Phase-8/9 DoD rows, Q.4/Q.7 (scripted cell sealed, forced kill `aborted`) | S | ✓ | ✓ | n/a (D.11.10) |
| G7 C6 old-vs-new (diagnostic, "not a release gate") | S | ✓ local 14/14 (`docs/reports/migration/gate-c6.md`) | n/a | n/a |

**So the status gate passes on scripted evidence for agentdojo and autodojo**, apart from the recorded local-CI run
(G2) and the re-probe after the window (G5). AgentDyn's part needs its held branches and its registered env first.
These are build steps, not pilot steps.

### 2.2 Caveat gate (D.3.2 rule 3: "fake-client tested in v0.1; no real-model run" until an approved real-model run)

| Gate | Kind | All three parts |
|---|---|---|
| G8 A real-model run through the product path (`agentprov run`) | R | ✗ never done (the pilot) |
| G9 The user approves its results (U-10 as amended, U-18 approval) | user | ✗ |
| G10 "Sealed" (I.5 rule 2 wording) | — | **impossible in this build** (F4); see D-724 |

### 2.3 Claim gate (not in scope; recorded so nobody reads the pilot as meeting it)

"Live Capture" in a title, or any live result in the paper, needs an approved, **sealed**, non-`test_only` live
corpus (AD-08, U-18, NC-LIVE-02, Q.11b). The pilot cannot meet this (F4), and it does not try to. After the pilot,
the claims library's `real_model_live` lint stays as it is.

---

## 3. Promotion proposal

### 3.1 Status: `partial` for all three parts, together (D-720)

- **Not `gated`.** It would be a new status string (F1, R-15).
- **Not `supported`.** Real-model runs are admitted only for a declared subset of configurations:
  - local servers, or API endpoints with caps (§3.2);
  - `--defence none` until D-677's live profiles v2;
  - the `native` LLM element, as AgentDyn refuses `gateway_compat`.
- **`partial` is D.3.2's own definition:** "Implemented for a declared subset of configurations only". The caveat
  must name the subset. This is also the worst-case reading that I.5 rule 3 favours.
- **What `partial` unlocks.** The status gate in `run.py` already admits `partial` (F2). The subset is enforced by
  the endpoint policy of §3.2, not by the status.

All three parts move in one class-1 commit, as the user decided (D-684). `agentdyn · live` must exist on main first,
so that commit goes on top of `agentdyn-backend-core`.

### 3.2 How "local" and "API" gating is expressed (D-721)

There is one status per part. The run-time policy depends on the **endpoint class** of the resolved agent:

| Endpoint class | Definition (computed by T0 before any network or `.env` key use) | Admitted with |
|---|---|---|
| `local` | The `endpoints.toml` entry has `local = true` **and** the resolved base URL's host is loopback (`127.0.0.1`, `::1`, `localhost`). A LAN address under `--allow-lan-endpoint` (D-698) counts as `local` only once the egress proxy's LAN forward mode exists; until then sandbox-exec refuses LAN anyway (`cli.refused.lan_containment`) | **consent** (interactive, or `--i-consent-to-local-run`; D-726); `--containment`; loopback-only sandbox profile (D-664: no proxy, `EGRESS_PORT = LOOPBACK_PORT` = the server port) |
| `api` | Anything else: `local = false` entries, `--endpoint` with `--allow-custom-endpoint`, a `--base-url` that is not loopback | **consent** (interactive, or `--i-consent-to-api-costs`); **both caps** `--max-calls N` and `--max-cost-usd X` (D-725; refused with exit 4 `cli.refused.api_caps` if either is missing); `--containment`; the D-664 egress proxy allowing exactly the endpoint's `(host, 443)`; the key only through `--env-file` / `--env-stdin` / `--keychain` (D-702), registered with the redactor before use |

**Where it is enforced.** The policy lives in the CLI (`run.py`, a `_endpoint_class()` helper called right after
`_real_agent` resolves the URL and before consent, the preflight probe or any spawn), with the caps in
`cli/live/campaign.py`.

- This is class 0: `cli/` is in no stage digest.
- It applies to every real-model run of every source, so a future registry edit cannot widen it by accident.
- The endpoint class is not a new registry field. A registry schema field would add class-1 churn and duplicate
  `endpoints.toml`, which already carries `local`. It was considered and rejected (§8).
- The class is recorded:
  - in the run's notices;
  - through the agent record already in the configuration digest (endpoint name, base URL, `local`);
  - with the caps in the campaign record (`live.caps`, below).

**Caps (D-725), enforced by T0 in the campaign loop, never by the model.**

- `--max-calls N` counts every **billed** wire attempt (2xx replies) in the capture logs of the campaign's settled
  sessions, plus the preflight probe.
- A cell starts only if the remaining budget covers its **worst case**: `(max_iters + 1)` billed calls, which is 16
  for AgentDojo-family pipelines.
- `--max-cost-usd X` works the same way, with a per-cell worst-case cost. The prices come from `--price-in` and
  `--price-out` (USD per million tokens, required for `api`). At run time they are filled from the D-650 shipped
  table and printed with its `as_of` date.
- **Worst-case tokens per cell.**
  - Input: the context bound of the request (`max_iters + 1` calls at the endpoint's context limit, or the measured
    largest request so far, whichever is larger).
  - Output: `max_tokens` when it is transmitted; otherwise the model's output limit from the table.
- **After each cell**, the recorded `usage` gives the actual spend. A campaign that hits a cap stops before the next
  cell, with exit 1 and the reason `cap_reached`.
- **No mid-cell stop.** A cap can never be overshot, because a cell only starts when its worst case fits. A per-call
  stop inside the worker would need `backends/shared`, and it misses this env-rebuild window.
- **The hard backstop is the provider's.** The user sets a credit limit on each key in the provider's own console
  (OpenRouter key credit limit; Anthropic workspace spend limit; recommended $1 each). That is the "spend-capped key"
  of U-10, and it does not depend on our code.
- **Prices with prompt caching (Anthropic).** The worst case prices every input token at the highest input-side
  price: input, cache write or cached, whichever is largest. So caching can only lower the actual spend under the cap.
- **`--preflight-only` is exempt from the caps.** It is a fixed one-billed-call operation: retries happen only on
  429, 5xx or connection errors, which are not billed. Its worst case is one call at the stated `max_tokens`. It
  still needs consent and containment. This keeps the D-656 session's approved probe command valid as written (§5.3a).

### 3.3 Caveat texts

**Step 1, at promotion (before the pilot).** Rule 3's phrase stays. Proposed `_AGENTDOJO_LIVE_CAVEAT`:

> partial: real-model runs are admitted for local model servers (endpoints.toml `local = true`, loopback only) with
> consent, and for API endpoints only with consent, a call cap and a USD cost cap (`--max-calls`, `--max-cost-usd`),
> under `--containment` with the D-664 egress allowlist; `--defence none` and the `native` LLM element only.
> fake-client tested in v0.1; no real-model run (D.3.2 rule 3). Live corpora cannot be sealed in this build, so no
> live corpus supports a "Live Capture" claim (U-18).

- **AutoDojo** gets the same text, plus: "isolated environment (fork @ `aa458794`); the `autodojo` attack replays a
  verified fork cache; ROPE-hosted runs cannot be reproduced (D.11.6)".
- **AgentDyn** gets the same text, plus: "AgentDyn @ `5353cf76` (D.11.10); its tools read the clock and the random
  generator, so a re-run is not a reproduction (`agentdyn.art.nondeterministic_tools`)".

**Step 2, after the user approves the pilot (D-722).** One sentence changes:

- "fake-client tested in v0.1; no real-model run (D.3.2 rule 3)" becomes "real-model pilot <date>, approved by the
  user: local `<model id>` (<n> cells) [, OpenRouter `<model id>` (<n> cells), Anthropic `<model id>` (<n> cells)] through `agentprov run`
  (`docs/reports/live-pilot/`); working corpora, not sealed".
- The sentence about sealing stays.
- Each part names only the endpoint classes it actually ran. Under the plan in §5, the OpenRouter and Anthropic
  runs cover `agentdojo · live` only. Its caveat names both classes; the other two name the local run only.

### 3.4 Stale caveats and text to fix in the same class-1 commit (D-727)

| Where | Stale text | Fix |
|---|---|---|
| `registry/__init__.py:237-242` (`agentdojo · live`) | "the backend project, agentprov run and the live gates are pending, so no session has been captured through the product path" | §3.3 step 1 |
| `registry/__init__.py:244-250` (`autodojo · live`) | "the backend environment and the live gates are pending … A real-model pilot needs the user's provider keys and explicit consent to API costs (U-10)" | §3.3 step 1 |
| `agentdyn-backend-core` registry 316-323 (`agentdyn · live`) | "a real-model pilot needs the user's provider keys and explicit consent to API costs (U-10)" | §3.3 step 1 |
| Registry comments 396, 531 and the module docstring | "``planned`` until its gates pass" | "`partial` (D-720)" |
| D.3.3 "Gated values in this build" | lists no live rows | add three live rows with their evidence (§2.1) |
| MN N.2.1b(1), N.3.1 | "a real-model run of a `planned` part exits 5" (still true) | add the endpoint-class rule and the caps (§3.2) |
| PQ Q.9; README:386-388; AGENTS.md:1895 | "real-model pilots wait on keys + consent (U-10)" | local: consent; API: consent plus caps |
| O_manuscript 89, 112, 267, 1276; I.4 NC-LIVE-02 | "in v0.1 both live backends are 'fake-client tested; no real-model run'" | keep until step 2; then "pilot run, not sealed" (still no "Live Capture") |
| Tests pinning `planned`: `test_capture_mapper.py:558`, `test_autodojo_live.py:34`, the agentdyn equivalents | `live_status == "planned"` and "in development" | the new values |
| Generated README blocks (`gen_readme_corpora`, `gen_readme_sources`) | "live planned" | regenerate with `--write` (README generator rule) |

---

## 4. Build items (before the pilot; nothing here is built yet)

| Item | What | Class | Branch |
|---|---|---|---|
| B1 | `_endpoint_class()`, refusals `cli.refused.endpoint_class` (an unknown class) and `cli.refused.api_caps`, `--i-consent-to-local-run`; derive the local names from `endpoints.toml`, replacing `LOCAL_ENDPOINT_NAMES` (F7) | 0 | `live-pilot-cli` (on main after the window and L land) |
| B2 | Caps: `--max-calls`, `--max-cost-usd`, `--price-in`, `--price-out`; the worst-case pre-cell check; actual spend from `usage`; `live.caps` and `cap_reached` in the campaign record | 0 | same |
| B3 | Tests: an API endpoint without caps is refused before any `.env` read or socket; a local entry pointed at a non-loopback host is refused; caps stop before a cell whose worst case does not fit (scripted, with fake `usage`); a scripted run is unaffected; netguard holds | 0 | same |
| B4 | Status `partial` and the caveats for the three parts; stale texts (§3.4); spec D.3.2 note, D.3.3 rows, N.2.1b, Q.9; test pins | **1** | `live-pilot-core`, held, on top of `agentdyn-backend-core` |
| B5 | Record the LM Studio version in the identity record (F10a): ask the local-endpoints session (`lms version`, or the server's own field) | 0 | theirs |
| B6 | Local CI evidence for G2: `ci_local --only backend-agentdojo` (offline), plus `live-run` and `backend-autodojo` (`--allow-network`, after a yes; the uv cache may make them offline in practice), recorded in this directory | — | records only |

B1–B3 are class 0 and can land on their own. **On a `planned` part they change nothing**, because the status gate
refuses first. B4 is what opens real-model runs, so B1–B3 must be on main **before** B4 lands, never after.

**Pilot order.** The pilot runs from this worktree with B1–B4 checked out on a held branch, before B4 reaches main.
The status therefore changes only on a branch that nobody else runs. The backends' registered environments are
separate projects and are unchanged by the core branch.

---

## 5. Pilot plan

### 5.1 Prerequisites (the orchestrator signals them)

1. The env-rebuild window has landed on main, with both registered envs rebuilt and re-probed under the D-664
   profile (G5).
2. L has landed: `agentprov models`, the identity record, A12/A14, D-697.
3. `agentdyn-backend` and `agentdyn-backend-core` have landed, and `agentdyn-5353cf76` is registered.
4. B1–B4 are built and green on held branches in this worktree (one pytest at a time, `-n 2` at most).
5. LM Studio's server is running on `127.0.0.1:1234`. No model download is needed.

### 5.2 Part L: local model (LM Studio)

- **Model:** `qwen3-8b-abliterated-v2` (`mlx-community/Qwen3-8B-abliterated-v2-mxfp4`, 4.1 GB).
  - It is the smallest and fastest of the three, and it has already produced a structured tool call (F11).
  - The 14B (12 GB) is an optional second model; the 35B-A3B (23 GB on a 32 GB Mac) is not used.
- **Settings:** `--temperature 0` (A3 checks that it is transmitted), default reasoning, `--jobs 1`.
- **Corpora:** `~/.agentprov/migration-work/live-pilot/<source>-local/`, one corpus per source. Scripted and real
  sessions never share a corpus.

| Run | Cells | Detail |
|---|---|---|
| L-AD `agentdojo` | 8 | banking; `user_task_0`–`user_task_3`; benign, plus `important_instructions` × `injection_task_0` |
| L-AU `autodojo` | 2 | banking `user_task_1`; benign, plus `autodojo` × `injection_task_0`, variant 0, the fork's verified cache (`a21dcc34…`, as in phase 9) |
| L-DY `agentdyn` | 2 | `shopping` (AgentDyn's own suite) `user_task_0`; benign, plus `important_instructions` × `injection_task_0`. The names are checked against `run agentdyn --catalogue` first. If SEM fails closed on `shopping`, use `banking` and record why |

**Scope change for L-DY (orchestrator, 2026-10-22).**

- **Why.** The registered `agentdyn-5353cf76` environment is built from the main checkout by the AgentDyn live
  backend session. It is built only after `agentdyn-backend-core` (`a854a868` or later) lands, which is after the
  regeneration round (a user decision).
- **What runs now.** Part L runs L-AD and L-AU (10 cells).
- **L-DY runs post-round**, once that environment is registered. It needs its own typed yes, and it runs before B4.
- **B4 waits for L-DY**, because the three parts are promoted together (D-720).

Each run goes through the queue:
`uv run python tools/suite_queue.py --class import --cpu 2 -- uv run agentprov run <source> …`. The flags:

- `--model lmstudio --model-id qwen3-8b-abliterated-v2 --containment sandbox-exec`;
- `--env-file <scratch>/empty.env`, so the CLI reads no repo `.env` for a keyless run;
- `--i-consent-to-local-run` (given after the user's typed yes);
- `--max-attempts 2 --cell-timeout 600 --canary <cells>`. The canary covers every cell (F10b).

Steps:

- **L0** (no inference): `agentprov models --endpoint lmstudio --model-id qwen3-8b-abliterated-v2 --format json` (the
  identity record; weights hashed from the cache) and `backends build <b> --offline-check` for the three envs.
- **L1:** `--preflight-only` once per source: 3 probe calls, A3/A4/A9/A12.
- **L2:** the three campaigns.
- **L3:** the checks of §5.4 on each corpus.

### 5.3 Part A: one capped OpenRouter run

- **Model:** `openai/gpt-4o-mini` through `openrouter`.
  - It is cheap: $0.15 in, $0.60 out per million tokens; D-650 table, `as_of` 2026-10-21.
  - Its tool calling is stable.
  - It is not a local model, so this run adds an independent class.
  - Alternative: `qwen/qwen3-14b` ($0.12 / $0.24) shares the local model's family, but OpenRouter routes it across
    hosts, which adds A12 routing noise.
- **Run A-AD `agentdojo`, 4 cells:** banking `user_task_0`, `user_task_1`; benign, plus `important_instructions` ×
  `injection_task_0`.
- **Flags:**
  - `--max-attempts 1 --cell-timeout 300 --temperature 0 --containment sandbox-exec`;
  - `--max-calls 80` (4 × 16 worst case + the probe = 65);
  - `--max-cost-usd 1.00` (the user sets the value);
  - `--price-in 0.15 --price-out 0.60`;
  - `--i-consent-to-api-costs`.
- **The egress proxy** allows exactly `openrouter.ai:443`.
- **Corpus:** `~/.agentprov/migration-work/live-pilot/agentdojo-openrouter/`.

**Cost.** D-653's formula, from the shipped table, with about 4 calls per cell and about 5k input tokens per call:

| | Input | Output | Cost |
|---|---|---|---|
| p50 | ≈ 85k tokens | ≈ 2k tokens | ≈ **$0.015** |
| p90 (both × 3) | | | ≈ $0.05 |
| Worst case the caps allow | 65 billed calls at about 20k each | `max_tokens` 16k | ≤ **$0.85** |

The worst case is under the $1 cap even with no `max_tokens` transmitted. The CLI prints its own worst case before
asking.

Steps:

- **A0** (no model call): `run agentdojo --model openrouter --model-id openai/gpt-4o-mini … --dry-run`.
  - With the repo `.env` (`--env-file <main checkout>/.env`), this resolves the key variable. Exit 3 names
    `OPENROUTER_API_KEY` if it is missing; it never prints a value. This is the CLI's own presence check.
  - It also prints the plan and the worst-case spend. It works only once B4 is checked out (on a `planned` part the
    status gate exits 5 first).
  - If this session's sandbox refuses the CLI's read of `.env`, the user runs A0 to A2 in their own Terminal tab
    from the command I give, and consents interactively. I run A3 afterwards.
  - **Key source (user rule, relayed 2026-10-22): the Keychain first, then `.env`.**
    - Today both keys are only in the main checkout's `.env`, and a worktree has none. So Parts A and B pass
      `--env-file <main checkout>/.env` explicitly, as D-656's approved probe does.
    - Once the GUI's D-702 keychain-first default is on the pilot branch, they use `--keychain` instead.
    - The file is never read or printed by this session; the CLI reports key presence by name only.
- **A1:** `--preflight-only` (1 call).
- **A2:** the campaign.
- **A3:** the checks of §5.4, plus the actual spend from `usage` against the caps.

**What the user must confirm in this window first**, with the exact command lines:

- the plan;
- the cost table above;
- the cap values;
- that the OpenRouter key has its own credit limit set.

### 5.3a Part B: one capped Anthropic run (direct endpoint, D-656)

**Preconditions.**

- D-656's harness and core are on main.
- The registered `agentdojo` env is rebuilt in the window and contains `agentprov_backend/_anthropic_llm.py` and the
  guarded-list entry.
- The declared port (AnthropicPortLLM) is used.
- **The pilot's held branch also carries `anthropic-endpoint-core` (`b89f69a5`, class 1, held)**, unless it has
  landed by then. Main's capture mapper does not know the Messages sent forms, the `anthropic_messages` catalogue or
  the "empty thinking withheld" rule. Mapped with it, Part B's sessions still validate. But they show
  `agentdojo.capture_sent_form_unexplained` and `instrumentation_unrecognised`, and record empty thinking as text
  `""`, which PG5 would have to explain away. With the core branch they should map clean. Whichever way it runs, the
  D-656 session maps the sessions with its core branch afterwards, to show the difference.

**B0, the D-656 probe, which runs once and is owned by the D-656 session.** The user has already given that session
its typed yes for this exact command:

```
uv run agentprov run agentdojo --preflight-only --model anthropic --model-id claude-haiku-5-5 --max-tokens 1024 \
  --containment sandbox-exec --env-file <repo>/.env --i-consent-to-api-costs
```

- It is one canned two-tool request: under $0.001 expected, output capped at 1,024 tokens, up to 9 unbilled retries
  on 429, 5xx or connection errors.
- `run` admits it only from a checkout with B1–B4, because on main the part is `planned` (exit 5). So this session
  sends the D-656 session the held branch and commit to run it from, once Part A is done. The D-656 session runs it
  there, in its own worktree, and sends back the result and the staged session path. This session never runs that
  standalone probe.
- The command is valid under B1–B2 unchanged, because `--preflight-only` is exempt from the caps (§3.2).

**B1, the campaign (this session, after B0's result and the user's typed yes here).**

- **Run B-AD `agentdojo`, 4 cells:** banking `user_task_0`, `user_task_1`; benign, plus `important_instructions` ×
  `injection_task_0`.
- **Flags:**
  - `--model anthropic --model-id claude-haiku-5-5 --max-tokens 1024` (stated, never neither);
  - `--max-attempts 1 --cell-timeout 300 --containment sandbox-exec`;
  - `--max-calls 80 --max-cost-usd 1.00` (the user sets the value);
  - `--price-in 0.10 --price-out 0.50`, from the D-650 table, `as_of` 2026-10-21, with cache write $0.125 and cached
    $0.01; the worst case uses $0.125 for every input token;
  - `--env-file <repo>/.env --i-consent-to-api-costs`.
- **The egress proxy** allows exactly `api.anthropic.com:443`.
- **The campaign's own preflight probe** (one call, as in every real run) counts against `--max-calls`. It is not a
  second standalone probe.
- **Corpus:** `~/.agentprov/migration-work/live-pilot/agentdojo-anthropic/`.

**Cost**, by D-653's formula:

| | Estimate |
|---|---|
| p50 | ≈ 100k input and 3k output tokens ≈ **$0.012** |
| p90 | ≈ $0.04 |
| Worst case under the caps | 65 billed calls × 20k input at $0.125, plus 65 × 1,024 output at $0.50 ≈ **$0.20** |

**B2:** the checks of §5.4, plus the D-656 session's checks of the AER and the wire:

- `usage` in the Anthropic convention: `input_tokens` uncached, cache read and write separate, no total or
  reasoning tokens;
- the items `anthropic_element_port@1`, `anthropic_max_tokens@1` (explicit, 1024) and
  `temperature_not_transmitted@1`;
- `params.transmitted` with `max_tokens` 1024 and `stream` true;
- `input_at` present;
- `finish_reason` taken from `stop_reason`;
- a `text/event-stream` response blob;
- no `x-api-key` value in the wire headers.

**What the user confirms here first:**

- the plan and cost above;
- the cap values;
- that the Anthropic workspace or key has a spend limit set;
- the exact command line.

### 5.4 Evidence per pilot gate (each recorded in `docs/reports/live-pilot/README.md`)

| PG | Check | Pass criterion |
|---|---|---|
| PG1 | Environment identity | `--offline-check` exit 0 for each env; the sandbox probe `passed` under the D-664 profile digest |
| PG2 | Model identity | The identity record (`identity_sha256`) is in the plan and configuration digests. T0 re-observes it before every cell with `matches_plan: true` (no A14 drift). Served model = requested model, or recorded acceptance (A12) |
| PG3 | Containment | `producer.sandbox.kind = sandbox_exec`, `declared_by: probe`, `profile_sha256` in force. Local: no proxy, loopback port only. API: `producer.sandbox.egress` shows the single allowed pair and no refused connections, or refusals recorded |
| PG4 | Preflight | A3 parameters transmitted, A4 `structured`, A9 `accepted` |
| PG5 | Campaign | Every cell conclusive, or each failure explained by a recorded cause; no canary fired; quality report (finish reasons, retries, text tool calls 0, `param_not_transmitted` 0); `live.test_only: false`, `synthetic: false` |
| PG6 | Capture chain | T1 chain verification per session; `agentprov verify --corpus <c>.partial --level chain` passes (checksums unverified on a working tree, as expected) |
| PG7 | Live vs native | No `live_native_divergence` issue; seal accounting `consistent` |
| PG8 | Validation | `agentprov validate --corpus <c>.partial --strict --report <scratch>/validate.json`: all pass, linkage 100 %. Not `--release` (F5) |
| PG9 | Recompute | `agentprov recompute --corpus <c>.partial --dry-run`: 0 differences |
| PG10 | Secrets | The G.6.4 literal scan at T0 holds (no session kept a secret); the recorded wire headers follow the allowlist; `grep -c` of the key variable's *name* only in run logs (never the value) |
| PG11 | Negative checks (no model call) | An API endpoint without caps → exit 4 `cli.refused.api_caps`; a `local = true` entry with `--base-url http://192.0.2.1:1234/v1` → refused; both before any `.env` read or socket |
| PG12 | Caps (Part A) | Calls and spend stay under the caps; `live.caps` is recorded |
| — | Sealing | **Not possible** (F4): recorded as a gap, not as a failure |

The corpora's agent verdicts (utility, security) are recorded **as data**. They are not a result: four to eight
cells on one abliterated model measure nothing about attack success (F9).

### 5.5 Run time and load on this Mac (M2 Max, 32 GB)

| Step | Expected | Ceiling (I stop and report) |
|---|---|---|
| L0 identity and offline checks | 1 min | 5 min |
| L1 three probes (the first loads the model, about 20 s) | 1–2 min | 5 min |
| L2 12 local cells, about 3–6 calls each, reasoning on, at about 1–2 min per cell | 15–25 min | 60 min |
| L3 checks on three small corpora | 5–8 min | 20 min |
| A0–A3 4 OpenRouter cells and checks | 5–10 min | 20 min |
| B0 (D-656 session) and B1–B2: 4 Anthropic cells and checks | 5–10 min | 20 min |
| **Total** | **≈ 35–55 min** | **100 min** |

Expected API spend for the whole pilot: about $0.03, with at most about $1.05 in the worst case the caps allow.

Load:

- LM Studio uses the GPU and about 6–8 GB of unified memory (the model plus a 40k-context KV cache).
- The CLI work goes through the queue with `--cpu 2`.
- The machine stays usable but slow during L2.
- Nothing runs in parallel with a pytest.

---

## 6. Downstream effects (CLAUDE.md rule 10)

- **B1–B3 (class 0).**
  - No AER, SEM or PROV byte changes; no corpus or manuscript number changes.
  - New refusal codes (`cli.refused.api_caps`, `cli.refused.endpoint_class`) and the `live.caps` campaign member go
    in the N.1.3 list and in the GUI's error table.
- **B4 (class 1).**
  - If the D-451 import-closure digests count the registry, every corpus's `aer` stage `code_sha256` moves. Then
    `recompute` at main reports drift for corpora built before it (the F-8 ruling). The orchestrator times it with
    the round.
  - README generated blocks change, as do the `agentprov info` output, the datasheet status lines and the GUI status
    loop.
  - No stored corpus changes.
- **GUI.** Once a part is `partial`, the Run live form enables real-model runs. It must show the cap fields for an
  `api` endpoint and the local consent text otherwise; the CLI refusal covers it either way. Hand-off to the GUI
  session.
- **Inspect harness.** If its live runs go through `agentprov run`, the same endpoint-class policy covers them.

---

## 7. Decisions (D-720..D-729)

| ID | Decision | Who |
|---|---|---|
| D-720 | The three live parts move `planned` → **`partial`** together (not a new `gated` string, not `supported`), with caveats naming the admitted subset | user |
| D-721 | **Endpoint classes** `local` / `api`, computed in the CLI from `endpoints.toml` `local = true` plus the resolved loopback host, enforced for every real-model run before consent, keys or sockets. No registry field. LAN counts as `local` once the egress forward mode exists | user (local vs API rule); orchestrator (placement) |
| D-722 | **Two-step caveat**: rule 3's phrase stays at promotion and is replaced only after the user approves the pilot's results | user |
| D-723 | **Gate evidence**: the D.3.2 "CI" clause is met by local CI (D-462): `ci_local` live jobs recorded, plus the integration tests. `--allow-network` for `live-run` and `backend-autodojo` only with a yes | user (network yes); orchestrator |
| D-724 | **Unsealed pilot**: the evidence is a working corpus checked with `validate --strict`, `recompute --dry-run`, `verify --level chain` and live-vs-native. The I.5 rule 2 word "sealed" is read as "sealed when live sealing exists" and recorded as a gap. "Live Capture" stays barred (U-18). Live sealing (`run --spec`, `package` live rows) is a follow-up | user |
| D-725 | **API caps**: `--max-calls` and `--max-cost-usd` (with `--price-in` and `--price-out`) are required for `api`; T0 checks each cell's worst case before starting it; actual spend comes from `usage`; the provider-side key limit is the backstop | user |
| D-726 | **Local consent**: interactive, or `--i-consent-to-local-run` (accepted for `local` only); `--i-consent-to-api-costs` stays the API flag. Local runs take no caps beyond `--max-attempts`, `--cell-timeout` and the canary | user |
| D-727 | **Stale caveats and texts** (§3.4) are fixed in the B4 commit; README blocks regenerated | orchestrator |
| D-728 | **Pilot plan** §5 (models, cells, flags, corpora under `migration-work/live-pilot/`, never kept or deposited unless the user says so); the D-656 standalone probe runs once, by the D-656 session, from the held branch | user (typed yes three times: Part L, Part A, Part B) |
| D-729 | spare | — |

**Rejected.**

- A `gated` status string (R-15).
- `supported` with an API refusal written only in the caveat: not enforced, and best-case.
- A registry field `live_endpoints` (class-1 schema churn; it duplicates `endpoints.toml`; a CLI policy is stricter
  by default).
- A hidden pilot override of the `planned` gate (a bypass).
- Promoting on the pilot's own evidence before the scripted gates are recorded (rule 1 order).
- `validate --release` as the pilot gate (it cannot pass: F5).
- Relying on the model or the worker for the cost cap (no mid-cell stop exists in this window; the pre-cell
  worst-case check cannot overshoot).
- Reading `.env` from the session to check the key (the CLI's dry-run resolution does it without showing a value).

---

## 8. User decisions needed, in plain words

1. **Status:** promote the three live parts to `partial`, meaning "real runs allowed, only for the configurations
   the caveat names"? There is no `gated` status to use. (Recommended: yes.)
2. **Local versus API:** local model servers need your consent only. API endpoints need consent **and** a call cap
   **and** a dollar cap on every run, always. Enforced in the CLI. (Recommended: yes.)
3. **The providers' own limits:** please set a credit limit on the OpenRouter key and a spend limit on the Anthropic
   workspace or key (suggested $1 each). They are the one cap that does not depend on our code.
4. **Abliterated model:** the pilot uses `Qwen3-8B-abliterated-v2`, a model with its refusals removed. Fine for
   testing the capture path. Its attack verdicts must never be reported as results. Accept, or download the stock
   Qwen3-8B (about 4.5 GB, which needs its own yes)? (Recommended: accept for the pilot.)
5. **No sealing:** live corpora cannot be sealed yet. Is an approved, unsealed pilot enough to drop "no real-model
   run" from the caveat? Under this option, "Live Capture" in the paper still waits for live sealing. (Recommended:
   yes, with the caveat saying "not sealed".)
6. **Local CI network:** may `ci_local` run its `live-run` and `backend-autodojo` jobs with `--allow-network`? They
   rebuild backends from the uv cache and may download nothing. If not, the recorded integration tests stand in.
7. **Running the pilot** (later, after the orchestrator's signal): three typed yeses in this window.
   - Part L: 12 local cells, about 30–45 minutes, with the machine busy.
   - Part A: 4 OpenRouter cells (`openai/gpt-4o-mini`), expected about $0.015, capped at the $X and N calls you
     choose.
   - Part B: 4 Anthropic cells (`claude-haiku-5-5`, `--max-tokens 1024`), expected about $0.012, with its own caps.
     The D-656 probe before it already has your yes in that session's window.
8. **Keep any pilot corpus?** By default they stay in `~/.agentprov/migration-work/live-pilot/` and are never
   deposited.

---

## 9. Coordination

| Session | Ask |
|---|---|
| Local LLM endpoints | (a) Record the LM Studio version in the identity record (F10a). (b) Agree that `LOCAL_ENDPOINT_NAMES` is derived from `endpoints.toml` (B1). (c) Update the stale design-note header and the D.10.9 canary paragraph (A12, A14) (F10c, F10d) |
| AgentDojo backend environment build | The registered `agentdojo-79922295` is rebuilt and re-probed under the D-664 profile in the window (G5); the B6 local-CI record |
| AgentDyn live backend | The B4 commit sits on `agentdyn-backend-core`; the registered `agentdyn-5353cf76` from main; the suite and task names for L-DY |
| GUI | `partial` unlocks real-model runs in the Run live form: the cap fields for `api` endpoints, the local consent text, and the new refusal codes |
| Inspect harness | The same endpoint-class policy if its live runs go through `agentprov run` |
| Anthropic endpoint D-656 | Runs its approved `--preflight-only` probe once, from this session's held branch (B1–B4 on the window), when this session signals it after Part A. It sends the result and the staged session path. This session then runs Part B and never runs that standalone probe |
| Orchestrator | The order: window → L → AgentDyn → B1–B3 (class 0) → B4 held → pilot from the held branch (L, then A, then the D-656 probe, then B) → user approval → B4 plus the step-2 caveat land |
