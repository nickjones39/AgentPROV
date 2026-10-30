# Memory of the tier-4 PROV round trip: prov 3.2.2, rdflib 7.6.0, alternatives, Python levers

Research note, 2026-10-14. Environment measured: CPython 3.14.8 (generational GC), prov 3.2.2, rdflib 7.6.0, macOS.
Source paths below are relative to `.venv/lib/python3.14/site-packages/`. Measurements use a synthetic PROV-JSON
generator (session scratch script `synth.py`: B bundles × 100 entities, 50 activities, ~300 relations with 8
custom-namespace attributes each). Heap figures come from `tracemalloc` (requested bytes, no allocator overhead). RSS
figures come from `ru_maxrss` in separate processes without tracemalloc. No corpus fixtures were read.

Caveat: the synthetic literals repeat a lot (11.9 k distinct term values for 230 k term slots), so the interning gains
below are optimistic. Per-object and per-triple figures do not depend on this.

---

## 0. Versions

| Package | Installed | Latest on PyPI | Notes |
|---|---|---|---|
| prov | 3.2.2 | **3.2.2 (2026-09-18)** | 3.2.x: 3.2.0 2026-09-12, 3.2.1 2026-09-12/13, 3.2.2 2026-09-18. The "Unreleased" changelog only adds Python 3.15 to CI (#542). [PyPI JSON](https://pypi.org/pypi/prov/json), [changelog](https://prov.readthedocs.io/en/latest/history.html) |
| rdflib | 7.6.0 | **7.6.0 (2026-02-13)** | No 8.x pre-release on PyPI. [PyPI](https://pypi.org/project/rdflib/) |
| orjson / ijson / memray | n/a | 3.13.0 / 3.6.0 / 1.20.0 | |
| oxrdflib / pyoxigraph | n/a | 0.5.0 / 0.5.11 | |

Changelog items in prov that touch performance or memory:
- 3.2.0 added `__slots__` and stored hashes on `Identifier`, `QualifiedName`, `Namespace` and `Literal` ([#443](https://github.com/trungdong/prov/pull/443)). The PR measured traced heap after 100 k records at 132.7 MB before and 133.1 MB after: "Net memory per record is essentially flat". The stored hash cancels the saving, because CPython 3.11+ instance dicts are already cheap.
- 3.2.0 also added a per-manager str→QualifiedName resolve cache ([#442](https://github.com/trungdong/prov/pull/442)) and a benchmark suite ([#433](https://github.com/trungdong/prov/issues/433)).
- 3.1.1 made bundle equality linear ([#409](https://github.com/trungdong/prov/pull/409)).
- Earlier: "Do not deepcopy the cache!" ([#158](https://github.com/trungdong/prov/pull/158), 2024), and an RDF-serialisation slowness report that turned out to be the user's own O(n²) code ([#150](https://github.com/trungdong/prov/issues/150)).
- No issue or PR deals with model memory, large documents, or the qualification-head rebuild in the RDF encoder.

Roadmap items that bear on this ([ROADMAP.md](https://github.com/trungdong/prov/blob/main/ROADMAP.md)):
- 3.3.0: parent-aware namespace reconciliation, so bundles stop copying the document's prefixes ([#449](https://github.com/trungdong/prov/issues/449)).
- 3.5.0: a store protocol with a SQLite engine.
- Unscheduled: an optional pyoxigraph RDF backend.

## 1. prov 3.2.2 internals that matter for memory

### 1.1 Records

**Record object.** `ProvRecord` (`prov/model/records.py:652-681`) has no `__slots__`. Each instance holds `_bundle`, `_identifier` and `_attributes = defaultdict(TypedValueSet)` (`:677`). On 3.11+ the instance `__dict__` is created lazily, so it costs little unless something reads `vars(record)`/`__dict__` or pickles the record. Doing that materialises a dict of about 296 B per record. [What's New 3.11, "lazily created object namespaces"](https://docs.python.org/3/whatsnew/3.11.html)

**Attribute storage is the main cost.** Every attribute name maps to its own `TypedValueSet` (`records.py:279-336`, `__slots__=("_index",)`). That object wraps a dict keyed by `(type(value), value)` tuples (`:315-326`). Most attributes hold one value, which still costs:
- TypedValueSet: 40 B
- inner 1-entry dict: 224 B
- key tuple: 64 B
- defaultdict slot: about 30 B

Measured cost per extra attribute is **≈360 B**, excluding the value object (scratch `perrec.py`):

| Record | Bytes per record |
|---|---|
| entity, 0 attributes | 556 B |
| entity, 1 attribute | 1,044 B |
| entity, 8 attributes | 3,468 B |
| entity, 16 attributes | 6,373 B |
| identified `wasGeneratedBy`, 0 extra attributes | 1,766 B |
| identified `wasGeneratedBy`, 8 extra attributes | 4,518 B |

On the synthetic document as a whole:
- 3.85 KB per record
- 510 B per attribute value, including values
- 31.5 MB of model for 1.6 MB of JSON, about 20× the JSON size

**Bundles and documents.** Each `ProvBundle` (`prov/model/bundle.py:326-355`) holds:
- `_records` (a list)
- `_id_map` (`defaultdict(list)`, one list per identifier)
- its own `NamespaceManager`

`ProvDocument._bundles` is a dict (`bundle.py:1674`).

**Records and bundles form reference cycles** (record→bundle→records). A model is freed only by the cycle GC, never by `del` alone. Verified: a 15.8 MB model stays at 15.8 MB after `del` and drops to 0 after `gc.collect()`. rdflib `Dataset`s behave the same way (51.7 MB stays after `del`; scratch `cycles.py`).

### 1.2 Identifiers and namespaces

- `Identifier` (`prov/identifier.py:183-243`) has slots `_uri` and `_hash`. `QualifiedName` (`:245`) adds `_namespace`, `_localpart` and `_str`. A QualifiedName costs 88 B plus three strings (`_uri`, `prefix:local` and `localpart`), so about 250 B per distinct name.
- QNames are interned per `Namespace` object through `Namespace._cache` (`identifier.py:463-469`).
- `NamespaceManager._resolve_cache` (`prov/model/namespaces.py:47`, `:220-229`) adds one str→QName entry per distinct identifier string, per manager.
- `_reconcile_qualified_name` (`namespaces.py:250-287`) ignores the parent manager. When a QName from the document is added to a bundle, the bundle makes its own copy of the `Namespace`, with its own `_cache`. **The QNames are then duplicated per bundle** ([#449](https://github.com/trungdong/prov/issues/449)).
  - This hits the RDF decode path, which builds the second model from QNames resolved against the document.
  - Measured effect: the decoded model is about 10% larger than the JSON-loaded one (34.6 vs 31.5 MB).

### 1.3 The PROV-JSON reader

The path `ProvDocument.deserialize(content=str)` makes several copies before any record exists:
1. `bundle.py:1971` wraps the text in `io.StringIO(content)`. A StringIO built from an initial value stores it as a **UCS-4 buffer: 4 bytes per character**. Measured: a 10 MB ASCII string becomes a 40 MB StringIO.
2. `ProvJSONSerializer.deserialize` (`prov/serializers/provjson.py:105-120`) calls `json.load`, which does `stream.read()`. That is another full copy (1 byte per character for ASCII).
3. `ProvJSONDecoder.decode` (`provjson.py:146-165`) builds the full dict tree and only then calls `decode_json_document`.

So the transient cost is about 6× the JSON size in text, plus about 4× the JSON size for the dict tree. The caller's own `json.dumps(renamed)` adds 1× more.

`decode_json_document`/`decode_json_container` (`provjson.py:336-399`) are public functions. They mutate their input: they delete the `"bundle"` key and every `"prefix"` key, so give them shallow copies. They decode one bundle at a time (`:360-364`).

### 1.4 PROV-O encode

**`encode_document`** (`prov/serializers/provrdf.py:825-897`):
1. Encodes the document's own records into a plain `Graph` (`doc_graph`, `:851`), which stays alive for the whole call.
2. For each bundle, builds a temporary plain `Graph` (`:858`) and copies it into the `Dataset` with `addN` (`:880`).
3. Peak is therefore the Dataset plus one bundle's Graph, plus `doc_graph` for the whole call. Measured: 104 MB retained, 127 MB peak.

**`encode_container`** (`:899-985`) writes elements as direct triples and relations through the qualification pattern.

**`_encode_relation`** (`:1031-1094`) calls `_encode_relation_head` (`:1096-1159`) again for every attribute until a blank node is minted. An identified relation never mints one, so it rebuilds the head K times. The code comment admits this. Each rebuild:
- re-evaluates `record.formal_attributes`, which builds a new tuple each time (`records.py:790-800`), 3-4 times per rebuild;
- appends the formal attribute names to `formal_objects` again, so the list grows to K×F entries and `attr in formal_objects` scans it linearly (quadratic per relation);
- re-issues idempotent `container.add` and `container.remove` calls.

The memory cost is transient churn. The cost in time is large: 11.7 s to encode 77 k quads.

Terms are built fresh for every triple (`URIRef(value.uri)` in `encode_rdf_representation`, `:510-553`). The encoded Dataset had 148,587 distinct term objects for 230,346 term slots, but only 11,908 distinct values.

### 1.5 PROV-O decode

**`decode_document`** (`provrdf.py:1304-1366`) calls `decode_container` on each graph in `content.graphs()`. Each graph is decoded independently against the shared document namespaces.

**`decode_container`** (`:1368-1422`) builds a `_DecodeState` (`:337-377`) holding, per subject:
- a `str(subject)` copy (str of a str-subclass always copies);
- two `OrderedDict`s (formal attributes and unique sets);
- attribute lists.

It frees this state after emitting the records. The peak during decode was about the size of the resulting model (35 MB).

Iterating a context graph copies that context's triple set first (`rdflib/plugins/stores/memory.py:429`, `.copy()`).

## 2. rdflib 7.6.0 memory behaviour

### 2.1 Memory and SimpleMemory stores

**`SimpleMemory`** (`rdflib/plugins/stores/memory.py:42-...`) is not context-aware. It keeps nested dicts `spo[s][p][o]=1`, `pos[p][o][s]=1` and `osp[o][s][p]=1`.

**`Memory`** (`:269-311`), the default store, keeps the same three indexes plus:
- `__contextTriples`: a dict from context string to a set of triple tuples. Every triple is in the `None` set and in its own context's set, so it sits in **two sets** and owns a tuple (72 B).
- `__tripleContexts`: a dict from triple to `{ctx_str: quoted, None: quoted}`. The entry is stored only when a triple's context info differs from `__defaultContexts`, which is simply the first triple's dict (`__add_triple_context`, `:591-642`).
- `__ctx_to_str` (`:681-700`) formats a **new** `"URIRef:<graph IRI>"` string on every add.

**Consequence for many named graphs (one per PROV bundle):** every triple outside the first context gets its own context dict and its own copy of the context string. That is **+≈370 B per triple**. In the encoded Dataset, 76,780 of 76,783 quads carried a private context dict. This tracker search found no rdflib issue about it.

**Measured bytes per triple** (100 k triples, scratch `measure2.py`). These are worst cases, because every triple has a distinct subject and object:

| Store layout | Bytes per triple |
|---|---|
| `Graph(Memory)`, one context | 1,429 |
| `SimpleMemory` | 1,272 |
| `Dataset`, one named graph | 1,428 |
| **`Dataset`, 50 named graphs** | **1,797** |
| Fresh term objects for every triple (what a parser produces) | 1,816 |

**Measured on the realistic PROV mix** (synthetic document, 76,783 quads, scratch `measure.py`, `measure3.py`):

| Store | Bytes per quad |
|---|---|
| Plain `Graph(Memory)`, shared terms | 744 |
| `SimpleMemory`, shared terms | 618 |
| `encode_document` Dataset | 1,351 |
| N-Quads-parsed Dataset | 1,450 |

Term sizes:
- `URIRef` (a str subclass): 109 B for a 26-character IRI.
- `Literal`: about 84 B plus `_value`. For a plain string, `_value` is a **second copy** of the lexical form. For `xsd:dateTime` it is a 48 B `datetime`.

`str` subclasses cannot go through `sys.intern`. rdflib keeps them as `str` subclasses for hashing speed ([#2866](https://github.com/RDFLib/rdflib/issues/2866)). Object interning for terms is an open proposal ([#2972](https://github.com/RDFLib/rdflib/issues/2972)); an earlier `sys.intern` attempt was closed ([#1302](https://github.com/RDFLib/rdflib/issues/1302)). Related: pickle duplicates terms ([#740](https://github.com/RDFLib/rdflib/issues/740)).

### 2.2 Dataset, N-Quads parser and N-Quads serializer

- `ConjunctiveGraph.addN` (`rdflib/graph.py:2281-2290`) calls `_graph(c)`, which goes through `get_context`. That creates a `Graph` object for every quad; it is transient. `Store.add` also dispatches an event for every triple.
- **N-Quads parser** (`rdflib/plugins/parsers/nquads.py:70-142`):
  - It streams line by line, so the input text is not duplicated: `data=bytes` is wrapped in a `BytesIO`, which shares the buffer (measured 0 MB extra).
  - It creates new `URIRef` and `Literal` objects for every line and never interns them. A parsed Dataset therefore shares **no** terms: 230,346 distinct objects for 11,908 values.
- **N-Quads serializer** (`rdflib/plugins/serializers/nquads.py`) streams `_nq_row` for each triple of each context.

## 3. Large-document handling elsewhere (selected)

- **ProvToolbox** (Java, [repo](https://github.com/lucmoreau/ProvToolbox)): PROV-JSON(-LD) goes through Jackson deserializers into an in-memory model (`modules-core/prov-jsonld/.../deserial/`). Large-scale handling lives in separate modules: `modules-storage` (filesystem, Redis index, MongoDB) and `modules-summarisation`. I found no streaming PROV-JSON reader. PROV-JSON itself is a whole-document format ([W3C submission](https://www.w3.org/submissions/2013/SUBM-prov-json-20130424/)).
- **ProvStore** (Huynh & Moreau, IPAW 2014, [eprint](https://eprints.soton.ac.uk/365509)) is built on the same `prov` package with documents held per request. It shows no special large-document technique.
- **CamFlow** (Pasquier et al., SoCC 2017, [arXiv 1711.05296](https://arxiv.org/abs/1711.05296)) streams provenance as a flow of records (MQTT or Flume, binary or PROV-JSON) instead of one document. It calls PROV-JSON "bloated" and adds a compact binary format. The paper cites 8% of PROV-JSON size with compression. The lesson: process unit by unit.
- **Summarisation and compression:**
  - Moreau, "Aggregation by Provenance Types", GaM 2015 ([arXiv 1504.02616](https://arxiv.org/abs/1504.02616)), implemented in ProvToolbox's summarisation module.
  - Xie et al., "Compressing Provenance Graphs", TaPP 2011 ([USENIX](https://www.usenix.org/conference/tapp11/compressing-provenance-graphs)): dictionary encoding of node and edge identity plus adjacency lists, ratios up to 3.31:1. This is the same insight as interning repeated terms.
  - PROV-Template (Moreau et al., IEEE TSE 44(2) 2017, [eprint](https://eprints.soton.ac.uk/405025)): bindings are about 40% of the size of the expanded provenance.
  - These change the representation, so they are not drop-in for a fidelity round trip.
- **ProvONE** is a workflow vocabulary with no memory technique; left out.

## 4. Python techniques, assessed for this workload

**`__slots__`**
- Little gain on 3.11+ unless something materialises `__dict__`. prov's own measurement shows a flat heap ([#443](https://github.com/trungdong/prov/pull/443)).
- The real saving in prov is in the per-attribute container (§1.1), not in instance dicts.
- Watch for code that calls `vars()`, `copy` or `pickle` on records.

**`sys.intern`**
- Works only on exact `str`, so not on `URIRef` or `Literal`.
- Usable for prov strings (QName parts, decode-state keys).
- For rdflib terms, use a canonicalising dict (`d.setdefault(t, t)`). Measured: an interning `Memory` subclass cut the parsed Dataset from 111.3 to 79.0 MB (−29%). It also removed the per-triple context-string copies.

**Avoid intermediate trees and text copies**
- CPython's `json` already memoises object keys within one `loads` call (`json/decoder.py:143-169`), but not values.
- `object_pairs_hook` could intern values, but costs speed.
- [ijson](https://github.com/ICRAR/ijson) `kvitems(f, "bundle")` streams one bundle at a time. Its yajl2_c backend is fastest. It returns `Decimal` for non-integers unless `use_float=True`.

**json vs orjson** ([README](https://github.com/ijl/orjson)) — only parsing matters, since the bytes are canonical JCS ([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)):
- orjson parses `bytes` directly, so there is no decoded `str` copy.
- It caches up to 2,048 keys of ≤64 bytes per process.
- It rejects NaN/Infinity, invalid UTF-8 and lone surrogates, limits nesting to 1,024 levels, and has no hooks. Its integers are limited to 64 bits.
- On JCS input these differences cannot arise:
  - JCS numbers are ES6 shortest round-trip doubles, with integer literals within ±2^53.
  - Both parsers produce correctly rounded floats and the same `int`s.
  - JCS strings are I-JSON (no lone surrogates), and there are no duplicate keys and no NaN.
- So the parsed tree would be equal. The memory win is small, though: the text copy is 1×, while the tree is about 4× and the model about 20×.
- It adds a native dependency, and `agentprov.ingest` is stdlib-only for untrusted input. Low priority.

**`gc`**
- prov models and rdflib graphs are cyclic, so call `gc.collect()` at phase boundaries after `del`.
- On 3.14.8 the GC is generational again: the 3.14.0-3.14.4 incremental GC was reverted in 3.14.5 after reports of memory pressure ([What's New 3.14](https://docs.python.org/3.14/whatsnew/3.14.html)). Thresholds are (2000, 10, 10).
- `gc.disable()` during a build saves time, not peak memory.
- `gc.freeze()` ([docs](https://docs.python.org/3/library/gc.html#gc.freeze)) moves objects to a permanent generation that is never collected. Never freeze a model you will drop later: its cycles would leak until `gc.unfreeze()`.

**Allocator**
- pymalloc serves objects ≤512 B from 1 MiB arenas on 64-bit systems. An arena goes back to the OS (`munmap`) only when it is completely empty ([C-API memory docs](https://docs.python.org/3.14/c-api/memory.html)). A few long-lived survivors pin arenas, so RSS stays at the high-water mark.
- Keeping the working set small and short-lived (one bundle at a time) is what lets arenas be reused.
- `PYTHONMALLOC=mimalloc` is selectable on default (non-free-threaded) builds and handles all allocation sizes. It is worth an A/B test of RSS.
- On macOS, `ru_maxrss` is in bytes (Linux reports KiB). Freed pages may stay counted until memory pressure; Apple's `footprint`/`vmmap --summary` give a fairer view. This last point is unverified here.

**Profilers**
- `tracemalloc` counts bytes requested from Python's allocators, without arena or fragmentation overhead. It is right for per-structure attribution like the tables above, but slows runs and inflates RSS.
- [memray](https://bloomberg.github.io/memray/python_allocators.html) also tracks native allocations. With pymalloc active it sees whole arenas unless you pass `--trace-python-allocators`. Use it to explain the 851 KB → 1.85 GB RSS case.

## 5. Estimates per PROV statement and per triple

Triples per statement:
- Element with K attributes: 1 + K.
- Identified relation with K extra attributes: about K + 4 (rdf:type, `qualified*` link, 2 formal attributes, optionally time).
- Unidentified relation with attributes: binary triple + link + blank-node type + formal attributes + K.

| Item | Model (per copy) | Each multi-bundle rdflib Dataset | N-Quads text |
|---|---|---|---|
| Element | ≈0.55 KB + 0.36 KB·K | ≈1.4 KB·(1+K) | ≈120-150 B per line |
| Identified relation | ≈1.8 KB + 0.35 KB·K | ≈1.4 KB·(K+4) | ≈120-150 B per line |
| Example: relation with K=8 | ≈4.5 KB | ≈17 KB | ≈1.6 KB |

At the tier-4 peak, the live set is: first model, text1, parsed image, second model, plus any uncollected encode Dataset. That is about **25 KB per record**. Measured: 685 MB for 26.9 k records from 4.8 MB of JSON, about 140× the JSON size. The Datasets dominate at about 70%.

## 6. Experiments with the calling code (same 4.8 MB synthetic document, max RSS)

| Variant | Max RSS | Time | Models equal |
|---|---|---|---|
| Current sequence (`deserialize(content=json.dumps)`, then encode, parse, decode, compare, encode) | 759 MB | 88 s | yes |
| Plus `gc.collect()` after each `del` | 720 MB | 80 s | yes |
| Plus `decode_json_document(shallow copy)` instead of dumps/deserialize | 737 MB | 62 s | yes |
| **Bundle at a time** (document-level records first, then one bundle per unit; each unit loaded, encoded, parsed, decoded, compared and re-encoded, then dropped) | **74 MB** (start 53) | **45 s** | yes |

Load stage on its own (1.6 MB JSON): peak 49.1 → 31.5 MB with `decode_json_document` on a shallow-copied tree.

**Why bundle at a time is equivalent:**
- prov already encodes each bundle with its own `encode_container` call (`provrdf.py:858`).
- It already decodes each named graph independently (`decode_container`, `:1338-1350`).
- `_graphs` already compares N-Quads line sets per graph name.

**What differs:**
- Namespace-binding collisions across bundles: the rename to `prefix1` disappears. This changes decoded prefix strings, not URIs; QName equality is by URI.
- Blank-node labels, which were never comparable anyway.

This must be gated on the regression corpus before adoption: identical per-graph line sets minus blank-node lines, identical findings, and the recompute/compat gates.

## 7. Levers, ranked

### (a) In the calling code (`validate/roundtrip.py`, `prov/serialise/nquads.py`)

1. **Run the round trip one bundle at a time** (plus a unit for the document-level records). Peak memory then scales with the largest bundle, not the whole document: measured 737 → 74 MB, and faster. To go further, stream bundles from the bytes with `ijson.kvitems(..., "bundle")`, or reuse the already-parsed tree. Per-bundle line sets also keep `_graphs` small.
2. **Load from the parsed tree.** Call `decode_json_document` on a shallow-copied tree instead of `ProvDocument.deserialize(content=json.dumps(renamed))`. This avoids the dumps text, the 4-bytes-per-character StringIO and the `read()` copy (§1.3).
3. **Call `gc.collect()` after every `del`** of a model or Dataset, and inside `encode_nquads` after serialising. Both object kinds are cyclic and are otherwise freed only when the generational GC decides to collect.
4. **Parse into a store that shares terms and contexts.**
   - Either use a `Memory` subclass that canonicalises terms and memoises context strings (−29% on the parsed image),
   - or parse each graph's lines into its own plain `Graph`, which removes the ≈370 B per-triple context dict, and call `decode_container` per graph.
   - The subclass touches rdflib private names (`_Memory__ctx_to_str`), so pin rdflib and test.
5. **Drop the first model before decoding the second.** Keep a per-bundle digest multiset of records instead, and reload from JSON only on mismatch. The digest must respect prov's equality semantics (Literal value-space and langtag rules), so this is the riskiest item in this list.
6. **Lighten `_quads`/`_graphs`.** Don't materialise two full sets of `bytes` lines for whole texts; work per graph, and stream text2 against text1's set.
7. **Measure with memray** (`--native`, `--trace-python-allocators`) on the real 851 KB → 1.85 GB case. Also A/B `PYTHONMALLOC=mimalloc`. Keep tracemalloc runs separate from RSS runs.

### (b) Needs a fork or an upstream change

1. **prov: store single attribute values inline** and switch to `TypedValueSet` only when a second value arrives. Saves ≈300 B per attribute, about 60-70% of the model.
2. **prov: build the qualification head once per relation.** Compute `formal_attributes` once and hold `formal_objects` as a set. This is mainly a time fix, plus transient memory. It must keep the output byte-identical (re-run golden/compat).
3. **prov: parent-aware namespace reconciliation** ([#449](https://github.com/trungdong/prov/issues/449), on the roadmap for 3.3.0). Stops per-bundle Namespace and QName copies, which cost ≈10% on decoded models.
4. **prov: `deserialize(content=…)` should call `json.loads` directly** instead of going through StringIO. `encode_document` should not keep `doc_graph` or the per-bundle temporary Graphs alive. Decode could reuse term strings instead of `str(node)` copies.
5. **rdflib `Memory`:**
   - memoise the context string per graph;
   - share copy-on-write context sets instead of a fresh dict for every triple (≈370 B per triple in multi-graph Datasets; no upstream issue found);
   - intern terms in the parsers (open proposal [#2972](https://github.com/RDFLib/rdflib/issues/2972));
   - stop `Literal` keeping a second copy of plain-string lexical forms.
6. **Alternative backend:** [oxrdflib](https://github.com/oxigraph/oxrdflib) (pyoxigraph store, data outside the Python heap). Its parsers and serializers are "not 1:1 compatible" with rdflib's, so adopting it changes the D-131 path and is a decision, not an optimisation.
