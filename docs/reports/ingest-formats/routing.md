# Ingest formats: items routed to other owners (2026-10-13)

The ingest-formats session owns `ingest/`, `raw/members.py` and the expand path, `io/workers.py` budgets, their tests
and spec text. These needs fall outside it and go through the orchestrator.

| # | Need | Owner | Why |
|---|---|---|---|
| RI-1 | A new origin kind for the split descriptor object (for example `split {"archive": "zip", "parts": ["sha256:…", …]}`): `raw/origins.py` (`ORIGIN_KINDS`, field checks), spec C.3.12 and H.2.3, `corpus/manifest.py` (snapshot origin kinds, l. 836), `corpus/rawtree.py` (re-mapping treats it like `member`: no input label) | orchestrator (data model, `corpus/`) | D-244 (user choice (a), 2026-10-13). An AER never cites the descriptor, so `aer/0.1` is untouched; only `raw/origins.jsonl` rows carry the new kind |
| RI-2 | The importer: declare split parts from the profile or pin (`(sha256, size)` in order), store each part, call `raw.members.store_split_descriptor`, record its origin (RI-1), and pass `ContainerSpec(..., parts=...)` | deferrals session (archive inputs, part A) | D-243/D-244; the parts are pinned by their HF LFS oids (sha256) |
| RI-3 | The importer: a top-level `tar.zst` candidate is sniffed as `zstd` (G.3.1 step 2) and today registered `ingest.stream.codec` (deferred); when the profile declares it a container, it goes to `expand` like a zip | deferrals session | D-240 accepts a zstd tar at level 1; T0 still only sniffs magic bytes |
| RI-4 | The MCPHunt reader: call `agentprov.ingest.jsonstream.open_json_stream(ctx.open_input(i), limits, arrays=(...))` with a seekable handle (never `read_input`, which holds the whole document); declare the arrays in the profile | the adapter session that builds the MCPHunt reader | D-242; the document structure (`messages`, `events`, or a top-level array) is to be confirmed by that session's census |
| RI-5 | Spec H.1.4 / `raw/members.jsonl` documentation: a `container` digest may name a split descriptor | orchestrator (HL section) | D-244; the row format itself is unchanged |

## Follow-up status (2026-10-13, branch `ingest-formats-2`)

RI-1, RI-2, RI-3 and RI-5 are implemented on `ingest-formats-2` (D-247–D-249, proposals; the runner part goes to the
deferrals session for review). RI-4 stays with the future MCPHunt session. New:

| # | Need | Owner | Why |
|---|---|---|---|
| RI-6 | A corpus schema version whose sealed `zenodo` (and `hf`) snapshot origin can name the parts of an archive stored as byte parts (a `parts` member); until then a Zenodo split snapshot is refused at sealing | orchestrator (HL, the next corpus schema version) | D-163 freezes `corpus-0.1.schema.json`, which the manifest declarations generate; no Zenodo split source exists today (control-arena is HF and seals with `path`) |
| RI-7 | Profiles of HF archive inputs must record `gated = true/false` in the pin: H.2.3 requires it for a sealed `hf` origin and nothing defaults it | the profile sessions (control-arena, MCPHunt) | D-249 |
