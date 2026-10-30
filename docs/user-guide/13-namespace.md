# 13. Vocabulary and identifiers

The terms in AgentPROV's PROV documents (`apv:evidenceClass`, `apv:ToolExecution`, …) come from the AgentPROV
vocabulary, `apv`. This chapter explains how to look a term up, how to tell which vocabulary version a corpus uses,
where the vocabulary is published, and (for maintainers) how a new version is published.
[Chapter 2](02-concepts.md#the-agentprov-vocabulary-apv) explains what the terms are for.

| | |
|---|---|
| Namespace | `https://w3id.org/agentprov/ns#`, prefix `apv:` |
| Ontology IRI | <https://w3id.org/agentprov/ns> |
| Current version | apv 0.2.0 (published 2026-10-22), `owl:versionIRI` `https://w3id.org/agentprov/ns/0.2.0` |
| Execution instance IRIs | `https://w3id.org/agentprov/exec/<execution-id>#<local-id>` (identifiers only) |
| Source of truth | [`src/agentprov/vocab/apv-0.2.ttl`](https://github.com/nickjones39/AgentPROV/blob/main/src/agentprov/vocab/apv-0.2.ttl) in the AgentPROV repository |
| Published copies | the public repository [`nickjones39/agentprov-ns`](https://github.com/nickjones39/agentprov-ns), served by GitHub Pages |

## Looking up a term or a version

The ontology IRI and each version IRI answer with **303 See Other**. Where they send you depends on what the client
asks for:

| Request | Redirected to |
|---|---|
| `https://w3id.org/agentprov/ns` with `Accept: text/turtle` | the current vocabulary as Turtle (`…/agentprov-ns/ns/apv.ttl`) |
| `https://w3id.org/agentprov/ns` from a browser | the current documentation page (`…/agentprov-ns/ns/`) |
| `https://w3id.org/agentprov/ns/<x.y.z>` with `Accept: text/turtle` | that version's Turtle (`…/agentprov-ns/ns/<x.y.z>/apv.ttl`) |
| `https://w3id.org/agentprov/ns/<x.y.z>` from a browser | that version's page (`…/agentprov-ns/ns/<x.y.z>/`) |

A term IRI such as `https://w3id.org/agentprov/ns#ToolExecution` is the ontology IRI plus a fragment. A browser opens
the documentation page at that term's entry (`#ToolExecution`); an RDF tool fetches the Turtle and finds the term in it.
Term IRIs carry no version: the same term has the same IRI in every version.

From a terminal:

```bash
curl -sI -H 'Accept: text/turtle' https://w3id.org/agentprov/ns     # the Turtle redirect
curl -sI https://w3id.org/agentprov/ns                              # the HTML redirect
curl -sL -H 'Accept: text/turtle' https://w3id.org/agentprov/ns/0.1.0   # the 0.1.0 Turtle itself
```

*Checked on 2026-10-22 (06:52 UTC):* `https://w3id.org/agentprov/ns`, `/ns/0.1.0` and `/ns/0.2.0` each answered
`HTTP/1.1 303 See Other`, with `Location: https://nickjones39.github.io/agentprov-ns/ns/…apv.ttl` for
`Accept: text/turtle` and the matching HTML directory otherwise. The `/ns/0.2.0` redirect worked before 0.2.0 was
published; its target files appeared with the publication on 2026-10-22 (see the status table below). A second check after
the publication (20:49 UTC) found the same three redirects and the served `ns/apv.ttl` and `ns/0.2.0/apv.ttl` equal to the
source (sha256 `2c6407d1…ca5e`).

**Execution IRIs do not resolve to anything specific.** `https://w3id.org/agentprov/exec/…` leads to a page explaining
that these IRIs are identifiers. An execution is described by the corpus that contains it: look its id up in the
corpus's `executions.jsonl`, or run `agentprov inspect <execution-id> --corpus DIR`.

## Which version a corpus uses

A corpus records its vocabulary version in two places:

- **`corpus.json`**, under `ontology`:

  ```json
  "ontology": {"iri": "https://w3id.org/agentprov/ns#", "prefix": "apv", "version": "0.2.0"}
  ```

  The corpus format fixes it: `agentprov-corpus/0.2` corpora record 0.2.0, `agentprov-corpus/0.1` corpora 0.1.0.
- **every PROV document**, on its derivation activity (`xd:derive.<key>`, the activity of rule `aprov.t_derive@1`):

  ```json
  "apv:vocabularyVersion": "0.2.0"
  ```

To read the terms a document used, fetch the matching version IRI, for example
`https://w3id.org/agentprov/ns/0.2.0`, not the version-free one, which always gives the latest version.

## The agentprov-ns repository

[`nickjones39/agentprov-ns`](https://github.com/nickjones39/agentprov-ns) is the public GitHub Pages site that
w3id.org redirects the `/ns` and `/exec` IRIs to. It holds only published vocabulary files and pages:

```text
index.html            the namespace site's own landing page (https://w3id.org/agentprov/ leads to the project website)
exec/index.html       the page that explains execution instance IRIs
ns/apv.ttl            the current version, Turtle
ns/index.html         the current version, documentation page
ns/<x.y.z>/apv.ttl    each published version, kept unchanged
ns/<x.y.z>/index.html
.nojekyll, LICENSE    (content licensed CC BY 4.0)
```

Nothing there is edited by hand. Each Turtle file is a byte copy of the AgentPROV source of truth, and each page is
generated from it by `tools/ns_page.py`. **A published `ns/<x.y.z>/` is never changed**, and terms are never deleted
after release, only deprecated, so a document that names a version can always be read with that version's terms.

## Version status

| Version | Published at `ns/<version>/` | Date | Notes |
|---|---|---|---|
| 0.1.0 | yes | 2026-10-08 | agentprov-ns commit `8ac6511`; recorded by `agentprov-corpus/0.1` corpora; 96 classes, 156 properties, 125 individuals |
| 0.2.0 | yes | 2026-10-22 (UTC) | agentprov-ns commit `7ee2fde`; the version the code writes (`agentprov-corpus/0.2`); minor and additive over 0.1.0: 96 classes, 183 properties, 125 individuals; adds 27 terms (the `apv:<property>Status` properties of D-500 and `apv:adapterAssumption` of D-501), changes none |

The version-free IRIs now serve 0.2.0; 0.1.0 stays available at its own version IRI. A corpus carrying 0.2.0 terms may be
deposited now that the 0.2.0 IRIs resolve (a deposit still needs the project owner's explicit instruction).

## Publishing a new vocabulary version (maintainers only)

Publishing makes a version public and permanent. It needs the **project owner's explicit go**, every time.

The procedure, from
[`docs/ns/README.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/ns/README.md):

1. **Check the source.** In the AgentPROV checkout, `uv run python tools/sync_ns.py --check` must pass: the
   repository's published copy `docs/ns/apv-<x.y>.ttl` equals the source of truth
   `src/agentprov/vocab/apv-<x.y>.ttl`. A new version adds terms only; check that every term of the previous version
   is still declared.
2. **Copy the Turtle** byte for byte into a clone of `agentprov-ns`, twice: as `ns/apv.ttl` (the current version) and
   as `ns/<x.y.z>/apv.ttl` (the versioned copy).
3. **Render both pages** from the AgentPROV checkout:

   ```bash
   uv run python tools/ns_page.py --out <agentprov-ns>/ns/<x.y.z>/index.html
   uv run python tools/ns_page.py --out <agentprov-ns>/ns/index.html
   uv run python tools/ns_page.py --check <agentprov-ns>/ns/<x.y.z>/index.html
   uv run python tools/ns_page.py --check <agentprov-ns>/ns/index.html
   ```

4. **Never edit a published `ns/<version>/`**, not even to fix a typo: a correction is a new version.
5. **Update the agentprov-ns README** (current version, counts, version list) and commit only the new files and the
   changed current-version files; push fast-forward only.
6. **The w3id rules need no change.** The redirects in `perma-id/w3id.org` already cover every `/ns/<x.y.z>`.
7. **Check the live result** with the `curl` commands above, for the new version and the version-free IRI, and
   compare the served file's sha256 with the local one.
8. **Run `uv run python tools/sync_ns.py --check` again**, and record the publication (date and agentprov-ns commit) in
   `docs/ns/README.md`.

Safeguards:

- Corpora that carry `https://w3id.org/agentprov/` IRIs of a version are not deposited until those IRIs resolve
  (DECISIONS Addendum D-3).
- `tools/ns_page.py` and `tools/sync_ns.py` take no network access; only the push and the final check do.
- The vocabulary's own text is copied as it is: a statement in the Turtle that is out of date is fixed in the source
  (a new version of the file in AgentPROV), never in the published copy.
