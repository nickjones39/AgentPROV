# D-416: corpus reader speed (index, register, JCS) — design note

Session: pipeline-perf. Status: **built; reviewed by core review B** (finding A fixed: the guard runs inside the `try`; B1/B2 subclass tests added). Every check the reader makes today stays; only the cost of making it
changes. Measurements are read-only, on the stored corpora, single process, CPU seconds, counts only.

## 1. Where the time goes

`agentdyn-a-p10` (38,281 index rows, 90,474 register entries), unprofiled, under shared load (about 25):

| Call | CPU | Main costs (profiled shares) |
|---|---|---|
| `CorpusReader.iter_index()` | 5.65 s | `rfc8785.dumps` about 55% (2 calls per row: the row's canonical check and the `source_key` locator check); `IngestLimits()` built once per row (about 12%) inside `strict_json_loads(..., record=True)` with no limits passed; `IndexRow` construction and checks |
| `CorpusReader.register()` | 10.73 s | `rfc8785.dumps` about 75%; `RegisterEntry.rid` computed **5 times per entry** (452,370 calls for 90,474 entries: `from_json`'s check, `best.get(rid)`, and twice through `to_json` via `sort_key` and the final `canonical()`); base32 of each rid |

Every caller pays this, for example `validate`, `verify`, `derive`, `recompute`, `package` and the D-554 size hints.

## 2. Changes

**A. A guarded stdlib fast path inside `io.canonical.jcs_bytes`.** The definition stays RFC 8785, and `rfc8785` stays its
reference implementation. `jcs_bytes(obj)` first checks whether `obj` is *plain*:
- only exact `dict`, `list`, `str`, `int`, `bool` and `None` (no subclasses, tuples, other Mappings or floats);
- integers within ±(2⁵³−1), which are `rfc8785`'s own bounds;
- object keys are exact `str` with every code point at most U+FFFF;
- nesting depth at most 128, which also bounds a cyclic structure.

A plain value is encoded with `json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"),
allow_nan=False)` and then UTF-8 encoded. On `UnicodeEncodeError` (a lone surrogate), `ValueError` or `RecursionError`,
and for every value that is not plain, the call goes to `rfc8785.dumps` exactly as today. So every error type and every
non-plain value behave as before.

Why the bytes are equal on the plain domain:
- **null, true, false:** identical literals.
- **Integers:** both write `int.__repr__`/`str(int)`, inside the same bounds; outside them the call falls back, so
  `rfc8785` raises its `IntegerDomainError` as before.
- **Strings:** both escape the same set from the same table: `"`, `\`, `\b`, `\f`, `\n`, `\r`, `\t`, and the other C0
  controls as lower-case `\u00xx`. Nothing else is escaped, and both write UTF-8. This was checked exhaustively for all
  65,536 BMP code points plus astral samples: 0 differences. Lone surrogates are rejected by both, because the fast path
  falls back and `rfc8785` raises its own error.
- **Member order:** `rfc8785` sorts keys by their UTF-16BE bytes. For keys made only of BMP characters, UTF-16 code-unit
  order is code-point order, which is Python's `str` order. Keys with an astral character fall back. A `dict` cannot
  hold duplicate keys.
- **Floats** always fall back: JCS number formatting is ECMAScript `Number.prototype.toString`, which `float.__repr__` is
  not. The AER encodes its floats explicitly (C.11.3–C.11.4), so this is the rare path.

**B. One shared default `IngestLimits` in `ingest.loaders`.** Today `strict_json_loads` runs `limits = limits or
IngestLimits()` on every call. `IngestLimits` is frozen with slots, so a module-level default instance is
indistinguishable. Nothing else changes, and every bound stays the same.

**C. A register entry's `rid` is computed once.** It is computed in `__post_init__` and stored in a `field(init=False,
compare=False, repr=False)` slot.
- `rid` depends on `code`, `stage` and `subject`. `subject` is the private copy that `_subject()` makes, and nothing in
  the code base mutates it (checked).
- `dataclasses.replace` re-runs `__init__`, so a replaced entry gets a fresh `rid`.
- `_collapse_sorted` computes each entry's canonical bytes once, instead of up to three times.
- `decode_register` still re-encodes the whole file and compares bytes, so its check is unchanged.

**Kept unchanged:**
- strict parsing with every bound;
- the per-row JCS comparison;
- sorted/unique `ex`;
- the layout path checks;
- the register's sorted, collapsed and canonical byte comparison;
- every error code.

## 3. Stage digests

`io/canonical.py`, `ingest/loaders.py`, `corpus/index.py` and `corpus/register.py` are in no stage code digest:
- aer is `adapters/runner` and `aer`;
- sem is `sem`, `adapters/semantics_profiles.py` and the families;
- prov is `prov` and `vocab`;
- validation is `validate`, `aer/validate.py`, `aer/accounting.py` and `sem/validate.py`;
- expand is `EXPAND_MODULES`.

So there is **no `engine_code_sha256` move and no regen-batch item.** Because the bytes are identical, every id
derived through JCS (`rid`, `lk_`, the digests) is identical too.

## 4. Evidence so far

**Differential sweep.** Every index, register, origins and members line, plus sampled AER (200 files), SEM (100) and PROV
(30) per corpus, across 8 stored corpora (agentdyn, adprov, agentdojo-upstream head and 2024-06, both ast-survey
corpora, Mandate, ROPE): **466,848 documents, 0 mismatches**. Every stored line was already canonical.

**Patched in memory on agentdyn** (A + B; C not yet measured), with identical row and entry fingerprints:

| Call | Before | After |
|---|---|---|
| `iter_index()` | 5.65 s | 2.37 s |
| `register()` | 10.73 s | 4.72 s |

C is expected to take `register()` lower: after A, its remaining cost is mostly the 4 extra `rid` hashes and base32
spellings per entry.

On real documents the fast path is 3.6–4.2× faster than `rfc8785.dumps` (ROPE: index, AER and PROV objects).

## 5. Proof plan (before any push)

1. **Unit tests:**
   - the exhaustive code-point table;
   - a Hypothesis differential over JSON-like values that deliberately include ±2⁵³±1, lone surrogates, astral keys and
     values, floats including −0.0, NaN and inf, tuples, `IntEnum`, `str` and `dict` subclasses, non-string keys,
     nesting at 127–130, and a cycle;
   - the check: equal bytes, or the same exception type, for both implementations.
   - Plus the existing C.16 vectors.
2. **Gates:** golden, gate D and the compat oracle (byte-for-byte).
3. **Scratch imports** before and after (Mandate release, ROPE `--limit 1500`), with a byte-diff of the whole tree,
   `-j8` against `-j3`. Expected: 0 differences, not even `derivation.json`.
4. **Reports:** `validate --corpus --jobs 3` and `verify --level chain` reports byte-identical before and after.
5. **Timings:** `iter_index`, `register`, `verify --level chain` and the import T0 seal, before and after.
6. **The full suite** on the exact commit.

## 6. Rejected alternatives

- **A compiled JCS library:** a new core dependency, which needs the user's yes.
- **Skipping the canonical check for sealed corpora:** that weakens a guard.
- **Caching parsed index rows across processes:** staleness and a second source of truth.
- **Replacing `rfc8785` outright:** it stays the reference and the fallback, so any value outside the proven domain gets
  the reference behaviour.
- **Changing `decode_register`'s whole-file re-encode check** to an equivalent per-line check: it is provable, but C
  already removes most of the cost without touching the check.

## 7. Risks

- **A future CPython changes `json`'s escaping or separators.** The exhaustive table and the differential test run in
  every suite, and the environment record already carries the Python version.
- **A caller mutates a register entry's `subject` after construction.** None does today. The slot is documented, and
  the mutation would already be a bug, because the dataclass is frozen.
