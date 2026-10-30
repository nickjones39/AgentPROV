# w3id pull request: point `w3id.org/agentprov` at the project website (prepared, not submitted)

**Status (2026-10-29):** prepared only, for the layout the user chose ("yes option 2": the website on the AgentPROV repository's Pages, the guide at `/docs/`). Nothing has been pushed, forked or opened. Submitting it is a public action on
the owner's GitHub account, so the orchestrator asks the owner when. Recommended: release day, after the website is
live (go-live step 6 in `docs/user-guide/_go-live.md`), so the new targets resolve the moment the redirect is merged.
Decision: D-1000.

## What it changes

`perma-id/w3id.org` serves our space from `ids/agentprov/` (PR 6836, merged 2026-10-09; the versioned `/ns/<x.y.z>`
rules came in 0a74ba5d and d6e64b1b). Today its last rule sends everything that is not `/ns` or `/exec`, including
the bare `w3id.org/agentprov/`, to the vocabulary site `nickjones39.github.io/agentprov-ns/`. The patch adds two rules
just before that catch-all and documents them; **no existing line changes**, so every `/ns` and `/exec` rule stays
exactly as it is.

| Request | Today | After the patch |
|---|---|---|
| `/agentprov/` | `agentprov-ns/` (302) | `https://nickjones39.github.io/AgentPROV/` (302) |
| `/agentprov/docs`, `/agentprov/docs/` | `agentprov-ns/docs` (302, a 404) | `https://nickjones39.github.io/AgentPROV/docs/` (302) |
| `/agentprov/docs/08-desktop-app/` | `agentprov-ns/docs/08-desktop-app/` (302, a 404) | `…/AgentPROV/docs/08-desktop-app/` (302) |
| `/agentprov/ns`, `/ns/`, `/ns/0.1.0`, `/ns/0.2.0` (HTML or Turtle) | unchanged (303) | unchanged (303) |
| `/agentprov/exec/…` | unchanged (302) | unchanged (302) |
| any other path, for example `/agentprov/docsx` | `agentprov-ns/<path>` (302) | unchanged |

**Other paths keep the catch-all to `agentprov-ns`.** Only the bare space and `/docs…` move. Every other path still
redirects to `nickjones39.github.io/agentprov-ns/<path>`, as it has since #6836. That keeps any link already made into
the vocabulary site working: its pages, assets and the explanation pages under `/exec`. It also keeps the change to
two added rules. A path that should reach the AgentPROV site later gets its own rule, the way `/docs` does here.

The table's "after" column was checked by running the proposed rules in order over these paths (Python `re`, which
agrees with Apache's PCRE on these patterns). `w3id.org/agentprov` without the slash is redirected to `/agentprov/` by
Apache before the rules run, then lands on the website.

## Files

- [`agentprov-website.patch`](agentprov-website.patch): the change, as `git diff` against `perma-id/w3id.org`
  `master` at `fed39864` (2026-10-29). Its `index` line names the upstream blob `5b9e917` of `ids/agentprov/.htaccess`
  and `823281f` of `ids/agentprov/README.md`; `git apply --check` passed on those blobs.
- [`proposed.htaccess`](proposed.htaccess) and [`proposed-README.md`](proposed-README.md): the two files as they would
  be after the patch.

## Before submitting (release day)

1. The website is live: `https://nickjones39.github.io/AgentPROV/` and `…/docs/` both answer 200.
2. Upstream has not changed our files since `fed39864`:
   `gh api repos/perma-id/w3id.org/contents/ids/agentprov/.htaccess --jq .sha` prints `5b9e91771922a0bed4a73cde1a288209043b672f`.
   If it does not, rebase the patch by hand and recheck the table.
3. The owner says yes in the orchestrator's window.

## Submitting (the owner, or a session with the owner's typed yes)

The fork `nickjones39/w3id.org` already exists (the head of PR 6836 was `nickjones39:agentprov`).

```bash
gh repo sync nickjones39/w3id.org --source perma-id/w3id.org --branch master
gh repo clone nickjones39/w3id.org w3id.org -- --depth 1 --branch master
cd w3id.org
git switch -c agentprov-website
git apply --check ../agentprov-website.patch && git apply ../agentprov-website.patch
git commit -am "agentprov: redirect the bare space and /docs to the project website"
git push -u origin agentprov-website
gh pr create --repo perma-id/w3id.org --base master --head nickjones39:agentprov-website \
  --title "agentprov: redirect the bare space and /docs to the project website" --body-file ../pr-body.md
```

(`pr-body.md` is the body below, saved to a file.)

## Pull request title

agentprov: redirect the bare space and /docs to the project website

## Pull request body

This updates the existing `agentprov` space (added in #6836) so that its root and `/docs` lead to the project's
website, which is now live on GitHub Pages:

- `https://w3id.org/agentprov/` → `https://nickjones39.github.io/AgentPROV/` (302)
- `https://w3id.org/agentprov/docs/…` → `https://nickjones39.github.io/AgentPROV/docs/…` (302, path preserved)

The two rules are added just before the existing catch-all. No existing rule changes: the vocabulary namespace
(`/ns`, `/ns/<x.y.z>`, content-negotiated 303s) and the execution IRIs (`/exec/…`) behave exactly as before. Every
other path keeps the existing catch-all to `nickjones39.github.io/agentprov-ns/`, so links already made into the
vocabulary site keep working. The README of the space lists the new targets.

Maintainer of the space: @nickjones39 (unchanged).
