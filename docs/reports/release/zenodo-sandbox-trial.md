# Zenodo sandbox trial of `tools/zenodo_draft.py` (D-790, D-800)

Date: 2026-10-23. Tool at commit `91a816c3` of branch `zenodo-sandbox-trial` (main `af344d97` plus the licence-id fix).
Target: `sandbox.zenodo.org` only. The user ran every command that talked to Zenodo, in their own terminal, with a
sandbox token of scope `deposit:write` that no session saw. Nothing was published; the user discards the trial draft in
the web UI. No deposition id, account name, e-mail or token appears in this report: "the trial draft" is the draft.

## What was sent

A synthetic deposit: three licence-cleared AgentDojo benchmark logs (MIT) sealed as `sandbox-trial` 0.1.0, 10 files,
175,225 bytes, release scan 0 findings. The archives hold one fictional benchmark e-mail address (an AgentDojo persona,
the attacker recipient of its workspace `InjectionTask0`), approved by the user. The release scan has no e-mail detector, so
it reported nothing there: **a gap in `tools/release_scan.py`, routed.**

## Run (`./trial.sh run`)

| Step | Result |
|---|---|
| Create (`--create-draft`, phrase typed by the user) | exit 0; all 10 files uploaded; each returned md5 and size equalled the manifest's |
| Resume test (`--resume`, phrase typed by the user, after the user deleted one file, `CHANGELOG.md`, from the draft in the web UI) | exit 0; the tool uploaded exactly that one file (`[1/10] uploading CHANGELOG.md`) and reported the other nine as "already in the draft with the same md5"; the final state is correct (below) |
| Second create | refused before any prompt, exit 4, "a receipt exists ... No second deposition is created" |
| Read-only check (`trial_check.py`, two GETs) | state `unsubmitted`, `submitted: false`, 10 of 10 files present, 0 md5 mismatches against `DEPOSIT-MANIFEST.json` and the local files |

The receipt (`<deposit dir>.zenodo-sandbox-draft-receipt.json`, beside the directory) holds the target, host, status
`complete`, `metadata_set: true`, and for each of the 10 files its bytes, sha256 and md5 (all equal to the manifest) and
`uploaded: true`. It contains no token and no `Authorization` text.

## Items relied on from memory, and their verdicts

