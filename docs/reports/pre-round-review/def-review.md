# Local review of areas D, E and F at c4d7b785

Date: 2026-10-22. Areas re-scoped out of the ultrareview (user decision 2026-10-22):
- **D. Ingest trust boundary:** `ingest/`, `io/`, `worker.py`, `cli/backends.py`.
- **E. Provenance core:** `prov/` (without `prov/compat/`) and `validate/`.
- **F. AER, SEM, views:** `aer/`, `sem/`, `views/`, with aer/0.2 as the focus.

The code was reviewed as it stands at c4d7b785, not as a diff. The brief was `docs/review/REVIEW.md`: its definition of
Important, its "Do not report" list and its "Always check" list. The pre-round findings PR-1..PR-14 and RC-1..RC-19 were
excluded.

## Verdict

**Six Important findings, all scientific-correctness or trust-boundary defects, plus 21 Minor and 2 Nits.**
- The trust boundary in area D is solid: bounded parsers, extraction-free archives, strict JSON, minimal worker
  environments. Differential fuzzing of JCS, `jsonstream` and `jsonspan` against the reference parsers found 0
  mismatches. The one Important there is a label-normalisation defect (D-1).
- Area E's validator is the weak point. Tier 4 accepts three kinds of PROV documents that the specification forbids
  (E-1..E-3).
- Area F has one aer/0.2 rule-coverage gap that lets an I-class rule ground a Derived core statement (F-1), and a view
  defect that labels degenerate runs "benign" (F-2).

None of these is caused by the integration, and none blocks the regeneration round as a re-import. But E-1..E-3 and F-1
mean tier-4 "pass" is weaker than the corpus documentation claims. Fixing them moves the `validation` (and, for F-1, the
`aer`) stage digests (class 1). Re-validating after the fix could reject documents that pass today. So the
recommendation is to land E-1..E-3 and F-1 before the round, if the round's validation is to stand as evidence.

## Method

- **Workflow** `wf_85280183-27f`, 84 agents, seven finders:
  - D: parsers; names, paths and io; workers and backends;
  - E: PROV engine; validation;
  - F: AER; SEM and views.
- **Verification:** every finding went to two adversarial verifiers, one reproducing it with a probe or a targeted test,
  one checking intent and severity against REVIEW.md, DECISIONS and the spec. A completeness critic followed, and its
  finding was verified the same way.
- **Outcome:** of 38 findings, 29 were confirmed by both verifiers, 5 are plausible and 4 were refuted.
- **Probes:** synthetic, from the `tests/` fixtures, with targeted tests only. No heavy job, so the queue was not needed.
- **Data:** `~/.agentprov/review/pre-round/def-result.json`, which holds every finder's 'checked' list. Probes moved with
  the scratch (below).

## Important

