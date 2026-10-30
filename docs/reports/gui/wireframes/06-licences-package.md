# 06 Licences and Package

## Licences

```
┌ Licences ── [Adopted sources] [Excluded (708)] ── filter [______]  flags [any ▾] ────────────────────────┐
│ source   SPDX          policy   restr.  copyleft  NC  private-only  search decision  corpus class   parts │
│ src-a    MIT           include  —       —         —   —             included         MIT/Apache/CC  2     │
│ src-g    AGPL-3.0-only include  —       ✓         —   ✓ (fixture)   included         AGPL-3.0 own   1     │
│ src-h    CC-BY-4.0     include  ✓       —         —   —             included         MIT/Apache/CC  1     │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ src-g · evidence                                                                                         │
│   registry      LicencePolicy spdx AGPL-3.0-only · policy include · basis "…" (escaped, one line)        │
│   profile       src-g.profile.toml [licence] basis "…" · holders … · data_licence …                     │
│   screening     records-merged.jsonl: decision included · corpus_licence_class AGPL-3.0 own corpus       │
│   flags         copyleft: release/metadata.py rule · private-only: THIRD_PARTY_NOTICES.md entry          │
│   feeds         own corpus (D-94) · datasheet §Distribution · LICENSES/src-g/ · deposit class AGPL-3.0   │
│   unmatched     —                                                                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
Excluded tab: name · exclusion code (EX-LIC-1 …) · reason text from eligibility-criteria.md · strand.
```

## Package flow

```
┌ Package ── step 2 of 9: Withholding review ───────────────────────────────────────────────────────────┐
│ 1 Preconditions ✓  2 Withholding ●  3 Counts & licences  4 Datasheet  5 Seal  6 Verify  7 Release scan │
│ 8 Deposit  9 Finish                                                                                    │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ From `package --dry-run`:                                                                              │
│ reason          basis         entries   executions affected   withheld                                 │
│ secret          purge         1         1                     1                                        │
│ secret          profile_rule  326       0                     0      rules: ns.withhold_a@1       │
│ licence         raw_policy    0         —                     —                                        │
│ Values are never shown. The private sidecar DIR.withheld/ is not opened.                               │
│                                                                    [Back] [Next]                       │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌ Package ── step 9 of 9: Finish ─────────────────────────────────────────────────────────────────────────┐
│ ✓ Sealed corpus-y 0.1.0   root sha256:… (copy)                                                          │
│ ✓ verify --level chain --release: ok                                                                    │
│ ✓ Deposit built: 7 archives, 2.1 GiB · DEPOSIT-MANIFEST.json · verify (archive mode): ok                │
│                                                                                                         │
│ Nothing has been uploaded. Uploading to Zenodo is a manual step, done only on the project owner's      │
│ explicit instruction. Files to upload (plain text):                                                     │
│   corpus-y-v0.1.0.meta.zip  corpus-y-v0.1.0.raw.000.zip  …  README.md  DATASHEET-corpus-y.md            │
│                                                       [Copy file list] [Reveal folder] [Done]           │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
