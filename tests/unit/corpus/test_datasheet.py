"""``DATASHEET.md`` (``agentprov.corpus.datasheet``; HL H.9; G.8.5; HL-T8) and the decided statements.

One test per row of ``docs/reports/analysis/datasheet-items.md``: each statement is rendered for exactly the corpora its
row names, with its decided wording and its figures shown with their source. The renderer's guards: the card mode must
be the corpus mode, a card with a literal number is refused, a claim that does not hold fails, every
``licences.raw[].basis`` and restriction appears verbatim, and the G.8.5 "Untrusted content" section is present. The
statement mechanism is data-driven: a new row for a new corpus is a table change only.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import seal_support as ss

from agentprov.adapters.registry import claims
from agentprov.adapters.registry.claims import CHECKER, lint_datasheet
from agentprov.corpus.datasheet import ATTRIBUTION_PREFIX, DatasheetError, StatementTable, load_statements, render
from agentprov.corpus.package import seal

TABLE_BYTES = (ss.REPO / "corpora" / "datasheet-statements.toml").read_bytes()
TABLE = load_statements(TABLE_BYTES)
ALL = ("adprov-v1-release", "agentdojo-upstream-2024-06", "agentdojo-upstream-head", "rope", "agentdyn-a",
       "mandate-agentdojo-eval", "ast-survey-agentdojo", "ast-survey-agentharm", "dtap-bench")  # fmt: skip
CARD = "---\nmode: import\n---\n\n## Motivation\n\nA test card.\n"
_MANIFEST: dict[str, Any] = {}


@pytest.fixture(scope="module")
def manifest(tmp_path_factory) -> dict[str, Any]:
    if not _MANIFEST:
        root = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("ds") / "mini")
        seal(root, corpus_version="0.1.0", inputs=ss.inputs())
        _MANIFEST.update(json.loads((root / "corpus.json").read_text()))
    return copy.deepcopy(_MANIFEST)


def _render(manifest: dict[str, Any], corpus_id: str, *, card: str = CARD, table: StatementTable = TABLE, **kw: Any) -> str:
    manifest = {**manifest, "corpus_id": corpus_id}
    return render(manifest, card, {}, {}, checker=CHECKER, statements=table, **kw).text


def _emitted(manifest: dict[str, Any], corpus_id: str) -> list[str]:
    return render({**manifest, "corpus_id": corpus_id}, CARD, {}, {}, checker=CHECKER, statements=TABLE).statements


def _only(manifest: dict[str, Any], statement_id: str, corpora: set[str]) -> None:
    for corpus_id in ALL:
        assert (statement_id in _emitted(manifest, corpus_id)) == (corpus_id in corpora), (statement_id, corpus_id)


# ------------------------------------------------------------------------------------------------ one test per row
def test_row1_core_only_consumers_for_the_inferred_identity_profiles(manifest):
    _only(manifest, "core-only-consumers", {"rope", "agentdyn-a", "ast-survey-agentdojo"})
    assert "must load the core and the inference bundles" in _render(manifest, "rope")


def test_row2_agentdyn_gemini_undefended_baseline(manifest):
    _only(manifest, "agentdyn-gemini-undefended-baseline", {"agentdyn-a"})
    text = _render(manifest, "agentdyn-a")
    assert "425 [phase10-examination-2.md §8.1] of 648 [phase10-examination-2.md §8.1] cells" in text
    assert "52-minute [phase10-examination-2.md §8.2] window" in text
    assert "detector-arm comparisons are paired, and the undefended baseline is flagged" in text


def test_row3_content_addressed_execution_ids(manifest):
    _only(manifest, "content-addressed-execution-ids", {"agentdojo-upstream-2024-06", "agentdojo-upstream-head"})
    assert "14,182 [phase10-examination-2.md §7.3" in _render(manifest, "agentdojo-upstream-head")


def test_row4_implied_prov_inferences_for_every_corpus(manifest):
    _only(manifest, "implied-prov-inferences", set(ALL))
    assert "implied by the PROV inference rules" in _render(manifest, "mandate-agentdojo-eval")


#: Row 5: the source-artefact disclosures and the corpora each names (first analysis §8.1, examination 2 §10.1).
ROW5 = {
    "art-benign-security-constant": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                                     "ast-survey-agentdojo", "mandate-agentdojo-eval", "adprov-v1-release"},
    "art-run-error-imposed": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "agentdyn-a", "ast-survey-agentdojo"},
    "art-silent-rerun": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a", "adprov-v1-release"},
    "art-iteration-cap-cut": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                              "ast-survey-agentdojo", "adprov-v1-release"},
    "art-outcome-only-logs": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope"},
    "art-payload-never-reached": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                                  "ast-survey-agentdojo", "mandate-agentdojo-eval", "adprov-v1-release"},
    "art-identical-trajectories": {"agentdojo-upstream-head", "rope", "agentdyn-a", "ast-survey-agentdojo"},
    "art-success-without-exposure": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a"},
    "art-vacuous-utility": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                            "ast-survey-agentdojo", "adprov-v1-release"},
    "art-defences-in-benign-runs": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                                    "mandate-agentdojo-eval"},
    "art-text-tool-calls": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a",
                            "ast-survey-agentdojo", "ast-survey-agentharm", "adprov-v1-release"},
    "art-autodojo-yaml-escaped": {"rope"},
    "art-empty-assistant-text": {"agentdojo-upstream-head", "agentdyn-a", "ast-survey-agentdojo"},
    "art-provider-call-ids": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "rope", "agentdyn-a"},
    "art-package-version-not-code": {"agentdojo-upstream-head", "rope", "agentdyn-a"},
    "art-rope-tag-names-another-model": {"rope"},
    "art-rope-effect-corrections": {"rope"},
    "art-camel-feedback-as-user": {"agentdyn-a"},
    "art-drift-post-isolation": {"agentdyn-a"},
    "art-agentdyn-generations": {"agentdyn-a"},
    "art-rope-long-horizon-version": {"rope"},
    "art-survey-security-gloss": {"ast-survey-agentdojo"},
    "art-mandate-allows-inferred": {"mandate-agentdojo-eval"},
    "art-n2-escaped-newlines": {"agentdojo-upstream-head", "agentdojo-upstream-2024-06", "adprov-v1-release", "agentdyn-a",
                                "ast-survey-agentdojo", "rope"},
    "art-n4-empty-final-replies": {"agentdyn-a", "agentdojo-upstream-head", "ast-survey-agentdojo",
                                   "agentdojo-upstream-2024-06", "rope"},
    "art-n5-dropped-high-bytes": {"agentdyn-a", "adprov-v1-release"},
    "art-n6-completeness-model-confounded": {"adprov-v1-release"},
    "art-n7-activity-times": set(ALL),
    "art-n8-argument-types": {"adprov-v1-release", "agentdyn-a", "rope"},
}


@pytest.mark.parametrize("statement_id", sorted(ROW5))
def test_row5_source_artefact_disclosures(manifest, statement_id):
    _only(manifest, statement_id, ROW5[statement_id])


def test_row5_covers_n2_and_n4_to_n8():
    ids = {s.id for s in TABLE.statements}
    assert {"art-n2-escaped-newlines", "art-n4-empty-final-replies", "art-n5-dropped-high-bytes",
            "art-n6-completeness-model-confounded", "art-n7-activity-times", "art-n8-argument-types"} <= ids
    assert {s.id for s in TABLE.statements if s.id.startswith("art-")} == set(ROW5)


def test_row17_code_agent_misalignment_harness_account_path_d609(manifest):
    _only(manifest, "cam-harness-account-path-withheld", {"code-agent-misalignment"})
    assert "cam-harness-account-path-withheld" in _emitted(manifest, "code-agent-misalignment")
    text = _render(manifest, "code-agent-misalignment")
    assert "272 [code-agent-misalignment.md PC-01; DECISIONS D-609] `final_diff.patch` context files" in text
    assert "(1 [DECISIONS D-609] file)" in text and "reason `personal_data`" in text
    assert "so no execution is withheld" in text


DTAP = ("dtap-injection-path-unobservable", "dtap-one-judge-several-attempts", "dtap-rejudged-results",
        "dtap-harness-failures-judged", "dtap-constant-task-success", "dtap-configuration-link-tiers", "dtap-datasheet-counts",
        "dtap-host-accounts-redacted")  # D-607


@pytest.mark.parametrize("statement_id", DTAP)
def test_rows6_to_11_dtap_bench_only(manifest, statement_id):
    _only(manifest, statement_id, {"dtap-bench"})


def test_dtap_figures_carry_their_source(manifest):
    text = _render(manifest, "dtap-bench")
    assert "57.3 % [dtap-bench.md §6]" in text and "3,533 [dtap-bench.md §6]" in text


# ------------------------------------------------------------------------------------------------ data-driven statements
def test_a_new_row_for_a_new_corpus_is_data_only(manifest):
    extra = TABLE_BYTES + b'''
[[statement]]
id = "new-corpus-row"
item = "a new row"
corpora = ["brand-new-corpus"]
section = "known_issues"
decided = "test"
source = "test"
text = "A new disclosure with {{f:n}} items."

[statement.figures]
n = { value = "12", source = "test report" }
'''
    table = load_statements(extra)
    assert "A new disclosure with 12 [test report] items." in _render(manifest, "brand-new-corpus", table=table)
    assert "new-corpus-row" not in render({**manifest, "corpus_id": "rope"}, CARD, {}, {}, checker=CHECKER,
                                          statements=table).statements


@pytest.mark.parametrize(
    "bad",
    [
        b'[table]\nversion = 1\n[[statement]]\nid = "x"\nitem = "i"\ncorpora = ["a"]\nsection = "nowhere"\ndecided = "d"\nsource = "s"\ntext = "t"\n',
        b'[table]\nversion = 1\n[[statement]]\nid = "x"\nitem = "i"\ncorpora = ["a"]\nsection = "uses"\ndecided = "d"\nsource = "s"\ntext = "{{f:n}}"\n',
        b'[table]\nversion = 2\n',
        b'[table]\nversion = 1\n[[statement]]\nid = "x"\nitem = "i"\ncorpora = []\nsection = "uses"\ndecided = "d"\nsource = "s"\ntext = "t"\n',
    ],
)
def test_the_statement_table_is_checked(bad):
    with pytest.raises(DatasheetError):
        load_statements(bad)


def test_a_statement_with_a_literal_number_is_refused(manifest):
    bad = load_statements(b'[table]\nversion = 1\n[[statement]]\nid = "x"\nitem = "i"\ncorpora = ["*"]\nsection = "uses"\n'
                          b'decided = "d"\nsource = "s"\ntext = "We saw 648 cells."\n')
    with pytest.raises(DatasheetError):
        _render(manifest, "rope", table=bad)


# ------------------------------------------------------------------------------------------------ guards (HL-T8)
def test_an_import_corpus_with_a_live_card_is_refused(manifest):
    with pytest.raises(DatasheetError) as info:
        _render(manifest, "rope", card=CARD.replace("mode: import", "mode: live"))
    assert info.value.exit_code == 4


def test_validate_card_rejects_a_literal_number(manifest):
    with pytest.raises(DatasheetError) as info:
        _render(manifest, "rope", card=CARD + "\nThe corpus has 396 runs.\n")
    assert info.value.code == "corpus.datasheet.card"


def test_a_failing_claim_fails_the_build(manifest):
    with pytest.raises(DatasheetError) as info:
        _render(manifest, "rope", card=CARD + "\n{{claim:restricted_use}}\n")
    assert info.value.exit_code == 1


def test_basis_and_restrictions_appear_verbatim(manifest):
    m = copy.deepcopy(manifest)
    m["licences"]["restrictions"] = ["AgentHarm task data: MIT License with an additional clause (use only to improve AI "
                                     "safety and security)"]
    text = _render(m, "ast-survey-agentharm")
    for raw in m["licences"]["raw"]:
        assert f'"{raw["basis"]}"' in text
    assert m["licences"]["restrictions"][0] in text


def test_required_attribution_is_quoted_verbatim_d910(manifest):
    """A source's required attribution is third-party credit, quoted on one line that starts with the fixed prefix, so a
    title holding a lint word (the survey artefact's "Reproducible") does not fail the datasheet; no HTML comment is
    written (K.12.6(e)); the claims lint holds the same prefix."""
    assert ATTRIBUTION_PREFIX == claims.ATTRIBUTION_PREFIX
    m = copy.deepcopy(manifest)
    m["licences"]["attribution"] = ["A, Reproduction Artifact for 'Benchmarks: A Reproducible Study' (CC-BY-4.0)",
                                    "B (MIT): the benchmark text"]
    text = _render(m, "ast-survey-agentdojo")
    line = next(x for x in text.splitlines() if x.startswith(ATTRIBUTION_PREFIX))
    assert line == (ATTRIBUTION_PREFIX + '"A, Reproduction Artifact for \'Benchmarks: A Reproducible Study\' (CC-BY-4.0)"; '
                    '"B (MIT): the benchmark text".')
    assert lint_datasheet(text) == [] and "<!--" not in text


def test_an_attribution_cannot_add_a_line_markup_or_a_second_exempt_line(manifest):
    """The attribution text is escaped to one inert line: a line break followed by the prefix, an HTML comment and a
    heading stay inside the one quoted entry, so they can neither open a second exempt line nor hide text."""
    m = copy.deepcopy(manifest)
    m["licences"]["attribution"] = ["X\n" + ATTRIBUTION_PREFIX + "lossless\n# heading <!-- hidden"]
    text = _render(m, "ast-survey-agentdojo")
    assert sum(1 for x in text.splitlines() if x.startswith(ATTRIBUTION_PREFIX)) == 1
    assert "<!--" not in text and "\n# heading" not in text
    assert lint_datasheet(text) == []


def test_the_datasheet_has_the_untrusted_content_section_g85(manifest):
    text = _render(manifest, "rope")
    assert "## Untrusted content" in text and lint_datasheet(text) == []
    assert lint_datasheet(text.replace("## Untrusted content", "## Something else"))


def test_values_and_claims_come_from_the_manifest(manifest):
    card = CARD + "\nThere are {{v:/counts/executions}} records. {{claim:raw_included}}\n"
    text = _render(manifest, "rope", card=card)
    assert f"There are {manifest['counts']['executions']} records." in text
    assert CHECKER.claim_text("raw_included") in text


def test_the_field_group_table_is_injected(manifest):
    text = _render(manifest, "rope", field_groups=lambda m: "| group | share |\n|---|---|\n| messages | 1 |")
    assert "| messages | 1 |" in text


# ------------------------------------------------------------------------------------------------ escaping (F-12C-03)
_BENIGN_MODELS = (
    ("gpt-4o-2024-05-13", ["gpt-4o-2024-05-13"], "openai"),
    ("openai/gpt-4o", ["gpt-4o-2024-08-06", "gpt-4o"], "openai"),
    ("claude-3-5-sonnet-20240620", [], None),
    ("anthropic/claude-3-opus@20240229", ["claude-3-opus-20240229"], "anthropic"),
    ("gemini-1.5-pro-002", ["models/gemini-1.5-pro-002"], "google"),
    ("meta-llama/Llama-3-70b-chat-hf", [], "together"),
)
_BENIGN_FRAMEWORKS = (
    ("agentdojo", "agentdojo", "0.1.35", "v1.2.1"),
    ("autodojo", "agentdojo", "0.1.35", "important_instructions-tool_knowledge"),
    ("inspect_ai", "inspect-ai", "0.3.58", "agentharm_benign"),
    ("x", None, None, None),
)
_VALUE_CARD = ("---\nmode: import\n---\n\n## Motivation\n\nA test card for {{v:/corpus_id}} ({{v:/title}}), version "
               "{{v:/corpus_version}}, mode {{v:/mode}}, model {{v:/models/0/requested}}.\n\n{{v:/models/1/requested}}\n\n"
               "{{v:/framework_identities/0/reported_version}}\n")


def _with_identities(manifest: dict[str, Any], models: Any, frameworks: Any) -> dict[str, Any]:
    m = copy.deepcopy(manifest)
    template = m["models"][0]
    m["models"] = [{**copy.deepcopy(template), "requested": r, "served": s, "provider": p} for r, s, p in models]
    m["framework_identities"] = [
        {"executions": 1, "system_prompt_sha256": None, "tool_definitions_sha256": "sha256:" + "1" * 64, "fw": f,
         "distribution": d, "reported_version": v, "suite_set": s} for f, d, v, s in frameworks]
    return m


def test_benign_values_render_byte_identical_to_the_pre_fix_datasheet(manifest):
    """The F-12C-03 escaping changes nothing for ordinary values. The expected lines are the renderer's output before the
    fix (commit 3c2503d) for the same manifest; when the fix was made the whole document was also compared byte for byte
    with the pre-fix output, over every corpus id and every in-repo card."""
    text = _render(_with_identities(manifest, _BENIGN_MODELS, _BENIGN_FRAMEWORKS), "rope", card=_VALUE_CARD)
    expected = [
        "Corpus `rope` version `0.1.0` (mode `import`). ",
        "A test card for rope (Three golden AgentDojo logs (test corpus)), version 0.1.0, mode import, model "
        "gpt-4o-2024-05-13.\n\nopenai/gpt-4o\n\n0.1.35\n",
        "| Requested model | Served model | Provider | Evidence (requested) | Executions |\n|---|---|---|---|---|\n"
        "| `gpt-4o-2024-05-13` | `gpt-4o-2024-05-13` | openai | I | 1 |\n"
        "| `openai/gpt-4o` | `gpt-4o-2024-08-06`, `gpt-4o` | openai | I | 1 |\n"
        "| `claude-3-5-sonnet-20240620` | not recorded | not recorded | I | 1 |\n"
        "| `anthropic/claude-3-opus@20240229` | `claude-3-opus-20240229` | anthropic | I | 1 |\n"
        "| `gemini-1.5-pro-002` | `models/gemini-1.5-pro-002` | google | I | 1 |\n"
        "| `meta-llama/Llama-3-70b-chat-hf` | not recorded | together | I | 1 |\n",
        "| `agentdojo` | agentdojo | 0.1.35 | v1.2.1 | recorded | not recorded | 1 |\n"
        "| `autodojo` | agentdojo | 0.1.35 | important_instructions-tool_knowledge | recorded | not recorded | 1 |\n"
        "| `inspect_ai` | inspect-ai | 0.3.58 | agentharm_benign | recorded | not recorded | 1 |\n"
        "| `x` | - | - | - | recorded | not recorded | 1 |\n",
        "| `2024-06` | https://github.com/ethz-spylab/agentdojo @ `c274885610efaaafec38b6d3eb07152ba7ff3f94` `runs` | include "
        "| 3 | 3 | 0 | none |\n",
    ]
    for part in expected:
        assert part in text


_HOSTILE = ("m`<img src=x onerror=alert(1)>`[c](javascript:alert(1))" + chr(0x1B) + "[2J" + chr(0x202E) + "|"
            + chr(13) + "# cr" + chr(0x2028) + chr(0x85) + chr(0x2029) + chr(9) + "\n## lf <!-- &#96; \\")


def test_every_data_derived_cell_and_value_is_escaped(manifest):
    """F-12C-03: requested, served, provider, every framework-identity column, and a ``{{v:...}}`` value at the start of
    a line are one escaped line each: no raw control or line terminator, no backtick, no ``<`` but a ``<U+XXXX>``
    marker, no ``[``/``]``, no ``|`` that splits a table cell, no heading."""
    import re
    import unicodedata

    m = _with_identities(manifest, [(_HOSTILE, [_HOSTILE], _HOSTILE)], [(_HOSTILE, _HOSTILE, _HOSTILE, _HOSTILE)])
    card = "---\nmode: import\n---\n\n## Motivation\n\nA test card.\n\n{{v:/models/0/provider}}\n"
    text = _render(m, "rope", card=card)
    assert not [ch for ch in text if ch != "\n" and unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp")]
    lines = [line for line in text.split("\n") if "m&#96;" in line]
    assert len(lines) == 3  # the placeholder line, the models row and the frameworks row
    for line in lines:
        assert "`" not in line and "[" not in line and "]" not in line and "<!--" not in line
        assert not re.search(r"<(?!U\+[0-9A-F]{4,6}>)", line)
        assert not line.startswith("#")
        assert "\\|" in line and "&amp;#96;" in line and "\\\\" in line
    placeholder, models_row, frameworks_row = lines
    assert len(re.findall(r"(?<!\\)\|", models_row)) == 6 and len(re.findall(r"(?<!\\)\|", frameworks_row)) == 8
    assert placeholder.startswith("m&#96;&lt;img src=x onerror=alert(1)>&#96;&#91;c&#93;(javascript:alert(1))<U+001B>")


def test_the_per_unit_inputs_of_a_snapshot_are_listed_d221(manifest):
    """Pre-round review #16: the datasheet names a snapshot's context trees, pinned objects and skipped roles (D-221),
    and a corpus without them renders as before."""
    plain = _render(manifest, "mini")
    assert "Per-unit inputs" not in plain
    snapshot = manifest["sources"][0]["snapshots"][0]
    snapshot["context"] = [{"role": "tasks", "stored": 3, "verification": {"kind": "blob", "verified": 3, "unverified": 0},
                            "origin": {"kind": "git", "repo": "https://github.com/o/tasks", "commit": "b" * 40, "subtree": ""}},
                           {"role": "supp", "stored": 2, "verification": {"kind": "download", "verified": 2, "unverified": 0},
                            "origin": {"kind": "zenodo", "doi": "10.5281/zenodo.9", "file": "supp.zip"},
                            "input": {"kind": "archive", "label": "supp.zip", "sha256": "sha256:" + "c" * 64, "bytes": 9}}]
    snapshot["pinned_objects"] = [{"label": "runs/x.json", "sha256": "sha256:" + "d" * 64, "bytes": 5,
                                   "origin": {"kind": "hf", "repo": "o/data", "revision": "e" * 40, "path": "runs/x.json"}}]
    snapshot["context_skipped"] = ["notes"]
    text = _render(manifest, "mini")
    assert "Per-unit inputs" in text
    for cell in ("context `tasks`", "context `supp`", "archive supp.zip", "Zenodo `10.5281/zenodo.9`", "download",
                 "pinned object runs/x.json", "context `notes`", "skipped at import"):
        assert cell in text, cell


_REVISION = "e" * 40


@pytest.mark.parametrize(("origin", "cell"), [
    # unchanged: the text git and corpus origins had before ultra seal-release #10, byte for byte
    ({"kind": "git", "repo": "https://github.com/o/r", "commit": "b" * 40, "subtree": "runs"},
     f"https://github.com/o/r @ `{'b' * 40}` `runs`"),
    ({"kind": "git", "repo": "https://github.com/o/r", "commit": "b" * 40, "subtrees": ["a", "b"], "subtree": ""},
     f"https://github.com/o/r @ `{'b' * 40}`"),
    ({"kind": "corpus", "corpus": "adprov-v1-release", "version": "0.1.0", "producer_commit": "a" * 40},
     f"adprov-v1-release 0.1.0 @ `{'a' * 40}`"),
    ({"kind": "capture", "session_ids": ["s1"]}, "capture"),
    # new: the pin itself, not only its kind word
    ({"kind": "zenodo", "doi": "10.5281/zenodo.123", "file": "runs.zip"}, "Zenodo `10.5281/zenodo.123` runs.zip"),
    ({"kind": "hf", "dataset": "owner/name", "gated": False, "revision": _REVISION, "path": "data/train.jsonl"},
     f"owner/name @ `{_REVISION}` data/train.jsonl"),
    ({"kind": "hf", "dataset": "owner/name", "gated": False, "revision": _REVISION, "path": "logs",
      "parts": [{"file": "logs/a.zip", "bytes": 1, "sha256": "sha256:" + "0" * 64}]},
     f"owner/name @ `{_REVISION}` logs"),
    ({"kind": "hf", "dataset": "owner/name", "gated": True, "revision": _REVISION}, f"owner/name @ `{_REVISION}`"),
    ({"kind": "url", "url": "https://example.org/runs.zip", "retrieved_at": "2026-01-01T00:00:00Z"},
     "https://example.org/runs.zip"),
])
def test_the_snapshot_table_names_the_pinned_origin(manifest, origin, cell):
    """Ultra seal-release #10: the snapshot table's "Pinned origin" cell renders a Zenodo, Hugging Face or URL pin in
    full (DOI and file, dataset @ revision and path, URL), as the per-unit table does, not as the bare kind word."""
    snapshot = manifest["sources"][0]["snapshots"][0]
    snapshot["origin"] = origin
    row = next(line for line in _render(manifest, "mini").split("\n") if line.startswith(f"| `{snapshot['snapshot_id']}` |"))
    assert row.split(" | ")[1] == cell


def test_the_snapshot_origin_cell_stays_escaped(manifest):
    """F-12C-03 still applies to the newly rendered origin values: a ``|`` cannot split the table cell."""
    snapshot = manifest["sources"][0]["snapshots"][0]
    snapshot["origin"] = {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a|b`[x](y)`.zip"}
    row = next(line for line in _render(manifest, "mini").split("\n") if line.startswith(f"| `{snapshot['snapshot_id']}` |"))
    assert "a\\|b" in row and "`[x]" not in row and "](y)" not in row
    assert len([i for i, ch in enumerate(row) if ch == "|" and row[i - 1] != "\\"]) == 8


def test_an_empty_table_says_what_there_is_none_of(manifest):
    """F-8 (user-guide findings): an empty table rendered as a bare "(none)" line (in the Composition section, after the
    models table, for a corpus without framework identities). Every empty table now names what it lists."""
    manifest["framework_identities"] = []
    manifest["models"] = []
    text = _render(manifest, "mini")
    composition = text.split("## Composition", 1)[1].split("\n## ", 1)[0]
    assert "Models: none recorded." in composition and "Framework identities: none recorded." in composition
    assert "(none)" not in text.split("\n")
    assert not lint_datasheet(text)


def test_every_shipped_statement_passes_the_card_lint():
    """Pre-round review PR-14: ``render`` lints each selected statement as a card (H.9(3)), so a literal number outside a
    placeholder failed only at ``package``. Every statement of the shipped table is linted here, by the same call."""
    from pathlib import Path

    from agentprov.corpus.datasheet import load_statements

    root = Path(__file__).resolve().parents[3]
    table = load_statements((root / "corpora" / "datasheet-statements.toml").read_bytes())
    failing = {s.id: CHECKER.lint_card("---\nmode: import\n---\n" + s.text)[:2]
               for s in (getattr(table, "statements", None) or list(table))
               if CHECKER.lint_card("---\nmode: import\n---\n" + s.text)}
    assert failing == {}
