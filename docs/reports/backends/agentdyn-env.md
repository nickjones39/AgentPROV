# The registered AgentDyn backend environment `agentdyn-5353cf76`

This file records how the AgentDyn backend environment (D.11.10, D-680..D-688) was built under `~/.agentprov/envs/`
and how it was checked. It was built after the class-1 train that brought the `agentdyn · live` part, the
`agentdyn-live` profile and `BACKENDS["agentdyn"]` reached main (`d7e6e0ee`, 2026-10-23).

No network was used and no real model was called. The build ran `uv --offline` from the uv cache, which already held
AgentDyn's pinned checkout (fetched once with the user's approval on 2026-10-22; see
[`../agentdyn-backend/README.md`](../agentdyn-backend/README.md) section 2). The build ran from the main checkout,
because PEP 610 `direct_url.json` records the `backends/shared` source path (the same rule as
[`agentdojo-env.md`](agentdojo-env.md)), and it went through `tools/suite_queue.py --class import --cpu 2`.

**Verdict: pass.** The build completed offline. `--offline-check` passes, hello reports AgentDyn's identity, and the
sandbox probe passes under the current profile.

## Environment

| | |
|---|---|
| Environment id | `agentdyn-5353cf76` (`commit8_source: fork_commit`) |
| Built from | main `d7e6e0ee`, `agentprov backends build agentdyn` (no `--allow-network`) |
| Built at | `2026-10-22T20:40:35Z` (UTC; 2026-10-23 local) |
| Source | `https://github.com/SaFo-Lab/AgentDyn` @ `5353cf7615b135cace8d07c8f12dac53a16b6db3` (PEP 610, verified) |
| Lock | `backends/agentdyn/uv.lock`, sha256 `7ef22ee1c690bc25…b575` |
| Python | 3.12.14 |
| `agentdojo` distribution | reports `0.1.35`, benchmark `v1.2.2`; RECORD sha256 `793b6813…a4f4`, 1,431 files |
| Files verified | 1,485 (build and `--offline-check`) |
| Size | 137 MB |
| Default system prompt | sha256 `21a1c00d…3e36` (AgentDyn's own, design F-1) |
| Tool definitions | sha256 `b89e8a7e…e0ee` |
| Guarded sources | 24 (the stock list plus `AGENTDYN_GUARDED_NAMES`: `_supports_temperature`, `AgentPipeline.from_config`, `load_system_message`) |

## Checks

1. **Dry run.** `--dry-run` printed `uv sync --locked --no-config --no-dev --link-mode copy --offline --exclude-newer
   2026-10-07T00:00:00Z`, the 74 `--no-build-package` names, and both `--reinstall-package agentprov-capture` and
   `--reinstall-package agentprov-backend`. Network: none.
2. **Build.** Exit 0; no download was attempted.
3. **T0 identity.** The marker's `t0_identity` records the `agentdojo` distribution from the AgentDyn commit (RECORD
   digest above).
4. **Hello.** `hello_identity` names the AgentDyn repository and commit, the seven suites (`workspace`, `travel`,
   `banking`, `slack`, `shopping`, `github`, `dailylife`) and AgentDyn's system prompt digest. `hello_worker` reports
   backend `agentdyn`.
5. **Sandbox probe.** `passed` under profile `sha256:34018a40…eaef`, which is the current `PROFILE_SHA256` at
   `d7e6e0ee`. Egress is allowed, loopback v6 is allowed, other loopback is denied, remote connect is denied, and reads
   of credentials, `.env` and the repository are denied. Writes are allowed only to the staging folder and to T2's home
   folder.
6. **`--offline-check`.** Passes (marker, lock, RECORD, guarded files, hello identity).
7. **Catalogue.** `agentprov run agentdyn --catalogue` returns `agentprov-backend-catalogue/0.1` for backend `agentdyn`.
   It lists 7 suites with 157 user tasks and 63 injection tasks (workspace 40/14, travel 20/7, banking 16/9, slack
   21/5, shopping 20/9, github 20/9, dailylife 20/10) and 17 attacks.

## What this enables

The live gates pilot's L-DY step (scripted, then gated real-model cells under the pilot's approval) can now use
`agentdyn-5353cf76`. The part stays `planned` until promotion (D-684).
