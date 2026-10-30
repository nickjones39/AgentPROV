# Memory of PROV processing: profile, research and ranked proposals (prov-perf Part 2)

Session: prov-perf, branch `prov-perf`. Measured 2026-10-14 at `690b3629` (origin/main `654cef4c` + D-550) on the M2 Max
MacBook Pro (32 GB, CPython 3.14.8, prov 3.2.2, rdflib 7.6.0). The machine was shared and under load (swap about 80%
used), so wall times are indicative and **memory is the measured quantity**. Decision ids D-551..D-556 are reserved for
the proposals in §6. Nothing in this part is built: the scripts are scratch, and the user decides.

## 1. Method

- **Documents.** 81 executions from scratch clones of the 8 stored corpora (`~/.agentprov/migration-work/prov-perf/corpora`):
  per corpus the 3 largest PROV files plus log-spaced sizes (0.1–4.0 MiB). An extension with the long-run sources (the
  phase-10o `cam-j4` trial, PROV up to 18.2 MiB, and the two DTap documents of `roundtrip-bench`, 4.1 and 10.4 MiB) is
  **queued** (§2.5). Only paths, sizes, counts and code locations were recorded; no corpus text.
- **Stages** (scratch `profile_mem.py`, one fresh process per document): load AER and SEM; `derive` (engine and JCS);
  tier-4 pre-checks (strict JSON load, canonical check, structure, constraints, linkage, profiles); then the round trip
  step by step, exactly as `validate/roundtrip.py:_round_trip` runs it: `json.dumps`, model 1 (`ProvDocument.deserialize`),
  encode 1 (`encode_nquads`), parse (`parse_nquads`), model 2 (`_decode`), model compare, completeness, encode 2, line-set
  compare.
- **RSS** is sampled every 2 ms by a thread (`proc_pidinfo`, as the worker watchdog does). Each stage records its RSS
  before, its peak and its RSS after. A `gc.collect()` precedes every stage, so a stage's growth is its own.
  `validate_prov`'s real peak (no collections in between) is measured separately with `ru_maxrss` (`variants.py`).
- **Allocations**: `tracemalloc` in a separate pass (it inflates RSS). Peak and live heap per stage, plus the live heap by
  file and by line at each stage's end.
- No new dependency (memray was not needed; §5).

## 2. Results

### 2.1 Peak RSS is linear in the PROV size

Over the 81 documents, the peak above the interpreter's base (median 46.6 MiB, with every validator and profile
imported) is:

**peak − base ≈ 1.7 MiB + 82.2 × PROV MiB** (R² 0.999; a power-law fit gives exponent 0.95, R² 0.997).

The validator itself has no superlinear term. The "square of run length" growth noted in AGENTS.md (an 851 KB AER
peaking at 1.85 GB) is in the **PROV size**: in the `members` context encoding (E.6.1), each assistant turn uses
every earlier message of its pass, so PROV grows with turns². Per corpus, PROV ∝ AER^1.11–1.59 (R² 0.84–1.00). In
the phase-10o trial, a 399 KiB AER gives 18.2 MiB of PROV.

| Corpus | Largest PROV (MiB) | Its AER (KiB) | Statements | Attributes | Peak RSS (MiB) |
|---|---|---|---|---|---|
| agentdyn-a | 3.98 | 139 | 7,018 | 54,334 | 374 |
| adprov-v1 | 3.78 | 277 | 7,271 | 57,649 | 363 |
| ast-survey-agentdojo | 3.19 | 170 | 5,657 | 43,560 | 309 |
| rope | 2.68 | 89 | 4,776 | 36,848 | 271 |
| agentdojo-upstream-head | 2.11 | 130 | 4,207 | 34,551 | 225 |
| agentdojo-upstream-2024-06 | 2.11 | 130 | 4,207 | 34,551 | 218 |
| mandate | 1.21 | 85 | 2,428 | 18,651 | 149 |
| ast-survey-agentharm | 0.35 | 124 | 837 | 6,153 | 79 |

