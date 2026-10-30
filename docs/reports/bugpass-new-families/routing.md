# Bug pass bugpass-new-families: routed findings

These findings are in files that another session owns or is building on. They are sent through the orchestrator. Each
has a reproduction under `repro/NF-nn_*`. The fix sketches are the verifiers'. The owner decides on items and versions.

## R-NF-1..3 to regen-items (owner of R-10j-1, item 105 on `regen-held-4`, which wires the shared agentdojo redaction)

- **R-NF-1 (NF-1; profile `environmentoptim-agentdojo`, which item 105 edits for its redact rules).** Lines 61 and 75
  name the owner of the upstream AgentDojo copies by corpus id `agentdojo-upstream`, but the registry source id is
  `agentdojo`. `_owner` falls back, so all 36,679 `select.owned_elsewhere` rows of the trial register carry the
  unregistered source id `agentdojo-upstream`.
  - Fix: `owner = "agentdojo"` (add `owner_corpus` if the head corpus is meant), and the lineage entry
    `{ of = "agentdojo", part = "head", ... }`, as ceferisbarov writes it.
  - Optional class-0 guard: `profiles._check_import` and the lineage check test registry membership, not only the id's
    shape.
- **R-NF-2 (NF-2; D-510 identity recipe).** EnvironmentOptim's 13 doubly nested logs cannot be keyed by "layout facet
  → `redact_value` → row". Under the layout grammar their account directory is the optional `arm` facet and
  `pipeline_dir` is `workspace`. Item 105 needs:
  - a layout that puts the account directory in `pipeline_dir` for both shapes, or explicit rows for the nested shape;
  - a correction of `d510-directory-account-paths.md:60` and D-510's identity bullet ("the same pattern applies to the
    13 nested logs" does not hold).
- **R-NF-3 (NF-10, NF-11, NF-12; `adapters/agentdojo/redact.py` and its callers; two are security findings).**
  - NF-10: the redactor never decodes `{"$utf16": …}` nodes. An observed model string with a lone surrogate keeps the
    account path, base64-encoded, with no D tag, no `rescont.redacted` entry and no issue.
    - Fix: decode `$utf16` nodes in `Redactor.apply`, then replace and re-encode.
    - Or: run the D-378 surrogate scrub first (NF-13, item 119), so no observed value is `$utf16` when the redaction
      runs.
  - NF-11: `parse_redact_rules` accepts zero-width patterns, and `_render`'s `{leaf}` fallback can copy the whole match.
    In both cases a label still holding the account is reported as redacted.
    - Fix: `_render` refuses an empty match. After rendering, it refuses a label that still contains the matched span
      (`ProfileError`).
    - R-10j-1's recommended rule is not affected (checked).
  - NF-12: builds that do not apply a declared redact scope ignore it silently: the capture mapper, and `ResultsBuild`
    for any scope but `model_id` (TraceLogger and DRIFT are what item 105 wires).
    - Fix: each build refuses (`ProfileError`) a declared rule whose scope it does not feed to a `Redactor`.

## R-NF-4 to the orchestrator and phase 10i (a seal policy; class 0 but a decision)

- **NF-24.** `agentprov package` seals a corpus imported with D-530 context trees or R3 pinned objects without a
  refusal or notice. The closed corpus-0.1 snapshot drops `context[]` and `pinned_objects`, so every re-map of the sealed
  corpus runs without the `<role>:` joins (fixture: `recompute` 23/25 unexplained).
  - This affects DTap and AgentOps-Bench, and later RedCode Qwen Code and `redcode-exec-openhands`.
  - Options: refuse to seal (or require an explicit acknowledgement recorded in the datasheet) while corpus-0.1 cannot
    hold the context; or carry the context in the sealed form (a format change: corpus/0.2, with part C).

## R-NF-5 to `phase-10i-context` (D-530/D-560 build, regen items 98-100)

- **NF-25 (class 1, `importer.py:2261`).** G4 `_check_identity` ignores context roles, context pins and the
  `pinned_objects` set. A resumed working corpus can mix joined and unjoined units, while the manifest records only the
  last run's set.
  - Fix: compare the recorded snapshot's context identity (sorted roles, each pin, the archive sha256, the
    `pinned_objects` labels and sha256) and refuse a difference.
- **NF-26 (class 0, `corpus/derive.py:1910`).** A re-map writes `snapshot.context[i].verification = null`.
  - Fix: carry the recorded verification by role in `_merge_sources`.
  - Note: `derive.py` is also edited by derive-bugpass and the importer merge order.
- **NF-27 (class 0, `cli/import_.py:495`).** `--context` accepts a duplicate ROLE (the last one wins) and a PATH in which
  no file matches the role's `context_artefacts`. The pin check then passes vacuously, every unit is mapped un-joined,
  and the import exits 0.
  - Fix: refuse a repeated role; refuse a git-pinned role whose PATH holds none of the pin's role files.
- **NF-28 (class 0, `cli/import_.py:527,556`).** A context download pin or an `lfs_object` pin without `sha256` is
  accepted from the fetch cache, checked by md5 and size only.
  - Fix: mirror the primary path, raising `raw.fetch.unverifiable` / `UnpinnedInputError`.
- **NF-29 (class 0, wording).** `--no-context ROLE` is described as "recorded" (D-530, MN N.2.2, the notice text), but
  the corpus keeps no record of it.
  - Fix: reword to "reported as a notice", or record it in the snapshot.

## R-NF-6 to `regen-held-2` (R-10j-2, regen item 95)

- **NF-30 (class 1, `runner/__init__.py:497`).** `own_pin_part(profile, part)` ignores the file's origin. With the
  part importable, `--snapshot history --pin head` would map all 47,723 head files as part `history`.
  - Fix: make the exemption hold only for files whose git origin commit is the part's own pin.
- **NF-31 (text).** The registry caveat, the README row, the profile comments, the history table header and D.6.14
  item 11 describe all 621 logs as `drift.k18.messages`. One is `v1.k14.incomplete`
  (`shopping/injection_task_0/none/none.json`).
  - Fix: `variants = ("drift.k18.messages", "v1.k14.incomplete")`, as part `a` does.
- **NF-32 (text).** The history pin's commit facts are wrong. The directory was replaced at `4d2748c6` (the pin's
  child), not `6623a721`. The 621st file is not present from `2d4ad05a`; only the 620 shared blobs are unchanged from
  `2d4ad05a` to `785b9127`.
  - Fix: amend the profile pin note and the table header before item 95 lands (v3 in place, no v4).
- **NF-33's profile side.** The census tooling fix is on this branch (850b2142). The history part declares no
  `observed` counts and its pin is not `primary`, so no standing gate measures it. Whether to add counts is the
  owner's call.
