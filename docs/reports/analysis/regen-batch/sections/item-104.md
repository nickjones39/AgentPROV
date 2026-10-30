## Item 104 (built 2026-10-21; D-456, pre-check PC-05; user decision 2026-10-15; held branch `bugpass-regen-d456`)

`interbolt-agentdojo` profile version 2 adds `[withhold]` (reason `personal_data`, pattern rule `macos-account-path` at
object scope): the run manifests that hold a third-party workstation account path are withheld at seal, digests kept.
D-31: v1 archived under `profiles/archive/` (pre-check scratch corpora record it; owner's ruling 2026-10-15).

| stored bytes | |
|---|---|
| AER | the header's profile version and `profile_sha256` of every interbolt AER (7 phase-10d fixture pins re-pinned); SEM and PROV follow through `aer_digest` |
| WITHHELD.json, sidecar | a sealed interbolt corpus withholds the 24 manifests (object level) |
| stored corpora | none records the profile; the two pre-check scratch corpora (v1) must never be sealed |

**What the rule takes (checked 2026-10-21 on the pinned snapshot `43e2b5fa`, every one of its 2,254 blobs, a superset of
the stored objects; labels counted, no content read out; D-31 owner's request).** 25 blobs match
`/Users/[A-Za-z0-9._\-]{1,64}/`: the 24 `run_manifest.json` (stored as context artefacts) and `analysis_out/artifact_manifest.md`
(not stored: not in `context_artefacts`). **0 of the 2,016 primary logs** match, so no execution is withheld, and the
snapshot holds no archive (nothing for the decoded scan). A later profile that stored more files would have them checked
the same way.

