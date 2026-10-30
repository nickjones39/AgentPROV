# Phase 10j: routed requests

Status 2026-10-14. Phase 10j adds new files and append-only registry entries only. The items below change files other
sessions own; each says what is needed, why, and how it was measured. Ids come from the ledger (`tools/reserve_id.py`).

## R-10j-1. An agentdojo-family redaction of the logged `pipeline_name` (D-255; user decision 2026-10-14)

**Owners.** memo-ozdincer (`phase-10q-ozdincer`, D-476) builds the shared `[[family.agentdojo.redact]]` table and
`adapters/agentdojo/redact.py`, with scopes `model_id` and `pipeline_name`. The regen-items session wires it into the
TraceLogger mapper and adds EnvironmentOptim's profile rules. Sent through the orchestrator on 2026-10-14.

**Finding.** Measured on all 6,016 local-Qwen logs of EnvironmentOptim @ `febf82d8`.
- **Raw:** exactly one field holds the cluster home path: the top-level string `/pipeline_name`, once per log. No other
  string in those logs holds it, and no slashed form (`/ceph/ssd/students/…`) occurs. One account segment.
- **Shapes** (account masked):

  | Shape | Logs |
  |---|---:|
  | `_ceph_ssd_students_<account>_qwen3_5` | 5,910 |
  | `_ceph_ssd_students_<account>_qwen3_5-2B` | 53 |
  | `_ceph_ssd_students_<account>_qwen3_5-4B` | 53 |

  The 104 `qwen3_5-9B_baseline*` logs use the unsuffixed form.
- **AER today:**
  - `mapper.py` copies the value verbatim to `ext.agentdojo.pipeline_name` (with its lex hint, so transcript/v1
    reproduces it).
  - `identity.resolve` compares it with the row's `pipeline_name` list, or with the pipeline directory, and raises
    `agentdojo.pipeline_name_mismatch`. The redaction must apply before that comparison, or the row must list the
    redacted label: the identity table never carries the raw value.

**Request.**
- **Scope:** `pipeline_name`.
- **Structural pattern:** `^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$` (or the prefix-only
  form `_ceph_ssd_students_(?P<span>[^_/]+)_`).
- **Template:** `_ceph_ssd_students_{span12}_{leaf}`. This uses D-182's vocabulary: a salted short digest of the account
  span; the literal prefix and the model leaf are kept, because the D-254 rows for `-2B`/`-4B` rest on that leaf.
- **As in D-182:** the locator stays on the raw `/pipeline_name`, the pointer is tagged D and cites the redaction rule,
  and an info issue is sealed. Raw ships as is (D-186 (c)).

**Until it lands:** the 6,016 logs are `select.redaction_pending` in `environmentoptim-agentdojo`.

## R-10j-2. An AgentDyn `history` part for 620 DRIFT runs (R-3; user decision 2026-10-14)

**Owner.** The regen-batch session (owner of `agentdyn.profile.toml`), through the orchestrator.

**Finding.** The fetch was approved by the user on 2026-10-14: a blob-less bare clone of `SaFo-Lab/AgentDyn`, 3.7 MB,
26 commits, logged in `~/.agentprov/migration-work/phase10j/acquisitions.jsonl`, with no blob contents.
- All 620 DRIFT logs in EnvironmentOptim's `runs/gpt-4o-mini-2024-07-18-drift/` are byte-identical (git blob ids) to
  AgentDyn's own files at the same path.
- AgentDyn holds them in every commit from `2d4ad05a` (2026-02-14) to `785b9127` (2026-04-09). At `6623a721`
  (2026-04-19) the directory was replaced: the pinned head `5353cf76` holds 648 different files there, the variant-A
  row of RT-8.
- All 4,878 of EnvironmentOptim's DRIFT logs are therefore in AgentDyn's history; none of its 6,120 new `v1.k14` logs
  is.

**Consequence (user decision).** The 620 belong to AgentDyn as a `history` part, not to EnvironmentOptim.
`environmentoptim-agentdojo` registers them `select.owned_elsewhere` (owner `agentdyn`).

**Request.**
- Add an `agentdyn` part `history` for `runs/gpt-4o-mini-2024-07-18-drift/**`, pinned at `785b9127` (the last commit
  that holds all 620), variant `drift.k18.messages`.
