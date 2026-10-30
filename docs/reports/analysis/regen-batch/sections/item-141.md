## Item 141 (built 2026-10-21; D-609, pre-check PC-code-agent-misalignment-01; user decision 2026-10-21; held branch `bugpass-regen-d609`)

`code-agent-misalignment-geminicli` profile version 2 adds two `[withhold]` pattern rules at object scope, reason
`personal_data`: `harness-account-path` (the harness's `diff -r` header form) and `deposit-readme-account-path` (the
README's home form). The 272 `final_diff.patch` objects and the README raw object that name a third-party workstation
account are withheld at seal, digests kept; no execution is withheld by them. Datasheet `known_issues` statement
`cam-harness-account-path-withheld`. D-31: v1 archived under `profiles/archive/` (`965b84dc288b…`; the phase-10o trial
and pre-check scratch corpora record it).

Census (exact rules; full scratch import `phase10o/trial/cam-j4`, the pinned tar's 63,384 members decoded in memory):

| objects matched | kind | count |
|---|---|---|
| `harness-account-path` | gemini_cli `final_diff.patch` (stored) | 272 (836 matches) |
| `deposit-readme-account-path` | `RESULTS_build/README.md` (stored) | 1 |
| either | any other stored object; AER, SEM, PROV, validation files | 0 |
| `harness-account-path` | codex_cli `final_diff.patch` (unselected, inside the withheld tar) | 226 |

Seal planner over `cam-j4` with v2: 275 objects withheld (272 + 1 `personal_data`, the D-336 stream `secret`, the tar
`container`); executions withheld by D-609: 0 of 2,182 (1 of 2,182 by D-336, unchanged); 0 unscanned.

| stored bytes | |
|---|---|
| AER | the header's profile version and `profile_sha256` of every geminicli AER (2,182; no committed pin to re-pin); SEM and PROV follow through `aer_digest` |
| WITHHELD.json, sidecar | a sealed corpus withholds the 273 objects (`profile_rule`, `personal_data`) besides the D-336 stream; the tar's container entry stays `secret` (BF-38: the first `REASONS` reason of everything it holds; without BF-38 the planner's reach order gave `personal_data`) |
| DATASHEET.md | one `known_issues` statement for `code-agent-misalignment` |
| stored corpora | none records the profile; the scratch corpora at v1 (`cam-j4`, pre-check `l2-results-raw-j1`/`j2`) must never be sealed |

