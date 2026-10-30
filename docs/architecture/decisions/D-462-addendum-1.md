- **D-462 addendum (2026-10-24, eight more accepted gitleaks false positives; user decision relayed by the orchestrator).**
  - **Found:** the first full-history `secrets` run of `tools/ci_local.py` since GitHub dispatch was blocked by billing
    (2026-10-22) reported 8 `generic-api-key` findings in two commits that no full-history scan had covered.
  - **Reviewed** by masked shape and location only (never the value):
    - `docs/architecture/decisions/D-269.md` line 5: the credleak benchmark's own placeholder literal, which D-269
      already triages as false-positive class (b) (user decision 2026-10-13);
    - 7 lines in `docs/reports/precheck/data/{controlarena-persistent,kexin-xu-01-agentharm,openagentsafety}/l2-sample-*.json`:
      sha256 digests (64 hex) of benchmark log files whose file names contain "key", "api" or "token" (pre-check
      census data, 2026-10-15). None is a credential.
  - **Accepted** as 8 commit-pinned fingerprints in `.gitleaksignore` (12 in all); the repository test now expects 12.
    A new commit, file or line is still a new finding, so no key can hide behind them.
  - **Rejected:** a whole-secret allowlist for 64-hex values in `.gitleaks.toml` (would also pass a real hex-shaped key
    anywhere); rewriting the census files (history keeps the old bytes, so the full-history scan still reports them).
