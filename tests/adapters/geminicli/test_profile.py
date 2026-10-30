"""Profile, registry entry and family schema of the ``geminicli`` family (docs/architecture D.23.10, D.3; D-330, D-331)."""

from __future__ import annotations

import fnmatch
import json
import tomllib

import geminicli_support as support

from agentprov.adapters.profiles import SELECT_CODES, load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "geminicli"


def test_profile_pins_licence_import_and_family_schema():
    import jsonschema

    profile = load_profile(support.PROFILE)
    assert (profile.family, profile.source_id, profile.parts) == ("geminicli", support.PROFILE, ("results-raw",))
    (pin,) = profile.data["source"]["pins"]
    assert pin["sha256"] == support.TAR_SHA256 and pin["primary"] is True and pin["kind"] == "zenodo"
    assert pin["doi"] == "10.5281/zenodo.20404563" and pin["file"] == "RESULTS_raw.tar.zst" and pin["size"] == 207950011
    assert profile.data["licence"]["spdx"] == "CC-BY-4.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "geminicli.stream_json" and imp["variants"] == ("v1",)
    assert {e["code"] for e in imp["exclude"]} == {"select.out_of_scope", "select.not_execution_artefact"} <= SELECT_CODES
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / f"{support.PROFILE}.profile.toml").read_text(encoding="utf-8"))["family"]["geminicli"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    assert family["semantics_profile"] == {"id": "geminicli.tools", "version": 1}


def test_out_of_scope_globs_are_exactly_the_excluded_scaffolds():
    """D-143 as data: one select.out_of_scope entry per excluded scaffold, on its verdicts only, and each is included
    (so the expand stage stores one member per rollout to register)."""
    profile = load_profile(support.PROFILE)
    family = profile.family_table()
    imp = profile.data["import"]
    out = [e for e in imp["exclude"] if e["code"] == "select.out_of_scope"]
    scaffolds = {e["glob"].split("/")[2].split("__", 1)[0] for e in out}
    assert scaffolds == set(family["excluded_scaffolds"]) and family["scaffold"] not in scaffolds
    for e in out:
        assert e["glob"].endswith("/verdict.json") and e["note"].startswith("D-143") and e["glob"] in imp["include"]
    label = "RESULTS_build/cells/gemini_cli__MiniMax-M2/SK-A__m01/gemini_stream.jsonl"
    assert any(fnmatch.fnmatchcase(label, g) for g in imp["include"])
    assert not any(fnmatch.fnmatchcase(label, e["glob"]) for e in imp["exclude"])


def test_withhold_policy_parses_and_matches_the_key_shape_only():
    from agentprov.corpus.withhold import policy_of_profile

    path = SRC / "profiles" / f"{support.PROFILE}.profile.toml"
    policy = policy_of_profile(path.read_bytes(), profile_id=support.PROFILE, profile_version=2)
    assert policy is not None
    rule = next(r for r in policy.rules if r.id == "google-api-key-shape")
    assert rule.kind == "pattern" and rule.scope == "executions"
    assert rule.reason == "secret"
    synthetic = b"AIza" + b"Q" * 35  # a synthetic value of the shape, never a real one
    assert rule.hits(b"x " + synthetic + b" y") and not rule.hits(b"AIza" + b"Q" * 30)


#: A made-up account (not a generic one, never a deposited name), assembled at run time.
_ACCOUNT = "q" + "z" + "x"


def test_d609_account_path_rules_are_object_scope_personal_data():
    """D-609: two structural pattern rules, object scope, reason personal_data (overriding the table's secret), each with
    its own public note; the key-shape rule is unchanged. Version 2 is current; version 1 is the archived D-31 bytes."""
    from agentprov.corpus.withhold import policy_of_profile

    profile = load_profile(support.PROFILE)
    assert profile.version == 2 and load_profile(support.PROFILE, 1).version == 1
    policy = policy_of_profile(path_text().encode(), profile_id=support.PROFILE, profile_version=2)
    assert policy is not None
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("deposit-readme-account-path", "pattern", "object", "personal_data"),
        ("google-api-key-shape", "pattern", "executions", "secret"),
        ("harness-account-path", "pattern", "object", "personal_data"),
    ]
    notes = {r.id: r.public_note for r in policy.rules}
    assert "D-609" in notes["harness-account-path"] and "D-609" in notes["deposit-readme-account-path"]
    assert "credential" in notes["google-api-key-shape"]
    # the profile names no account: the patterns are structural
    assert _ACCOUNT not in path_text()


def path_text() -> str:
    return (SRC / "profiles" / f"{support.PROFILE}.profile.toml").read_text(encoding="utf-8")


def test_d609_harness_rule_matches_the_diff_header_form_only():
    from agentprov.corpus.withhold import policy_of_profile

    policy = policy_of_profile(path_text().encode(), profile_id=support.PROFILE, profile_version=2)
    assert policy is not None
    harness = next(r for r in policy.rules if r.id == "harness-account-path")
    readme = next(r for r in policy.rules if r.id == "deposit-readme-account-path")
    header = f"diff -r /home/{_ACCOUNT}/jss_agent_work/before/app.py /home/{_ACCOUNT}/jss_agent_work/after/app.py\n"
    assert harness.hits(header.encode()) and not readme.hits(header.encode())
    home = f"Source: /home/{_ACCOUNT}/TempXy/results/\n".encode()
    assert readme.hits(home) and not harness.hits(home)
    # agent-written placeholder paths and generic homes are not the harness form
    for benign in (f"+    path = '/home/{_ACCOUNT}/projects/app'\n", "+ cd /home/user/agent_work\n",
                   "/home/user/project/src\n", "/home/alice/Documents/notes.txt\n", "C:\\Users\\foo\\app\n",
                   f"/Users/{_ACCOUNT}/jss_agent_work\n", f"/home/{_ACCOUNT.upper()}/jss_agent_work\n"):
        assert not harness.hits(benign.encode()) and not readme.hits(benign.encode()), benign


def test_registry_entry_is_supported_and_cc_by():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source(support.PROFILE)
    (part,) = reg.capabilities
    assert part.part == "results-raw" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == support.PROFILE and part.semantics == ("geminicli.tools@1",)
    assert part.corpus_id == "code-agent-misalignment"
    assert reg.licence.spdx == "CC-BY-4.0" and reg.licence.restrictions == () and reg.licence.policy == "include"
    assert resolve_factory(READERS["geminicli.stream_json"]).__name__ == "GeminiStreamReader"
    assert resolve_factory(MAPPERS["geminicli.stream_json"]).__name__ == "GeminiStreamMapper"
