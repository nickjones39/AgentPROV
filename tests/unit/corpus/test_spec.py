"""The corpus spec (``agentprov.corpus.spec``; HL H.1.6) and the committed specs of the v0.1 corpora (D-35, D-44).

* the parser is closed and strict (unknown keys, local and mutable origins, malformed ids, ``subtree``/``subtrees``);
* every committed ``corpora/<id>/`` holds exactly the three M.3.1 files, the spec loads, its id is its directory name,
  its licence decision is ``inherit`` (D-44), its profile and origin agree with the in-package profile pins, and its
  card passes the card lint;
* the two AgentDojo working trees become two corpora (D-35);
* ``.gitignore`` carries the M.3.1 negations.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry.claims import lint_card
from agentprov.corpus.spec import CorpusSpecError, check_origin, load_spec, parse_spec, selection_of

REPO = Path(__file__).resolve().parents[3]
CORPORA = REPO / "corpora"
V01 = ("adprov-v1-release", "agentdojo-upstream-2024-06", "agentdojo-upstream-head", "rope", "agentdyn-a",
       "mandate-agentdojo-eval", "ast-survey-agentdojo", "ast-survey-agentharm")  # fmt: skip
#: The wave-2 corpora (drafts of the wave-2 pre-release checks, 2026-10-29): one per valid tree of the wave-2 build.
W2 = ("agentdyn-b", "agentdyn-c", "agentops-bench", "aiauthz-agentdojo", "atia-benchmark", "authority-caps-agentdojo",
      "autogen-guard-placement", "bookkeeper-agentdojo", "ceferisbarov-agentdojo", "code-agent-misalignment",
      "controlarena-persistent", "craibench-agentdojo", "credleak-p15b", "dca-agentdojo", "drift-head", "drift1-agentdojo",
      "fragfuse-agentharm", "gate-agentdojo", "geryon-agentdojo", "glitch-agentdojo", "hilarytorn-trajectory-poisoning",
      "interbolt-agentdojo", "ipi-defenses-agentdojo", "kavach-agentdojo", "kexin-xu-01-agentharm", "kongminos-agentdojo",
      "linyxus-agentdojo", "llm-lock-agentdojo", "mcphunt", "melon-agentdojo", "memo-ozdincer-agentdojo", "menelaus29-ipi-multidomain",
      "mohameduk-agentdojo", "openagentsafety", "redcode-exec-openhands", "redcode-exec-qwencode", "seagent-agentdojo", "sentry-agentdojo",
      "shreeyavarma-llm-safety", "tacit-agentdojo", "what-surrounds", "whistlebench", "yockcheng-prompt-injection-harness")  # fmt: skip
#: DTap, the later wave-2 batch (tree dtap-bench-w2c; draft of 2026-10-29).
W2_DTAP = ("dtap-bench",)
COMMITTED = V01 + W2 + W2_DTAP
MINIMAL = b'''corpus_id = "x"
corpus_version = "0.1.0"
title = "t"
mode = "import"
[[sources]]
source_id = "agentdojo"
profile = "agentdojo-upstream@1"
parts = ["head"]
[[sources.snapshots]]
snapshot_id = "head"
origin = { kind = "git", repo = "https://github.com/a/b", commit = "089ed468cf3ed0322acc66b0211f26d9d90dbf60", subtree = "runs" }
raw_policy = "include"
[derive]
sem_profiles = []
prov_specs = ["agentprov-prov/0.1"]
views = []
options = { context_encoding = "members" }
[licence]
derived = "inherit"
decided_by = "test"
files = []
[layout]
shard_depth = 1
'''


def test_a_minimal_spec_parses():
    spec = parse_spec(MINIMAL)
    assert spec.corpus_id == "x" and spec.source.profile == "agentdojo-upstream@1"
    assert spec.source.snapshots[0].include is None  # the profile's [import] applies


@pytest.mark.parametrize(
    "change",
    [
        (b'mode = "import"', b'mode = "import"\nextra = 1'),
        (b'corpus_id = "x"', b'corpus_id = "X_bad"'),
        (b'corpus_version = "0.1.0"', b'corpus_version = "1"'),
        (b'commit = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"', b'commit = "main"'),
        (b'{ kind = "git", repo = "https://github.com/a/b", commit = "089ed468cf3ed0322acc66b0211f26d9d90dbf60", subtree = "runs" }',
         b'{ kind = "local", path = "/x" }'),
        (b'subtree = "runs"', b'subtrees = ["runs"]'),
        (b'subtree = "runs"', b'subtree = "runs/"'),
        (b'raw_policy = "include"', b'raw_policy = "maybe"'),
        (b'views = []', b'views = ["stats"]'),
        (b'options = { context_encoding = "members" }', b'options = { context_encoding = "collection" }'),
        (b'shard_depth = 1', b'shard_depth = 3'),
        (b'profile = "agentdojo-upstream@1"', b'profile = "agentdojo-upstream"'),
        (b'\nfiles = []', b'\nfiles = ["NOTICE.md"]'),  # anchored: "sem_profiles = []" also ends in "files = []"
    ],
)
def test_the_parser_is_closed_and_strict(change):
    with pytest.raises(CorpusSpecError):
        parse_spec(MINIMAL.replace(*change))


@pytest.mark.parametrize("names", [b'["notice.md"]', b'["Notice.MD"]', b'["LICENSE", "license"]', b'["COPYING", "copying"]'])
def test_licence_files_that_collide_case_insensitively_are_refused(names):
    # A case-insensitive volume (default APFS) would write one over the other, or over the generated NOTICE.md (G.3.6).
    with pytest.raises(CorpusSpecError) as info:
        parse_spec(MINIMAL.replace(b"\nfiles = []", b"\nfiles = " + names))
    assert info.value.code == "corpus.spec.invalid"


def test_distinct_licence_files_are_accepted():
    spec = parse_spec(MINIMAL.replace(b"\nfiles = []", b'\nfiles = ["LICENSE", "NOTICE", "COPYING.md"]'))
    assert spec.licence_files == ("LICENSE", "NOTICE", "COPYING.md")


def test_subtrees_is_an_array_of_several_trees_d33():
    origin = {"kind": "git", "repo": "https://github.com/a/b", "commit": "0" * 40, "subtrees": ["a", "b"]}
    assert check_origin(origin)["subtrees"] == ["a", "b"]
    with pytest.raises(CorpusSpecError):
        check_origin({**origin, "subtree": ""})


def test_selection_defaults_to_the_profile_import():
    spec = parse_spec(MINIMAL)
    selection = selection_of(spec.source.snapshots[0], {"include": ["runs/**/*.json"], "exclude": [{"glob": "**/x"}]})
    assert selection == {"include": ["runs/**/*.json"], "exclude": [{"code": "select.not_execution_artefact", "glob": "**/x",
                                                                      "owner": None}]}


# ------------------------------------------------------------------------------------------------ committed specs (D-44)
def test_the_v01_corpora_are_committed():
    assert sorted(p.name for p in CORPORA.iterdir() if p.is_dir() and p.name != "personas") == sorted(COMMITTED)


def test_committed_persona_files_are_digest_only_valid_and_referenced_by_digest():
    """D-810: ``corpora/personas/`` holds persona files (digests, never addresses); each spec's ``[scan]`` reference carries
    the sha256 of the file it names, and every file is referenced by at least one spec."""
    import hashlib

    from agentprov.corpus.personas import parse_persona_file

    directory = CORPORA / "personas"
    files = sorted(directory.iterdir()) if directory.is_dir() else []
    referenced: set[str] = set()
    for corpus_id in COMMITTED:
        spec = load_spec(CORPORA / corpus_id / "corpus-spec.toml")
        for relative, digest in spec.persona_files:
            path = (CORPORA / corpus_id / relative).resolve()
            assert path.parent == directory.resolve() and path.is_file(), (corpus_id, relative)
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == digest, (corpus_id, relative)
            observed = [g for g in parse_persona_file(path.read_bytes()).groups if "corpus_id" in g]
            assert all(g["corpus_id"] == corpus_id for g in observed), (corpus_id, relative)  # owning corpus only
            referenced.add(path.name)
    for path in files:
        assert path.name.endswith(".personas.toml") and path.name in referenced, path.name
        text = path.read_text("utf-8")
        parse_persona_file(path.read_bytes())
        assert "@" not in text.replace("sha256:", "")  # no address: digests and pinned paths only


@pytest.mark.parametrize("corpus_id", COMMITTED)
def test_each_committed_spec(corpus_id):
    directory = CORPORA / corpus_id
    assert sorted(p.name for p in directory.iterdir()) == ["CARD.md", "CHANGES.toml", "corpus-spec.toml"]
    spec = load_spec(directory / "corpus-spec.toml")
    assert spec.corpus_id == corpus_id and spec.corpus_version == "0.1.0" and spec.mode == "import"
    assert spec.licence_derived == "inherit" and "D-44" in spec.licence_decided_by  # user ruling 2026-10-11
    # the version the sealed corpus records, current or archived (D-31; agentdyn-a records v3, current v4 since D-933)
    profile = load_profile(spec.source.profile_id, spec.source.profile_version)
    assert profile.version == spec.source.profile_version and profile.data["profile"]["source_id"] == spec.source.source_id
    assert set(spec.source.parts) <= set(profile.parts)
    primary = [p for p in profile.data["source"]["pins"] if p.get("primary")]
    for snapshot in spec.source.snapshots:
        # a snapshot's pin is its part's primary pin, or the primary pin of its role (several snapshots of one part:
        # redcode-exec-openhands); a part read at another part's pin (agentdyn c at a's, dca drift at v1's) has none of
        # its own, and then the profile has exactly one primary pin
        pins = ([p for p in primary if p.get("part") == snapshot.snapshot_id]
                or [p for p in primary if p.get("role") == snapshot.snapshot_id] or primary)
        assert len(pins) == 1, snapshot.snapshot_id
        pin, origin = pins[0], snapshot.origin
        if origin["kind"] == "git":
            assert origin["commit"] == pin["commit"]
            assert origin["subtree"] == str(pin.get("tree") or "").strip("/")
            assert origin.get("subtree_sha1") == pin.get("tree_sha1")
            assert origin["repo"] == pin.get("repo", profile.data["source"]["canonical_repo"])
        elif origin["kind"] == "zenodo":
            assert (origin["doi"], origin["file"]) == (pin["doi"], pin["file"])
        elif origin["kind"] == "hf":
            assert (origin["dataset"], origin["revision"]) == (pin["dataset"], pin["revision"])
        elif origin["kind"] == "url":
            assert origin["url"] == pin["url"]
        else:  # the AgentDojo-PROV release: a corpus origin at the producer commit of the pin (R-26)
            assert origin["kind"] == "corpus" and origin["producer_commit"] == pin["commit"]
    assert lint_card((directory / "CARD.md").read_text("utf-8")) == []
    changes = tomllib.loads((directory / "CHANGES.toml").read_text("utf-8"))
    assert [c["version"] for c in changes["change"]] == ["0.1.0"]


def test_restricted_use_class_of_ast_survey_agentharm_d44():
    harm = load_profile(load_spec(CORPORA / "ast-survey-agentharm" / "corpus-spec.toml").source.profile_id)
    runs = load_profile(load_spec(CORPORA / "ast-survey-agentdojo" / "corpus-spec.toml").source.profile_id)
    assert harm.data["licence"]["restrictions"] and not runs.data["licence"].get("restrictions")
    assert harm.data["licence"]["spdx"] == runs.data["licence"]["spdx"]  # same SPDX, different class (restrictions)


def test_two_agentdojo_corpora_from_one_profile_d35():
    a = load_spec(CORPORA / "agentdojo-upstream-2024-06" / "corpus-spec.toml")
    b = load_spec(CORPORA / "agentdojo-upstream-head" / "corpus-spec.toml")
    assert a.source.profile == b.source.profile == "agentdojo-upstream@2"
    assert a.corpus_id != b.corpus_id and a.source.parts != b.source.parts


def test_gitignore_admits_only_the_three_spec_files():
    git = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", "corpora/rope/notes.txt"], check=False)
    assert git.returncode == 0
    for name in ("corpus-spec.toml", "CARD.md", "CHANGES.toml"):
        kept = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", f"corpora/rope/{name}"], check=False)
        assert kept.returncode == 1, name
    top = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", "corpora/datasheet-statements.toml"],
                         check=False)
    assert top.returncode == 1
