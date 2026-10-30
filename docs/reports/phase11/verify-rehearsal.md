# Verify rehearsal (phase 11, U4; 2026-10-12)

A rehearsal of `agentprov verify` (all three levels, tree and archive mode), `agentprov validate --corpus` and the
deposit builder with the injected `chain` verifier, on a **copy** of one working corpus. Nothing was uploaded or
published; the copy, its release scan, the triage file and the deposit draft were deleted afterwards.
`~/.agentprov/corpora/*` was only read (copied with `cp -Rp`). Numbers and digests only; no corpus content is reproduced.

Environment: AgentPROV 0.1.0 at commit `db47752d830a9821c99543aa74e26a6f16c914ac` (branch `phase-11-u4`, clean tree),
CPython 3.14.8, zlib 1.2.12, gitleaks 8.30.1, M2 Max. Scratch area `/private/tmp/u4_rehearsal/`. Wall times are single
runs (`/usr/bin/time -p`, real).

## Steps

1. Copied `mandate-agentdojo-eval-p10.partial` to the scratch area as `mandate-agentdojo-eval.partial` (71 MB).
2. Sealed it: `agentprov package --corpus <copy> --corpus-version 0.1.0 --spec corpora/mandate-agentdojo-eval/corpus-spec.toml
   --release-date 2026-10-11` (`LICENSE` from the corpus's own raw store, as in the U5 rehearsal). Sealing now runs
   `verify --level chain` before the swap (N.2.11 step 3).
3. `agentprov verify` on the sealed tree at `checksums`, `chain` and `rederive` with `--release --root-digest <the
   printed root digest>`; then `rederive` on a seeded sample (dev mode).
4. `agentprov validate --corpus <sealed> --strict --report <outside>`.
5. `tools/release_scan.py` on the sealed copy; a rehearsal triage file (see below); scan again with `--triage`.
6. `agentprov package --deposit` (the CLI now injects the `chain` verifier); `verify` on the deposit directory at
   `checksums` and `chain` (and `chain --release --root-digest`), and on the lone meta archive; the deposit files' sha256
   compared before and after.

## Sealing

| Corpus | Executions | Files | Seal time (incl. chain verify) | Content digest | Root digest |
|---|---|---|---|---|---|
| `mandate-agentdojo-eval` 0.1.0 | 396 | 1,616 | 15.7 s | `sha256:b6b5a86ec5c30411b1ab77b4f0943224c12ed466c11f1d3f64f00cf083c29082` | `sha256:c3c59c74d8cea8b6c2f589feb7320074deb95c0b2a55fe88953cdc70502a4f22` |

The U5 rehearsal sealed the same corpus in 6.5 s without the chain verification; the content digest differs from U5's
because the producer commit differs (H.2.7).

## Verify, tree mode (release mode, published root digest given)

| Level | Wall time | Exit | Findings | Counters |
|---|---|---|---|---|
| `checksums` | 0.98 s | 0 | 0 | 1,615 files listed, 1,615 matched; root digest compared |
| `chain` | 6.33 s | 0 | 0 | 396 executions checked; 400 raw objects; manifest members recomputed equal |
| `rederive` (`--jobs 10`) | 69.1 s (user 362 s) | 0 | 0 | 396 identical, 0 changed, 0 unexplained, 0 failed, 0 unverified; 400 raw objects re-hashed and linked into the scratch tree; stages aer, sem, prov, validation |
| `rederive --sample 40 --seed rehearsal` (dev mode) | 9.1 s | 0 | 0 | 40 executions re-mapped and re-derived, 40 identical |

The `rederive` notices say that the code digests of the `aer`, `sem`, `prov` and `validation` stages differ from the ones
the import recorded while every declared version is the same; every output is byte-identical, so it passes (H.8.4(2)).

## Validate --corpus (strict)

| Wall time | Executions | Passed | Stored rows reproduced | Linkage | Tiers (executions passed / with a row) |
|---|---|---|---|---|---|
| 262.5 s | 396 | 396 | 396 of 396 (0 differ) | 396 / 396 resolved, `linkage_resolved_pct` `100.00` | tier 2: 396/396; tier 3: 396/396; tier 4: 396/396 |

The report's D-40 `ValidationSummary` is equal to the sealed manifest's `validation` member. Validation runs in the CLI
process (no T1 job kind for it; `validate_prov` dominates, about 0.66 s per execution).

## Release scan

gitleaks 8.30.1 with the committed allowlist left **3** findings (all `generic-api-key`: two in PROV files, one in
`register.jsonl`), against 1,570 before the allowlist (U5 rehearsal). gitleaks' redacted context shows all three are
AgentPROV content-addressed key fields (`derivationKey`, `subject_key`) whose match boundary escapes the anchored
allowlist (`^(derivationKey|subject_key|logical_key)":"…"$`): in one the match begins inside the key name
(`ivationKey":"…"`), in another it ends without the closing quote. They were triaged `false-positive` **for this
rehearsal only**; this is not a release decision. Follow-up for the allowlist owner (U5/D-42): widen the anchors to these
boundary variants. Scan wall time 14.4 s.

## Deposit and archive-mode verify

The deposit (5 archives, 1,616 members) was built in 7.0 s; `DEPOSIT-MANIFEST.json` records `verification.level` =
`chain`. The four data archives have the same sha256 as in the U5 rehearsal (raw `c78f803c…`, aer `c5ad30c5…`, prov
`65e365e2…`, sem `a5e26999…`), as expected from deterministic archives over byte-identical files; the meta archive
differs (`e6890f16c4d72224f75287aed7c45d82d663ea46b6f70756902da0c5e4c3cb32`, 367,366 bytes) because the manifest and
datasheet record the producer commit. `DEPOSIT-MANIFEST.json` sha256 `ab1f1e0a460acdc2c3afc1cff9518a4ea4fe08260b7d04101118ec67485f2dc7`.

| Input | Level | Wall time | Exit | Findings |
|---|---|---|---|---|
| deposit directory | `checksums` | 0.46 s | 0 | 0 (9 files hashed against the deposit manifest; 1,616 members; 1,615 matched `checksums.sha256`) |
| deposit directory | `chain` | 6.04 s | 0 | 0 (396 executions checked, 400 raw objects) |
| deposit directory | `chain --release --root-digest` | 6.03 s | 0 | 0 |
| lone meta archive | `chain` (dev) | 0.66 s | 0 | 2,384 `archive.not_present`, all unverified (27 members it holds matched) |
| lone meta archive | `chain --release --root-digest` | — | 1 | unverified findings fail in release mode |

Nothing was extracted: the sha256 of every deposit file was identical before and after the five runs, and no file was
created in the deposit directory.

## Clean-up

The sealed copy, its release scan, the triage file, the deposit draft and the summaries were deleted after these numbers
were taken.
