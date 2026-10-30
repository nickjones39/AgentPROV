# Phase 10k part C: scratch trials (2026-10-13)

All trials ran on scratch copies under `~/.agentprov/migration-work/phase10k/trial/`. No real corpus was touched. The
input is the pinned v3 deposit file, staged at `~/.agentprov/staging/10k/v3/` and checked against the profile's pin
(sha256 `7e5f7e40…`, md5 and size). Scripts are in `~/.agentprov/migration-work/phase10k/scripts/` (`t1_maptrial.py`,
`t2_import.py`, `c2_rerun.sh`, `t3_released_scan.py`, and the property checks `c13`, `c16`-`c20`). Outputs are counts, codes and rule ids only.

## C1: every run through the family, and the withholding policy against the census

`t1_maptrial.py` runs over all 643 cells and 19,636 runs, 4 workers, about 16 minutes, in process. For each run it calls
`map_unit`, seals through the writer's checks, then runs SEM (`credleak.tools@1`) and PROV (`agentprov-prov/0.1`), with
tier-4 `validate_prov` on every 20th run. It scans every raw cell and every derived file (AER, SEM, PROV) with the
shipped profile's `[withhold]` rules and compares the per-run hits with the census classification.

Final run, against the four-rule policy of commit `0ffc47b`:

| | |
|---|---:|
| runs mapped / degenerate | 19,636 / 0 |
| cells with a raw rule hit | 325 of 643 |
| runs whose derived files hit (all in the AER; 2,240 also in PROV, from tool-call args) | **5,422** |
| census value-bearing runs (tag or key shape in content) | **5,422** |
| census vs derived mismatches | **0** |
| clean runs of a withheld cell (released, raw object withheld) | 4,415 |
| tier-4 validation sample: runs / failed checks | 974 / 0 |
| seal issues | `missing_generated_by` 19,636; `accounting_unverifiable` 36,126 (`aer.acc.agent_calls_vs_assistant` with no model call, and `toolCallCount` absent from old-schema runs); `credleak.invocation_error` 59 |

The trial ran three times, and each earlier run changed the policy:
1. **Bare marker:** 5,422 / 5,422 with no mismatch. But the C2 seal then failed the `chain` backstop on two member
   labels (see C2).
2. **`CANARY[^_]` only:** 5,421, with 1 mismatch. One hijacked run holds the tag only after a letter and before `_`.
   Census step 12 had counted the `canariesFound` labels, which the AER does not copy. Hence `canary-tag-left`
   (census step 15).
3. **Four rules:** the table above.

## C2: the product path on the real deposit (today's runner)

`agentprov import` refuses a `planned` source, as the registry gate intends. So `t2_import.py` does exactly what
`import --input FILE --verify-against-pin` does: the profile's pin, the offline `verify_download`, a D-200
`ArchiveTree`, then `import_source` in release mode with 4 workers.

The first C2 run (on `0ffc47b`) stopped at the release scan. It was re-run end to end on the branch head `78f703d`
after the rebase (`c2_rerun.sh`), because the D.19 renumbering and `canary-tag-left` had changed the family's
catalogue, profile and semantics digests, so the first seal's `chain` check now fails `rules.mismatch` as it should.

| Step (re-run on `78f703d`) | Result |
|---|---|
| import | 643 cells seen. **8 single-run cells sealed clean**; **635 multi-run cells sealed degenerate** (`map.unparseable_artefact`): the runner maps one execution per whole file. This is **R-10k-1** (`routing.md`). The collector-log JSON is stored and excluded |
| `validate` | 643 of 643 passed (dev mode, tiers aer, sem, prov, linkage; linkage 100%) |
| `recompute --dry-run` | 643 identical, 0 changed, 0 unexplained, 0 failed |
| `package` (release seal, scratch spec) | sealed. **Withheld 327 raw objects** (325 cells, the collector-log JSON, and the deposit zip as `container`) **and 1 execution**: the one value-bearing single-run cell. The other value-bearing runs sit in multi-run cells, which are degenerate today, and their degenerate AERs hold no content |
| `verify --level chain --release --root-digest` | **passed**, 0 failed, 0 unverified (root `sha256:e65cf938…`) |
| `tools/release_scan.py` (gitleaks 8.30.1) | **1 finding** (`generic-api-key`, one raw object of a released clean cell; two matches on one line, one fingerprint). Triaged `false-positive` in a **scratch, provisional** triage file (below) |
| `package --deposit` (scratch metadata) | **built**: 5 archives, nothing uploaded. A rescan of every deposited file and archive member with the four rules finds one hit only: `rules/credleak-p15b.profile.toml`, the policy's own pattern text, which D-236 exempts by design. The private sidecar holds 658 hit objects (the control) |

