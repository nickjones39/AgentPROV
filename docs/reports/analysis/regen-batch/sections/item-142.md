## Item 142 (built 2026-10-21; D-603, pre-check PC-01; user decision 2026-10-21; held branch `bugpass-regen-d603`)

`autogen-guard-placement` profile version 2 adds `[withhold]` (reason `secret`, pattern rule `langfuse-secret-key` at
object scope): the deposit zip, whose unselected member `results/phase7/capture.json` holds a real-format service secret
key, is withheld at seal by the decoded scan (D-450), digest kept; no execution is withheld. D-31: v1 archived under
`profiles/archive/` (`1a7573f4e88a…`; phase-10n and pre-check scratch corpora record it).

Census (exact rule; real pinned zip read in memory; pre-check corpus `l2-v1.0-j2`): 1 of 109 members (not selected,
deflated); 0 of 14 primary run files; 0 of 29 stored context objects; 0 of 1,080 AER/SEM/PROV each; product backstop
(`withhold.rescan`): 1 hit (the zip object), 0 unscanned. 0 of 1,080 executions withheld.

| stored bytes | |
|---|---|
| AER | the header's profile version and `profile_sha256` of every autogen AER (1,080; no committed pin to re-pin); SEM and PROV follow through `aer_digest` |
| WITHHELD.json, sidecar | a sealed autogen corpus withholds the deposit zip (object level, `profile_rule`, decoded detector) |
| stored corpora | none records the profile; the scratch corpora (v1: `autogen-d321-j8`, pre-check `l2-v1.0-j1`/`j2`; older partials `autogen-j3`/`autogen-j8` at `56b86c1131fd…`) must never be sealed |

