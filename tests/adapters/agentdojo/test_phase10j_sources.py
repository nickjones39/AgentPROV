"""The phase-10j AgentDojo-format profiles (D-250..D-258; docs/reports/phase10j/; docs/architecture D.6.21).

Six profiles for the sources phase 10d deferred: two Zenodo deposits with nested tar.gz members, the Figshare DCA
artefact (a v1.k14 part and a DRIFT part), Kavach at three branch pins, EnvironmentOptim (104 logs mapped, the rest held
or owned elsewhere) and drift-1. The real fixtures (``tests/fixtures/<source>/``, written byte-identically by
``tools/agentdojo/phase10j_profiles.py fixtures``) are mapped under the origin the import gives them (``member`` for
archive members, ``git`` for blobs) and sealed by the core writer in release mode. The logs hold prompt-injection
payloads: nothing here prints them.
"""

from __future__ import annotations

import hashlib
import json
import re
import zlib
from pathlib import Path

import pytest
from agentdojo_support import REPO

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.runner import NotSelected, aer_bytes, map_artefact_total, map_unit
from agentprov.adapters.runner.importer import _match
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.rules import load_catalogue
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.origins import Origin

#: profile id -> (fixture directory, parts, semantics, the registry parts' import status)
PROFILES = {
    "authority-caps-agentdojo": ("authority-caps", ("head",), "agentdojo.suites@2"),
    "ipi-defenses-agentdojo": ("ipi-defenses", ("head",), "agentdojo.suites@2"),
    "dca-agentdojo": ("dca", ("v1", "drift"), "agentdojo.suites@2"),
    "kavach-agentdojo": ("kavach", ("main", "nav-fixer2", "rearch-forcedformat-fix"), "agentdojo.suites@2"),
    "environmentoptim-agentdojo": ("environmentoptim", ("head",), "agentdojo.suites@3"),
    "drift1-agentdojo": ("drift1", ("drift",), "agentdojo.suites@2"),
}
TABLES = ("authority_caps_pipeline_dirs", "ipi_defenses_run_dirs", "dca_run_dirs", "kavach_run_dirs",
          "environmentoptim_run_dirs", "drift1_model_dirs")
