# `aer/0.2`: design for approval (deferrals part C, 2026-10-12)

Status: **design only; no code is written until the user approves.** Decision proposals D-210..D-213 (DECISIONS.md, at
the end of this document's merge). Scope as narrowed by the user on 2026-10-12 (relayed by the orchestrator): the two
`aer/0.1` limits, plus any other `aer/0.1` workaround that can be justified. The AER-V34 widening to code ranges is
**dropped** (D-213, with the evidence).

## 1. What changes, and why it needs a new format version

`aer/0.1` is frozen (D-14; `versions.FROZEN`; `tests/unit/test_format_freeze.py`): a change to its schema, record kinds
or closed enums is a new version, never an in-place edit. Since D-163 a sealed corpus's `schemas/**` and the
`aer-0.1.schema.json`/`corpus-0.1.schema.json` it carries are compared byte for byte with the package by `verify
--level chain`, so a published schema's bytes are frozen with its version.

Both changes below are **relaxations**: a member that `aer/0.1` requires becomes absent when an `unk` declaration names
its pointer. No record kind, closed enum, reference or PROV rule is added. They still change what is *valid*, which is
the meaning of the format, so they cannot be made in `aer/0.1` (the brief's escape, "a design that changes no aer/0.1
bytes and no aer/0.1 meaning", is not available: a validator that accepted these records under `aer/0.1` would
contradict every `aer/0.1` reader and the frozen schema).

### 1.1 A live header cut before `instrumentation` (D-210)

| | |
|---|---|
| Today (`aer/0.1`) | `execution.instrumentation` is required for `mode: live` (C.3.1). When the verifiable prefix of a capture log ends before the `instrumentation` event, `capture_mapper.py` writes `"instrumentation": []` with `unk {"/instrumentation": "ambiguous"}` under `agentdojo.capture_instrumentation@1` (D.10.4a item 5). `ambiguous` is the one reason AER-V16 allows beside a value, but the true reason is that the event was **not captured**, and an empty list reads as "no instrumentation" to any consumer that ignores `unk`. |
| `aer/0.2` | For `mode: live`, `instrumentation` is required **unless** `unk["/instrumentation"]` is `not_captured`; then the member is absent. Schema: the live branch's `required` drops `instrumentation`; a conditional (`if mode = live and not unk./instrumentation then required`) states the rule. Validator: AER-V07 (required members) learns the conditional; AER-V16 unchanged (no value beside the declaration). |
| Mapper | `capture_mapper.py` writes no member and `unk {"/instrumentation": "not_captured"}`; the rule stays `agentdojo.capture_instrumentation@1`. The mapper is the regen-batch session's; this is its one-line change after approval. |
| PROV | `agentprov-prov/0.1` already handles an import header without `instrumentation` (`unk not_recorded`); the live branch emits no instrumentation statements for an absent member. Check: one live fixture with a cut prefix derives and passes tier 4. |

### 1.2 `withheld` on a required part member (D-211)

| | |
|---|---|
| Today (`aer/0.1`) | A message part's content member is required: `text` of a `text`, `reasoning` or `refusal` part, `args` of a `tool_call`, `value` of an `other` part (`aer-0.1.schema.json` `$defs/part*`; a `tool_result` has no required content member). When capture redaction withholds it (C.13.5; `capture_redaction`), `aer/0.1` cannot declare `withheld` on a required member, so the mapper keeps the redacted placeholder value as if it were content (D.10.4a item 23; D_adapters.md l. 3723: "A redacted required member (message text) keeps its redacted value"). A consumer then reads the placeholder as the message text. |
| `aer/0.2` | One of those members (`text`, `args`, `value`; never `t`, a `tool_call`'s `name` or a blob's `data`) may be absent when `unk` declares `withheld` or `not_captured` at its pointer (`/parts/<k>/<member>`). Only these two reasons (the producer or the capture deliberately or necessarily did not expose it); not `not_recorded` (the source has no slot, which a required member cannot be). Schema: each part type's `required` list becomes conditional on the declaration; validator AER-V07 and the part checks (AER-V17's empty-assistant-text sentinel among them) read an absent declared member as unknown, never as empty. The part keeps its `t` and, where the source recorded it, `sha256` of the withheld bytes (C.3.12 already allows the digest without the content). |
| Mapper | `capture_mapper.py` writes no member, `unk {"/parts/<k>/text": "withheld"}` and keeps the `capture_redaction` issue. Regen-batch session's change after approval. |
| SEM, PROV, views | The SEM engine's marker search and the PROV engine's part entities must treat an absent declared member as unknown (no content attribute, no marker hit; an assessment that needed the text is `unverifiable`, as for any `unk`). The transcript/v1 view renders a withheld text as `null` (the view's existing `null` text form; C.15). Each is a code path to check and test, not a semantic change. |

### 1.3 Considered and left out (D-212)

| Candidate | Why not in `aer/0.2` |
|---|---|
| AER-V34 widened to verified code ranges | **Dropped by the user** (2026-10-12). Part B's measurement (`docs/reports/deferrals/part-b/README.md` §4): over `c274885..<introducing commit>`, only `agentdojo.duration_scope@1` and `agentdojo.incomplete_run@1` keep their cited passages for all 10,732 head-only `v0.k11` logs, and `agentdojo.call_id_unique_match@1` for 5,558; the cited code changed from 2024-06-06, a day after the pin, before the first head-only log was introduced (2024-06-20). The head-only logs keep the `_unverified` twins (D-84). |
| Tool-runtime delegation INFERRED for want of a wheel identity (phase-8 follow-up) | Not an `aer/0.1` limit: `actor.code.wheel_sha256` exists and AER-V34 already accepts it. What lacks the hash is the frozen `capture/0.1` identity event of a PyPI wheel. A mapper-side source exists without any format change: the backend's `uv.lock` (pinned by `session.start.runtime.lock_sha256`) records the `agentdojo` wheel's SHA-256. Routed to the mapper owner as a possible fix; not a format change. |
| A degenerate header that cannot name its task (`task.task_id` required, phase-12a proposal) | Solved by the mapper on main (`eb8c377`: a degenerate header keeps a usable task id). No format change needed. |
| `$utf16` in typed text (escaping audit) | Rejected by D-23 (adapter-layer fix, item 7); unchanged. |
| The D.12.4 candidates: `decision.replacement` (`apv:ApproverModification`), `tool_execution.requested_in`, `scope.forked_after` and `state_change.restores` (in-file branches, restores), `related.rel ∈ {spawned, spawned_by}`, `message.generated_by` → `activity`, the delta form of `model_call.input`, the collection context encoding | These are **new semantics**, not workarounds: each needs a new typed reference or enum value **and** an EF rule in the provenance catalogue, a SEM consideration and an emitter in at least one adapter (Inspect approvals and branches, FooBench restores). Today each is a disclosed, named gap that emits no wrong statement (NE-18, `inspect.branch_unsupported`, `foobench.restore_unmodelled`). Adding schema without emitters and rules is dead format; adding them with emitters is a project of its own (`agentprov-prov` catalogue changes, golden and gate-D pins). Proposed: keep them as candidates for a later version, driven by a source that needs them. |

## 2. Version discipline (D-31; `versions.py`)

| Axis | Change |
|---|---|
| `aer` | `aer/0.1` → **`aer/0.2`** for every record the writer seals from the release of this change on. `aer/0.1` stays frozen, readable and verifiable (§3). |
| `corpus_format` | **`agentprov-corpus/0.1` → `agentprov-corpus/0.2`**: `corpus-0.1.schema.json` pins `formats.aer` to the constant `"aer/0.1"` and the derivation's `aer` stage to `format: "aer/0.1"`; D-163 freezes those bytes. A new `corpus-0.2.schema.json` admits `formats.aer = "aer/0.2"` and nothing else changes in it. |
| `sem/0.1`, `capture/0.1`, `agentprov-prov/0.1`, `adprov-v2.3-compat` | **Unchanged by `aer/0.2`.** (The `apv` vocabulary moved to 0.2.0 separately, with regen items 85/86, D-500/D-501; corpus/0.2 records it.) SEM records point at AER records by id and digest; the PROV specification id stays (D-31: a format change of its input is not a specification change); the compat oracle is frozen and still reproduces the baseline byte for byte (its input is the v1 view, which is unchanged for every converted and released trace). |
| software | a minor SemVer bump (`0.2.0`), with the tag `v0.2.0` when released. |
| adapter catalogues and profiles | none required by the format change itself. The live mapper's two edits change `adapters/agentdojo` code only; its catalogue rule ids stay. |

Files: `src/agentprov/schemas/aer-0.2.schema.json` (new; built by the same schema builder with the two conditionals),
`corpus-0.2.schema.json` (new), `aer-0.1.schema.json` and `corpus-0.1.schema.json` byte-identical, `versions.py`
(`VERSIONS["aer"] = "aer/0.2"`, `VERSIONS["corpus_format"] = "agentprov-corpus/0.2"`, a new `READABLE_AER = ("aer/0.1",
"aer/0.2")`), `test_format_freeze.py` extended to pin **both** schemas (0.1 as today, 0.2 once approved and frozen).

## 3. How `aer/0.1` records stay readable and verifiable

1. **Reader** (`aer/reader.py`): dispatches on the header's `aer` member; `"0.1"` loads under the frozen 0.1 rules,
   `"0.2"` under 0.2. An unknown value is refused as today.
2. **Validator** (`aer/validate.py`): the version selects the schema and the two conditionals; every other check is
   shared. An `aer/0.1` record that omits `instrumentation` or a declared part member stays **invalid**, as it is today:
   the relaxation never applies retroactively.
3. **Writer** (`aer/writer.py`): writes `aer/0.2` only. Nothing re-seals an `aer/0.1` record in place.
4. **Corpora**: a sealed `agentprov-corpus/0.1` corpus verifies at every level with this build (its schemas are the
   frozen 0.1 files, D-163), derives PROV from its stored `aer/0.1` records (`derive`), and recomputes them (`recompute
   --stages sem,prov,validation`). `recompute` with `--stages aer` re-maps into `aer/0.2`: the H.8.4 classification
   reports the change as **explained** (a declared format version change), never `unexplained_change`.
5. **One format per corpus version.** A corpus version holds records of one AER version (as H.2.5 holds one version per
   catalogue); a working corpus begun under 0.1 refuses a 0.2 import (G4, the `aer` stage's `format`), so the
   regeneration round builds new corpus versions.

## 4. Stage identities, manifests, golden pins and gates

| Item | Effect |
|---|---|
| `derivation.json` `aer` stage | `format: "aer/0.2"` and the `engine_code_sha256` of `adapters/runner` + `aer` move: a new `fn_digest`. |
| `sem`, `prov`, `validation` stages | `engine_code_sha256` moves where `aer/` code is hashed (`validation` hashes `aer/validate.py`); `sem` and `prov` only if their code changes for the absent-member paths (§1.2). |
| `corpus.json` | `format`/`formats.corpus` `agentprov-corpus/0.2`, `formats.aer` `aer/0.2`; corpus SemVer: a **minor** bump for every corpus (D-31's corpus axis), with the change noted in `CHANGELOG.md`. |
| Golden pins | Every AER byte pin moves (the header's `aer` member): `tests/adapters/*/aer_digests.json`, the C.16 vectors (resealed, C.16.1/C.16.2) and the C.14.5 SEM example (its `aer_digest`), `tests/golden/prov_digests.json` and `gate_d_digests.json` (PROV embeds the AER digest), FooBench's golden AER, the phase-10d/10f fixture pins. The v1 transcript views and the compat graphs do **not** move (gates A1, A2, B: byte identity with the baseline holds). |
| Gate R | R1/R2 compare views and compat graphs: unchanged. R3 compares projections that skip the `aer` member: unchanged. |
| Gate D | re-pinned (golden and full), as for every catalogue change. |
| Gate E | unchanged (it reads compat edges and the map). |
| Gate C | C2, C5, C6 compare views, graphs and validators of the compat port: unchanged; C6's live AERs are mapped fresh and gain `aer/0.2`, with no observation (the projection skips the format member). |
| `stats`, `datasheet` | `formats.aer` is shown as recorded; nothing else. |

## 5. Downstream (the regeneration round)

**Every AER digest moves, so every corpus is regenerated** in the round the user approves separately: AgentDojo
2024-06 and head, ROPE, AgentDyn, the survey's AgentDojo runs and AgentHarm, Mandate, adprov-v1 release, and every
corpus imported later (DTap, the phase-10d/10f/10g/10h/10i sources). The regeneration is a re-map from stored raw
(`recompute --stages aer,sem,prov,validation`); no network. Records whose content changes beyond the header: only live
records with a cut prefix or a redaction (no stored corpus holds a live record today; the capture mapper's tests,
`tests/adapters/agentdojo/test_capture_mapper.py`, cover both cases, and every capture fixture pin is regenerated). The round already re-maps every AgentDojo-family and Inspect corpus for items 3,
13, 14 and 17; doing the format change in the same round costs no extra regeneration.

Merging the code moves the stage identities above, so it follows the phase-12a resume rule: no import is paused across
the merge.

## 6. What stays frozen

`aer/0.1` (schema bytes, reader and validator semantics), `capture/0.1`, `prov/compat/adprov_v2_3` (the baseline still
reproduces byte for byte: gates A1, A2 and B run in the pre-merge checks), `sem/0.1`, `agentprov-prov/0.1` (its
specification id; code paths for absent members are bug-compatible additions, tested on the golden set).

## 7. Implementation plan after approval (for sizing)

1. `aer-0.2.schema.json` + `corpus-0.2.schema.json` from the builders; reader/validator dispatch; writer emits 0.2.
2. Absent-member paths in SEM, PROV and the transcript/v1 view, each with a test on a synthetic record.
3. Freeze tests for both versions; the CLI's `info` lists both readable versions.
4. Routed (regen-batch session): the two `capture_mapper.py` edits (§1.1, §1.2), re-pinning the capture fixtures.
5. Golden and gate-D pins regenerated in one commit, with a byte prediction in `regen-batch.md` (an item of its own:
   "every AER digest; corpus format 0.2").
6. Spec: C.3.1 and the part tables, C.17 (AER-V07 conditionals), H.2 (`agentprov-corpus/0.2`), M (versions), D.10.4a
   items 5 and 23 resolved.