**E-1. Tier 4 never checks the placement of unidentified relations** (#20; CONFIRMED, both Important).
- **Rule:** E.5.1 item 3 is normative:
  - `specializationOf` only at top level, one `aprov.t_spec@1` per bundle;
  - `hadMember` only for tool-call requests;
  - `mentionOf` only in the inference and assessment bundles;
  - never `alternateOf`.
- **Cause:** these relations carry no rule, class or pointer, so `pv.linkage.evidence_attributes` (`linkage.py:166`) and
  `pv.profiles.rule_section` (`profiles.py:203`) skip them, and `prov_structure._relations` checks only their attributes.
- **Probes** (generic derivation, re-serialised with JCS), each passes tier 4:
  - a forged `specializationOf` or `alternateOf` in the core bundle;
  - a top-level `alternateOf`;
  - a missing `t_spec`;
  - a forged top-level `specializationOf(xd:provenance, raw:…)`.
- **Fix:** a placement check for E.5.1(3). **Class:** 1 (validation).

**E-2. The pointer exemption for `aprov.n_capture_profile@1` is keyed by rule, not by node** (#21; CONFIRMED, both
Important).
- **Cause:** E.10 exempts only `x:capture-profile`, but `linkage.py:65-66,204-207` exempts any statement whose
  `apv:rule` is that rule, and `profiles.py:51-52,205-211` lets the rule emit any entity.
- **Effect:** an Observed message or artefact can claim the rule, drop `apv:sourcePointer`, `basisRule` and
  `rulePointer`, and pass.
- **Fix:** bind the exemption to `x:capture-profile` typed `apv:CaptureProfile`, and refuse the rule on any other key.
- **Class:** 1.

**E-3. Evidence linkage accepts a source pointer that resolves to the wrong record** (#22; CONFIRMED, both Important).
- **Cause:** `pv.linkage.source_pointer` (`linkage.py:199-228`) checks only that the pointer resolves, that pointers are
  ordered, and that the field is not weaker. It never checks that the record is the statement's own node, an endpoint,
  or a premise its rule names (K.10 "that justifies it", E.10(11)).
- **Probes:** `x:m0` citing `m1`, and a `wasGeneratedBy` citing another generation's field, both pass.
- **Fix:** bind pointers to the statement's node, endpoint or rule premises. **Class:** 1.

**F-1. AER-V14 does not check scoped-rule pointers below an `evf` key** (#37, critic; CONFIRMED, both Important).
- **Cause:** C.6.4 says "the applicable set of a D pointer MUST NOT contain an I-class rule". `_rule_coverage`
  (`aer/validate.py:601`) evaluates only top-level fields and `evf` keys.
- **Effect:** `mc1.rule = ['tst.d@1', 'tst.i@1#/input/2']` with no `evf` passes tier 2. The engine then emits
  `used(x:mc1, x:m2)` in the core bundle as `apv:Derived` with `basisRule tst.i@1` and no `apv:method`, and tier 4
  passes. That is an inferred relation presented as derived. The control with `evf {'/input/2': 'D'}` is refused.
- **Fix:** add the scoped pointers to the evaluated set. Optionally, a tier-4 check that a non-Inferred statement's
  basis rule is not I-class.
- **Class:** 1 (aer and validation). Stored AERs that rely on such a scope would start failing, so check the corpora's
  rule references when it lands.

**F-2. The transcript/v1 view renders a degenerate AER as a complete benign run** (#32; CONFIRMED, Important/Minor).
- **Cause:** `render_converted` (`transcript_v1.py:480,490`) and the field table's `null_renders = 'benign'`
  (`transcript_v1_fields.toml:69-72`) label an absent `task.attack_id` "benign", not only a null one. The view then has
  `turns: []`.
- **Effect:** `derive._views_and_compat` (`derive.py:1675-1694`) builds a compat PROV graph from it, with an empty user
  query. So an attacked run whose map failed is shown as a benign run: an invented value.
- **Fix:** refuse the view for a degenerate AER (register view and compat as failed), or apply "benign" only to a present
  null `attack_id`.
- **Class:** 2 for corpora with degenerate units (their views and compat outputs).

**D-1. `discover()` returns the on-disk label, but `open_evidence()` opens its NFC form** (#5; CONFIRMED,
Important/Minor).
- **Cause:** `_iter_tree` validates with `logical_name` but discards its NFC result (`paths.py:427,444,463`).
  `open_evidence` opens the NFC form (`paths.py:300-303`). Siblings are not collision-checked, unlike archives
  (`archives.py:483-501`).
- **Effect:**
  - On Linux, with NFD and NFC siblings, the NFD-labelled member is recorded with the NFC file's bytes. With only an NFD
    file, an uncaught `FileNotFoundError` crashes the import (`LocalTree.read` catches only `IngestError`).
  - On APFS, the recorded label is non-NFC, against G.3.6.
- **Reach:** `--input` trees and live staging directories written by a T2 worker.
- **Fix:** use `logical_name`'s return value, refuse sibling collision groups, and add an NFD test.
- **Class:** 1, or 2 for corpora with non-NFC names.

## Minor

**D, trust boundary** (all class 0 or 1):
- **#4:** YAML sexagesimal ints build in quadratic CPU within `max_yaml_bytes`, about 50 s per 1 MiB tool output through
  the marker normaliser (`yamlsafe.py:89`, `markers.py:152`). Verifiers rate it Minor. Refuse long sexagesimal plain
  scalars in `_prescan`.
- **#0 (PLAUSIBLE):** the `jsonstream` pass-1 scanner pushes frames before any depth or duplicate check, about 73×
  memory on bracket-heavy envelopes. Under MCPHunt's 64 MiB raise it could exceed the worker RSS cap.
- **#1/#8 (PLAUSIBLE):** `nested_raises` accepts `max_ratio = nan`, which disables the ratio gate (profile-controlled).
- **#2:** `zip_precheck` does not refuse a classic-EOCD multi-disk zip (G.3.5, D-243).
- **#3 (PLAUSIBLE):** one member with an undecodable name refuses the whole zip, where G.3.5(5) says only that member.
- **#6:** breaking a stale lock is not atomic, so two processes can both hold a `ResourceLock` or `LockFile`.
- **#7:** `jsonschema_subset.unsupported_keywords` raises `TypeError` on a list- or object-valued `type` from an
  untrusted SEM header.
- **#9:** `collision_key = NFC(casefold())` misses APFS collisions (U+0345 cases).
- **#10:** `escape_markdown(line_start=True)` leaves `~~~` fences and four-space indents at line start.
- **#11:** map and expand requests over 4 MiB are sent unchecked; the worker rejects them, so a valid large container
  becomes a degenerate `adapter_defect` unit.
- **#12:** a D-554 admission ticket leaks when a worker cannot be spawned, so later pools can wait forever.
- **#13 (PLAUSIBLE):** the T1 audit hook misses process creation through `_posixsubprocess.fork_exec`.

**E, provenance core:**
- **#15:** negative rule conditions treat an `unk` field as absent, and the `attr_message` guard is dead code
  (`prov/rules/edges.py`). Class 2.
- **#16:** an item-level `unk` on `/input/i` or `/inputs/i` still fires `use_context`, `g_use` and outcome usages.
- **#17:** message nodes never carry `apv:partOf`/`apv:thread`, contrary to E.1.3 and E.1.4. Class 2.
- **#18:** two header artefacts with identical bytes make derive refuse a valid AER.
- **#23:** no check keeps a statement's class within its rule's ceiling (E.1.5(2)). A Derived-ceiling node raised to
  Observed passes.
- **#24:** `pv.linkage.premise` skips the routing-scope check when the premise is in an assessment bundle.
- **#25:** a reflexive `mentionOf` is never reported (Constraint 52).
- **#26 (PLAUSIBLE):** tier 4 never binds the PROV document to the AER it is validated against.

**F, AER, SEM, views:**
- **#27:** the validator and writer accept `accounting_*` mirror issues that no check produces.
- **#28:** `$utf16` and `$lit` are accepted beyond their definitions; an odd-length `$utf16` crashes `decode_value` on a
  validated AER.
- **#30:** the D-216 1 MiB inline-string limit is not applied to the seal record.
- **#34 (PLAUSIBLE):** SEM-V11 is vacuous for an annotation with no premises.
- **#35:** transcript/v1 drops an aer/0.2 withheld reasoning or refusal part instead of rendering it null.

## Nits

- **#14:** `backends build --offline-check` is documented as "without writing", but it creates scratch directories and
  runs without the build/staging locks.
- **#31:** the aer-0.2 schema leaves `task.task_id` optional unconditionally, and its description names only D-211
  (D-219 is the other reason).

## Refuted

- #19 (message `contentSha256` restating an ambiguous part).
- #29 (the reader does not check `execution.aer`).
- #33 (SEM-V03 catalogue binding).
- #36 (annotation id order).

## Checked and sound (highlights; full lists in `def-result.json`)

- **Archives:**
  - `zip_precheck` and `_open_zip` checked against CPython 3.14.8 `zipfile`;
  - the overlap, collision, link, encryption, ratio and total gates;
  - a custom tar parser with no `tarfile` (pax allowlist, octal-only sizes, bounded GNU long names);
  - bounded gzip and zstd decoders.
  - Mutation fuzzing (6,000 zip, tar.gz and tar.zst cases) produced only typed errors, and nothing is ever extracted.
- **Strict JSON:** BOM and UTF-16/32 sniffing, duplicate keys, NaN, digit caps, depth prescan, lone surrogates.
- **Differential fuzzing:** `jsonstream` (9,000 cases at chunk sizes 1-64) and `jsonspan` (20,000 cases) against
  `strict_json_loads` found 0 mismatches. The JCS fast path against `rfc8785` (200,000 cases) found 0 differences.
- **Names, YAML, quoting:**
  - `names.logical_name`;
  - the `paths` `dir_fd` walk with `O_NOFOLLOW_ANY`, regular-file and `nlink == 1` checks;
  - `quote_untrusted` escaping of every control, bidi and tag class;
  - `yamlsafe` refusing aliases, tags, merge keys and duplicate keys.
- **io:** atomic writes, and lock registration ordering.
- **Workers:** argv carries no secret; the environment is the minimal allowlist; job directories are 0700 with random
  names; `close_fds`; process-group kill; framing bounded.
- **Determinism:** results are collected in job order, not completion order.

## Scratch

**Cleaned up 2026-10-22, by the same rule as before.**
- **Removed:** the review worktree `~/.agentprov/review/pre-round/def`.
- **Moved** to `~/.Trash/agentprov-cleanup-2026-10-22/pre-round-review/`:
  - the probes (`probes-def/`, 8.6 MB);
  - two 1-byte temp directories that the APFS collision probe had created inside the worktree.
- **Kept:** `~/.agentprov/review/pre-round/def-result.json`.
