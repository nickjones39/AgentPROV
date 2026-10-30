# Strict JSON loader: a depth fast path (D-412)

Status: **built on branch `pipeline-perf`** (2026-10-14), after the deferrals session's review (OK-with-changes, one
must-fix, applied: §2a). User-approved 2026-10-14.

## 1. The change

In `agentprov.ingest.loaders.strict_json_loads`, compute

```
k = data.count(b"[") + data.count(b"{")
```

once, after the UTF-8 decode check. Then:

- skip `_prescan_depth(data, max_json_depth)` when `k <= max_json_depth`;
- skip `_walk(value, max_json_depth, check_surrogates=False)` when `k + (1 if a python-json constant was mapped else 0)
  <= max_json_depth` (§2a). When `check_surrogates` is true, `_walk` runs as today, because it also counts lone
  surrogates.
- `loaders._DEPTH_FAST_PATH = False` restores the unconditional checks. The differential tests use it, and it can turn
  the fast path off if it is ever doubted.

Nothing else changes: the byte cap, the BOM and UTF-16/32 checks, the strict decode, `json.loads` with
`_no_duplicates`, the number hooks, the `RecursionError` mapping and the findings.

## 2. Soundness

**Claim.** For every input, the loader with the fast path returns the same value, appends the same findings and
raises the same `IngestError` (same code) as the loader without it.

**`_prescan_depth`.**
- Its only effects are raising `ingest.json.depth` when its counter exceeds `max_depth`, or returning `None`. The
  `None` includes the early return on an unterminated string.
- The counter starts at 0. It increases by 1 only when the regex match is group 1 with a value of `[` or `{`, that is,
  one byte of `data` outside any string token. Each increment consumes a distinct byte offset, because `finditer`
  matches do not overlap. Every other step leaves the counter unchanged or decreases it.
- So at every point the counter is at most the number of increments so far. That is at most the number of `[`/`{`
  bytes outside strings, which is at most `k`, the number of `[`/`{` bytes anywhere.
- If `k <= max_depth`, the counter never exceeds `max_depth`, the function cannot raise, and skipping it changes
  nothing.

**Strings, escapes and invalid input.**
- Brackets inside strings, including after escaped quotes (`"\"["`), are counted in `k` but never by the scan, so they
  only make `k` larger. The bound stays conservative and can never let a deep document through.
- Escapes cannot hide a structural bracket from `k`: `k` counts raw bytes and ignores tokenisation.
- An escaped bracket (`[`) is not a structural bracket for `json.loads` either.
- Invalid JSON (unterminated strings, stray closers) reaches `json.loads` exactly as before, which raises
  `ingest.json.syntax`. The skipped prescan could not have raised first, because it raises only on depth.

**`_walk` with `check_surrogates=False`.**
- `json.loads` builds one container per structural `[` or `{` byte, so the depth of the parsed value is at most the
  number of such bytes, which is at most `k`.
- `_walk` raises only when a container's depth exceeds `max_depth`, and returns 0 when it doesn't check surrogates.
- With `k <= max_depth` it cannot raise and returns 0, and the caller adds 0 to `lone`, except under `python-json`, where a mapped constant adds one level (§2a). Skipping it then changes nothing.

### 2a. Must-fix from the deferrals review: `python-json` constants

Under `profile="python-json"`, `parse_constant` maps `NaN`, `Infinity` and `-Infinity` to a `{"$float": ...}` dict.
That container comes from no bracket byte, so the parsed depth can be k + 1. Each mapped constant is a leaf dict, so
any number of them adds at most one level. Example: `[` × 256 + `NaN` + `]` × 256 has k = 256 = max, yet its parsed
depth is 257. Today `_walk` rejects it with `ingest.json.depth`, and the first draft would have accepted it.

The walk is therefore skipped only when `k + (1 if mapped else 0) <= max_json_depth`. A comment in the code states that
the bound holds only while no parse hook builds any container beyond that one-level dict. The prescan bound is
unaffected: it is defined on bytes, and constants contain no bracket byte.

