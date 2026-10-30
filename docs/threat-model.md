# AgentPROV threat model

This is the reader's version of the security architecture. The normative text is
[`docs/architecture/G_security.md`](architecture/G_security.md): assets, adversaries and trust zones (G.1), the threat
register T-01…T-27 (G.2), the controls (G.3–G.9) and the security test catalogue SEC-01…SEC-26 (G.10). Where this file
and G disagree, G wins and this file is wrong. Which test proves which SEC row today, and what is still missing, is in
[`docs/reports/hardening/sec-coverage.md`](reports/hardening/sec-coverage.md).

## 1. What AgentPROV protects

AgentPROV turns raw agent-execution evidence into provenance that a paper can cite. Its claim is a specified,
evidence-qualified, recomputable derivation from hash-pinned raw bytes. The security work exists to keep that claim
true and to keep the researcher's machine and keys safe while handling hostile data.

| Asset | Why it matters |
|---|---|
| Integrity of raw evidence and of everything derived from it (AER, SEM, PROV, index, manifest) | A changed byte anywhere breaks the scientific claim |
| Honesty of evidence qualification (`ev` class, attesting party `by`) | An upgraded `O` claim is a fabricated observation |
| The researcher's machine and credentials (`.env` provider keys, `gh`, Hugging Face, Zenodo) | Keys carry cost and identity; wire capture is the main leak path |
| The published corpus and software release | Must leak no secret or personal data, respect licences, and verify for third parties |
| LLM coding agents working on the repository, and LLM consumers of the corpora | The corpora contain prompt-injection payloads by design |
| Availability of bulk import | One hostile file must not stop an import of tens of thousands; it is sealed with issues |
| Reproducibility | Recompute must stay byte-identical |

## 2. Who might attack it

Upstream authors are not presumed malicious. Any public artefact can still be crafted or replaced, so every control
is fail-closed, cheap and testable, and none mutates raw evidence.

| Adversary | What they can do | What they want |
|---|---|---|
| Artefact crafter | Craft or replace any public file (Zenodo, HF, GitHub assets, repository data) | Code execution, denial of service, writes outside a destination, local-file exfiltration through links, corpus poisoning |
| Adversarial content by design | Benchmark payloads aimed at models, kept in logs and corpora | Steer an LLM: a coding agent here, an analysis agent, a RAG or fine-tuning consumer |
| Upstream maintainer or compromised upstream | Force-push, new commits, malicious code in benchmark packages the live backends run | Code execution in the live environment; silently changed evidence |
| Supply-chain attacker | Compromised PyPI release, typosquat, compromised Action; CPython, git or uv bugs | Code execution at install, build, CI or run time |
| Post-release tamperer | Modify a copy of a deposit, or publish a look-alike | Forged evidence accepted as AgentPROV output |
| Credential harvester | Scrape git history, released corpora, CI logs | Keys and tokens |
| Accident | Truncated downloads, Python-written `NaN`, huge files, encoding mistakes | (the most common real failure) |

**Out of scope:** an attacker already running code as the user; physical access; breaking SHA-256; compromise of
GitHub, Zenodo or Hugging Face themselves (detectable only against an external anchor); a researcher fabricating their
own live captures (a hash chain shows consistency, not truth); side channels; concurrent local attackers on a
multi-user host.

**The live tier is the exception.** T2 deliberately runs pinned third-party benchmark code as the user, with network
access and, for real-model runs, a provider key. A T2 compromise is a compromise of the user account. The controls
make T2 output pass the same checks as any import; they do not contain a malicious T2. Containment exists only for
real-model runs under AD-13(b) (macOS `sandbox-exec` profile, G.4.10), and no real-model run has been made yet.

## 3. Trust zones and the four boundary rules