**No document in the 8 stored corpora peaks above 0.4 GB.** By the fit, the phase-10o trial's 18.2 MiB documents
reach about 1.5 GB, and DTap's 10.4 MiB document about 0.9 GB. The earlier roundtrip-bench measurement of that DTap
document was 1.13–1.16 GB (DECISIONS D-130); §2.5 will confirm both.

### 2.2 Per stage (median over the 51 documents above 0.5 MiB, in MiB of RSS growth per MiB of PROV)

| Stage | RSS growth | Wall s per MiB | What is alive at the end |
|---|---|---|---|
| derive (engine + JCS) | 7.3 | 0.15 | the PROV bytes |
| tier-4 JSON load, canonical check, structure/constraints/linkage/profiles | 0.9 / 0.1 / 0.5 | 0.04 / 0.04 / 0.10 | the decoded tree, the `ProvView` |
| `json.dumps` of the renamed tree | 0.1 | 0.004 | the text (1×) |
| model 1 (`ProvDocument.deserialize`) | 16.5 | 0.07 | model 1 |
| **encode 1** (`encode_document` + N-Quads write) | **43.8** | **0.57** | model 1, the N-Quads text (about 5× the JSON), and the encode's own `Dataset`, uncollected (a cycle) |
| parse (rdflib N-Quads into a `Dataset`) | 9.8 | 0.32 | + the parsed image (reuses freed arenas) |
| model 2 (`_decode`) | 8.5 | 0.14 | + model 2 |
| model compare | 0 | 0.03 | |
| completeness | 10.6 | 0.10 | + triple sets; the image released (but cyclic) |
| encode 2 | 7.3 | 0.58 | + text 2 and the second encode `Dataset` |
| line-set compare | 0 | 0.04 | |

Wall time is dominated by the two encodes. Memory is dominated by the rdflib datasets: the encoded one and the parsed
one. PROV-JSON gives about 21,500 quads per MiB.

### 2.3 Allocation breakdown (tracemalloc, a 0.96 MiB survey document; RSS without tracemalloc 167 MiB)

Python-heap peak 67 MiB. At the end of each stage (live heap):

