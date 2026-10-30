"""The phase-10n ATIA profile (D-307–D-309, proposals; phase-10e card §3.5, D-144; docs/architecture D.9).

No real log is committed (D-309: the smallest pinned log is 11.5 MB of base64 media). The synthetic sample below has
the two shapes of ``inspect_ai 0.3.112`` that matter here: a tool event without ``message_id`` and media inputs as
``attachment://`` references. The pinned logs are mapped only when the fetch cache holds them (``slow``). Nothing here
prints log content (R-42).
"""

from __future__ import annotations

import json
import tomllib

import inspect_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator

COMMIT = "cc71caf55c6f35d7aad440a4a746f44ae39d17c4"
PROFILE_FILE = support.REPO / "src/agentprov/adapters/inspect/profiles/atia-benchmark.profile.toml"
#: The five pinned logs (git blob id, size), phase-10n census.
LOGS = {
    "logs/2025-07-17T01-47-02-04-00_account-takeover-suite_nffiXqUJ5vWY4Mw8wPNzxf.eval": ("8b5bca0549368b802cbd0abc49bc8b6bf12e6dc3", 43953245),
    "logs/2025-07-17T01-51-09-04-00_account-takeover-suite_9syKog9GdP5XjiLQvfq2K8.eval": ("a01b477f32ece8defc54b1f3405ea7d742b0f40a", 11729119),
    "logs/2025-07-17T01-52-51-04-00_account-takeover-suite_XCBkBJHpKcnhQg6qe2UnjH.eval": ("5513641018b70e00587c2743e62f5398849fcca6", 11475432),
    "logs/2025-07-17T01-54-19-04-00_account-takeover-suite_7EkZwrdNhAq9wAHr6EABpB.eval": ("7ab115ca32fe581075f67c42a6d6eb3aa368f17b", 43955377),
    "logs/2025-07-17T02-52-21-04-00_account-takeover-suite_4JHjSovoR8ySzitUi7H4Q9.eval": ("ed49f4ef115f9869248c52eb0866334aebc142eb", 51252339),
}
IMAGE = "data:image/png;base64,c3ludGhldGljLWltYWdl"
AUDIO = "data:audio/mpeg;base64,c3ludGhldGljLWF1ZGlv"


def _toml() -> dict:
    return tomllib.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def _validate(imported: support.Imported, unit: support.Unit) -> None:
    profile = load_profile("atia-benchmark")
    validator = AerValidator(store=imported.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def test_profile_pin_licence_and_import_table():
    profile = load_profile("atia-benchmark")
    data = _toml()
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["kind"] == "git" and pin["commit"] == COMMIT and pin["tree"] == "logs"
    assert (pin["expected_files"], pin["expected_bytes"]) == (len(LOGS), sum(size for _, size in LOGS.values()))
    assert data["licence"]["spdx"] == "MIT" and data["licence"]["policy"] == "include" and data["licence"]["attribution"]
    imp = data["import"]
    assert imp["dialect"] == imp["mapper"] == "inspect.eval" and imp["variants"] == ["v2"]
    assert imp["include"] == ["logs/*.eval"]
    family = data["family"]["inspect"]
    assert family["benchmark"] == "atia" and "no_attack" not in family
    assert family["producer_band"]["inspect_ai"] == ["0.3.112"] and family["log_versions"] == [2]
    assert profile.version == 1 and profile.parts == ("logs",)


def test_family_table_conforms_to_the_closed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((support.REPO / "src/agentprov/adapters/inspect/family.schema.json").read_bytes())
    jsonschema.validate(_toml()["family"]["inspect"], schema)


def test_quirk_rules_exist():
    for quirk in _toml()["family"]["inspect"].get("quirk", ()):
        for rule in quirk.get("rules", ()):
            entry = load_catalogue("inspect").get(rule)
            assert entry is not None and entry.citable, (quirk["id"], rule)


def test_registry_part_is_sealed_with_its_own_corpus_and_the_atia_semantics():
    registration = get_source("atia-benchmark")
    (part,) = registration.capabilities
    assert part.profile == "atia-benchmark" and part.corpus_id == "atia-benchmark" and part.part == "logs"
    assert part.import_status == "supported" and part.target_import_status == "supported"  # D-830, after the wave-2 seal
    assert part.caveat is not None and part.caveat.startswith(
        "full pinned snapshot imported through agentprov import in wave 2 and sealed as atia-benchmark 0.1.0 ("
    )
    assert [s.corpus_id for s in part.sealed] == ["atia-benchmark"]
    assert part.semantics == ("inspect.atia@1",)  # D-307 addendum (orchestrator request 2026-10-21)
    assert registration.family == "inspect" and registration.licence.spdx == "MIT"


def _media_sample(s: support.Sample, sample: dict) -> None:
    """0.3.112 shape: the tool event has no ``message_id``; the user turn carries an image and an audio attachment."""
    for event in sample["events"]:
        if event["event"] == "tool":
            del event["message_id"]
    s.attachments.update({"img0": IMAGE, "aud0": AUDIO})
    user = next(m for m in sample["messages"] if m["role"] == "user")
    user["content"] = [{"type": "text", "text": "Synthetic task prompt."},
                       {"type": "image", "image": "attachment://img0", "detail": "auto"},
                       {"type": "audio", "audio": "attachment://aud0", "format": "mp3"}]


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory: pytest.TempPathFactory) -> support.Imported:
    header = support.synthetic_header("0.3.112")
    header["eval"]["task"] = "account_takeover_suite"
    sample = support.basic_sample("s1", tune=_media_sample)
    data = support.build_eval(header, {"s1_epoch_1.json": sample})
    return support.import_log(data, tmp_path_factory.mktemp("atia-raw"), path="logs/x.eval",
                              profile=load_profile("atia-benchmark"))


