# D-510: workstation account paths in directory names, under the shared agentdojo redaction

Status: **approved by the user 2026-10-14, option (A)**; recorded as D-510 in DECISIONS.md. The census path lint is approved and assigned to the regen-items session. Requested by the orchestrator for phase 10j's R-10j-1: EnvironmentOptim
names each pipeline directory after its logged `pipeline_name`,
`runs/<arm>/_ceph_ssd_students_<account>_qwen3_5[-2B|-4B]/<suite>/<task>/<attack>/<file>.json`, in 6,016 logs (13 of them
nest one level deeper). The regen-items session wires the shared module (D-476) into the TraceLogger build. Facts are
cited from the code at `phase-10q-ozdincer` (all under `src/agentprov/`).

## 1. Where an origin path goes, and what checks it

| Place | Holds the git origin path? | Checked against what |
|---|---|---|
| AER `artifacts[].origin` | yes (`ArtefactRef.to_json`, `adapters/types.py:53-58`) | schema shape only; `o` locators resolve **inside that object** (AER-V21, `aer/validate.py:716-718`). Raw bytes are resolved by sha256 only |
| AER `ext` copies | TraceLogger copies `pipeline_name` to `ext.agentdojo.pipeline_name`; layout facets are not written (`pipeline_dir` only drives identity) | no check |
| SEM | no origin or path handling found in `sem/` | n/a |
| PROV | **yes**: the raw entity carries `apv:originPath` from the AER origin (`prov/rules/top.py:30-38, 88-103`); the entity IRI is path-free (`raw:sha256-<hex>`) | derived from the AER |
| `executions.jsonl` | no: `source_key` is `sha256:<hex>#<JCS loc>` (`corpus/index.py:449-457`); the execution id hashes sha256 + loc only (`aer/ids.py:139-157`) | n/a |
| register | yes: path subjects `{snapshot_id, path}` from ingest events (`corpus/register.py:115-128, 240`) | n/a |
| `raw/origins.jsonl` | yes, one row per origin (`raw/origins.py:366-382`) | `verify --against-pins` (`corpus/verify.py:662-697`) |
| `WITHHELD.json` | yes, `entries[].origins` (`corpus/withheld.py:254-272`) | equal to `origins.jsonl` (`verify.py:970-977`) |
| `raw/members.jsonl`, `checksums.sha256`, datasheet, `corpus.json` | no per-file origin path (member labels and the snapshot's `subtree` only) | |

What reads the AER origin path:
- **`verify --level chain`** compares each AER's `{(sha256, role)}` with the index and the origin *count* with
  `origins.jsonl` (`verify.py:712-774`). It never compares the AER origin object with `origins.jsonl`.
- **A re-map** (`recompute --stages expand,aer`) rebuilds candidates from `origins.jsonl`, labelled by the raw path
  (`corpus/rawtree.py:151-213`). It then maps them again, so the AER origin is produced by the mapper each time.

## 2. Options

### (A) Recommended: redact in the AER, which carries over to PROV; keep corpus-level raw descriptors as they are

1. **The shared module needs no new scope.** It replaces each observed string of a matched scope as a whole wherever
   the record holds it, including **inside longer strings** and in JSON-Pointer-escaped forms. When the TraceLogger build
   registers the logged `pipeline_name` as observed in scope `pipeline_name`, the account-bearing directory segment
   inside `artifacts[0].origin.path` is rewritten too: the walker covers the header's `artifacts` member and every
   `ext` copy.
   - **Prerequisite.** The directory segment must equal the logged `pipeline_name` byte for byte. 10j measured that it
     does ("the logged `pipeline_name` equals the directory everywhere").
   - **Fallback.** If a source ever differs, a third scope `path_segment` is needed, with the facet value as the observed
     string. It is a few lines in `redact.py`, but none is proposed until a source needs it.
2. **Resolution stays sound.** The redacted AER still names its raw object by sha256, which is how every tier resolves
   raw. `o` locators (`{"a":"a0","o":"/path"}`) resolve into the AER's own, redacted, origin object, so they stay valid.
   - Chain passes: it compares digests and origin counts, never the path.
   - A re-map is byte-identical: the mapper re-applies the same pure, salted redaction to the same raw path from
     `origins.jsonl`, so no `unexplained_change` arises.
3. **PROV** inherits the redacted `apv:originPath`. **SEM** holds no path.
4. **Corpus-level raw descriptors ship as they are:** `raw/origins.jsonl`, register path subjects and `WITHHELD.json`
   origins. They describe the raw object and repeat the path that is public at the pin, so they are covered by D-186 (c)
   ("raw ships as is"), not by D-182 (AER/SEM/PROV). `executions.jsonl` holds no path.
   - **This leaves one exposure.** A public release of the corpus would show the account in those three files, exactly
     as the raw bytes and the pinned repository already do.
5. **Identity (question (b)).** The TraceLogger build reads the `pipeline_dir` facet from the **raw** path (the mapper
   needs it to match the layout). It calls `redact_value(rules, "pipeline_name", facet, salt=<profile id>)` before
   `identity.resolve`, so the identity rows are keyed by the **redacted directory label** and list only redacted
   `pipeline_name` values.
   - With 10j's pattern `^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$`, the leaf is kept, so the
     D-254 `-2B`/`-4B` rows still distinguish the three checkpoints. The model comes from the README (D-255) or the leaf,
     never from the account.
   - The arm path keys (`runs/<arm>/<redacted dir>`) hold no account. The same pattern applies to the 13 nested logs,
     whose extra levels are not account-bearing.
   - 10j's table author computes labels with `redact_value` from the cache (as `tools/agentdojo/phase10q_trial.py` does
     here), so no raw directory name enters Git.
