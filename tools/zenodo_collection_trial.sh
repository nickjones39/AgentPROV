#!/usr/bin/env bash
# Sandbox trial of a collection with an index-only umbrella (D-870, D-947, D-949): part drafts, the index umbrella built
# from their receipts, communities, reserved DOIs, the cross-link membership check and the cross-links.
#
# For the user to run in their own terminal, on the SANDBOX only. It never publishes: tools/zenodo_draft.py has no
# publish request, and each step asks you to type its confirmation phrase yourself. It never prints or reads the token
# beyond checking that ZENODO_SANDBOX_TOKEN is set.
#
# Before running:
#   - build one or more small part deposits (agentprov package --deposit) from synthetic sealed corpora, one licence
#     class each (user guide chapter 5, "Sandbox trial checklist"); include a GPL or AGPL corpus to see its datasheet
#     linked rather than copied (D-949);
#   - write a release.toml for the index (title, creators, keywords, description_preamble);
#   - create (or pick) a community on sandbox.zenodo.org and note its identifier (the slug in its address);
#   - read -rs ZENODO_SANDBOX_TOKEN && export ZENODO_SANDBOX_TOKEN
#
# Usage:
#   tools/zenodo_collection_trial.sh COMMUNITY RELEASE_TOML INDEX_DIR PART_DIR=ROOTS [PART_DIR=ROOTS ...] \
#       --corpora CORPUS_DIR [CORPUS_DIR ...]
# ROOTS is the comma-separated root digests (sha256:HEX) of the part's corpora, as noted when you sealed them (taken from
# outside the deposit, like --root-digest). INDEX_DIR must not exist yet. CORPUS_DIR are the sealed corpora the parts hold.
set -euo pipefail

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -ge 6 ]] || usage
if [[ -z "${ZENODO_SANDBOX_TOKEN:-}" ]]; then
    echo "ZENODO_SANDBOX_TOKEN is not set (read -rs ZENODO_SANDBOX_TOKEN && export ZENODO_SANDBOX_TOKEN)" >&2
    exit 2
