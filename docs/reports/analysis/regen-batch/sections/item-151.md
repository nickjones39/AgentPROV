## Item 151: D-219's adapter half, crash-path degenerate AERs seal (deferrals part C; routed by the orchestrator 2026-10-22, pre-round review #29; branch the pre-round integration branch (ac7526c4))

**What changes.**
- On the job-failure path (a crashed or limited map job, D.2.8 case 3) the families that name the task only from the
  parsed value now write `unk {"/task/task_id": "not_captured"}` when no value was read: the AgentDojo/TraceLogger
  family (DRIFT delegates to it, and the results dialect, D-471), adprov and FooBench. `aer/0.2` allows the omission in
  a degenerate file only (D-219, AER validator). A unit whose value was read but holds no task id keeps
  `not_recorded` and is still refused.
- FooBench's degenerate header without a task no longer cites the unread header line (`ev` D, no `src`).
- The write-gate fallback (`importer._seal`: the mapper's records were refused, so the unit is rebuilt by
  `degenerate_unit` with no value) also reaches `not_captured`, although the task id was read and mapped: the degenerate
  AER is built from the stored artefact alone and does not carry the refused mapping (re-check RC-6; recorded in D-219).
- The runner's degenerate run scope cites the whole artefact (`{"a": "a0"}`, C.9.1) instead of its parsed root when no
  value was read: a root pointer does not resolve for bytes that are not JSON (`aer.locator.dangling`). Per-item units
  keep their own locator.
- `tests/adapters/runner/test_job_failure_degenerate.py`: agentdojo, adprov and foobench flip from `refused` to
  `seals`; the dispositions, carved-blob and pinned-object runner tests follow (an unparseable file is now a degenerate
  AER, not a failed unit).

**What moves (class 1).** The `adapter_code_sha256` of the agentdojo, adprov and foobench families, and the `aer` stage's
`engine_code_sha256` (`adapters/runner/`). AER bytes change only for crash-path degenerate AERs, which no stored corpus
holds as sealed AERs today (they were registered `map.adapter_defect` with the artefact stored). No pin moves.

**Item 20 (the capture-mapper half) is built on the same branch:** a live header whose capture ends before the
instrumentation event omits `instrumentation` with `unk not_captured` (D-210), and a redacted required part member (a
message text, a reply argument, a refusal or reasoning text; a dump or response blob's redaction at or under its
pointer) is omitted with `unk withheld` (D-211), instead of keeping the redacted value. Capture AERs with a cut header
or a redacted message part change; no committed fixture or vector has one. Tests: `test_capture_mapper.py`
(`..._d210`, `..._d211`).

