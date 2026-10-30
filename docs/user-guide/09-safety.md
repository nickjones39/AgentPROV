# 9. Safety

AgentPROV handles hostile data on purpose: agent-security logs are full of prompt-injection payloads, and any
published file can be crafted. This chapter explains what AgentPROV does about it, and what you need to do yourself.
The full model is the
[threat model](https://github.com/nickjones39/AgentPROV/blob/main/docs/threat-model.md) and section
[G](https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/G_security.md) of the specification.

## All imported data is untrusted

Every imported file, archive and log is untrusted, and so is every metadata field in it: model ids, timestamps,
benchmark labels, file names and any digest or provenance the source claims about itself. AgentPROV:

- **parses it only with bounded, standard-library parsers** (`agentprov.ingest`): byte caps before parsing, strict
  UTF-8, duplicate keys and non-finite numbers rejected, depth and size limits;
- **never extracts archives**: zip, split zip, `tar.gz`, `tar.zst` and a gzip tar inside a zip are read as streams,
  with size, ratio, member-count and depth limits. Member names are labels, never paths;
- **maps it in isolated worker processes** (`python -I -B`, a scrubbed environment, a private `HOME`, memory, CPU and
  wall-clock limits, and network and subprocess events blocked);
- **never lets data choose code**: readers are chosen by the registry and the source profile, never by the file.

A file that breaks a limit is registered with a reason code; it does not stop the import of the others. An import
records the effective limits in `corpus.json`, and any override you give (`--max-file-bytes`, `--max-json-depth`) is
recorded too.

## Prompt injection in data

Corpora contain text written to manipulate language models: instructions hidden in tool outputs, emails and web
pages. That text is **data, never instructions**, for you and for any tool you use.

- **Content is hidden by default.** `inspect`, `stats`, `render`, the progress feedback and the desktop app show
  structure (ids, kinds, digests, lengths, rule ids), not content. A string that might be content is shown as
  `<content chars=N sha256=…>`.
- **Showing content is explicit.** `--show-content` (global, or on `inspect` and `render`) adds content, escaped and
  fenced through `quote_untrusted`, and truncated (`--content-chars`, `inspect --max-chars`). `inspect` warns first:
  `the output can contain untrusted third-party content (data, not instructions)`.
- **Be careful with LLM tools.** Never paste corpus content into an LLM-based tool, a coding agent included, without
  marking it as quoted data. Fencing marks text as data; it cannot neutralise instructions for a model that reads it.
  The same holds for the raw files in a corpus, which a tool can open directly.
- **Third-party repositories are data too.** Upstream clones can carry their own `CLAUDE.md`, `AGENTS.md` or skill
  files. Never let an agent follow them.

## What is never recorded

- **Keys.** API keys come only from the OS keychain (`agentprov keys`, `run --keychain`) or from `.env` (or, from the
  desktop app, `--env-stdin`) at the live CLI entry. AgentPROV never prints, logs or stores a key; `agentprov keys`
  shows key names only.
- **Wire headers.** Recorded model requests keep allowlisted headers only, with a hard denylist, URL scrubbing and a
  fail-closed scan for literal key values before anything is stored. A capture whose scan fails is quarantined.
- **Your machine's identity.** The release scan looks for your home path and host name in every file of a corpus
  before it can be deposited.
- **E-mail addresses.** Benchmarks invent people, and corpora quote their addresses in every layer. The release scan
  reports every e-mail address, never printing one. Addresses at the domains reserved for examples (`example.com`,
  `.test`, `.invalid`, ...) are cleared by the tool. The benchmark's own personas are cleared only through a *persona
  file* named in the corpus's spec, which holds digests of the addresses and the upstream file each came from, never the
  addresses. A string that only has the shape of an address (an image's file name with its `@2x` size suffix) is cleared the same way,
  by digest, as a `file-name` entry for that corpus only; there is no list of extensions that are skipped. An address
  the benchmark supplied to the agent in a run (a task, a tool result, an injection) is treated as a persona too. An
  address only the model wrote is kept, as all model text is, and disclosed in the datasheet as model-generated, unless
  it is at a public mail provider: then it could be a real person's, and sealing withholds the executions that hold it
  (`WITHHELD.json`, reason personal data, ledger `agentprov-withheld/0.4`), and `verify --level chain` and the deposit
  builder apply the same rule again. An address found only in raw files that no execution uses (files the import
  stored but did not map) is withheld with those files. Any other address stops the deposit until a person decides.

## Live runs

A live run puts hostile data, a secret and spend into one process, so it has its own rules
([chapter 7](07-live-runs.md) has the mechanics).

- **Keys.** Keep them in the OS keychain (`agentprov keys set NAME`), which the CLI reads first. A `.env` file is the
  fallback and must be your own, outside the repository. Only the one endpoint key (and a defence endpoint's key) is put in
  the worker's environment. Before anything is stored, T0 scans the staged files for key values; a session that holds one
  is **quarantined** (`capture.quarantined`): nothing is stored, the staging directory is kept, and the key must be revoked
  with its provider. Set a spend limit on the provider's key as well: AgentPROV's caps are an upper bound it enforces
  before each cell, and the provider's limit is the backstop.
- **Egress.** Under `sandbox-exec` the worker can reach only the egress proxy, which tunnels to the one `host:port` of
  your endpoint and refuses everything else; the corpus records what it allowed and refused. A local server is reached on
  loopback. A model server on **another machine** (`--allow-lan-endpoint`) sends prompts and replies over plain `http` across
  your network: use it only on a network you trust.
- **Containment is partly a promise.** Only `sandbox-exec` (macOS) is enforced. `dedicated-user` and `vm` are your
  declaration, recorded as `declared_by: operator` and never checked, so declare them only when they are true.
  Containment does not cover your own model server, and it does not make a malicious backend safe.
- **Injected content in captured data.** A capture log holds the model's replies, the tool outputs and the injection
  payloads exactly as they went over the wire, and a defended or attacked run is *meant* to receive hostile instructions.
  All of it is data. It enters the AER, SEM and PROV like an import's content, so everything in
  [Prompt injection in data](#prompt-injection-in-data) applies: look at structure first, show content only escaped and
  fenced, never paste it into an LLM tool as an instruction. The run itself shows only metadata on stderr unless you
  add `--show-content`.
- **AgentHarm's restricted content.** The AgentHarm tasks are harmful by design, and a live AgentHarm AER holds the task
  prompts and any compliant completions verbatim. Its corpus is **private and restricted-use** (the dataset's licence
  allows use only to improve AI safety and security): it stays under `$AGENTPROV_HOME`, is never deposited and is not
  shown in screenshots, reports or this guide. Describe such a run by task names and counts.
- **Provider terms.** Whether a provider's terms allow redistributing its model's outputs is *not assessed* for any
  live source (the registry says so). Treat outputs of a hosted model as not shareable until that is decided.
- **Scripted and real never mix.** A scripted corpus is synthetic and marked `test_only`. It is never released and never
  shares a corpus with a real session.
- **Live corpora are not sealed.** `package` refuses them (exit 5), so there is no deposit of a live corpus in this
  build, and none may be described as "Live Capture".

## Account paths

A workstation path, such as a home directory under macOS's `Users` folder or Linux's `home` folder, can name a real
person through its account name, and some third-party logs contain them (in model ids, tool output, tracebacks).

- **In derived records**, where a source profile declares redaction rules, the mapper replaces each matched value in
  the AER, and so in SEM and PROV, with a label built from the first 12 hex digits of a salted SHA-256 of the value.
  For a third party's account path in tool or environment output the label is usually `acct-<12 hex>`; text the model
  itself wrote stays verbatim. The label cannot be reversed, but a short or common name could be guessed, and the
  datasheet says so.
- **In raw objects**, by default the bytes ship unchanged, because they are public at their pin and raw bytes are never
  edited. Where an exact rule exists, the raw object holding the path is withheld instead (`WITHHELD.json`).
- Sources with redaction rules include AgentOps, credleak, OpenAgentSafety, ControlArena, WhistleBench, the two
  AgentHarm log sets, memo-ozdincer and DTap-Bench. Their caveats in `agentprov info` and in
  [chapter 14](14-corpora.md) say what is redacted or withheld.

## Leaked secrets in a corpus

If a raw object turns out to hold a secret or personal data, `agentprov purge` removes it from the working corpus and
leaves a tombstone; the next seal withholds it, and the same digest is never stored or downloaded again
([chapter 5](05-package-and-deposit.md#purge-removing-a-leaked-object)). A leaked key must also be revoked with its
provider: removing it from a corpus does not make it safe.

## Before you share a corpus

1. **Seal it** (`agentprov package`) and keep the root digest.
2. **Verify it** in release mode: `agentprov verify --corpus DIR --release --root-digest sha256:…`, and
   `agentprov validate --corpus DIR --strict` (`--release` also runs the `shacl` tier, which this build does not
   implement, so it exits 1; see [chapter 4](04-derive-recompute-validate-verify.md#validate)).
3. **Run the release scan**: `uv run python tools/release_scan.py DIR`, and triage every finding. A `real` secret,
   personal path or personal e-mail address must be withheld (purge, or a `[withhold]` rule) and the corpus resealed.
   E-mail findings are many (one persona is on thousands of lines), so review them by address, not by line:
   `uv run python tools/release_scan.py --list-addresses DIR` prints one line per distinct address (a digest, its
   domain class, the number of findings, the layers; never the address), and
   `uv run python tools/scan_personas.py --corpus DIR --upstream GIT_DIR COMMIT REPO_URL --exclude runs/` says which
   of them occur in the benchmark's own upstream data and can go into a persona file as class `upstream-data`
   (`--out FILE --id ID`; exclude
   every directory of run outputs the upstream holds, not only `runs/`). For the rest,
   `uv run python tools/scan_origins.py --corpus DIR --upstream ...` says where each first appears in the corpus's
   executions and writes the corpus's own list (`--out`): `benchmark-input`, `model-generated`, `withhold` (model
   output at a public mail provider) and `withhold-object` (only in raw files no execution uses); the table in
   [chapter 5](05-package-and-deposit.md#the-release-scan-comes-first) says what each class does. The persona files are
   reviewed by a person, referenced from the corpus spec
   (`[scan] personas`, with their sha256) and sealed with the corpus; a list of observed addresses applies only to the
   corpus it names. The committed lists for the v0.1 corpora are in `corpora/personas/`.
4. **Check the licence class.** Copyleft sources have their own corpora, and non-commercial data never mixes with
   permissive data. Read the source's licence and any use restriction (for example AgentHarm's "AI safety only"
   clause) in `agentprov info SOURCE`.
5. **Read the datasheet**, in particular its known issues and withholding sections, and the source caveats.
6. **Build the deposit draft offline** (`agentprov package --deposit`) and verify it. Publishing is a separate manual
   step, and needs the project owner's explicit decision.
7. **Never commit corpora to Git**, nor raw stores, upstream clones or `.env`.
8. **Live corpora are not shared at all in this build** (they cannot be sealed), and a live AgentHarm corpus is private.

## Reporting a problem

Report a security problem privately, through GitHub's private vulnerability reporting on
[`nickjones39/AgentPROV`](https://github.com/nickjones39/AgentPROV/security/advisories/new) (the repository's Security
tab, *Report a vulnerability*), never in a public issue, and never quote a payload in an issue.