**`RecursionError`.** The `json` module's C scanner could only raise this for nesting near the interpreter's recursion
limit, far above 256. Skipping the prescan when `k <= 256` does not change whether it fires: the prescan would not
have raised for such documents either.

**What is not weakened.** Every document with depth > `max_json_depth` has `k > max_json_depth`, so it takes the
existing path and is rejected by the existing code at the same point, with the same code and offset.

## 3. Cost and benefit (measured 2026-10-14, ROPE clone, 300 random files per kind)

| Document kind | Documents | Fast-path hits | prescan + walk time today | Time saved | Cost of the two `count` calls |
|---|---|---|---|---|---|
| AER lines | 13,760 | 100% | 0.34 s | 0.34 s | 0.006 s |
| SEM lines | 17,740 | 100% | 0.25 s | 0.25 s | 0.005 s |
| PROV documents | 300 | 0% | 3.32 s | 0 | 0.040 s |

- **verify --level chain.** The loader is 57% of its profile (Mandate). Most calls are AER and SEM lines, so this is
  about 20–35% of verify's loader time. Estimate: ROPE verify-chain 268 s down by 40–70 s.
- **import, derive, validate.** The worker frames and the parent's AER/SEM reads are per-line documents, so they all
  hit. They are under 1% of an import's CPU, which tier 4 dominates.
- **PROV documents** (one JSON value per execution, hundreds of KB) never hit. A tighter bound for them would need a
  structural scan: the prescan itself.

This is a modest win. It is worth building for `verify` and for any line-oriented reader, and it is not worth any
risk. The review should weigh it on those terms.

## 4. Digests

`ingest/loaders.py` is in no stage `engine_code_sha256` (aer: `adapters/runner` + `aer/`; sem; prov; validation) and is
not in `raw.members.EXPAND_MODULES`. The change moves no corpus byte and no `derivation.json` digest.

## 5. As built: tests and proofs

- `tests/property/test_loader_fastpath_props.py`:
  - generated documents at limits 4–10 and depths limit−2 … limit+1. Leaves include strings full of brackets,
    escaped quotes, `\u005b`, lone surrogates, python-json constants and a "plain" mode in which k equals the
    nesting depth;
  - corruptions: truncation, stray closer, unterminated string, BOM;
  - every JSON profile; value, findings and error code are compared with `_DEPTH_FAST_PATH = False`;
  - the deferrals case at 255 and 256 for each constant.
- `tests/unit/ingest/test_json_loader.py::test_depth_checks_are_skipped_exactly_when_the_byte_count_bounds_them`:
  spies prove that the prescan and the walk are skipped or called exactly at the bound (k = max, max + 1, brackets
  in strings, python-json at k = max and max − 1, lone surrogates).
- **Mutation checks** (run by hand, not committed):
  - dropping the `+1` for mapped constants is caught by the generated property test and by the hand cases (4 failures);
  - an off-by-one in both bounds is caught by the generated test.
- **Identity:** Mandate imported with and without the change: 1,596 of 1,596 files byte-identical.
- **Measured:** `verify --level chain` on Mandate, CPU, three alternating runs each: 5.22–5.33 s → 4.76–4.88 s (−9%).
  That is below the §3 estimate, because the cProfile share of the loader had overstated it.

## 6. Tests as proposed

- **Differential property test** (Hypothesis, in `tests/property/`):
  - `strict_json_loads` with and without the fast path agree on the value, the findings and the exception code for
    generated JSON, including nesting at depths 255, 256 and 257;
  - strings full of `[`/`{`, escaped quotes and `[` escapes;
  - unterminated strings and stray closers;
  - lone-surrogate escapes, which force `check_surrogates`;
  - `k` exactly at `max_json_depth` and `max_json_depth + 1`.
- The existing depth tests (`ingest.json.depth` at 257, the SEC depth cases) stay as they are and must pass unchanged.
