"""Seed the bare fetch cache with a profile's git pin from a local clone, offline (MN N.1.11; G.7.5; HL H.2.3).

    uv run python tools/seed_git_cache.py --profile agentdojo-upstream --pin head --clone PATH [--cache DIR] [--phase TEXT]

The pinned commit is fetched with ``git fetch --depth 1`` into ``<cache>/git/<host>/<owner>/<repo>.git`` through
:class:`agentprov.raw.fetch.Fetcher`, exactly as ``agentprov fetch`` would, except that the remote is the local clone
(git's file protocol; the Fetcher's ``remote_urls``/``file_protocol`` seam). No network is used. The content is
authenticated by the 40-hex commit id (the SHA-1 chain from the commit to every blob) and by ``transfer.fsckObjects``;
a clone that does not hold the pinned commit fails. The acquisition is logged in ``<cache>/acquisitions.jsonl`` with the
consent text below, as the phase-6 survey row was. Prints the commit, tree, file count and bytes only.

Every git call runs with ``GIT_NO_LAZY_FETCH=1`` (the Fetcher's environment): a partial (``blob:none``) clone is never
allowed to fetch a blob it lacks from its promisor remote, which for a real clone is the upstream host (network use
without consent; routing R2). A clone that lacks a blob of the pinned tree therefore fails with a typed code
(``raw.fetch.git`` from the fetch, or ``raw.fetch.blob_absent`` from a store that lacks a blob), exit 1 or the code's exit
status, and nothing is logged; seed from a complete clone instead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CONSENT = ("{phase} import evidence: seeded offline from the local shallow clone at the pinned commit (file protocol); "
           "content authenticated by the 40-hex commit id and fsck")


def _is_partial_clone(clone: Path) -> bool:
    """Whether the clone's config names a promisor remote (read as text, bounded; git is not run on the clone here)."""
    for config in (clone / ".git" / "config", clone / "config"):
        try:
            with config.open("rb") as stream:
                text = stream.read(1 << 20).lower()
        except OSError:
            continue
        if b"partialclone" in text or b"promisor" in text:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    from agentprov.adapters.profiles import load_profile
    from agentprov.errors import AgentProvError
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pin", required=True, help="pin role")
    parser.add_argument("--clone", required=True, type=Path, help="a local clone holding the pinned commit")
    parser.add_argument("--cache", default=None, help="fetch cache (default $AGENTPROV_UPSTREAM_CACHE, else $AGENTPROV_HOME/cache)")
    parser.add_argument("--phase", default="phase-10")
    args = parser.parse_args(argv)
    profile = load_profile(args.profile)
    source = profile.data["source"]
    pin = next((dict(p) for p in source.get("pins", ()) if p.get("role") == args.pin), None)
    if pin is None or pin.get("kind") != "git":
        print(f"profile {profile.id} has no git pin with role {args.pin!r}", file=sys.stderr)
        return 2
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    clone = args.clone.resolve()
    if not (clone / ".git").exists() and not (clone / "objects").is_dir():
        print("--clone is not a git repository", file=sys.stderr)
        return 2
    assert recipe.repo is not None
    fetcher = Fetcher(resolve_cache_dir(args.cache), allow_network=True, consent=CONSENT.format(phase=args.phase),
                      remote_urls={recipe.repo: clone.as_uri()}, file_protocol=True)
    try:
        result = fetcher.fetch(recipe)
    except AgentProvError as exc:
        hint = " (the clone is a partial clone: seed from a complete one)" if _is_partial_clone(clone) else ""
        print(f"{exc.code}: {exc}{hint}", file=sys.stderr)
        return exc.exit_code or 1
    print(f"commit {recipe.commit} tree {result.tree} files {result.files} bytes {result.bytes} "
          f"{'seeded' if result.network_used else 'already cached'}; problems: {list(result.problems) or 'none'}")
    return 0 if not result.problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
