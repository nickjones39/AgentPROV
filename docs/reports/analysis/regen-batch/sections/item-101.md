## Item 101 (built 2026-10-15; D-455, R-10j-3; user decision 2026-10-15: approved; held branch `bugpass-regen-d455`)

URL download pins become archive inputs, as Zenodo and Hugging Face files are (D-200): `DOWNLOAD_PIN_KINDS` gains
`url`. The file is checked against the pinned SHA-256 and size, stored with a `url {url, retrieved}` origin, expanded in
place and its members mapped. A URL is mutable, so the retrieval time comes only from the recorded fetch: the fetch
cache's acquisition record (`FetchResult.retrieved_at`, also read back on a cache hit), else the pin's `retrieved_at`
(RFC 3339 UTC). With neither the import is refused (`raw.origin.unpinned`, exit 3); nothing is stamped with the time of
the import. The working snapshot `pin` records `retrieved_at`, and the seal builds `{kind: url, url, retrieved_at}`
(H.2.3). Re-maps label the stored object by its URL, then by the recorded input label.

| stored bytes | |
|---|---|
| AER, SEM, PROV, validation, index, register, manifest | **none** for every existing corpus: no stored corpus has a `url` snapshot (the import refused them before) |
| `derivation.json` | `adapters/runner/` is in the `aer` stage's `engine_code_sha256`, so that digest and the stage's `fn_digest` move for every corpus imported or re-mapped afterwards |

Unblocks phase 10j's `dca` (Figshare) corpus. `raw/fetch.py`, `corpus/manifest.py` and `corpus/rawtree.py` are in no
digest. Tests: `tests/adapters/runner/test_url_archive_input.py` (retrieved present, missing or malformed → refused,
sha mismatch → refused, the acquisition record over the pin, the sealed origin and its checks).