| Zone | What is in it | Rule |
|---|---|---|
| **Untrusted (U)** | Every imported file, archive and log; the *content* of AgentPROV's own capture logs (model replies, tool outputs, payloads); upstream repositories, including their `CLAUDE.md`, `AGENTS.md` and `SKILL.md` files; all imported metadata (model ids, timestamps, labels, versions, file names, in-band digests, self-declared provenance); AgentPROV's own deposits when downloaded again | Data only. Parsed only in T1 workers, under limits. Never executed, imported, `eval`'d, unpickled, used as a path, used to choose code, or shown unquoted |
| **Semi-trusted (S)** | Hash-locked dependencies; the benchmark code inside the separate live environments; model endpoints (their reports are claims `by: provider`); CI runners and SHA-pinned actions; git, uv, gitleaks, osv-scanner, Graphviz `dot` | May execute, only where declared, pinned and identity-checked |
| **Trusted (T)** | AgentPROV code at a reviewed commit; in-package profiles, catalogues, registry, schemas and vocabulary; the user's own configuration; the raw store as AgentPROV wrote it. **Not** the `rules/` copy inside a corpus, which is a record, never loaded | Selects code and rules; changes go through review and visible version bumps |

1. Data crosses from U to T only as sha256-addressed bytes in the raw store, and as values computed by T code in a T1
   worker and re-validated by the parent.
2. Nothing in U selects code. Readers are chosen by registry and profile; sniffing only picks among registered
   readers; no dynamic import is driven by data.
3. Nothing in U becomes a filesystem path.
4. U content reaches a human or an LLM only through `quote_untrusted`, and by default not at all: reports show
   locators and hashes.

Process tiers: **T0** is the parent (fetch, hash, store, manifests, write gate). **T1** is a pool of rlimited worker
processes (`python -I -B`, scrubbed environment, private `HOME`, CPU/memory/wall/file-size limits, an audit hook that
blocks network and subprocess events) for container expansion, sniffing, parsing and mapping. **T2** is the live
backend in its own uv project on Python 3.12.

## 4. Threats and controls at a glance

Each row condenses one G.2 row. "Tests" names the SEC rows; their current state is in the coverage report.

