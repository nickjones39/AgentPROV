# 12. Glossary

**Adapter.** The code and data that turn one log format into AERs: a reader (one or more dialects), a mapper, source
profiles, a rule catalogue and semantics tables. Adapters supply data; they never define PROV semantics.

**AER.** AgentPROV Execution Record (`aer/0.2`): one JSONL file per execution with typed records, explicit unknowns,
locators into the raw bytes and a seal. Always written out in full; not the "Agent Execution Record" of Vispute and
Kadam.

**apv.** The AgentPROV vocabulary, namespace `https://w3id.org/agentprov/ns#`: classes, properties and individuals that
qualify W3C PROV statements (evidence class, rule, source pointer, statuses). Current version 0.2.0. See
[chapter 13](13-namespace.md).

**Artefact (source-data).** A known defect or quirk of a source's harness or data, listed in the adapter's
`artefacts.toml` with a handling class (CR, DR, RJ, FO, NR). Not to be confused with the generic AER record kind
`artefact`.

**Assessment bundle.** The PROV bundle that holds claims that are not PROV facts: integrity labels, exposure, taint,
injection markers.

**Bundle.** A named PROV graph inside a document: the core bundle, one inference bundle per method, and assessment
bundles.

**Canary.** The first `--canary N` cells of a live run (default 10), checked for known capture problems (A3, A4, A6, A11, A12, A14). A condition stops the campaign; re-running the same command resumes. See [chapter 7](07-live-runs.md#quality-checks-retries-and-run-states).

**Candidate.** A file or archive member an import considered. Every candidate is in the register, mapped or not.

**Caps.** `--max-calls` and `--max-cost-usd` (priced with `--price-in` and `--price-out`): an upper bound on the billed calls and the spend of a live corpus, enforced before each cell starts. Required for an API endpoint.

**Cell.** One execution of a live plan: a suite, a user task and, for an attacked cell, an attack and an injection task. For an Inspect plan, a batch of at most `--cell-size` samples evaluated together.

**Configuration digest, plan digest.** The plan digest hashes a live plan's expanded cells and the agent and backend configuration; the configuration digest adds the backend's identity. They decide whether two runs are "the same run" when one resumes the other.

**Containment.** What a real-model run declares with `--containment`: `sandbox-exec` (macOS only; enforced, backed by a passed probe) or `dedicated-user` and `vm` (declared by the operator, recorded and never checked).

**Content digest, root digest.** Two digests of a sealed corpus. The root digest is the sha256 of `checksums.sha256`
and identifies the exact sealed tree; publish it outside the corpus.

**Corpus.** A directory of executions with a manifest (`corpus.json`), an index (`executions.jsonl`), a register and a
digest chain from raw bytes to PROV. A **working tree** (`DIR.partial`) is being written; a **sealed** corpus (`DIR`)
is never modified.

**Core bundle.** The PROV bundle with observed and derived statements only, each with its evidence class, rule and
source pointer.

**Defence.** A protective mechanism run as the experimental treatment of a live plan (`--defence NAME`, a registry id). Recorded as treatment, not as instrumentation. Only the `agentdojo` backend builds them.

**Deposit draft.** The offline output of `package --deposit`: deterministic archives and metadata, ready for a manual
upload that AgentPROV never makes.

**Dialect.** One variant of a log format that a reader understands (for example `v0.k11` and `v1.k14` of AgentDojo's
TraceLogger).

**Display name.** The name by which attacks such as `important_instructions` address the model. A model id without a stock name needs `--model-display-name`.

**Egress proxy.** The CONNECT-only proxy T0 starts for a sandboxed run to a non-loopback endpoint: it tunnels to the endpoint's exact `host:port` and refuses everything else. What it allowed and refused is recorded as `live.egress`.

**Endpoint class.** `local` (a `local = true` endpoint on loopback) or `api` (everything else), decided before consent. It sets the consent flag and whether caps are required.

**Environment id.** The name of a built backend environment, such as `agentdojo-db3901f1`: the backend plus the first 8 hex digits of the sha256 of its lockfile (for a version-pinned backend) or of its fork commit (for the git-pinned AutoDojo and AgentDyn). A new lock gives a new id for a version-pinned backend.

**Evidence class.** O (observed), D (derived by a declared rule) or I (inferred under a named assumption). Combining
classes gives the weakest.

**Execution IRI.** An identifier of a node of one execution, `https://w3id.org/agentprov/exec/<execution-id>#<local-id>`
(prefix `x:`). Not individually dereferenceable.

**Fetch cache.** `$AGENTPROV_HOME/cache`: verified, extraction-free copies of pinned upstream bytes, and the log of
every download (`acquisitions.jsonl`).

**Inference bundle.** A PROV bundle of inferred statements, one per method (set of assumptions).

**Issue.** A note on an AER's seal with a code and the rule that raised it, for example
`map.earlier_attempts_unobservable`. An execution with issues is still sealed and kept.

**Live run.** Executing a benchmark in a backend and capturing raw evidence (`capture/0.1`), then importing it like a
released log.

**Live status.** A live part's registry status: `partial` (real-model runs are admitted for a stated subset, with consent, caps and containment) or `planned` (scripted runs only). There is no `gated` status.

**Part.** One registered subset of a source (a snapshot, a branch, an archive), with its own status and profile.

**Pin.** The exact published bytes a part refers to: a git commit (and tree), a Zenodo file, a Hugging Face file or a
URL file, with digests. Imports refuse bytes that do not match.

**Preflight probe.** A small request sent through the recording transport before the first cell of a real run, to check reachability, message roles, tool calls and transmitted parameters. At most three calls, each charged to the caps.

**Purge.** Removing a leaked raw object from a working corpus, leaving a tombstone; the next seal withholds it.

**Raw store.** `raw/objects/` in a corpus: source bytes stored unchanged under their sha256, with their origins.

**Recompute.** Re-deriving a corpus from its stored raw objects or AERs and comparing bytes. "0 differences" means every
output is byte-identical.

**Register.** `register.jsonl`: one row per candidate with its disposition and a reason code.

**Release mode.** Strict checks (`--release`): no filters or limits, every applicable validation tier, unverified
checks fail, and the interpreter must be 3.14.8 or later.

**Rule catalogue.** The versioned list of rules (`aprov` for the engine; one per adapter family) that every derived
value and PROV statement cites.

**Scripted transport.** `--llm-script FILE`: a live run whose model is a list of canned replies. No network, no keys, no cost. Its sessions are `test_only` and its corpus is synthetic and never released.

**Seal.** The last record of an AER, with the digest over all records; also, `package` turning a working tree into a
sealed corpus.

**SEM.** Standoff semantic annotations (`sem/0.1`) from a versioned semantics profile.

**Source profile.** The data that pins a part's bytes and says how to map them (`<id>.profile.toml`, with an integer
version).

**Spend upper bound.** The ceiling `live.caps` records for a run's cost, priced from the per-call bound; a real bill is lower.

**T0, T1, T2.** The process tiers: T0 is the `agentprov` process (fetch, store, checks); T1 the rlimited workers that parse and map untrusted bytes; T2 the live backend worker, which runs pinned third-party benchmark code.

**Tier 4.** The W3C PROV round-trip check, the most expensive validation step; its results are cached.

**Tombstone.** The record a purge leaves in place of a removed raw object.

**versionIRI.** `owl:versionIRI`: the IRI of one version of an ontology, such as `https://w3id.org/agentprov/ns/0.2.0`,
beside the version-free ontology IRI `https://w3id.org/agentprov/ns`.

**w3id.** [w3id.org](https://w3id.org/), a permanent-identifier service run by a W3C community group. AgentPROV's IRIs
under `https://w3id.org/agentprov/` redirect to wherever the vocabulary is hosted.

**Withholding.** Leaving raw objects (and the executions citing them) out of a sealed corpus's released tree,
listed by digest in `WITHHELD.json`, instead of editing them.
