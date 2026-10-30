- **D-702 amendment (2026-10-22, the default key source; user rule given in the local-endpoints window and confirmed
  by the orchestrator: "have the code look for the keychain first as the source of truth and if not then read the
  .env").**
  - `run` with none of `--keychain`, `--env-file` or `--env-stdin` takes the selected endpoint's key from the OS keychain
    first and falls back to the repository's `.env`. The other `.env` variables (model id, base URL, effort) are still
    read.
  - Each explicit option names one source only.
  - An unavailable keychain, or a missing entry, is a notice in the default mode. When neither source holds the key,
    the error names the variable and both places (exit 3), never a value.
  - `AGENTPROV_NO_KEYCHAIN=1` turns the keychain off for a process and its children. The test session sets it, so no
    test reads a developer's keychain.
  - `agentprov models` (D-730) follows the same order.
  - `estimate` is unchanged: it plans with a key only when given a source, else with the scripted stand-in.
  - **Why:** a worktree has no `.env`, and keys belong in the keychain.
  - **Rejected:** `.env` first (the keychain would be a fallback, against the rule); requiring `--keychain` (the
    default would stay `.env`).
  - **Tests:** `tests/cli/test_keys_cmd.py` covers keychain first, the `.env` fallback, neither source, an unavailable
    keychain, an explicit `--env-file` as the only source, and notices that name variables only.
  - **Order with the live pilot (train-2 land, 2026-10-22).** D-721's caps check comes first. A non-local endpoint
    entry without both caps is refused (exit 4) before any key source is read. That covers the keychain in the default
    mode and `--keychain` too: `--keychain` is checked for usage at the start but read only on the real-agent path,
    after the caps check. `--env-stdin` is still read first, because stdin is consumed before any other step (D-395).
    The test `test_an_uncapped_api_run_reads_no_key` covers both modes.
  - **Class 0.**