| Id | Threat | Main controls | Residual risk | Tests |
|---|---|---|---|---|
| T-01 | Malicious JSON (duplicate keys, `NaN`, `1e400`, huge integers, BOM, UTF-16, lone surrogates, depth bombs) | Byte cap before parse; strict UTF-8 of bytes; duplicate-key, non-finite and digit-cap rejection; iterative depth check (256); `$utf16` for escaped surrogates | CPython's C scanner (T-26); a document under the caps can still cost ~24× its size | SEC-01, 02, 04 |
| T-02 | Malformed JSONL (U+2028/U+0085 splitting, bare CR, silent truncation, CRLF, blank, NUL) | Binary LF-only framing; per-line cap with explicit over-length detection; distinct codes with `(line, offset)` locators; the rest of the file still mapped | A file truncated exactly at a line boundary | SEC-03 |
| T-03 | Oversized records and members | Size decided from `fstat` or the declared size before reading; per-document, line and member caps; a violation is a register row holding no bytes | A recorded override weakens the cap for that run | SEC-04 |
| T-04 | Recursive structures (deep JSON, YAML aliases and billion laughs, nested archives) | Iterative checks; YAML only via `ingest.yamlsafe` (1 MiB, no aliases); nested archives only where a profile declares them, depth ≤ 2 | In-process SEM puts a PyYAML defect in T0 | SEC-02, 05 |
| T-05 | Decompression bombs | v0.1 decompresses zip members (deflate, zstd) through a per-member gate (declared-size stop, CRC, size, ratio, running total) in T1, and a gzip tar nested in a zip through `iter_gzip_bounded` (one member, `max_stream_bytes`, ratio checked as the output grows, trailer CRC; D-57); other single compressed streams are stored inert and never decompressed; the container is read through a verified handle, never held whole (D-58) | CPU time below the cap (bounded by the worker limit) | SEC-06, 07 |
| T-06 | Archive bombs and metadata exhaustion | EOCD/ZIP64 size check before `ZipFile()`; member count, overlap, prefix and trailing-data checks after opening; methods {0, 8, 93}; encrypted members rejected; a top-level tar refused; a `tar.gz` inside a zip read by AgentPROV's own 512-byte header parser, never `tarfile` (GNU long names held only up to 1,024 B, obs-G1; pax, `K`, sparse and unknown types reject the archive; links and devices rejected members; D-57); selection globs bounded to two `*` per segment (D-59) | Pre-allocation bugs below CPython 3.14.8 (refused in release mode) | SEC-07 |
| T-07 | Path traversal | No extraction exists; names are labels; output paths only from ids and digests; locators resolve only inside the digest-checked artefact; deposit trees validated before opening | None known | SEC-08, 14, 15 |
| T-08 | Malicious file names (controls, ANSI, bidi, NFC/NFD and case collisions, reserved names) | `logical_name` (length checked before NFC); all colliding members rejected; names shown only quoted | Homoglyphs stay labels | SEC-09 |
| T-09 | Symlinks, hardlinks, FIFOs | Non-regular zip members rejected; git links stored as data; no-follow opens (`O_NOFOLLOW_ANY` on macOS, a `dir_fd` walk on Linux); `O_NONBLOCK`; `st_nlink > 1` refused unless allowed | The Linux walk has not been evaluated on a real Linux workstation | SEC-10, 14 |
| T-10 | Executable content (pickles, notebooks, scripts, polyglots) | Nothing from U is executed (static AST scan); magic-byte sniffing at offset 0; objects mode 0444, no exec bits; generic `artefact` content stored, never decoded | Someone opening a stored blob with another tool | SEC-11 |
| T-11 | Prompt injection in data and in the repository, aimed at LLM agents | Corpora live outside the repository; display only through `quote_untrusted`; content only with `--show-content`; escaped exception arguments; fixtures marked binary, excluded from search and denied to agents; `CLAUDE.md`/`AGENTS.md` rules | **High** for an agent reading raw files directly: fencing marks data as data, it cannot neutralise instructions | SEC-12, 13 |
| T-12 | Malicious tool outputs in live runs | Recorded verbatim; never re-parsed; bounded marker normaliser; transport-level capture does not change what the model sees | The agent under test may be steered (that is the experiment) | SEC-14 |
| T-13 | Forged provenance (embedded PROV, claimed digests and producers, a forged corpus with its own `rules/`) | In-band claims are `O` data `by: source`, never identity or PROV structure; `hadPrimarySource` only for native or byte-derived artefacts; `rederive` loads catalogues only from the package | A self-consistent forged corpus is caught only against the anchored root digest | SEC-15, 17 |
| T-14 | Corrupted provenance (bit rot, partial writes, edited manifests, regenerated checksums) | Digest chain raw → AER seal → SEM → PROV → index → manifest → checksums → root digest; never-overwrite store protocol; `verify` at three levels | The only copy can be detected corrupt, not repaired | SEC-15 |
| T-15 | Altered timestamps | Times are claims, never ordering or causal evidence; never fabricated; an implausible time is flagged (`time.implausible`), never corrected | A plausible false time | SEC-18 |
| T-16 | Reordered events | Capture hash chain (`seq`, `prev`); AER backward-only references, canonical order and seal | A source that consistently mis-orders its own log | SEC-16 |
| T-17 | Duplicate executions | `source_key` collapse with several origins; ownership declared once (`select.owned_elsewhere`) | Near-duplicates with different bytes (fingerprints deferred, AD-10 row 7) | SEC-19 |
| T-18 | Model identity spoofing | Identity from the profile's rules, never one self-reported field; requested and served both kept, conflict is `identity_conflict` | A provider that consistently misreports | SEC-20 |
| T-19 | Benchmark metadata poisoning (`/`, `..`, ANSI in ids; unknown tools; undeclared generic `type`s) | Identity from observed commits or digests; unknown tools fail closed in SEM; closed AER vocabularies; generic `type`s must be declared in the family catalogue | Consistent mislabelling upstream (traceable to `by: source`) | SEC-21 |
| T-20 | Source-hash manipulation and hostile references | AgentPROV computes every digest; pins are 40-hex commits plus blob SHA-1 and recorded sha256; references resolve only against in-package origins; tokens only to the declared host, never across redirects | A malicious first acquisition is faithfully preserved | SEC-15, 24 |
| T-21 | Adapter supply chain (malicious adapter, profile or catalogue) | In-repo registry with namespaced factories; profiles and catalogues only from package resources; profile files refused in release mode; readers and mappers import only stdlib and `agentprov` | A reviewed but subtly wrong mapper | SEC-23 |
| T-22 | Malicious dependencies | Minimal core runtime set; stdlib-only parsing of untrusted bytes; `uv sync --locked`; fixed `exclude-newer`; osv-scanner plus `uv lock --check` | A malicious release older than `exclude-newer` and unknown to OSV | SEC-23 |
| T-23 | Malicious plugins | No plugin loading (`entry_points` forbidden in `src/`) | None in v0.1 | SEC-23 |
| T-24 | Compromised upstream repositories | Exact commits only; hardened bare fetch (no hooks, no working tree, no submodules, no LFS smudge, `fsckObjects`, no lazy fetch from a promisor remote, absent blobs refused; D-54); T0 cross-checks backend identity before and during a live run | Malicious code already at the pin runs in T2 as the user | SEC-24, 14 |
| T-25 | Secret leakage | Allowlist capture with a hard denylist and fail-closed scan; a purged (tombstoned) object is never stored or downloaded again (D-61); keys only in T2; T0's staging re-scan quarantines; home-path and host-name redaction; gitleaks pre-commit, over history in CI and over release trees; `WITHHELD.json`; `purge` tombstones | Secrets in unknown formats inside third-party data; a leaked key must be revoked | SEC-25 |
| T-26 | CPython parser vulnerabilities | Core on ≥ 3.14 (CI on the latest patch); below 3.14.8 release mode refuses archive and stream ingestion, dev mode warns and records; parsing in T1 | Unknown memory-safety bugs in C parsers give code execution in T1 (no T1 OS sandbox; AD-10 row 18) | SEC-26, 22 |
| T-27 | (reserved) Outcome replay | Deferred (AD-10 row 2); a T-27 row and protocol must be added before any replay code lands | — | — |