**Seal findings that changed the policy.**
- The first release seal failed `chain` with `withheld.rule_hit` in `raw/members.jsonl`. That file lists every member
  label and stays released (D-231). Two not-selected collector-log labels carry the tag between underscores. Hence the
  tag rules became bounded patterns that skip that form.
- The seal also refused the first `rates.toml`, whose exclusion named no issue code. Hence the
  `credleak.invocation_error` info issue.

**The release-scan finding.** Its properties, read without printing the text (`c13_triage.py`, `c16_token_props.py`):
- the matched token is 16 characters: three `/`-separated segments of 5 digits, `api`, and a 6-letter dictionary word;
- **every one of its 4,437 occurrences in the deposit is preceded by `localhost:`**, so it is the path of a loopback
  URL, `localhost:<port>/api/<word>`;
- it occurs only in the T4 cells (the web channel, `01-injection-map/`): in agent text (1,777), tool outputs (1,676),
  shell commands (935), fetched URLs (42) and written content (7); in no non-cell member;
- it carries no tag and no key shape.

That is the study's local test endpoint, not a credential. gitleaks' `generic-api-key` keys on the word `api` next to a
high-entropy value. The profile's `scan_rules` include `generic-api-key` (D-236), so a deposit needs every such finding
triaged `false-positive`. For the scratch deposit only, `c2seal.triage.toml` (in the trial folder, never committed)
triages it `false-positive`. The reason was first marked provisional; the user then ruled the classes false positives
(D-269).

## C3: a full-size release-scan estimate (what a full import's triage would face)

R-10k-1 keeps the product path from sealing the multi-run cells, so `t3_released_scan.py` estimates the full-size scan:
it maps all 19,636 runs in process (as C1), writes the AER, SEM and PROV of every run with no `[withhold]` hit to a
scratch folder (one file per run and kind; no raw bytes), and runs gitleaks with `release_scan`'s configuration over it.
About 14 minutes with 6 workers.

- **Runs:** 14,214 written (released), 5,422 withheld: D-265's expected split on the derived files.
- **gitleaks:** 14 fingerprints, none in SEM. With the one raw-object fingerprint of C2 (the released raw cells are
  scanned there in full), a full import should raise about **15**. Every one reads as a false positive (property
  checks `c18`, `c19`, `c20`; masked shapes and booleans only):

| Fingerprints | Rule | Files | What it is |
|---:|---|---|---|
| 1 + 2 | `generic-api-key` | 1 raw object, 2 AER | the loopback URL path `localhost:<port>/api/<word>` (above) |
| 6 | `generic-api-key` | 1 AER (6 lines) | `API_KEY=placeholder_12345`: the literal word "placeholder" and `12345`, in a T4 run (7 occurrences in the deposit) |
| 1 | `curl-auth-user` | 1 PROV (tool-call args) | a `date '+%Y-%m-%dT%H:%M:%SZ'` format string next to `"$user:$TOKEN"` shell variables, in TSTAGE commands (33 occurrences) |
| 5 | `generic-api-key` | 5 PROV | **AgentPROV's own `apv:derivationKey` values** (each is the derivation key of its file), cut by gitleaks' fragment boundaries beyond `release_scan`'s allowlist: four with the field name cut to 3-5 characters (the allowlist needs 6), one with the key cut to 12 characters (it needs 16) |

The last row is not a credleak matter: any large corpus can hit it. It was routed as R-10k-2 (`routing.md`) and is resolved by D-310 (`a4fca19`, on main at `0b663f3`), so a full import
should now raise about 10 findings for triage. Widening
the allowlist is not a safe one-line fix: a field suffix of 3 characters (`Key":"`) would also hide a 26-character
lower-case key in a field such as `apiKey`. The fingerprints (path, rule, line) of a real corpus depend on its layout,
so these counts are an estimate, not a triage file.

## What the trials leave open

- **R-10k-1** (runner): the full product-path import, and so a full-size seal, `chain` and deposit of the deposit's
  14,214 releasable runs.
- ~~The triage~~ decided by the user (D-269): the three classes of C3 are `false-positive`; a real seal's triage file
  lists each fingerprint after a property check, and any other finding needs a new triage.
- ~~R-10k-2~~ resolved by D-310 (`0b663f3`).
- Imports into a real corpus wait for the regeneration round and the user's approval. aer/0.2 will move every AER pin,
  including the credleak goldens: regenerate, never hand-merge.
