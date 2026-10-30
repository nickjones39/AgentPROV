# Migration gate reports (full scope)

Numbers-only records of the local full-corpus run of gates G0, A and B (docs/architecture J.2.6, J.3.0-J.3.3; K.20;
DoD Q.5). They contain counts, digests, codes and relative item labels only: no corpus content and no absolute home
paths (the home directory is written `<home>`). The baseline corpora are not in Git (D9).

| File | Gate | Verdict |
|---|---|---|
| `G0.json` | G0 baseline verification | pass (10 of 12 checks passed, 2 skipped, 0 failed) |
| `A-full.json` | A1 (JCS) and A2 (bytes), v1 -> AER -> v1 view from the AER alone | pass, 35,691 of 35,691 |
| `B-full.json` | B1 (compat graph from the view) and B2 (compat graph from the source) | pass, 35,691 of 35,691 |

Regenerate with (from the repository root, `AGENTPROV_BASELINE_CORPUS` naming the old repository):

```
uv run agentprov migrate gate G0 --scope full --workers 10 --report docs/reports/migration/G0.json
uv run agentprov migrate gate A  --scope full --workers 10 --report docs/reports/migration/A-full.json
uv run agentprov migrate gate B  --scope full --workers 10 --report docs/reports/migration/B-full.json
```

## Run

| | |
|---|---|
| Date (UTC) | 2026-10-07 |
| AgentPROV commit | `8160a633db2a75884caaaea73ff1dba2887f7e03`, **working tree dirty** (the gate runner and the `migrate` command were uncommitted) |
| Baseline lock sha256 | `f1d7993b39296466d73d1fddf4ad8c4d72d4b57e58a1a02571e72c3bb87092b9` |
| Interpreter | CPython 3.14.8 (at the J.0 floor, no `interpreter_advisory`); baseline interpreter not used (G0, A and B do not execute the old package) |
| Platform | macOS 27.0.1 arm64, 12 cores |
| Libraries | prov 3.2.2, rdflib 7.6.0, pyshacl 0.40.1, rfc8785 0.1.4, pyyaml 6.0.3 |
| Mode | **dev** (`params.strict: false`), 10 workers; mapping in T1 workers, sealing and comparison in the parent |
| Runtime | G0 6.7 s, A 736 s, B 759 s |

These are **not** release-mode reports. K.20 requires reports produced with `--release` for the release commit.
Release-mode G0 currently fails on exactly two checks, `environment.requirements_lock` and `environment.baseline_wheel`:
the lock does not record those two J.1.6 hashes yet (the hash-locked requirements export and the baseline wheel are built
with the differential gates), and an unrecorded hash is a skip in dev mode and a failure in release mode. Release-mode A
and B pass on the golden set; they cannot start at full scope until a release-mode G0 report exists (J.3.0 order).
The reports must also be regenerated on the clean release commit.

## Counts

| Tree | Transcripts | A1 | A2 | B1 | B2 |
|---|---|---|---|---|---|
| release (`corpus-prov`) | 17,664 | 17,664 | 17,664 | 17,664 | 17,664 |
| converted (`corpus-og-agentdojo-runs-prov`) | 18,027 | 18,027 | 18,027 | 18,027 | 18,027 |
| total | 35,691 | 35,691 | 35,691 | 35,691 | 35,691 |

Inputs match the lock pins (J.1.4): every transcript and graph listing digest equals the lock's, and every transcript
pairs with exactly one graph. Every produced AER passes the release-mode AER validator with locators resolved against the
digest-checked artefact and none is degenerate. The AER digest listing is identical in the A and B reports (two
independent full runs): release `fcd04818...`, converted `d9b28c5e...`.

Not part of these reports: the J.3.3 acceptance items that run the ported `validate_prov_document` and the five
conformance checks on all graphs (gate B here is the byte comparison B1/B2), and gates D and E.

## Seal accounting verdicts (per trace; `details.accounting` in `A-full.json` and `B-full.json`)

| Tree | consistent | inconsistent | unverifiable |
|---|---|---|---|
| release | 14,688 | 32 | 2,944 |
| converted | 25 | 0 | 18,002 |

* `unverifiable:aer.acc.agent_calls_vs_assistant@1:model_calls_derived_from_messages` (release 2,944; converted
  18,002): the v1 transcript records no model-call events, so the mapper derives the calls from the assistant messages
  and the check cannot be verified (C.12.2). A property of the source form, not a defect.
* `inconsistent:aer.acc.reported_counts@1:reported_calls_differ` (release 32; qwen_qwen-2.5-72b-instruct 20,
  google_gemini-2.5-flash 12): the usage-reported call count exceeds the assistant messages in the transcript.
  Their paths are in `details.accounting.inconsistent_listed`.
* The core accounting fix (an `unk /finish_reason` counts as a finish-reason entry, C.19(15)) removes the
  `finish_reasons_differ` verdict: 158 released traces were `inconsistent` under the previous rule and are
  `consistent` now; no trace carries `finish_reasons_differ` in these reports.