- It needs its own identity row: model `gpt-4o-mini-2024-07-18`, defence `drift`. This is the row phase 10l's stand-in
  lacked, which raised `agentdojo.pipeline_name_mismatch` on all 620.
- Bytes: the 620 blobs are absent from the blob-less clone. They can be fetched from GitHub by blob id (a fetch that
  needs the user's yes), or read from EnvironmentOptim's pinned tree, which holds the same blobs.
- Phase 10l mapped all 620 cleanly (`~/.agentprov/migration-work/phase10l/mapping/environmentoptim.json`: 620/620
  valid).
- Licence: AgentDyn's (MIT).

## R-10j-3. A `url` download pin as an archive input (Figshare 32657856; D-252)

**Owner.** The runner's owner (`adapters/runner/importer.py`, `cli/import_.py`), through the orchestrator.

**Finding.** `agentprov import --input FILE --verify-against-pin` builds an `ArchiveTree` only for the pin kinds in
`DOWNLOAD_PIN_KINDS = ("zenodo", "hf")` (`runner/importer.py`). `raw.fetch.verify_download` already accepts a `url` pin
(sha256, md5, size). The DCA artefact is a Figshare file (`https://ndownloader.figshare.com/files/65496114`), so
`dca-agentdojo` has no import path today. Census §1 said a `url` pin needs no change; that holds for `raw/`, not for the
runner (corrected here).

**Request.**
- Accept `url` in `DOWNLOAD_PIN_KINDS`.
- In `ArchiveTree`, a `url` pin's container label is the pin's `file` (the deposit's file name; the URL's last segment is
  a numeric file id) and its origin is `Origin.url(url, retrieved)`. `Recipe` must then allow `file` on a `url` pin, or
  the label comes from a new optional key.
- Alternative: a `figshare` pin kind (`doi`, `file_id`, `file`) whose origin keeps the DOI. This is a `raw/` and
  `origins` change, larger.

**Until then:** the census maps every DCA log with the `member` origin an import would give it (all 16,221 sealed in
release mode), and the registry parts stay `planned`.

## R-10j-4. A negative logged `duration` makes the AER invalid (agentdojo mapper; regen-batch session)

**Finding.** Two Figshare CaMeL logs record `duration` −0.2246 s and −0.6300 s (the runner's clock went backwards, or it
subtracted the wrong way). The TraceLogger build writes the value to the scope's `t/dur_s`, the schema's `minimum` 0
rejects it (`aer.schema.pattern` at `/t/dur_s`), and the log cannot be sealed. On import it would be a failed execution.
Logs: `camel/logs_camel_gptoss20b_openrouter_agentdojo/openai_gpt-oss-20b+camel/travel/injection_task_3/none/none.json` and
`camel/logs_camel_qwen36_27b_full_agentdojo/qwen3.6:27b+camel+secpol/workspace/user_task_11/important_instructions/injection_task_13.json`
(under `DCA_AgentDojo_artifact_v1_20260612/results/logs/`).

**Request.** When the logged duration is negative, write no `dur_s`, add `unk {"/t/dur_s": "inconsistent"}` (or the
closest C.3 reason), keep the raw value as a lexical `ext` note, and seal an info issue (e.g. `agentdojo.negative_duration`).
Byte-neutral for every stored corpus that has no negative duration. A test can build a synthetic log.

## R-10j-5. A tool literally named `none` trips the sentinel check (DRIFT build or the AER validator)

**Finding.** In one Figshare DRIFT log
(`drift/runs_agentdojo_full_gptoss20b_compat_module/gpt-oss:20b/slack/user_task_10/important_instructions/injection_task_2.json`)
the model called a function named `none`, and the runner logged it as called. The DRIFT build copies the name into the
tool execution's `name` and the message part's `name`. The validator's sentinel rule (`aer.sentinel`;
`aer/validate.py` `_SENTINELS`) refuses `none` as a placeholder, so the log cannot be sealed.

**Request (owner's choice).**
- (a) The validator exempts values that are observed verbatim (evidence O, with a source locator): a logged name is data,
  not a placeholder (core change, `aer/`).
- (b) The DRIFT and TraceLogger builds keep such a name only in a lexical `ext` field and write the record's `name`
  through an escape the validator accepts (adapter change).

Until then, the census counts this source's DRIFT part over 2,846 sealed logs.