| After | Live heap | Largest owners |
|---|---|---|
| model 1 | 15.4 MiB | `prov/model/records.py`, `prov/identifier.py` |
| encode 1 | 61.5 MiB | **`rdflib/plugins/stores/memory.py` 34.0 MiB** (227k blocks: the encode's Dataset, unreachable but not yet collected), records 5.7, the N-Quads text 5.1, `rdflib/term.py` 5.0, the decoded tree 3.0 |
| parse | 51.2 MiB | **memory store 21.6 MiB** (the parsed image), `term.py` 7.8 (127k terms: the parser shares no terms), records 5.7, text 5.1 |
| model 2 | 59.0 MiB | store 21.6, records 11.2 (two models), terms 7.8, `identifier.py` 2.2 |
| completeness | 51.6 MiB (peak 67.2) | store 21.6, terms 7.8, records 5.6, triple-set tuples |

**Larger documents** (tracemalloc pass, 2026-10-15; Python-heap peak and the live heap after decoding model 2):

| Document | PROV MiB | Heap peak | rdflib memory store | `prov` records (two models) | rdflib terms | N-Quads text |
|---|---|---|---|---|---|---|
| Mandate | 1.21 | 88 MiB | 27.0 MiB | 14.3 MiB | 9.8 MiB | 5.8 MiB |
| agentdyn | 3.98 | 277 MiB | 81.6 MiB | 43.3 MiB | 31.8 MiB | 20.3 MiB |
| phase-10o `cam-j4` | 10.06 | 683 MiB | 213.6 MiB | 115.5 MiB | 75.6 MiB | 51.2 MiB |
| DTap | 10.44 | 775 MiB | 237.8 MiB | 128.8 MiB | 84.0 MiB | 60.4 MiB |

The shares are the same at every size: the rdflib store is about a third of the heap, the two `prov` models about a
sixth, and terms and text about a tenth each. The heap peak is about 70 MiB per PROV MiB, inside the RSS slope of 80
(the rest is allocator overhead). At the end of encode 1, the store's share is larger: about 130 MiB of 238 MiB
(agentdyn). That is the encode's own Dataset, unreachable but not yet collected, which is the D-551 mechanism. RSS is about 2.3×
the Python heap here: the base, pymalloc arenas that stay mapped, and malloc'd text buffers.

### 2.4 Scratch prototypes of fixes in our code (fresh process per run; report bytes compared)

| Variant | 0.96 MiB doc: peak RSS | 3.98 MiB doc: peak RSS | Tier-4 report |
|---|---|---|---|
| as built (`validate_prov`) | 166.8 MiB | 398.9 MiB | (reference) |
| + `gc.collect()` after encode 1, after `del first`, after completeness, after `del second` | 122.5 (−27%) | 370.6 (−7%) | byte-identical |
| + model 1 from the parsed tree (`decode_json_document` on shallow copies; no `json.dumps`/`StringIO`) | 165.0 | 385.9 | byte-identical |
| both | 123.0 (−26%) | 349.4 (−12%) | byte-identical |
| **per unit**: the document-level records, then one bundle at a time, each loaded, encoded, parsed, decoded, compared and re-encoded, then dropped (models equal per unit; no findings yet) | **66.4 (−60%)** | **205.4 (−49%)** | not yet built as a check |

Per unit, the peak follows the **largest bundle**, not the document. In real documents one bundle holds about 70% of
the bytes (3.08 of 4.35 MB for the agentdyn document; 15 bundles). The research note's synthetic document had 61 even
bundles and fell from 737 to 74 MiB; real documents gain less.

**CPU of the variants** (CPU time of `validate_prov`, with the time inside `gc.collect()` measured directly; report
bytes identical for every variant):

| Document (PROV MiB) | as built | + tree (D-552) | + gc at 4 points (D-551) | + gc after completeness only | gc CPU at 4 points |
|---|---|---|---|---|---|
| 0.96 | 1.90 s, 161 MiB | 1.87 s, 165 MiB | 2.02 s, 122 MiB | 1.92 s, 147 MiB | 0.22 s (+11%) |
| 2.28 | 4.57 s, 250 MiB | 4.55 s, 260 MiB | 4.96 s, 224 MiB | 4.52 s, 252 MiB | 0.67 s (+15%) |
| 3.98 | 8.32 s, 398 MiB | — | 8.81 s, 357 MiB | 8.19 s, 380 MiB | 1.24 s (+15%) |

A full collection traverses the models and datasets, so it costs in proportion to them. `gc.freeze()` of the
long-lived objects before the round trip does not help (0.99 s instead of 1.24 s for three collections).

### 2.5 Long-run sources (confirmation run, 2026-10-15)

Same harness, run through the import queue. Peak RSS against the §2.1 model (base + 1.7 + 82.2 × PROV MiB):

| Document | PROV (MiB) | AER (KiB) | Peak RSS (MiB) | Model (MiB) | Encode 1 wall (s) |
|---|---|---|---|---|---|
| phase-10o `cam-j4` | 18.18 | 399 | 1,432 | 1,542 | 14.5 |
| phase-10o `cam-j4` | 17.64 | 391 | 1,485 | 1,499 | 19.3 |
| phase-10o `cam-j4` | 10.06 | 291 | 860 | 876 | 8.0 |
| phase-10o `cam-j4` | 6.65 | 231 | 559 | 596 | 6.5 |
| phase-10o `cam-j4` | 3.77 | 165 | 344 | 358 | 3.1 |
| phase-10o `cam-j4` | 1.90 | 122 | 194 | 205 | 1.6 |
| DTap (`roundtrip-bench`) | 10.44 | 8,775 | 974 | 906 | 7.9 |
| DTap (`roundtrip-bench`) | 4.11 | 7,066 | 417 | 386 | 7.5 |

**Refit over all 89 documents: peak − base ≈ 3.6 + 80.2 × PROV MiB (R² 0.997).** For documents above 0.5 MiB, the
measured peak is 0.93–1.09 of the model, so a ×1.25 margin covers every document seen.

The phase-10o trial shows the quadratic PROV growth at its clearest: a 399 KiB AER gives 18.2 MiB of PROV and a
1.4 GB peak. DTap's AERs are large (7–9 MB of tool outputs), but its PROV is not, and its peaks sit 7–8% above the
model (its literals are larger).

The model was handed to pipeline-perf for D-554, together with the orchestrator's observation of a 3.9 GiB import
*parent* (D-414's territory; a pool budget has to reserve it). The tracemalloc passes for these documents are
attribution only and do not change the model.

### 2.6 phys_footprint against resident size (for D-554's admission controller, 2026-10-15)

The model is fitted on resident size (`proc_pidinfo`). D-554 admits jobs on `phys_footprint` (`proc_pid_rusage`,
`RUSAGE_INFO_V4`), because resident size drops under compression. Six documents, measured with both metrics in the same
process; "lifetime max" is the kernel's `ri_lifetime_max_phys_footprint`:

| PROV (MiB) | Resident: base → peak (growth) | Footprint: base → lifetime max (growth) | Model growth |
|---|---|---|---|
| 0.32 | 46.0 → 73 (27) | 33.8 → 61 (27) | 29 |
| 1.21 | 47.1 → 150 (103) | 35.0 → 138 (103) | 101 |
| 3.98 | 46.6 → 377 (330) | 34.5 → 367 (333) | 322 |
| 6.65 (phase-10o) | 46.3 → 575 (528) | 34.1 → 563 (529) | 537 |
| 10.44 (DTap) | 46.5 → 980 (934) | 34.3 → 969 (934) | 841 |
| 18.18 (phase-10o) | 47.0 → 1,545 (1,498) | 34.8 → 1,533 (1,499) | 1,461 |

The growth is the same under both metrics (within 3 MiB), and the footprint base is about 12 MiB lower. The slope
(80.2) and the ×1.25 margin hold for `phys_footprint` too. The 2 ms-sampled footprint peak equalled the kernel's lifetime
maximum in every run. These runs had no memory pressure; under pressure, footprint keeps counting compressed pages,
which is why D-554 uses it.

## 3. What actually limits the worker count

The pool does **not** size itself by measured memory. `resolve_worker_count` (io/workers.py, D-55) takes
`min(CPUs, floor(0.75 × RAM / max RSS cap))`, and the cap for `prov` and `validate` jobs is **4 GiB**. On this machine
that gives 6 workers:

| Cap | Default workers, M2 Max 32 GB (12 CPUs) | Mac Studio M5 Ultra 256 GB |
|---|---|---|
| 4 GiB (now) | **6** | 48 → CPU-bound |
| 2 GiB | 12 (CPU-bound) | CPU-bound |
| 1 GiB | 12 | CPU-bound |

The stored corpora peak at **≤ 0.4 GB**, a tenth of the cap. The long-run sources reach 1.5 GB (§2.5). Making the validator leaner therefore does not, by
itself, change the worker count, and it does not change the round's time on this machine. What changes it is **the
cap, or how the pool admits jobs**, made safe by evidence (§6, D-554). The memory fixes (D-551..D-553) widen the
margin for the long-run sources (phase-10o, DTap), whose documents reach 1–2 GB.

The Mac Studio is CPU-bound at any cap up to 4 GiB. Memory is not its limit; the cache (D-550) and CPU are.

## 4. Research (summary; the full note with citations is `research.md` in this directory)

- **prov 3.2.2 is the latest release (2026-09-18).** Its changelog and tracker have nothing on model memory, large
  documents or the encoder's per-attribute qualification-head rebuild. 3.2.0 added `__slots__` to identifiers. Its
  own PR measured the per-record heap as flat, because 3.11+ instance dicts are already lazy
  ([#443](https://github.com/trungdong/prov/pull/443)). Parent-aware namespaces are on the roadmap for 3.3.0
  ([#449](https://github.com/trungdong/prov/issues/449)), and a pyoxigraph backend is unscheduled.
- **prov's model costs about 20× the JSON.** Every attribute, even single-valued, gets its own `TypedValueSet` with
  a one-entry dict keyed by `(type, value)`: about 360 B per attribute (`prov/model/records.py:279-336`, `:677`).
  Records and bundles form reference cycles, so `del` frees nothing until the cycle collector runs. That is the
  mechanism of the `gc` lever in §2.4.
- **rdflib 7.6.0's `Memory` store costs about 1.35–1.45 KB per quad** in these datasets. Each triple outside the first
  named graph gets its own context dict and a freshly formatted context string, about 370 B per triple
  (`rdflib/plugins/stores/memory.py:591-642`, `:681-700`). No upstream issue was found. The N-Quads parser creates
  fresh term objects per line (230k objects for 12k values in the synthetic test). Term interning is an open proposal
  ([#2972](https://github.com/RDFLib/rdflib/issues/2972)).
- **The JSON path copies the text.** `deserialize(content=str)` wraps it in a `StringIO` (4 bytes per character for
  an initial value), then `json.load` reads it again (`prov/model/bundle.py:1971`; `prov/serializers/provjson.py:105-120`).
- **Other tools.** ProvToolbox loads PROV-JSON into an in-memory model. Its scale work is storage and summarisation
  modules, not streaming parsers. CamFlow streams provenance record by record. Graph compression and summarisation
  (Xie et al. TaPP 2011; Moreau 2015) change the representation, so they cannot replace a fidelity round trip.
- **Python levers.**
  - `__slots__` gains little on 3.11+.
  - `sys.intern` does not apply to rdflib's `str` subclasses; a canonicalising dict does.
  - orjson parses JCS bytes to an equal tree, but it saves only one text copy (about 1× the JSON, against about 20×
    for a model), and it adds a native dependency in a stdlib-only ingest path. Not worth it.
  - CPython 3.14.8's GC is generational again (the incremental GC was reverted in 3.14.5).
  - pymalloc returns an arena only when it is empty, so a smaller live set at peak is what keeps RSS down.
  - `PYTHONMALLOC=mimalloc` is worth one A/B measurement.

## 5. Tools

tracemalloc for attribution, and a 2 ms `proc_pidinfo` sampler for RSS, were enough: the per-stage growth fits the
PROV size with R² 0.999, and the heap attribution names the owners. memray (native allocations) is **not requested**.
It would only matter if a residue appeared that tracemalloc cannot attribute, and none did.

## 6. Ranked proposals

Effect on the round: on the M2 Max the default is 6 workers at the 4 GiB cap. Moving to the CPU limit (12 workers;
8 performance and 4 efficiency cores, where an efficiency core is about 0.45 of a performance core) raises usable
capacity from about 6 to about 9.8 performance-core equivalents: **about 1.6× throughput in the CPU-bound phases**.
The round's 15–19 h estimate would become about 9–12 h, and less still where the D-550 cache serves re-validation
(`validate --corpus`, `recompute --dry-run`, post-checks: about 90% of tier 4 removed on a warm run). On the Mac
Studio nothing in this section changes the worker count; only D-550 and CPU matter there.

| Rank | Id | Change | Where | Byte identity | Measured or estimated saving | Effect on workers / round |
|---|---|---|---|---|---|---|
| 1 | **D-554** | **Size the pool by evidence, not the 4 GiB cap.** Either (a) a `prov`/`validate` cap from the predicted peak (base + 82 MiB per PROV MiB, ×1.5 margin; for `derive`/`recompute`/`validate` the stored PROV sizes are known in advance, and for a re-import the previous version's are), or (b) workers = CPUs with **admission control** (dispatch while the sum of predicted peaks of running jobs stays under 0.75 × RAM), keeping the 4 GiB hard cap per job | `io/workers.py`, the runner, `corpus/validation.py` (pipeline-perf owns io/workers and the runner; route via the orchestrator; it fits D-415's calibration) | Outputs unchanged (scheduling only). The recorded `memory_caps` and the default worker count change (host-dependent isolation records, already outside byte identity) | Stored corpora: from a 4 GiB budget per job to ≤ 0.6 GiB predicted | **M2: 6 → 12 workers, about 1.6×; round about 15–19 h → 9–12 h.** Mac Studio: none |
| 2 | **D-551** (measured after approval: not worth it, §2.4) | `gc.collect()` at the four round-trip phase boundaries (after encode 1, after dropping model 1, after completeness releases the image, after dropping model 2) | `validate/roundtrip.py` (class 1; rides with regen item 94) | **By construction**: collection frees only unreachable objects. Proof: report bytes on every proof document | −10% to −25% peak; **CPU +6% to +15%** (measured, §2.4) | Widens the margin for D-554 on long runs |
| 3 | **D-553** | **Per-unit round trip**: the document-level records, then one bundle at a time, each round-tripped and dropped. The outcomes are assembled per graph exactly as now: model equality per container (as `_model_diff` already compares), N-Quads line sets per graph (as `_graphs`), completeness per graph (as `_completeness`) | `validate/roundtrip.py` (class 1) | **Not by construction.** It must reproduce today's outcomes and findings: for example, a cross-bundle namespace collision renames a prefix (an IRI is unaffected), the "differ outside their records" finding, and blank-node counting. Gate: every document of the 8 corpora plus the 81 crafted documents and the negative controls, with outcomes byte-identical | −49% to −60% peak (§2.4). The peak follows the largest bundle (about 70% of a document) | Makes a 2 GiB cap safe for the long-run sources (DTap 1.85 GB → about 0.9 GB, estimated) |
| 4 | **D-552** | Model 1 from the parsed tree: `decode_json_document` on shallow copies of the container dicts, instead of `deserialize(content=json.dumps(renamed))` | `validate/roundtrip.py` (class 1) | By construction: the decoder sees an equal tree in the same order (prov mutates only the `bundle`/`prefix` keys of the containers, which are copied). Proof as D-551 | Removes the transient text copies, but no measurable peak change (§2.4); about −1% CPU | Small |
| 5 | **D-555** | **Library changes (proposal only; fork or upstream suggestion):** prov stores single-valued attributes inline (about −300 B per attribute, −60% to −70% of each model) and builds a relation's qualification head once (mostly time: the encoder is 41% of import CPU, profile.md); rdflib `Memory` memoises context strings and shares context sets (about −370 B per triple, about −25% of each dataset) and interns parser terms (#2972) | `prov`, `rdflib` | **A library change moves the libraries' file digests**, so the D-550 cache misses, and must be proven byte-identical on every document. The versions recorded in validation rows change if released upstream | Model −60%, datasets −25% (estimates from the research note's per-object costs) | Same direction as D-553, plus CPU from the head fix |
| 6 | **D-556** | **Not proposed, recorded:** the `collection` context encoding (E.6.2, deferred) would make PROV linear in turns, but it changes the PROV output; orjson/ijson (§4); `gc.freeze` (it leaks dropped models); oxrdflib/pyoxigraph (its parsers and serialisers are not 1:1 with rdflib's, so it would change the D-131 path) | | | | |

**Outcome (user decisions 2026-10-14, relayed by the orchestrator).**
- D-554 is approved and routed to pipeline-perf (with D-415, after D-414).
- D-553 is deferred, D-555 is not proposed, and D-556 is rejected.
- D-551 and D-552 were approved on this report's earlier estimate ("CPU under 2%"). The measurement in §2.4 then
  showed +6% to +15% tier-4 CPU for D-551, and no peak gain for D-552.
- On those measurements the user then decided **not to adopt either** (2026-10-14). D-551 is "measured, not adopted".
  Revisit it only for jobs above a size threshold (long-run sources at 1–2 GB), and only if D-554's budget needs it.
  D-552 is "not adopted: no measurable benefit".
