# 5. Package and deposit

`agentprov package` has two modes:

- **seal mode** turns a working corpus (`DIR.partial`) into a sealed corpus version (`DIR`) and prints its root digest;
- **deposit mode** (`--deposit OUT`) builds a deposit draft (deterministic archives plus metadata) from one or more
  sealed corpora.

**`package` never uploads.** It works offline and starts no upload. A deposit draft is a directory on your disk;
publishing it (for example on Zenodo, which mints the DOI) is a separate, manual step that only the project owner
takes. An optional helper script can create an *unpublished* Zenodo draft from the directory
([below](#creating-an-unpublished-zenodo-draft)); it never publishes. AgentPROV corpora get their own Zenodo record and
concept DOI, never a new version of AgentDojo-PROV's.

## Before you seal

Sealing is release mode. It refuses unless:

1. **The corpus was imported or derived without problems that block release**: no `incomplete` snapshot, no
   `--skip-prov-conformance` mark, and an interpreter without an advisory (3.14.8 or later).
2. **You have a corpus spec.** The spec is a directory `corpora/<corpus-id>/` holding `corpus-spec.toml` (identity,
   sources and pinned snapshots, derivation settings, licence), `CARD.md` (the hand-written parts of the datasheet)
   and `CHANGES.toml` (the changelog; every corpus version needs an entry). The shared decided statements file
   `corpora/datasheet-statements.toml` must sit beside it, one level up. The repository's `corpora/` directory holds
   the specs of the declared corpora; `--spec PATH` names another one.

   A spec can also name the corpus's **persona files** (`[scan] personas`, each with its `path` and `sha256`): the
   reviewed lists of e-mail addresses, as digests only, that the release scan clears and the seal withholds
   ([below](#the-release-scan-comes-first)). Sealing copies each into `rules/personas/`, so it is covered by the root
   digest. It refuses a file that is missing, does not match the spec's digest or does not parse, and an observed list
   that names another corpus (`package.refused.persona`). The committed files are in `corpora/personas/`.
3. **The checkout is clean.** `package` records the producer's git commit, and refuses when the tree has uncommitted
   changes:

   ```text
   agentprov: error [package.refused.git]: package runs in release mode: the producer commit must be known and its tree clean (H.2.7)
   ```

   The same holds for the checkout that *built* the corpus: a corpus whose manifest records a build step from a dirty
   tree is refused (`package.refused.build_dirty`), because its recorded commit would not describe the code that ran.
   Rebuild it from a clean checkout. A build from an installed wheel (no git checkout) is not refused; the datasheet
   shows why no commit is recorded, and a corpus built before commits were recorded seals with "building commit not
   recorded".

4. **Upstream licence files are available.** A licence file the spec names (`[licence] files`) is taken from the
   corpus's raw store when the import stored it at the pinned path; otherwise give it with `--licence-file NAME=PATH`.
   `NOTICE.md` records which files were supplied at sealing.

For the demo, a spec `specs/demo-agentdojo/` was written beside a copy of `corpora/datasheet-statements.toml` (in
`specs/`), naming the pinned snapshot, `agentdojo-upstream@2`, `agentdojo.suites@2` and one licence file. The licence
text supplied below is a placeholder for the demo; a real corpus carries AgentDojo's `LICENSE` from the pinned commit.

## Worked example: sealing the demo corpus

A dry run computes and checks everything and writes nothing:

```text
$ agentprov package --corpus corpora/demo --corpus-version 0.1.0 --spec specs/demo-agentdojo/corpus-spec.toml --licence-file LICENSE=LICENSE.demo --release-date 2026-10-22 --dry-run
agentprov package: units=3 plan=seal
package: finished in 242ms (exit 0)
  units    3 of 3: ok 3
dry run: demo-agentdojo 0.1.0 would seal with content digest sha256:e8d2ac2efb731e94f10bdfad0847985e0020032ed6ef77c523905a4ec130c9f6
```

Then seal:

```text
$ agentprov package --corpus corpora/demo --corpus-version 0.1.0 --spec specs/demo-agentdojo/corpus-spec.toml --licence-file LICENSE=LICENSE.demo --release-date 2026-10-22
agentprov package: units=7 plan=seal
package: finished in 334ms (exit 0)
  units    7 of 7: ok 7
sealed demo-agentdojo 0.1.0: 3 executions, 40 files
content digest sha256:e8d2ac2efb731e94f10bdfad0847985e0020032ed6ef77c523905a4ec130c9f6
root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
```

`corpora/demo.partial/` is now `corpora/demo/`, with `checksums.sha256`, the full `corpus.json`, `DATASHEET.md`,
`CHANGELOG.md`, `LICENSES/`, and record copies of the rule catalogues, profiles and spec in `rules/` and the schemas
in `schemas/`. The copies are a record only: `verify` and `recompute` load catalogues from the installed package.

Sealing is deterministic: two seals of the same working tree with the same inputs give the same digests.
`--release-date` fixes the release date (otherwise `SOURCE_DATE_EPOCH`, otherwise none).

### The two digests

- The **content digest** covers the corpus's contents.
- The **root digest** is the sha256 of `checksums.sha256`, which lists every file. It identifies this exact sealed
  tree. Publish it outside the corpus (the paper, the release notes, the annotation of the tag
  `corpus/<corpus_id>/v<version>`), so that anyone can check a copy with `agentprov verify --release --root-digest`
  ([chapter 4](04-derive-recompute-validate-verify.md#verify)).

### The datasheet

`DATASHEET.md` is generated at sealing. Every number in it is computed from the manifest, the index and the register,
or comes from a decided statement with its source. Its sections are:

| Section | Holds |
|---|---|
| Motivation, Maintenance | from `CARD.md` |
| Composition | counts by unit, status and completeness; each snapshot's pinned origin and raw policy; requested and served models with their evidence class |
| Uses | the decided statements that apply |
| Evidence and information loss | field-group coverage: for each group of fields, the share of executions whose fields are observed or derived; records by kind |
| Integrity and verification | digests, versions, the sealing commit and the building commits (or "building commit not recorded"), and how to verify |
| Known issues and validity caveats | issue codes and artefacts with counts |
| Distribution and licensing | licence class, licence files, withholding |
| Untrusted content | the prompt-injection notice |

`CARD.md` can use placeholders that sealing fills: `{{v:/counts/executions}}` (a value from the manifest) and
`{{claim:raw_included}}` (a statement from the claims library, checked against the corpus). `agentprov validate --card
CARD.md` lints a card before you seal.

### Withholding at sealing

A working corpus seals as a corpus version that withholds, rather than refusing, when it has purge tombstones, a
snapshot with raw policy `withhold`, or a source-profile `[withhold]` policy. The affected raw objects, and the
executions derived from them (unless the rule's scope is `object`), are moved into the private sidecar
`DIR.withheld/`, never deleted. `WITHHELD.json` in the sealed tree lists each withheld object's digest and pinned
origins and each withheld execution's id, and nothing else; the datasheet states the counts and the reasons.
`verify --level chain` in release mode accepts a tombstone only when `WITHHELD.json` lists it.

**E-mail addresses** are withheld the same way, by digest. A persona-file group of class `withhold` lists the addresses
that only a model wrote, at a public mail provider (they could be a real person's): sealing withholds every execution
that holds one, with reason `personal_data`. A group of class `withhold-object` lists addresses found only in raw files
that no execution uses: those objects are withheld, and no execution is affected. The rule matches digests, never a
literal address. A ledger that holds such an address rule is written as `agentprov-withheld/0.4` (other ledgers keep
their earlier versions, so their bytes do not change), and `verify --level chain` and the deposit builder apply the
rule again to check that nothing it matches was left in the sealed tree.

## Deposit drafts

### The release scan comes first

The deposit builder refuses a corpus without a **release scan** for the same root digest:

```text
$ agentprov package --deposit deposit --corpus corpora/demo --metadata release.toml --release-date 2026-10-22 --dry-run
agentprov: error [release.refused.scan_missing]: demo-agentdojo: no release scan for this corpus; run tools/release_scan.py on the sealed corpus and triage every finding (G.9.4)
```

The scan runs outside the CLI, because the builder starts no process. It needs gitleaks 8.30.1 (the pinned version;
any other is refused):

```text
$ uv run python tools/release_scan.py corpora/demo
release_scan: 0 finding(s) {}; root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3; written to …/corpora/demo.release-scan.json
```

Archives among the raw objects (zip, tar and the other stored containers) are read decoded, member by member, without
extracting anything, and so is every archive the sealing scan checks for withholding. Several archives are read at once,
up to the host's default worker count (D-890); one archive's members are still read in order, so the findings are the
same at any count.

It searches every file, raw objects included, for secrets (gitleaks plus AgentPROV's own token shapes), your home
path and host name, third-party workstation account paths and e-mail addresses (the `email-address` rule; a finding
never holds the address). Addresses at RFC-reserved domains (`example.com`, `.test`, ...) are cleared by the tool. The
others are cleared only by the *persona files* that the corpus's spec names (`[scan] personas`; digests only, sealed
with the corpus and bound to its root digest), whose groups say where each address first appears:

| Class | The address is | Outcome |
|---|---|---|
| `upstream-data` | in the benchmark's own published files at its pinned commit (its run outputs excluded) | cleared, `synthetic-benchmark` |
| `benchmark-input` | first in input the benchmark supplied to an execution (a task, a tool result, an injection) | cleared, `synthetic-benchmark` |
| `model-generated` | only in model output, at a domain that is not a public mail provider | kept, triaged `model-generated` and disclosed in the datasheet |
| `withhold` | only in model output, at a public mail provider | its executions are withheld at sealing ([above](#withholding-at-sealing)) |
| `withhold-object` | only in raw files that no execution uses | those raw objects are withheld at sealing |
| `file-name` | not an address but a file name of that shape (an image's `@2x` suffix) | cleared, `false-positive`, for that corpus only |

Every other address is a finding. [Chapter 9](09-safety.md#before-you-share-a-corpus) shows how to review them by
address and how `tools/scan_personas.py` and `tools/scan_origins.py` write the lists. Every finding must be triaged in a triage file
(`--triage TRIAGE.toml`) as `real`, `synthetic-benchmark`, `false-positive` or `pinned-account`; a `real` finding must
be withheld before the corpus can be deposited. See [chapter 9](09-safety.md#before-you-share-a-corpus).

### Building the draft

The deposit metadata is a small TOML file:

```toml
title = "AgentPROV user-guide demo deposit"
description_preamble = "A deposit draft built for the user guide; never uploaded."
keywords = ["demo"]

[[creators]]
name = "Example Creator"
```

```text
$ agentprov package --deposit deposit --corpus corpora/demo --metadata release.toml --release-date 2026-10-22
agentprov: finished in 219ms (exit 0)
deposit draft: wrote 5 archive(s) for 1 corpus version(s) to deposit
demo-agentdojo 0.1.0: root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3; licence class MIT
Nothing has been uploaded or published.
```

The draft directory holds:

| File | What it is |
|---|---|
| `<corpus>-v<version>.meta.zip` | the corpus's manifest, index, register, checksums, datasheet, licences and record copies |
| `<corpus>-v<version>.raw.001.zip`, `.aer.001.zip`, `.sem-<profile>.001.zip`, `.prov-<spec>.001.zip` | the data, split by layer (and on shard boundaries above `--max-archive-bytes`) |
| `DEPOSIT-MANIFEST.json` | every archive with its size and digests |
| `deposit-metadata.json` | the record metadata to enter on the repository's page |
| `README.md`, `DATASHEET-<corpus>.md`, `CHANGELOG.md` | the human-readable description |

Archives are deterministic: members are sorted, carry the release date as their timestamp and fixed permissions, and
use DEFLATE at a fixed level, so the same corpora and metadata give the same bytes.

**Licence classes.** A deposit refuses corpora of different licence classes (exit 4) unless you give
`--allow-mixed-licence-classes`, which is recorded; non-commercial data is never mixed in. Each copyleft source has its
own corpus.

### Verifying a deposit

`verify` reads deposit archives without extracting them. Verify the whole draft directory, with the root digest:

```text
$ agentprov verify --corpus deposit --release --root-digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
agentprov verify: units=1 mode=archive plan=level chain
…
agentprov verify: level chain (release mode): passed; 0 failed, 0 unverified or tombstoned
demo-agentdojo-v0.1.0: root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
```

A `.meta.zip` on its own can be verified too, but it does not contain the data archives, so their members are
reported `archive.not_present`. Without `--release` that is a pass with unverified checks; with `--release` an
unverified check fails (exit 1).

## Creating an unpublished Zenodo draft

The draft-only uploader can turn a verified deposit directory into an **unpublished draft** on Zenodo. It is not an
`agentprov` subcommand but its own distribution, `agentprov-zenodo` (D-880), so the `agentprov` package itself never
talks to the network for a release. In a checkout it is already installed (chapter 1, the `zenodo` extra) and runs as
`tools/zenodo_draft.py`, as below; `python -I -m agentprov_zenodo` and `agentprov-zenodo-draft` are the same program
with the same options. The desktop app runs it too (Package › 9 Finish › Create Zenodo drafts…, below). It never
publishes, edits a published record or deletes anything: you review the draft in the web UI and press Publish yourself.
Run it in your own terminal; the steps below use placeholders, not real output.

1. **Make a token** on the site you target. The sandbox (`sandbox.zenodo.org`) and production (`zenodo.org`) need
   separate accounts and tokens. The scope `deposit:write` is enough for a new draft; `--new-version-of` also needs
   `deposit:actions` (Zenodo's documentation lists it for new versions, and it also covers publishing, which this script
   never does), so give a sandbox token only the scopes you need. Put the token in your shell's environment
   yourself: `ZENODO_SANDBOX_TOKEN` for the sandbox, `ZENODO_TOKEN` for production. Or store it once in the OS keychain
   under the same name and add `--keychain` to each command ([below](#the-token-in-the-keychain-and-the-desktop-app)).
   The script never asks for it, and prints, logs and records neither it nor the `Authorization` header.
2. **Check offline first.** `--check` needs no token and sends nothing; it verifies the directory and shows exactly
   what would be sent:

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --check
   ```

   The offline checks refuse a directory that holds a file the deposit manifest does not list, or lacks one it lists, or
   whose size, sha256 or md5 differs, or that does not pass archive-mode `verify` in release mode. Pass the root digest
   you published outside the deposit with `--root-digest sha256:<hex>` (one per corpus). A deposit of more than one
   licence class, or with a licence the script cannot map to a Zenodo licence id, is refused.
3. **Try the sandbox first.** Zenodo's sandbox can be cleaned at any time (its documentation says test DOIs use the prefix `10.5072`; the trial of
   2026-10-23 saw a reserved DOI with the prefix `10.5281`, so judge a record by its host, not by its DOI prefix):

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --create-draft --root-digest sha256:<hex>
   ```

   `--target` has no default. The script shows the host, every file with its size and sha256, the title, version,
   licence and creators, and "this creates an unpublished draft; nothing is published". It needs a terminal and
   asks you to type a phrase that names the host; there is no `--yes`.
4. **Check the draft** at the address it prints. Each upload's md5 is compared with the manifest, and the draft's file
   list is read back at the end. A mismatch stops the run and is reported; nothing is deleted.
5. **Then production**, the same command with `--target production`. The last line is
   `Draft created, NOT published. Review it at <address> and press Publish yourself.`

The script writes a receipt `<deposit directory name>.zenodo-<target>-draft-receipt.json` **beside** the deposit
directory (never inside it: the directory is checksummed). While it exists, a second create is refused. If an upload
was interrupted, run the same command with `--resume`: it uploads only the files the draft lacks, to the draft the
receipt records, after checking that it is still unpublished. A first AgentPROV release is always a new deposition,
never a new version of AgentDojo-PROV's concept. A later version uses `--new-version-of <deposition id>` (the id of the
latest published version) and only works when the release metadata records the AgentPROV concept DOI; Zenodo copies the
previous version's files into the new draft, which this script never deletes, so remove them in the web UI before you
publish.

### Sandbox trial checklist

Do this once, on the sandbox, with a small synthetic corpus, before any production run. Every command is yours to run in
your own terminal; nothing here publishes anything, and no deposit of real corpora happens until you decide it (the
standing rule: no Zenodo deposit is made without your explicit instruction). Ids below are placeholders.

1. **Sandbox account and token (you).** Register at `sandbox.zenodo.org` (a separate account from `zenodo.org`), open
   Applications, create a personal access token with the scope `deposit:write` only, and keep it to yourself. Nobody else
   needs it, and no assistant session should see it.
2. **Put it in the environment without leaving it in your history.** In the terminal you will run the tool from:

   ```text
   $ read -rs ZENODO_SANDBOX_TOKEN && export ZENODO_SANDBOX_TOKEN
   ```

   (type or paste the token; nothing is echoed). Use a new terminal for the production run later, with `ZENODO_TOKEN`.
3. **Build a draft from the demo corpus** (synthetic, MIT; the worked example above): seal it, run the release scan, write
   `release.toml`, then build the draft, with your own paths in place of the placeholders:

   ```text
   $ agentprov package --corpus corpora/demo --corpus-version 0.1.0 --spec specs/demo-agentdojo/corpus-spec.toml --licence-file LICENSE=LICENSE.demo --release-date YYYY-MM-DD
   $ uv run python tools/release_scan.py corpora/demo
   $ agentprov package --deposit DEPOSIT_DIR --corpus corpora/demo --metadata release.toml --release-date YYYY-MM-DD
   ```

   Note the corpus's root digest from the sealing output (`sha256:<hex>`).
4. **Look before you send.** No token and no network are needed for this:

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --check --root-digest sha256:<hex>
   ```

   Read the file list, the licence (`mit`), the title and the creators. Anything listed as "NOT sent" has no Zenodo
   relation; decide whether that matters.
5. **Create the draft:**

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --create-draft --root-digest sha256:<hex>
   ```

   After the consent screen, type exactly `create unpublished draft on sandbox.zenodo.org`. The last line should read
   `Draft created, NOT published. Review it at https://sandbox.zenodo.org/deposit/<ID> and press Publish yourself.`
   Exit code 0. A receipt `DEPOSIT_DIR.zenodo-sandbox-draft-receipt.json` appears beside the directory.
6. **Check the draft on the sandbox page** (and do not press Publish):
   - the record is a draft (not published, no DOI registered; a *reserved* DOI is normal);
   - the title, version, creators, description (paragraphs), keywords and the licence (MIT; Zenodo stores it under its
     own id `mit-license`) are the ones you saw;
   - the files are the ones on the consent screen, with the same sizes; the md5 Zenodo shows for each equals the `md5`
     in `DEPOSIT-MANIFEST.json`;
   - any HTTP error text the tool printed (for example "Not a valid choice" for the licence) is worth copying back: it
     means a value the tool took from Zenodo's documentation, not from the live service, is wrong.
7. **Try `--resume`.** Delete one file from the draft in the web UI (a Ctrl-C during an upload is another way, but the
   tool has no safe pause point between files), then:

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --create-draft --resume --root-digest sha256:<hex>
   ```

   Type exactly `resume unpublished draft <ID> on sandbox.zenodo.org`. Only the files the draft lacks are uploaded. Running
   step 5 a second time instead is refused while the receipt exists: that refusal is the behaviour to see.
8. **Clean up (you).** Delete the sandbox draft in the web UI (the tool never deletes anything), remove the receipt
   file, and `unset ZENODO_SANDBOX_TOKEN` (or close the terminal). The sandbox may be cleaned by Zenodo at any time.
9. **What the trial of 2026-10-23 settled and did not** (`docs/reports/release/zenodo-sandbox-trial.md`): the metadata
   fields, the licence id `mit`, the md5 and size Zenodo returns for each upload, the receipt, the second-create refusal
   and the draft's state were confirmed on the live sandbox. The 100-file and 50 GB limits, the other licence ids, a new
   version of a published record and the error body shape were not tested (they are named constants, `MAX_FILES`,
   `MAX_FILE_BYTES`, `MAX_TOTAL_BYTES`, `LICENCE_IDS`, at the top of `zenodo/src/agentprov_zenodo/draft.py`).
   The collection trial of 2026-10-29 then confirmed communities, reserved DOIs, the cross-links (and that a second run
   changes nothing), the membership refusal, the index-only umbrella with a copyleft datasheet linked rather than
   copied, and the licence ids `gpl-3.0-only` and `cc-by-4.0`; the file and size limits are still untested.

### A release of several records: communities, reserved DOIs and cross-links

A deposit holds one licence class, so a release of corpora under several licences is several Zenodo records. The
helper can place them in one Zenodo community and link them to an umbrella record (D-870). The umbrella holds no
corpus data: it is an index built with `package --index` once the part drafts exist (D-947; step 3 below).

1. **Name the community** on every create (and on `--check` to see it): `--community SLUG`, repeatable, where `SLUG` is
   the identifier in the community's address. The consent screen lists it. Zenodo sends the community's curators a
   request, which they accept or decline.

   ```text
   $ uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox --create-draft --community SLUG --root-digest sha256:<hex>
   ```

2. **The reserved DOI is in the receipt.** Each draft has a DOI that is reserved, not registered until you publish. The
   helper reads it from Zenodo and records it in the receipt (`reserved_doi`, receipt format
   `agentprov-zenodo-draft-receipt/0.2`, which also records the metadata sent). It asks Zenodo for one only when the
   draft has none, and stops if the DOI ever changes. `--resume` reads it back and never asks for another; give
   `--resume` the same `--community` options as the create, or it refuses. A receipt of the earlier format 0.1 records
   no DOI, so it can't be resumed or linked: finish that draft in the web UI.
3. **Build the umbrella index** once every part draft is `complete`. It reads each part's receipt and the part's
   deposit directory beside it, and the sealed corpora those parts hold (each corpus in exactly one part):

   ```text
   $ uv run agentprov package --index INDEX_DIR --part PART_DIR.zenodo-sandbox-draft-receipt.json --part ... --corpus SEALED_DIR --corpus ... --metadata release.toml --release-date YYYY-MM-DD
   ```

   `INDEX_DIR` holds `README.md`, `COLLECTION-INDEX.json` (each part's reserved DOI and record id, its licence class
   and corpora; each corpus's version, content digest and root digest), one datasheet copy per corpus except those
   under a copyleft licence (GPL, AGPL, LGPL: their row names the datasheet in the part record, with its digests, so
   no copyleft-licensed corpus's text sits in the CC BY 4.0 index; D-949),
   `deposit-metadata.json` (licence CC-BY-4.0) and `DEPOSIT-MANIFEST.json` of kind `index`. It has no archives. It
   refuses a receipt that is not `complete` or has no reserved DOI, a part directory changed since its upload, and a
   corpus whose digests differ from its part's. Draft it like any deposit, without `--root-digest` (the index holds no
   corpus): `zenodo_draft.py INDEX_DIR --target sandbox --create-draft --community SLUG`. The consent screen says it is
   a collection index.
4. **Cross-link the drafts** once every one is `complete`, with the index's receipt as the umbrella:

   ```text
   $ uv run python tools/zenodo_draft.py --target sandbox --cross-link --umbrella UMBRELLA_DIR.zenodo-sandbox-draft-receipt.json --member MEMBER_DIR.zenodo-sandbox-draft-receipt.json --member ...
   ```

   Type exactly `link <N> unpublished drafts on sandbox.zenodo.org`. Each member gets `isPartOf` the umbrella's reserved
   DOI, and the umbrella gets `hasPart` each member's. The members are not linked to each other: the deposit API has no
   `isRelatedTo`. Any link to the software release belongs in `release.toml` `[[related]]` (for example
   `IsSupplementTo`). The step reads every draft before it writes any. It refuses, with nothing written, a published
   record, a receipt without a reserved DOI or not `complete`, a receipt given twice, related identifiers changed
   in the web UI, and, when the umbrella is an index, members that are not exactly the part records its
   `COLLECTION-INDEX.json` lists (by reserved DOI and deposition), or an index beside the receipt that is not the
   uploaded one (D-949). It sends each draft's recorded metadata again, so make other web-UI edits **after** cross-linking.
   Running it again changes nothing.
5. **Trial it on the sandbox first** (D-941 L-8, before any production draft):

   ```text
   $ tools/zenodo_collection_trial.sh COMMUNITY release.toml INDEX_DIR PART_DIR=sha256:<hex>[,sha256:<hex>] ... --corpora SEALED_DIR ...
   ```

   It runs steps 1 to 4 in order: the offline checks and the creates of the parts, the index built from their receipts,
   the index's check and create, a cross-link without the first part that must be refused (when there are two or more
   parts), the cross-link and a second, idempotent cross-link. You type every phrase. It then prints a checklist: the
   community is shown, each DOI equals its receipt's, the index holds no archive and no copyleft datasheet, and the
   links are visible. It reads the token from `ZENODO_SANDBOX_TOKEN` in the environment (`read -rs`, as in the checklist
   above), not from the keychain, and it works only on the sandbox. The user ran it to the end on the sandbox on
   2026-10-29 (`docs/reports/release/zenodo-sandbox-trial.md`); the file and size limits, `--keychain` and the desktop
   app's dialog are still untrialled.

**Draft a collection from the terminal** (D-949), in the order above: the parts, then the index from their receipts,
then the cross-link. The desktop app's *Create Zenodo drafts…* is for single records: it drafts every line it is given
and then cross-links them, so it cannot draft the parts before the index exists, and it asks before it cross-links two
or more lines.

### The token in the keychain, and the desktop app

`--keychain` reads the target's token from the OS keychain instead of the environment (D-880). Store it once with
`agentprov keys set ZENODO_SANDBOX_TOKEN` (or `ZENODO_TOKEN`; you type it at a prompt that does not echo) or in the
desktop app's Settings › Keys. The value never reaches argv, a log or the settings file.

The desktop app has the same steps ([chapter 8](08-desktop-app.md#package) shows them):
- **Settings › Zenodo** stores what to prefill: the target to preselect, community identifiers, the AgentPROV concept
  DOI and default creators. It holds no token.
- **Package › 9 Finish › Write release.toml from the Zenodo settings…** writes a `release.toml` template, and never
  over an existing file. Fill in its title and description before Build Deposit.
- **Package › 9 Finish › Create Zenodo drafts…** takes one deposit per line (`DEPOSIT_DIR sha256:ROOT`; the first is
  the umbrella, and an index umbrella is named alone, with no root digest). It runs the uploader for each deposit (`--resume` for an unfinished one), then `--cross-link`, all
  with `--keychain`. With two or more lines it asks first, since a collection is drafted from the terminal (D-949).
  - **Terminal pane:** the uploader runs in a terminal pane inside the dialog. Each run shows its usual screen, and you
    type its phrase in the field below the pane, exactly as in a terminal.
  - **Drafts only:** it creates and links unpublished drafts. You press Publish on Zenodo's website.
  - **Platforms:** macOS and Linux (it needs a pseudo-terminal).

## purge: removing a leaked object

`purge` removes one object, by sha256, from a working corpus's raw store (or one downloaded file from the fetch cache,
with `--cache`), and writes a tombstone. Executions that cite the object get the register code `release.withheld`, and
the next seal withholds them. Use it when a raw object turns out to hold a secret or personal data. **It is
irreversible**, so try it with `--dry-run` first:

```text
$ agentprov purge sha256:294d9d585c9dbb37ec560570df2cebd26d91badbef84fc78c7d9d74b8b820bd9 --corpus corpora/demo-views --reason secret --dry-run
would remove sha256:294d9d585c9dbb37ec560570df2cebd26d91badbef84fc78c7d9d74b8b820bd9 (3008 bytes) from the working corpus corpora/demo-views.partial: objects/29/294d9d585c9dbb37ec560570df2cebd26d91badbef84fc78c7d9d74b8b820bd9.json
  would write the tombstone in raw/tombstones.jsonl (reason secret, date 2026-10-22)
  1 execution(s) cite the object; 1 new register entry release.withheld
    ex_37evkqmflf2sqxvs7cc6sbgx6c
agentprov purge: dry run; nothing was removed or written
```

On a terminal, `purge` asks for confirmation. Elsewhere it refuses without `--yes`:

```text
$ agentprov purge sha256:294d9d585c9dbb37ec560570df2cebd26d91badbef84fc78c7d9d74b8b820bd9 --corpus corpora/demo-views --reason secret
agentprov: error [cli.refused.unconfirmed]: purging is irreversible and needs confirmation: run it in a terminal and answer the prompt, or pass --yes (N.2.15)
```

After the purge, `verify` reports the object as tombstoned rather than missing:

```text
$ agentprov verify --corpus corpora/demo-views.partial
…
  tombstoned: raw.tombstoned at raw/objects/29/294d9d585c9dbb37ec560570df2cebd26d91badbef84fc78c7d9d74b8b820bd9: purged 2026-10-22 (secret); checks that need its bytes are skipped
```

A purged object is never stored or downloaded again: a later import or fetch that meets the same digest refuses it.
A sealed corpus is never purged (exit 4, `corpus.sealed`); purge the working corpus it came from, or a new corpus
version, and seal again. `--reason` is `secret` or `personal_data`.

## Common errors

| Message | Cause and fix |
|---|---|
| `no corpus spec at '…/corpora/<dir>/corpus-spec.toml'; name it with --spec` (exit 2) | give `--spec`, or name the corpus directory like its spec directory |
| `corpora/datasheet-statements.toml is missing beside the corpora directory` (exit 2) | the spec must sit in `<dir>/<corpus-id>/` with `datasheet-statements.toml` in `<dir>/` |
| `[package.refused.git]` (exit 4) | commit or stash your changes; `package` records a clean producer commit |
| `[release.refused.scan_missing]` (exit 4) | run `tools/release_scan.py` on the sealed corpus and triage every finding |
| `[corpus.sealed]` (exit 4) | sealed corpora are never modified; work on a new version |
| `[cli.refused.unconfirmed]` (exit 4) | `purge` needs `--yes` when it cannot ask |
