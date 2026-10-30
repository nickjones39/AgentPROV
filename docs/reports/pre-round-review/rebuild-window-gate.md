# Rebuild window gate (2026-10-22)

The gate record for landing branch `rebuild-window-2026-10-22` on `main` (fast-forward from `32c89f96`).

## Contents

- **GUI G3** (the Run live form, backend picker, estimate, prices, keychain helper and CLI parity) with G4 and G5 (ad hoc
  signing, D-657).
- **D-652:** the `run --catalogue` worker op. **D-651:** `run --dry-run --plan-json`.
- **D-656, the direct Anthropic endpoint:** the harness (the declared AnthropicLLM port and max-tokens modes), the
  guarded-source lists, and the core part (Messages wire mapping, `anthropic_messages` catalogue, agentdojo-live and
  autodojo-live v2 with v1 archived byte-exact).
- **D-664:** the egress proxy and sandbox profile, the socket boundary fix and the R1-7 fix (no worker-chosen string
  recorded), plus the D-698 LAN forward mode.
- **AgentDyn:** the backend (class 0) and D-685(b) (agentdyn v2 in place, quirk-gated).
- **Inspect:** the harness (`backends/inspect`, T0) and D-710 (non-finite header tolerance, the `aer/locators.py`
  python-json profile).
- **Defences:** the `defence` catalogue home with D-670..D-679.
- **Local LLM endpoints:** D-690..D-699, and `agentprov settings` (D-703 part).
- **CI:** the lockfile lists.

## Review

[rebuild-window-review.md](rebuild-window-review.md): rounds 1, 2a, 2b and 3, and the final re-check, which was READY.
Stored-corpus bytes are unchanged. Every stage code digest moves once, before the regeneration round (class 1).

## Test gates

| Gate | Head | Result |
|---|---|---|
| Core full suite (`tools/suite_queue.py`, `-n 6`, `-k "not new_family_no_core_change"`) | `d8e1ec56` | 10,396 passed, 99 skipped, 0 failed (9 min 18 s) |
| GUI suite (offline, frozen) | `6fee4d97` | 631 passed, 2 skipped |
| `tests/repo` | `6fee4d97` | 62 passed |
| `make_capture_fixtures.py --check` (agentdojo, autodojo) | `d8e1ec56` | 0 stale |
| `tools/regen_pins.py --check` | `d8e1ec56` | every pin current |

Everything after `d8e1ec56` is docs only: the review report and this file.

## After the land

- **The registered envs** (`agentdojo-79922295`, `autodojo-aa458794`) hold the pre-window harness. They are rebuilt
  offline from the main checkout and re-probed under the new sandbox profile (`PROFILE_SHA256` `34018a40`) before any
  live run.
- **LAN hardening LF-1..LF-5** comes before the first real LAN run.
