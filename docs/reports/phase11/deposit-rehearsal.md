# Deposit rehearsal (phase 11, U5; 2026-10-11)

A rehearsal of `agentprov package --deposit` (D-42) on **copies** of two working corpora. Nothing was uploaded or
published; the copies, the release scans and the deposit drafts were deleted afterwards. `~/.agentprov/corpora/*` was
only read (copied with `cp -Rp`). Numbers and digests only; no corpus content is reproduced here.

Environment: AgentPROV 0.1.0 at commit `f5369ec0a211751bd0c6f9a122ab9d1ff339d572` (clean tree), CPython 3.14.8, zlib
1.2.12, gitleaks 8.30.1 (Homebrew), M2 Max. Scratch area `/private/tmp/agentprov-u5-rehearsal/`.

## Steps

1. Copied `ast-survey-agentharm-p10.partial` and `mandate-agentdojo-eval-p10.partial` to the scratch area as
   `<id>.partial`.
2. Sealed each copy with `agentprov package --corpus <copy> --corpus-version 0.1.0 --spec corpora/<id>/corpus-spec.toml
   --release-date 2026-10-11`. Mandate's `LICENSE` came from its own raw store. For agentharm, `LICENSE` was the survey
   repository's file from the local upstream clone, after checking that its git blob (`10fabd90…a429`) equals the blob at
   the pinned commit `89c4db2c…` (`git ls-tree` vs `git hash-object`), and `AgentHarm-LICENSE` was
   `tests/fixtures/LICENSES/AgentHarm-LICENSE.txt`. Both were passed as paths with `--licence-file`.
3. Ran the real release scan `tools/release_scan.py <sealed copy>` (gitleaks `dir --redact --ignore-gitleaks-allow`,
   default rules, plus the home-path and host-name search). Then built a rehearsal triage file from gitleaks' redacted
   reports (key context only, never a value) and re-ran the scan with `--triage`.
4. Built each deposit twice (`--deposit <out>-1`, `<out>-2`) from a placeholder `release.toml` and compared the trees.
5. Tried one deposit holding both corpora.
6. Read every archive member in memory (no extraction) and checked it against the corpus's `checksums.sha256` from the
   meta archive (a stand-in for U4's archive-mode `verify`).

## Sealing

| Corpus | Executions | Files | Seal time | Content digest | Root digest |
|---|---|---|---|---|---|
| `mandate-agentdojo-eval` 0.1.0 | 396 | 1,616 | 6.5 s | `sha256:faba88b0b2e6ff8405e1bd8ead47a003315a01ed1e8e9df90de7286393341e3b` | `sha256:835c633d343c4691cdad12540876d57249b12be9b8b293b45fccaf17b64468cf` |
| `ast-survey-agentharm` 0.1.0 | 1,056 | 4,262 | 22.5 s | `sha256:ea45f7e6b9165b3803f14659b5db6eb51ac4079e87b46f5dd84a887683381dd8` | `sha256:bc6b524c6d9ed318c4894e4624eb259382dd366ec3ad145f06d60b7036a9530d` |

The content digests depend on the producer commit (H.2.7), so they differ from any seal on another commit.

## Release scan (G.9.4)

| Corpus | Wall time | Findings (per path, rule, line) | Home path / host name | Rehearsal triage |
|---|---|---|---|---|
| `mandate-agentdojo-eval` | 6.6 s | 1,570, all gitleaks `generic-api-key` | 0 / 0 | 1,570 `false-positive` |
| `ast-survey-agentharm` | 30.5 s | 2,270: 2,269 `generic-api-key`, 1 `facebook-secret` | 0 / 0 | 2,156 `false-positive`, 114 `synthetic-benchmark` |

Where the findings are (gitleaks hits before collapsing to one per line):

- AgentPROV's own digest-valued keys: `derivationKey` in PROV files, `subject_key` in `register.jsonl`, `logical_key` in
  `executions.jsonl` (mandate 3,880 hits; agentharm 3,191). These are content-addressed digests, not credentials:
  triaged `false-positive`.
- AgentHarm content in raw objects, AER and PROV (agentharm only, 346 hits): credential-shaped values next to
  `encryption_key`, `key:` and similar in benchmark task text and model outputs, and one `facebook-secret` rule hit.
  Triaged `synthetic-benchmark`.

**The triage was made by the U5 agent for this rehearsal only**, from gitleaks' redacted match context (the key name
before the redacted value). It is not a release decision: before any real deposit, the user reviews the findings and
the triage file. Untriaged, both scans made the builder refuse (exit 4, `release.refused.scan_untriaged`), as tested.

A follow-up worth considering (not done here, not a corpus change): the three AgentPROV-generated fields will trip
gitleaks' `generic-api-key` rule in every corpus. A committed, reviewed triage rule for them (or a gitleaks allowlist
entry scoped to those key names in those AgentPROV-written files) would keep the human triage on third-party content.