AGENTDOJO = REPO / "src" / "agentprov" / "adapters" / "agentdojo"
#: A cluster home path with an account segment (D-255): the masked form `<account>` is allowed, a real segment never.
ACCOUNT = re.compile(r"_ceph_ssd_students_[A-Za-z0-9]")
#: The phase-10c secret-pattern set (counts only; D-257).
SECRETS = (
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"), re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(rb"\bhf_[A-Za-z0-9]{30,}\b"), re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _fixtures(profile_id: str) -> list[dict]:
    source = REPO / "tests" / "fixtures" / PROFILES[profile_id][0] / "SOURCE.json"
    if not source.is_file():
        pytest.skip(f"the {profile_id} fixtures are absent")
    return list(json.loads(source.read_bytes()))


def _raw(profile_id: str, entry: dict) -> bytes:
    raw = (REPO / "tests" / "fixtures" / PROFILES[profile_id][0] / entry["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"]
    assert f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" == entry["crc32"]
    return raw


def _origin(entry: dict) -> Origin:
    data = dict(entry["origin"])
    return Origin(data.pop("kind"), data)


def _records(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.splitlines()][:-1]


def _fixture_cases() -> list[tuple[str, str]]:
    out = []
    for profile_id, (directory, _parts, _sem) in PROFILES.items():
        source = REPO / "tests" / "fixtures" / directory / "SOURCE.json"
        if source.is_file():
            out += [(profile_id, e["chain"] + "@" + e["part"]) for e in json.loads(source.read_bytes())]
    return out


# ------------------------------------------------------------------------------------------------ profiles and registry
@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_profile_conforms_and_every_quirk_is_cited_and_censused(profile_id):
    jsonschema = pytest.importorskip("jsonschema")
    profile = load_profile(profile_id)
    table = family_table(profile)
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []
    # regeneration-batch item 106 bumped environmentoptim-agentdojo to version 2 (D-31; v1 archived)
    assert profile.version == (2 if profile_id == "environmentoptim-agentdojo" else 1)
    assert profile.parts == PROFILES[profile_id][1]
    assert table.verified_code == () and table.harness["code_identity"] == "unpinned"  # D-24: no harness verified
    for quirk in table.quirks:
        for rule in quirk.rules:
            entry = load_catalogue(rule.split(".", 1)[0]).get(rule)
            assert entry is not None and entry.citable, (quirk.id, rule)
        assert set(quirk.observed) & set(profile.parts), quirk.id  # measured (phase10j_profiles.py census)
    for part in profile.parts:
        assert [p for p in census.compare(table, part, {}) if "no census function" in p] == []


#: D-901: environmentoptim-agentdojo is excluded (the author withdrew the repository); its profile stays as a test vehicle
RETIRED = ("environmentoptim-agentdojo",)


@pytest.mark.parametrize("profile_id", sorted(set(PROFILES) - set(RETIRED)))
def test_registry_parts_are_sealed_with_their_own_corpus(profile_id):
    """D-830, D-833: at their v0.1 target after the wave-2 import and seal (the DRIFT parts stay partial)."""
    registration = get_source(profile_id)
    assert tuple(c.part for c in registration.capabilities) == PROFILES[profile_id][1]
    for part in registration.capabilities:
        assert part.profile == profile_id and part.corpus_id == profile_id
        assert part.import_status == part.target_import_status and part.import_status in ("supported", "partial")
        assert part.caveat is not None and part.caveat.startswith(
            f"full pinned snapshot imported through agentprov import in wave 2 and sealed as {profile_id} 0.1.0 ("
        )
        assert [s.corpus_id for s in part.sealed] == [profile_id]
        assert part.semantics == (PROFILES[profile_id][2],)
    assert registration.licence.policy == "include"
    assert registration.licence.attribution == tuple(load_profile(profile_id).data["licence"]["attribution"])


@pytest.mark.parametrize("profile_id", RETIRED)
def test_retired_profiles_are_not_registered(profile_id):
    with pytest.raises(KeyError):
        get_source(profile_id)


def test_pins_are_the_census_pins():
    pins = {pid: [dict(p) for p in load_profile(pid).data["source"]["pins"]] for pid in PROFILES}
    (caps,) = pins["authority-caps-agentdojo"]
    assert (caps["kind"], caps["record"], caps["version"], caps["size"]) == ("zenodo", 23138310, "2.1.0", 40160657)
    assert caps["sha256"].startswith("1dce0380")
    (ipi,) = pins["ipi-defenses-agentdojo"]
    assert (ipi["kind"], ipi["record"], ipi["version"], ipi["sha256"][:8]) == ("zenodo", 22011266, "4.0.0", "c2370724")
    (dca,) = pins["dca-agentdojo"]
    assert (dca["kind"], dca["sha256"][:8], dca["size"]) == ("url", "ed500ca3", 54196099)  # an archive input (D-455)
    assert dca["retrieved_at"] == "2026-10-11T09:46:41Z" and "retrieved" not in dca  # the phase-10c acquisition record
    assert [p["commit"][:8] for p in pins["kavach-agentdojo"]] == ["53df9545", "f2dd7efa", "6b31a554"]
    assert [p["part"] for p in pins["kavach-agentdojo"]] == ["main", "nav-fixer2", "rearch-forcedformat-fix"]
    assert pins["environmentoptim-agentdojo"][0]["commit"].startswith("febf82d8")
    assert pins["drift1-agentdojo"][0]["commit"].startswith("0e28729b")


def test_nested_archives_are_declared_for_the_two_zenodo_deposits():
    caps = load_profile("authority-caps-agentdojo").data["import"]["nested"]
    assert [n["id"] for n in caps] == ["exp4", "exp5", "exp7"]
    ipi = load_profile("ipi-defenses-agentdojo").data["import"]["nested"]
    assert [n["id"] for n in ipi] == ["run1-mini", "run2-mini", "run2-frontier"]


# ------------------------------------------------------------------------------------------------ identity tables
def test_identity_tables_hold_the_census_directories():
    rows = {pid: family_table(load_profile(pid)).table_rows for pid in PROFILES}
    assert len(rows["authority-caps-agentdojo"]) == 21 and len(rows["ipi-defenses-agentdojo"]) == 19
    assert len(rows["dca-agentdojo"]) == 22 and len(rows["kavach-agentdojo"]) == 13
    eo = rows["environmentoptim-agentdojo"]  # item 106: one row per arm path (D-254 addendum, option (a))
    assert len(eo) == 135 and eo["gpt-5.4-2026-03-05"]["model"] == "gpt-5.4-2026-03-05"
    assert {r["model"] for r in eo.values()} == {"gpt-5.4-2026-03-05", "Qwen3.5-9B", "Qwen3.5-2B", "Qwen3.5-4B"}
    assert set(rows["drift1-agentdojo"]) == {"gpt-4o-mini", "pact-gpt-4o-mini-banking10"}
    caps = rows["authority-caps-agentdojo"]
    assert caps["gpt-6-luna-capA3"]["defence"] == "authority_cap_a3" and caps["gpt-6-luna-capA3"]["model"] == "gpt-6-luna"
    assert caps["gpt-4o-mini-2024-07-18-noegress"]["defence"] == "no_egress"
    assert caps["claude-haiku-4-5-20251001-autoconfirm"]["defence"] == "none"  # a harness setting, not a defence
    dca = rows["dca-agentdojo"]
    local = dca["dca_direct/direct_agentdojo_qwen2_7b_ollama_gpu_important_instructions/local"]
    assert (local["model"], local["provider"], local["defence"]) == ("Qwen2-7B", "ollama", "none")  # README (D-92)
    oss = dca["drift/runs_agentdojo_full_gptoss20b_compat_module/gpt-oss:20b"]
    assert oss["model"] == "openai/gpt-oss-20b" and "provider" not in oss  # D-252: route unrecorded
    kavach = rows["kavach-agentdojo"]
    assert sum(1 for r in kavach.values() if "model" not in r) == 6  # D-253: six directories unresolved
    assert {r["model"] for r in kavach.values() if "model" in r} == {"gemma4:26b"}
    assert all("invalid" in kavach[k].get("note", "") for k in kavach if "slack_gemma_dell" in k)


def test_no_phase10j_file_carries_an_account_segment():
    """D-255: the EnvironmentOptim cluster home path is never written into Git, only its masked form."""
    files = [AGENTDOJO / "tables" / f"{t}.toml" for t in TABLES]
    files += [AGENTDOJO / "profiles" / f"{p}.profile.toml" for p in PROFILES]
    files += sorted((REPO / "docs" / "reports" / "phase10j").glob("*"))
    files += [REPO / "tools" / "agentdojo" / "phase10j_census.py", REPO / "tools" / "agentdojo" / "phase10j_profiles.py"]
    for directory, _parts, _sem in PROFILES.values():
        files += sorted((REPO / "tests" / "fixtures" / directory).glob("*"))
    for path in files:
        if path.is_file():
            assert ACCOUNT.search(path.read_text(encoding="utf-8")) is None, path.name


# ------------------------------------------------------------------------------------------------ selection
@pytest.mark.parametrize(("path", "code", "owner"), [
    ("runs/dojo_gpt-4o-2024-05-13/banking/user_task_0/none/none.json", "select.owned_elsewhere", "agentdojo"),  # NF-1
    ("runs/gpt-5.1-2025-11-13-drift/github/user_task_1/none/none.json", "select.owned_elsewhere", "agentdyn"),
    ("runs/gpt-4o-mini-2024-07-18-drift/github/user_task_1/none/none.json", "select.owned_elsewhere", "agentdyn"),
    ("runs/benign_injection/checkpoint_1/256/x/banking/user_task_0/none/none.json", None, None),  # item 106: mapped
    ("runs/soft_language_prompt/infix/seed25/50tokens/x/slack/user_task_0/none/none.json", None, None),
    ("runs/qwen3_5-2B_baseline/x/travel/user_task_0/none/none.json", None, None),
    ("runs/gpt-5.4-2026-03-05/banking/user_task_0/none/none.json", None, None),
])
def test_environmentoptim_selects_only_its_mapped_logs(path, code, owner):
    """D-254, D-255, R-3: copies are owned elsewhere; the local-Qwen arms and gpt-5.4 are mapped (item 106: the redaction
    rule covers the arms' account directory)."""
    imp = load_profile("environmentoptim-agentdojo").data["import"]
    assert any(_match(path, g) for g in imp["include"])
    entry = next((e for e in imp["exclude"] if _match(path, str(e["glob"]))), None)
    assert (entry or {}).get("code") == code and (entry or {}).get("owner") == owner


def test_drift1_excludes_the_drift_head_copies_only():
    imp = load_profile("drift1-agentdojo").data["import"]
    owned = [e for e in imp["exclude"] if e["code"] == "select.owned_elsewhere"]
    assert [(e["glob"], e["owner"]) for e in owned] == [("runs/gpt-4o-mini-2024-07-18/**", "drift")]
    assert not any(_match("runs/gpt-4o-mini/banking/user_task_0/none/none.json", str(e["glob"])) for e in imp["exclude"])


# ------------------------------------------------------------------------------------------------ fixtures
@pytest.mark.parametrize(("profile_id", "case"), _fixture_cases())
def test_every_fixture_maps_and_seals_in_release_mode(profile_id, case):
    chain, part = case.rsplit("@", 1)
    (entry,) = [e for e in _fixtures(profile_id) if e["chain"] == chain and e["part"] == part]
    raw = _raw(profile_id, entry)
    assert not any(p.search(raw) for p in SECRETS)  # D-257, D-258
    origin = _origin(entry)
    assert origin.kind == ("git" if profile_id in ("kavach-agentdojo", "environmentoptim-agentdojo", "drift1-agentdojo")
                           else "member")
    outcome, unit = map_artefact_total(raw, origin, profile_id=profile_id, part=part)
    assert unit.primary.variant == entry["variant"] and not outcome.degenerate
    data, info = aer_bytes(outcome)  # the core writer validates in release mode
    records = _records(data)
    agent = next(r for r in records if r.get("k") == "actor" and r.get("id") == "agent")
    table = family_table(load_profile(profile_id))
    facets = table.layout.match(origin.data.get("path") or origin.data.get("label"))
    key = facets.get(str(table.identity.get("model_from", "pipeline_dir"))) if facets else None
    if facets and not key and table.identity.get("model_dir_fallback") == "pipeline_dir":
        key = facets.get("pipeline_dir")  # item 106: a file with no experiment path is keyed by its directory
    row = table.table_rows.get(key) if key else None
    assert row is not None, key
    assert agent.get("model", {}).get("requested") == row.get("model")
    codes = {str(i["code"]) for i in info.issues}
    assert ("identity_unresolved" in codes) == ("model" not in row)
    assert "agentdojo.pipeline_name_mismatch" not in codes
    defences = sorted(str(r["name"]) for r in records if r.get("k") == "actor" and r.get("kind") == "defense")
    expected = set() if row.get("defence", "none") == "none" else {row["defence"]}
    if entry["variant"].startswith("drift."):
        expected.add("drift")  # the DRIFT build adds it from the key set, never twice
    assert defences == sorted(expected)


def test_fixture_budgets_stay_small():
    for directory, _parts, _sem in PROFILES.values():
        root = REPO / "tests" / "fixtures" / directory
        if root.is_dir():
            assert sum(p.stat().st_size for p in root.iterdir() if p.is_file()) < 256 * 1024, directory  # D-258


def test_a_dca_drift_log_belongs_to_the_drift_part():
    """variant_labels: a drift.k18.conversations log is never mapped as part v1 (and v1.k14 never as drift)."""
    entries = [e for e in _fixtures("dca-agentdojo") if e["part"] == "drift"]
    if not entries:
        pytest.skip("no DRIFT fixture")
    raw = _raw("dca-agentdojo", entries[0])
    with pytest.raises(NotSelected):
        map_artefact_total(raw, _origin(entries[0]), profile_id="dca-agentdojo", part="v1")


# ------------------------------------------------------------------------------------------------ Kavach denials
def _kavach_log(error: str, content: str) -> bytes:
    """A synthetic v1.k14 log (made up here, not source data) with one blocked call."""
    call = {"function": "send_email", "args": {"recipients": ["x@example.org"]}, "id": "c1", "placeholder_args": None}
    doc = {
        "suite_name": "workspace", "pipeline_name": "local-kavach", "user_task_id": "user_task_0",
        "injection_task_id": "injection_task_1", "attack_type": "important_instructions", "injections": {},
        "messages": [
            {"role": "system", "content": [{"type": "text", "content": "synthetic"}]},
            {"role": "user", "content": [{"type": "text", "content": "synthetic task"}]},
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "tool", "content": [{"type": "text", "content": content}], "tool_call_id": "c1", "tool_call": call,
             "error": error},
            {"role": "assistant", "content": [{"type": "text", "content": "done"}], "tool_calls": None},
        ],
        "error": None, "utility": False, "security": False, "duration": 1.0, "benchmark_version": None,
        "evaluation_timestamp": "2026-07-06 10:00:00.000000", "agentdojo_package_version": "0.1.35",
    }
    return json.dumps(doc).encode()


def _map_synthetic(raw: bytes, path: str):
    reader, mapper, profile = TraceLoggerReader(), TraceLoggerMapper(), load_profile("kavach-agentdojo")
    limits = IngestLimits()
    origin = Origin.git("https://github.com/Ishani018/Kavach", "6b31a5546b152c93435772bb4f3521dd78ee3446", path, "0" * 40)
    sniff = reader.sniff(raw, label=path, limits=limits)
    assert sniff.match, sniff.reasons
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=limits))
    return map_unit(ExecutionUnit(item), mapper, profile)


