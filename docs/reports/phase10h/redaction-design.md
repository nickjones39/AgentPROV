# Phase 10h part B: redacting workstation account paths (proposal D-182; not applied)

D-146 (user-approved) puts "redaction of model ids that carry workstation account paths" into the profiles of
kexin-xu-01 (and memo-ozdincer). This note proposes how a profile declares it, what the AER records, how identity stays
honest, and what remains true of the raw store. **Nothing here is implemented.** The profile schema and the Inspect
mapper are not changed by phase 10h. The change goes to `docs/reports/analysis/regen-batch.md` through the orchestrator
(`routing.md` R-H1), because it moves the adapter digest of every Inspect corpus.

No account name appears in this note, the census files or any committed file. Paths are shown by their structure only:
`<account>` and `<job>` stand for segments that were never printed.

## 1. What the census found (part A)

The scope is wider than model ids. Counts come from reading every member of every log through `agentprov.ingest`
(`census.json`, `account-paths-by-log.json`), and from mapping every log in memory with the current mapper
(`map-census.json`).

| Source | Where the account path is in the raw log | Logs | Reaches the AER today (mapper `inspect.eval` 0.1.0) |
|---|---|---|---|
| kexin-xu-01 | header `eval.model` and every model id derived from it: `vllm//workspace/shared/outputs/<job>/<run>/merged` (12 logs) and `vllm/Qwen/Qwen3-14B:/workspace/shared/outputs/<job>/<run>/lora` (6) | 18 (792 samples) | yes: `actor:/model/requested` (792), `model_call:/served_model` (3,129), `model_call:/params/transmitted/model` (2,638), `message:/ext/inspect/model` (3,129), `state_change:/patch/*/value/model` (2,141), `…/value/message/model` (680), `…/replaced` and `…/value` (680 each), `scope:/ext/inspect/events/*/event/message/message` (60, harness log lines) |
| kexin-xu-01 | header `eval.dataset.location` (and `_journal/start.json` of the 2 unfinished logs): `/home/<account>/.cache/inspect_evals/…`, two accounts | 68 (all) | no (the mapper does not copy `dataset`) |
| fragfuse | header `eval.dataset.location`: `/Users/<account>/Library/Caches/inspect_evals/…` | 28 | no |
| fragfuse | header `plan.steps[*].params(_passed).memory_bank_path`: `/Users/<account>/inspect_evals/src/…/bank_<x>/bank_<n>.jsonl` | 136 | no (the plan is not copied) |
| fragfuse | header and sample `error.traceback(_ansi)`, error events | 20 logs; 34 samples | yes: `scope:/ext/inspect/error/traceback(_ansi)`, `scope:/ext/inspect/events/*/event/error/traceback(_ansi)` (34 each) |
| fragfuse | sample `metadata.carrier_query_path` (a second account) | 4 (4 samples) | yes: `execution:/ext/inspect/sample_metadata/carrier_query_path` (4) |

Not account paths, and outside this proposal:

- AgentHarm's fictional file trees (`/home/user/…`, `/home/Desktop/…`, `/Users/Downloads/…` and similar) in prompts and
  tool outputs. They are benchmark content.
- One kexin sample whose model output names a `/Users/<name>/` path (in the message text, the refusal explanation and a
  state patch). It is model-authored content. Redacting it would edit evidence of agent behaviour, so it stays verbatim
  and is disclosed.

**Consequence for fixtures (user decision 2026-10-12, D-185):** every finished log of both sources holds an account path
in its raw bytes, and so do the two unfinished ones (`_journal/start.json`). Raw bytes are never edited, so no real log
is committed. The tests use synthetic logs (made-up account) and the pinned fetch cache.

## 2. Requirements

1. **Never record the original.** No AER, SEM, PROV, index row, register row, report or log line holds the account
   segment, or a digest of the whole id short enough to be reversed by guessing the account.
2. **Observed, not invented** (invariant 2). The redacted value stands for an observed value, so its locator stays on
   the raw field it came from. The record says that a profile rule transformed it. No model name is guessed: a label never
   claims a base model the id does not state.
3. **Identity stays distinct.** Different checkpoints keep different labels; the same checkpoint gets the same label in
   every log, sample, run and process (determinism, invariant 4). A label can never equal an unredacted id of another log.