## 5. What the controls do not give

- **Truth.** An imported log is evidence of what the source harness recorded (`by: source`), not of what happened.
  A consistently lying upstream is undetectable; it can only be attributed and cross-checked.
- **Isolation from a malicious T2.** See §2. Real-model runs need dedicated spend-capped keys and the user's consent
  (U-10), and `--containment`.
- **Protection of an agent that reads raw data directly.** Corpora and fixtures carry injection payloads. The repo
  makes it hard to read them by accident (search ignores, deny rules, binary attributes), but an agent told to open a
  fixture will see its text. Treat every such text as data.
- **Platform breadth in practice.** CI covers Linux x86_64/arm64, macOS and Windows; real use has been on macOS arm64
  only. Windows has no CPU limit and assigns the Job Object after spawn (G.4.12(7)).
- **CI evidence while Actions is blocked.** GitHub Actions has refused to start jobs since 2026-10-09 (billing), so
  the `secrets` (gitleaks) and `dependencies` (osv-scanner) jobs have no recent run on record. The DoD evidence for
  Q.16 and Q.17 is recorded with that caveat (`docs/reports/hardening/dod-evidence.md`).

- **Memory of a provenance job on the longest runs.** `prov` jobs run under a declared 4 GiB cap (16 GiB ceiling; D-55);
  a run whose tier-4 validation needs more is registered `worker.limit.rss` (or `worker.limit.output` when its PROV-JSON
  exceeds 256 MiB) with its sealed AER kept, not validated (`docs/reports/hardening/prov-rss.md`).

## 6. Process controls (not unit tests)

The DoD (Q.15 as amended) documents these instead of asking for a test per threat:

- **Dependency scanning:** osv-scanner in CI (job `dependencies`) and `uv lock --check` on all five lockfiles
  (job `core`).
- **Secret scanning:** gitleaks over the full history in CI (job `secrets`) and as a pre-commit hook; the
  repository-hygiene test greps tracked files for common key patterns.
- **Pinned-fetch hardening:** `agentprov.raw.fetch` (bare fetch, exact commits, blob SHA-1), tested on a local
  synthetic repository (SEC-24).
- **Interpreter policy:** `requires-python = ">=3.14"`, `.python-version` 3.14, CI on the latest 3.14 patch, the
  3.14.8 release-mode floor without an override flag (SEC-26, DoD Q.15a).
- **Agent hygiene:** `.gitattributes`, `.ignore`, `.rgignore`, `.claude/settings.json` deny rules, the Unicode
  control-character check in `lint` (SEC-13, DoD Q.31).

## 7. Reporting a problem

The repository is private. Report a security problem to the maintainer directly, not in an issue that quotes the
payload. Quote hostile text only through `agentprov.ingest.quote.quote_untrusted`.