fi
repo="$(cd "$(dirname "$0")/.." && pwd)"
community="$1" release_toml="$2" index_dir="$3"
shift 3
[[ -f "$release_toml" ]] || { echo "no such release.toml: $release_toml" >&2; exit 2; }
[[ ! -e "$index_dir" ]] || { echo "the index directory exists already: $index_dir" >&2; exit 2; }
parts=() roots=() corpora=()
while [[ $# -gt 0 && "$1" != "--corpora" ]]; do
    dir="${1%%=*}" root="${1#*=}"
    if [[ "$dir" == "$1" || ! -d "$dir" ]]; then
        echo "not PART_DIR=ROOTS with an existing directory: $1" >&2
        exit 2
    fi
    parts+=("$(cd "$dir" && pwd)")
    roots+=("$root")
    shift
done
[[ $# -ge 2 && "$1" == "--corpora" ]] || usage
shift
for dir in "$@"; do
    [[ -d "$dir" ]] || { echo "no such corpus directory: $dir" >&2; exit 2; }
    corpora+=("$(cd "$dir" && pwd)")
done
[[ ${#parts[@]} -ge 1 ]] || usage
receipt() { echo "$(dirname "$1")/$(basename "$1").zenodo-sandbox-draft-receipt.json"; }
draft() { (cd "$repo" && uv run python tools/zenodo_draft.py "$@"); }
set_roots() { ra=(); local IFS=,; for r in $1; do ra+=(--root-digest "$r"); done; }  # bash 3.2: no mapfile

echo "== 1. Offline checks of the part deposits (no token used, nothing sent)"
for i in "${!parts[@]}"; do
    set_roots "${roots[$i]}"
    draft "${parts[$i]}" --target sandbox --check --community "$community" "${ra[@]}"
done
read -r -p "Check the screens above (the 'Communities' line names ${community}). Enter to create the part drafts, Ctrl-C to stop: "

echo "== 2. Create one unpublished draft per part (type each phrase yourself)"
for i in "${!parts[@]}"; do
    if [[ -e "$(receipt "${parts[$i]}")" ]]; then
        echo "a receipt exists for ${parts[$i]}: skipping its create (use --resume by hand if it is not complete)"
        continue
    fi
    set_roots "${roots[$i]}"
    draft "${parts[$i]}" --target sandbox --create-draft --community "$community" "${ra[@]}"
done

echo "== 3. Build the index-only umbrella from the part receipts (offline)"
index_args=(package --index "$(cd "$(dirname "$index_dir")" && pwd)/$(basename "$index_dir")" --metadata "$release_toml"
            --release-date "$(date +%F)")
for dir in "${parts[@]}"; do index_args+=(--part "$(receipt "$dir")"); done
for dir in "${corpora[@]}"; do index_args+=(--corpus "$dir"); done
(cd "$repo" && uv run agentprov "${index_args[@]}")
index_dir="$(cd "$index_dir" && pwd)"
echo "files of the index (no archives; copyleft corpora's datasheets are not copied):"
ls -1 "$index_dir"

echo "== 4. Offline check of the index, then its draft (type the phrase yourself)"
draft "$index_dir" --target sandbox --check --community "$community"
draft "$index_dir" --target sandbox --create-draft --community "$community"

link=(--target sandbox --cross-link --umbrella "$(receipt "$index_dir")")
for dir in "${parts[@]}"; do link+=(--member "$(receipt "$dir")"); done

if [[ ${#parts[@]} -ge 2 ]]; then
    echo "== 5. The membership check: cross-linking without the first part is refused before the phrase is asked"
    echo "   (exit 4, 'the members are not the part records the umbrella's index lists'; nothing to type)"
    short=(--target sandbox --cross-link --umbrella "$(receipt "$index_dir")")
    for dir in "${parts[@]:1}"; do short+=(--member "$(receipt "$dir")"); done
    set +e
    draft "${short[@]}"
    rc=$?
    set -e
    if [[ $rc -ne 4 ]]; then
        echo "UNEXPECTED: the short cross-link ended with exit $rc, not 4; stop here and report it" >&2
        exit 1
    fi
    echo "refused as expected (exit 4)"
fi

echo "== 6. Cross-link the index and every part (type the phrase yourself)"
draft "${link[@]}"

echo "== 7. Run the cross-link again: it must change nothing and end with exit 0"
draft "${link[@]}"

echo "== 8. The reserved DOIs the receipts record (compare each with its draft's page)"
for dir in "$index_dir" "${parts[@]}"; do
    uv run --project "$repo" python -I - "$(receipt "$dir")" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
links = (d.get("cross_links") or {}).get("status")
print(f"{d['draft_dir']}: draft {d['deposition_id']}  {d['reserved_doi']}  status {d['status']}  cross-links {links}  {d['html_url']}")
PY
done

cat <<EOF

== 9. Check on sandbox.zenodo.org (and do NOT press Publish). Copy back any HTTP error text the tool printed.
  [ ] Community: each draft names "${community}" (as selected, or as a pending inclusion request).
  [ ] Reserved DOI: each draft's page shows a reserved (not registered) DOI equal to the receipt's above.
  [ ] The index draft holds README.md, COLLECTION-INDEX.json, deposit-metadata.json, DEPOSIT-MANIFEST.json and one
      DATASHEET-<id>.md per non-copyleft corpus, no archive; its licence is CC BY 4.0.
  [ ] Unchanged DOI: the DOIs are the same after the two cross-link runs (the tool stops if not; note it if it did).
  [ ] Links on the index: "has part" to each part's reserved DOI.
  [ ] Links on each part: "is part of" the index's reserved DOI.
  [ ] The second cross-link run added no duplicate links.
  [ ] Limits: the file count and total size of the largest part were accepted (L-8: confirm the 100-file and 50 GB
      limits with your largest synthetic part).
  [ ] Nothing is published; each draft is still a draft.
Then delete the drafts in the web UI (the tool never deletes), remove the receipts and the index directory yourself,
and unset ZENODO_SANDBOX_TOKEN (or close the terminal). Report the ticks to the session that wrote this script.
EOF