4. **Adapters supply data, the engine owns semantics** (invariant 1). The profile supplies patterns and labels; the
   mapper applies them through one versioned catalogue rule.
5. **Raw is untouched** (invariant 3). Redaction acts on the parsed value inside the mapper, never on stored bytes.

## 3. Profile declaration (schema change: `family.schema.json` gains `redact`)

A closed array of rules in `[family.inspect]`. Each rule names its scope, a pattern for the span to replace, and a
template built only from safe placeholders:

```toml
# kexin-xu-01-agentharm (proposed; version stays 1 until the corpus is released, AD-18)
[[family.inspect.redact]]
id = "local_checkpoint_path"
scope = "model_id"
pattern = '/workspace/shared/outputs/[^\s"]+'          # the span replaced; it never names an account
replacement = "<local-checkpoint:{span12}/{leaf}>"
leaf = '^(merged|lora)$'                               # {leaf} only when the last segment matches; else "?"
note = "18 logs; checkpoint paths of three fine-tuned Qwen3-14B runs (census, docs/reports/phase10h/)"

# fragfuse-agentharm (proposed)
[[family.inspect.redact]]
id = "home_account"
scope = "harness_text"
pattern = '(?<=/Users/)[^/\s"]+(?=/)'                  # only the account segment
replacement = "<account>"
note = "tracebacks (34 samples) and metadata.carrier_query_path (4)"
```