6. **Tests the wiring must add.** A synthetic log under a made-up account directory: the AER, SEM and PROV bytes hold no
   account path in any form; chain passes; a re-map is byte-identical; the identity row resolves on the redacted label.
   These match `tests/adapters/agentdojo/test_rescont.py::test_no_account_path_reaches_sem_or_prov` and the BF-21 key
   tests.
7. **Byte classes and digests.**
   - No stored corpus moves: the 6,016 logs are held (`select.redaction_pending`) and never imported.
   - The agentdojo `adapter_code_sha256` moves with the regen-items wiring (already in D-479's entry for this branch).
   - The `aer` stage identity moves only through R-10q-3.
   - 10j's profile gains `[[family.agentdojo.redact]]` and its identity rows change to redacted labels (D-31 version
     bump if 10j's profile is already released; it is not).
   - The AERs of the 6,016 logs differ from a hypothetical unredacted import in `artifacts[0].origin.path`,
     `ext.agentdojo.pipeline_name`, `agent.model` (where identity read it) and the redaction listing, `evf` and `rule`
     entries. PROV differs in `apv:originPath` and in whatever derives from those.

### (B) Also redact the corpus-level descriptors, with a private mapping

Rewrite the paths in `raw/origins.jsonl`, the register subjects and `WITHHELD.json`, and keep a private redacted-to-raw
mapping. **Not sound:**
- `verify --against-pins` looks raw paths up in the pinned tree (`verify.py:662-697`) and would fail on every redacted
  row.
- A re-map labels candidates by the `origins.jsonl` path (`rawtree.py:151-213`), so layout facets, path register
  subjects and `unreproducible()` would read redacted labels.
- The mapping would be evidence nobody else can check, which breaks the public recomputability that D-230 relies on.
- It also contradicts D-186 (c): raw origins are raw descriptors, public at the pin.

### (C) Keep holding the logs

Keep the 6,016 logs as `select.redaction_pending` (D-324). That is safe, but they never enter a corpus: about 6,000 of
EnvironmentOptim's runs stay out until (A) or (B).

## 3. Does this generalise? (question (c))

- **The rule.** Any source whose directory names carry an account path needs (A): the redaction of the observed string
  that the directory repeats, plus identity keyed by redacted labels.
- **memo-ozdincer (this branch).** Every selected origin path is account-free (`results/…`, `runs/results/…`); the
  accounts are only in the containers' `model` values, which D-476 already redacts. The census tool's leak check covers
  the plain, pointer-escaped and whole-string forms in every sealed AER.
- **D-182's AgentHarm sources (kexin-xu-01, fragfuse).** The phase-10h census found the account paths in log *content*
  (`eval.dataset.location`, checkpoint model ids, tracebacks, one metadata field), not in file or directory names
  (`DECISIONS.md` D-182). Their logs' paths were not reported as account-bearing. This has not been re-measured here.
- **Proposed safeguard.** A one-pass lint in each family's census or trial tool: scan every selected candidate's
  origin path with the redaction patterns' structure (`/home/<x>/`, `/Users/<x>/`, `/scratch/<x>/`, `/mfs1/u/<x>/`,
  and munged `_home_<x>_`/`_ceph_…_<x>_` forms). Report counts only. Without a declared redaction rule that covers the
  segment, the import is refused (or the files are held as `select.redaction_pending`). This catches the case in every
  family before import, rather than per source.
- **Inspect paths.** The Inspect family's D-182 module has no such scope yet. If an Inspect source ever names
  directories after accounts, the same approach applies there through its own `observed_model_ids`-style registration.

## 4. Recommendation

(A) for 10j, wired by the regen-items session with the existing `redact.py` (no new scope while the directory equals
`pipeline_name`), plus the census-time path lint as a family-level safeguard. Not (B), since it breaks pin verification
and re-mapping.