def test_a_kavach_block_is_a_deny_decision_of_the_kavach_defence():
    """D-113: the block text as error and output is a deny decision; the call is not executed."""
    text = "[KAVACH BLOCK — decided_by=EXECUTOR, synthetic]"
    path = "benchmarks/results_v2/agentdojo_workspace_not_forced2/logs/local-kavach/workspace/user_task_0/important_instructions/injection_task_1.json"
    records = [r for r in _map_synthetic(_kavach_log(text, text), path).records]
    decisions = [r for r in records if r.get("k") == "decision"]
    assert [d.get("verdict") for d in decisions] == ["deny"]
    assert not [r for r in records if r.get("k") == "tool_execution"]
    plain = [r for r in _map_synthetic(_kavach_log("ValueError: synthetic", "ValueError: synthetic"), path).records]
    assert not [r for r in plain if r.get("k") == "decision"] and [r for r in plain if r.get("k") == "tool_execution"]


def test_the_routed_requests_are_recorded():
    text = (REPO / "docs" / "reports" / "phase10j" / "routing.md").read_text(encoding="utf-8")
    for rid in ("R-10j-1", "R-10j-2", "R-10j-3"):
        assert f"## {rid}." in text
    assert Path(REPO / "docs" / "reports" / "phase10j" / "census.json").is_file()


def test_each_kavach_caveat_states_its_own_pins_unresolved_directories():
    # measured per pin over the census rows (phase10j profiles kavach.<part>.rows.jsonl, before the D-253 collapse):
    # main 1 directory (3 logs), nav-fixer2 6 (150), rearch-forcedformat-fix 5 (66); six across the three pins
    expected = {"main": "one directory identity_unresolved at this pin (3 logs",
                "nav-fixer2": "six directories identity_unresolved at this pin (150 logs",
                "rearch-forcedformat-fix": "five directories identity_unresolved at this pin (66 logs"}  # fmt: skip
    from agentprov.adapters.registry import REGISTRY

    caveats = {c.part: c.caveat for r in REGISTRY if r.source_id == "kavach-agentdojo" for c in r.capabilities}
    assert set(caveats) == set(expected)
    for part, text in expected.items():
        assert text in str(caveats[part]), part