- `scope = "model_id"`: the mapper first collects the observed model-id strings of the unit (header `eval.model`,
  `eval.model_roles`, every model event's `model`, `output.model`, message `model`, `requested_model`) that match the
  pattern. It then replaces each such **whole id string** wherever the mapper copies it, including inside longer harness
  strings (state patches, logger lines). Exact-string replacement of ids that were observed in model fields cannot reach
  benchmark content by accident.
- `scope = "harness_text"`: the pattern is applied only to fields the harness wrote and the mapper copies into `ext` or
  `params`: the sample `error`, error and logger events, `sample_metadata`, header `task_args`, `revision`,
  `model_generate_config`. It never applies to messages, tool calls, tool results, fixtures or judgements (content).
- `{span12}` is the first 12 hex digits of SHA-256 over the matched span **salted with the profile id** (for example
  `sha256("kexin-xu-01-agentharm\0" + span)`). It keeps checkpoints apart and is stable across runs. Against someone who
  already has the upstream path it reveals nothing new; it cannot be reversed from the label alone. `{leaf}` is the last
  path segment only when it matches the rule's `leaf` pattern.
- The schema rejects a rule whose `replacement` uses anything but `{span12}`, `{leaf}` and literal text, and a profile
  whose rules could make two different spans produce the same label (the validator checks label collisions per unit
  and the census per corpus).

Resulting labels for kexin's three checkpoints: `vllm/<local-checkpoint:hhhhhhhhhhhh/merged>` (two distinct `{span12}` values `h…`)
and `vllm/Qwen/Qwen3-14B:<local-checkpoint:hhhhhhhhhhhh/lora>`. The `vllm/` provider prefix and the stated base model
`Qwen/Qwen3-14B` are kept, because they are observed and carry no account.

## 4. What the AER records

Per redacted value (no new AER field; `aer/0.1` stays frozen):

- **The value** is the redacted label, at its usual place (`actor.model.requested`, `model_call.served_model`, …).
- **Evidence:** the pointer is tagged `D` and cites a new catalogue rule `inspect.value_redacted@1` (class D: a
  deterministic transformation of an observed value, specified by the profile). The record's `src` locator still points at
  the raw field (for example `a1:/eval/model`), so the derivation leads back to the observed bytes.
- **Which rule:** `ext.inspect.redacted` on the record lists `{"p": "<pointer>", "rule": "<profile id>@<version>#<rule
  id>"}` for each redacted pointer. Neither the original nor its digest is recorded.
- **Execution level:** a seal issue `inspect.value_redacted` (severity `info`) with the number of redacted pointers. The
  index, `stats unknowns` and the datasheet can then count redacted executions, and the C.3.1 artefact catalogue can
  describe the class (`artefacts.toml`: one entry, `recorded_as = { issues = ["inspect.value_redacted"] }`).
- **PROV:** the agent and model entities take their labels from the AER, so they carry the redacted id. The engine and its
  catalogue need no change (invariant 5 holds: the change is confined to `adapters/inspect/`).

## 5. Identity and statistics

- Execution ids and `source_key` come from raw digests and do not change.
- `stats` facets by model and `logical_key` group by the redacted label. The three kexin checkpoints stay three groups.
  A reader cannot mistake them for a hub model, because the label says `local-checkpoint`.
- The datasheet states for each redacted corpus: the rule ids, the number of executions and pointers, and that the raw
  objects hold the originals (§6).

## 6. The raw store (open question for the user: D-186)

Redaction does not touch raw objects, and every log of both sources carries an account path in raw: the container, the
`header.json` member object and, where listed above, sample member objects. G.9.5 and H.4.5 say that when a personal
datum is found in third-party raw, the artefact is **withheld from a public release together with the AER, SEM and PROV
of the affected executions**. Applied as written, nothing of either corpus could ever be released publicly. Options:

| | Raw in a public release | AER/SEM/PROV in a public release | Spec change |
|---|---|---|---|
| (a) G.9.5 as written | withheld | withheld | none; both corpora stay private |
| (b) **Withhold raw only** (recommended) | the containers and the member objects that hold an account path are withheld and cited by their pinned public origin (the git blob at the pin; members re-derivable by expanding it); clean member objects are shipped | shipped, redacted | G.9.5/H.4.5: a "raw-only" withholding for personal data already published at the pinned origin; `verify chain` checks a withheld raw object against its pin instead of its bytes |
| (c) Ship raw as is | shipped (the names are public at the pin) | shipped, redacted | G.9.5: an exception for data already public at the pin; weakest privacy position |

None of this affects the private corpora or the trial imports. It must be settled before either corpus is packaged.

**Update 2026-10-13.** The withholding work merged on main (D-230–D-237) provides option (b)'s mechanism: profile
`[withhold]` rules with scope `object` (D-235), and `WITHHELD.json` entries that keep pinned origins and stage digests
(D-230). The patterns can describe the path structure without naming an account. Because a hit in a derived file
withholds the whole execution, (b) depends on D-182 being applied first (D-186 addendum).

## 7. Downstream effects (for the regeneration batch)

- `adapters/inspect/mapper.py`, `family.schema.json`, `rules/inspect.rules.toml` (new rule; catalogue version bump) and
  `artefacts.toml` change. The adapter code digest moves, so **every Inspect corpus** (ast-survey-agentharm and the trial
  corpora of whistlebench and both phase-10h sources) changes stage identity, and `recompute --check` reports the
  bump as deliberate. AER bytes of corpora without a `redact` table change only through the catalogue-version list in
  the AER header (`rules`), if the inspect catalogue version is bumped. That is the cost of putting the rule in the
  shared catalogue rather than in each profile.
- Goldens: the survey goldens move with the catalogue version. kexin and fragfuse have no goldens yet.
- Tests: the two strict xfails in `tests/adapters/inspect/test_phase10h_agentharm.py` turn into passes when the rule is
  applied. The test that pins today's verbatim copy is then deleted.
- memo-ozdincer (agentdojo family, D-146) needs the same declaration in the AgentDojo family schema. This proposal keeps
  the table shape family-neutral (`redact` with `scope`, `pattern`, `replacement`) so that the agentdojo owner can adopt
  it unchanged.

## 8. Rejected alternatives

- **Editing the raw bytes, or storing a scrubbed copy as the primary artefact.** This breaks invariant 3 and the digest
  chain: the pin no longer vouches for the bytes.
- **Dropping the 18 kexin logs.** This loses the only fine-tuned models in either source; the paths are an artefact of
  the serving setup, not of the runs.
- **Recording the full SHA-256 of the original id.** It can be confirmed by guessing the account, and it adds nothing
  over a salted short label.
- **A free-text label table keyed by the original id.** The profile, which is committed to Git, would then have to hold
  the original id.
- **Redacting every string that matches `/Users/…` or `/home/…` anywhere.** That would edit model output and benchmark
  content (AgentHarm's fictional paths) and so falsify evidence.