def test_a_0_3_112_sample_seals_and_validates(synthetic: support.Imported):
    (unit,) = synthetic.units
    assert synthetic.register == [] and not unit.outcome.degenerate
    assert unit.header["task"]["benchmark"] == "atia" and unit.header["task"].get("attack_id") is None
    _validate(synthetic, unit)


def test_the_result_answers_its_call_without_message_id(synthetic: support.Imported):
    """0.3.112 writes no ``message_id`` on tool events; the result message still answers its call by ``tool_call_id``."""
    (unit,) = synthetic.units
    results = [p for r in unit.records if r["k"] == "message" for p in r["parts"] if p.get("t") == "tool_result"]
    assert results and all("responds_to" in p for p in results)
    assert "orphan_tool_result" not in {i["code"] for i in unit.outcome.issues}


def test_the_execution_generates_its_result_without_message_id(synthetic: support.Imported):
    """R-10n-1, closed by regeneration-batch item 25 (``inspect.tool_event_no_message_id@1``): at 0.3.112 the tool event
    links to the one tool message answering its id."""
    (unit,) = synthetic.units
    assert "missing_tool_result" not in {i["code"] for i in unit.outcome.issues}


def test_media_are_resolved_from_attachments_and_cited_by_locator(synthetic: support.Imported):
    """D-308: media inputs are raw evidence in the sample object, cited by locator ``/attachments/<hash>``. The part
    kind of audio and video is the mapper owner's (regen-batch item 25); the size rule of C.2.1(6) is routed
    (R-10n-2), so neither is asserted here."""
    (unit,) = synthetic.units
    user = next(r for r in unit.records if r["k"] == "message" and r["role"] == "user")
    locators = {s.get("p") for s in user.get("src", ())}
    assert {"/attachments/img0", "/attachments/aud0"} <= locators
    assert [p["t"] for p in user["parts"]][:2] == ["text", "uri"] and len(user["parts"]) == 3


def _cached_blob(path: str) -> bytes | None:
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    recipe = Recipe.from_pin(next(p for p in _toml()["source"]["pins"] if p.get("primary") is True))
    fetcher = Fetcher(resolve_cache_dir(None))
    if not fetcher.plan(recipe).cached:
        return None
    entries, _ = fetcher.git_tree(recipe)
    entry = next((e for e in entries if e.path == path), None)
    if entry is None:
        return None
    (blob,) = list(fetcher.iter_git_blobs(recipe, [entry]))
    return blob.data


@pytest.mark.slow
def test_the_smallest_pinned_log_maps_from_the_cache(tmp_path):
    path = min(LOGS, key=lambda p: LOGS[p][1])
    try:
        data = _cached_blob(path)
    except Exception as exc:  # an absent cache or blob: this test needs the user-approved fetch
        pytest.skip(f"the pinned ATIA log is not in the fetch cache ({type(exc).__name__})")
    if data is None:
        pytest.skip("the pinned ATIA log is not in the fetch cache")
    assert len(data) == LOGS[path][1]
    imported = support.import_log(data, tmp_path / "raw", path=path, profile=load_profile("atia-benchmark"))
    assert imported.register == [] and len(imported.units) == 19
    for unit in imported.units:
        assert not unit.outcome.degenerate
        _validate(imported, unit)