| Item | Verdict |
|---|---|
| `state` and `submitted` of a draft | **Confirmed, with a correction to the documentation.** `state` is `unsubmitted` (the documentation says `inprogress`), `submitted` is `false`. The tool tests `submitted is False` and `state != "done"`, which holds. |
| Metadata accepted | **Confirmed**: `publication_date`, `version`, `upload_type: dataset`, `access_right: open`, keywords, creators with no affiliation, an HTML description, and three related identifiers (`isDerivedFrom` on a DOI and on a URL, `references` on an arXiv id) were accepted and stored as sent. Zenodo adds `imprint_publisher`. An empty `related_identifiers` list and the relation `isOriginalFormof` were **not tested**. |
| Licence id | **`mit` accepted; it reads back as `mit-license`** (Zenodo's own id). The other ids were checked only against the sandbox's public licence vocabulary (444 entries; `cc-zero` is absent there, `cc0-1.0` present) and were **not sent to the deposit API**. |
| Stored description HTML | Stored exactly as sent: `<p>` paragraphs, no `&#x27;` (the apostrophe fix of `91a816c3` worked). A leading "- " in one paragraph comes from the deposit builder's text and is **routed**. **How it renders: not checked visually.** |
| Bucket `PUT` answer | **Confirmed**: `checksum` (`md5:<hex>`) and `size` came back for every file and equalled the manifest's. |
| Draft file listing | **Confirmed**: entries have `filename`, `filesize`, `checksum` (the md5 without a prefix in the listing), `id`, `links`. |
| `links.bucket` on the target host | **Confirmed** (every upload used it). |
| Draft DOI | A DOI is **reserved, not registered** (`prereserve_doi` with `doi` and `recid`; no `doi` field). The reserved DOI's prefix was `10.5281`, not the `10.5072` of the documentation. |
| `conceptrecid` / `conceptdoi` on a draft | `conceptrecid` is present, **`conceptdoi` is absent**. `conceptdoi` on a published record: **not tested** (cannot be without publishing). |
| Resume uploads only the missing file | **Confirmed live**: the draft listing showed nine files with their md5, the deleted one was absent and was uploaded alone. |
| Overwriting an existing file by bucket `PUT`; a duplicate key | **Not tested live** (the resumed file was absent, so nothing was overwritten; covered by the fake-server tests). |
| Error body shape | **Not tested** (no error occurred). |
| `MAX_FILES` 100, `MAX_FILE_BYTES` and `MAX_TOTAL_BYTES` 50 x 10^9 | **Not tested** (10 files, 175 KB). They remain the documented values, named constants. |
| New version, inherited files, interrupted create | **Not tested live.** A new version needs a published record. The create was not interrupted: the tool has no safe pause point between two files (it starts the next upload at once), so the live resume test used a file deleted in the web UI instead (it worked, above); the interruption is covered by the fake-server tests. |

The deposition's other field names (for the record): `conceptrecid, created, files, id, links, metadata, modified,
owner, record_id, state, submitted, title`; its links include `publish`, `edit`, `discard` and `newversion`, none of
which the tool can call (its request allowlist has no such entry).

## Fixes

- Before the run (`91a816c3`): `LICENCE_IDS` follows the sandbox vocabulary (`cc0-1.0` replaces `cc-zero`; `agpl-3.0-only`,
  `gpl-3.0-only`, `gpl-3.0-or-later` added; `GPL-3.0` maps to `gpl-3.0-only`); the description no longer entity-escapes
  quotes.
- After the run: no behaviour of the tool was wrong. The fake server now answers like the sandbox did (a draft without
  `conceptdoi`, a reserved DOI, `mit` read back as `mit-license`), with a test that none of this is treated as an error;
  the `LICENCE_IDS` comment records the live result; the user guide's checklist says what to expect (no registered DOI, the
  licence's stored id, the reserved DOI's prefix) and what the trial did not settle.

## Routed (owner blank)

- `tools/release_scan.py` has no e-mail detector; an AgentDojo persona address in a log went unreported.
- The deposit builder's description text starts a paragraph with "- " (a list bullet inside `<p>`).
- The REST documentation is out of date on the draft `state` value and the sandbox DOI prefix.

## Trialled 2026-10-29: communities, reserved DOIs, cross-links and the index umbrella (D-870, D-947, D-949)

The user ran `tools/zenodo_collection_trial.sh` to the end in their own terminal (sandbox only, a sandbox token no
session saw, every phrase typed by the user), from a clean checkout at `94756891`, on a kit built offline by a session:
two synthetic sealed demo corpora of three AgentDojo `c274885` logs each, one MIT and one with the trial-only
`[licence] derived = "GPL-3.0-only"`, their part deposits (10 files each) and an index `release.toml`; a sandbox test
community the user created. Steps 1–8 ended without an error: three unpublished drafts (the index and the two parts),
then the step-9 checklist in the web UI, which the user reports all fine. Nothing was published; the user deletes the
drafts in the web UI. The three receipts (format `agentprov-zenodo-draft-receipt/0.2`) are `complete`, every file
`uploaded: true`, `metadata_set: true`, and their cross-link status `linked`. As before, no deposition id, DOI, account
name or token is recorded here.

| Request or reading (assumed from the REST documentation, 2026-10-28) | Result |
|---|---|
| `communities: [{"identifier": SLUG}]` in the metadata `PUT` (`--community`) | **Confirmed**: accepted on each draft; each draft's page names the community |
| `metadata.prereserve_doi.doi` / `.recid` in the create answer | **Confirmed**: each draft has a reserved (not registered) DOI, prefix `10.5281` as in the 2026-10-23 trial, equal to its receipt's `reserved_doi` |
| `prereserve_doi: true` on a draft that has no DOI | **Not exercised**: every new draft came with a reserved DOI |
| a metadata `PUT` without `prereserve_doi` (cross-link) | **Confirmed**: the DOIs were unchanged after both cross-link runs (the tool would have stopped otherwise) |
| `isPartOf` / `hasPart` to reserved, unregistered DOIs | **Confirmed**: the index shows "has part" to each part's reserved DOI, each part "is part of" the index's; the read-back passed |
| the second cross-link run | **Confirmed**: it changed nothing and added no duplicate link (exit 0) |
| the membership check (a cross-link without the first part) | **Confirmed**: refused before any phrase, exit 4, as designed |
| licence id `gpl-3.0-only` | **Accepted live** (until now only `mit` had been sent); `cc-by-4.0` was accepted for the index |
| the index-only umbrella (`package --index`, D-947) | **Confirmed**: the index draft holds `README.md`, `COLLECTION-INDEX.json`, `deposit-metadata.json`, `DEPOSIT-MANIFEST.json` and one datasheet, no archive; licence CC BY 4.0 |
| copyleft datasheets linked, not copied (D-949) | **Confirmed**: no GPL datasheet in the index; its `COLLECTION-INDEX.json` row names the datasheet in the part record (location `part`, with its digests) |
| `MAX_FILES` 100 and `MAX_TOTAL_BYTES` 50 × 10^9 (L-8) | **Still not tested**: the parts were tiny (10 files, about 160 KB each). They remain the documented values |

## Not yet trialled: the keychain token and the desktop app (D-880, 2026-10-28)

The uploader is now the `agentprov-zenodo` distribution (`python -I -m agentprov_zenodo`; `tools/zenodo_draft.py` is its
checkout entry). Also untested against the sandbox:
- `--keychain`: the token read from the OS keychain through the core's helper. The tests use a stub.
- The desktop app's *Create Zenodo drafts…*, which runs the same uploader under a pseudo-terminal. Its tests use a fake
  uploader.

A sandbox run of the app would check that the terminal pane shows each screen, that the typed phrase is accepted, and
that the drafts, community and links match the CLI trial above.