## Deposits

Each deposit: `README.md`, `CHANGELOG.md`, `DATASHEET-<id>.md`, five archives, `DEPOSIT-MANIFEST.json`,
`deposit-metadata.json`. Default `--max-archive-bytes` (2^31 − 1), so one archive per stage.

| Corpus | Build time | Archive bytes | Uncompressed | Members | Two builds |
|---|---|---|---|---|---|
| `mandate-agentdojo-eval` | 1.1-1.2 s | 9,122,335 | 72,776,758 | 1,616 | byte-identical (`diff -r`) |
| `ast-survey-agentharm` | 4.4-5.3 s | 54,001,418 | 317,541,272 | 4,262 | byte-identical (`diff -r`) |

Archive digests (sha256 of the archive file; identical in both builds):

| Archive | Bytes | Members | sha256 |
|---|---|---|---|
| `mandate-agentdojo-eval-v0.1.0.meta.zip` | 367,128 | 28 | `f8f0253f38f3c19b0bb3e35df01b15b9901186b0d8bf763fb529e86d64961110` |
| `mandate-agentdojo-eval-v0.1.0.raw.001.zip` | 837,679 | 400 | `c78f803c783fdae62f88592de7fa398cc672bf3247c6ef25dbf3776ec35dccdc` |
| `mandate-agentdojo-eval-v0.1.0.aer.001.zip` | 1,770,377 | 396 | `c5ad30c573dcaa0d48f926f594b107d9dc4f10d519827d388873aacfd285b5dc` |
| `mandate-agentdojo-eval-v0.1.0.sem-agentdojo.suites-1.001.zip` | 509,599 | 396 | `a5e26999e628fc47e241ff61993a260c02dfbfd6c243e5aafbeb5e3fff4aa741` |
| `mandate-agentdojo-eval-v0.1.0.prov-agentprov-prov-0.1.001.zip` | 5,637,552 | 396 | `65e365e212de13de6f5d00f72527f6ab5fcea19075ffe9e4f924defd0d2a20ed` |
| `ast-survey-agentharm-v0.1.0.meta.zip` | 828,679 | 26 | `b1cff5819c159ec46a2b1b02f9aa071864e614e206e05f9cdf55215d5c5d1638` |
| `ast-survey-agentharm-v0.1.0.raw.001.zip` | 24,019,219 | 1,068 | `fd6c1516859df398735c49c4e79ab0611deb604b2e1258d85b02eff6466c4c0c` |
| `ast-survey-agentharm-v0.1.0.aer.001.zip` | 12,584,005 | 1,056 | `20c56e2aedf5117a15406f226de7fa0817809f2ece7892e272fc4dd6c89568d0` |
| `ast-survey-agentharm-v0.1.0.sem-inspect.agentharm-1.001.zip` | 933,697 | 1,056 | `dece40d6e30fc355051f8d6ad686484dfea57101bcbb7055b388fa6ba28589db` |
| `ast-survey-agentharm-v0.1.0.prov-agentprov-prov-0.1.001.zip` | 15,635,818 | 1,056 | `7367ca29f3e3908ae80c306cad16fca822aced8677521e90bfb56459e5da4277` |

`DEPOSIT-MANIFEST.json` sha256: mandate `b61d67873c988463ae82d346d64be73f26731d903d5516f0747e328e226e7d64`, agentharm
`b4e821907db5ca6dbdb6084de43660a33de04836518466acea3b0529f9f9530c`.

Metadata: both drafts `status: draft-unpublished`, `concept_doi` and `version_doi` null (none was given), licence
classes `MIT` (mandate) and `CC-BY-4.0` + 1 restriction (agentharm), scanner versions recorded (gitleaks 8.30.1,
path scan 1), verification level `checksums` (U4's `chain` level not yet available). Related identifiers came only from
the sealed corpora: mandate 1 (the pinned commit URL); agentharm 4 (the survey concept DOI `10.5281/zenodo.22135956`, the
two Zenodo version DOIs of the alternative origins, the pinned commit URL).

In-memory archive check: every member of every archive matched `checksums.sha256` (1,616 and 4,262 members, closed
world, each label once) and the root digest recomputed from the meta archive's `checksums.sha256` equals the sealed one.

## Mixed deposit

`agentprov package --deposit … --corpus mandate-agentdojo-eval --corpus ast-survey-agentharm` exited **4**
(`release.refused.mixed_licence_classes`: `MIT` vs `CC-BY-4.0` + 1 restriction) and wrote nothing (no `OUT`, no
`OUT.partial`).

## Clean-up

The two sealed copies, their release scans, the triage files and the four deposit drafts were deleted after these numbers
were taken.
