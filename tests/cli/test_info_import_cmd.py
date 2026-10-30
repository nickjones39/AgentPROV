"""``agentprov info`` (MN N.2.9; D.3.5; D-7) and the ``agentprov import`` pre-flight (N.2.2; N.1.3; N.3).

The registry is rendered per part with its gated statuses (phase 6); ``test_import_cmd.py`` covers the import pipeline.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from agentprov.versions import VERSIONS

# ---------------------------------------------------------------------------------------------- info


def test_info_text_lists_versions_registry_state_installation_and_host(cli, host_probe):
    run = cli("info")
    assert run.code == 0
    out = run.out
    for token in ("aer/0.1", "sem/0.1", "capture/0.1", "agentprov-prov/0.1", "apv 0.2.0"):
        assert token in out
    assert "SOURCE · PART" in out and "agentdojo · 2024-06" in out and "adprov-v1 · converted-legacy" in out
    assert "phase 3" not in out and "not part of this build" not in out
    assert "interpreter_advisory  none" in out
    assert "extras" in out and "tools" in out and "AGENTPROV_HOME" in out
    assert "isolation grade   watchdog" in out
    assert "os / arch" in out


def test_info_prints_exactly_the_registry_statuses(cli, host_probe):
    """D.3.5: one row per part, the registry's gated status and nothing else; a part with a caveat carries it."""
    from agentprov.adapters.registry import REGISTRY

    out = cli("info").out
    for registration in REGISTRY:
        for part in registration.capabilities:
            line = next(row for row in out.splitlines() if row.strip().startswith(f"{registration.source_id} · {part.part} "))
            fields = line.split()
            shown = fields[fields.index(part.role) + 1]
            assert shown == (part.import_status or "—"), line
    for source in ("stac", "midojo"):  # drift is registered since phase 10l
        assert f"{source} · " not in out  # sources this build does not register are not listed


def test_info_json_payload_is_canonical_and_holds_the_registry(cli, host_probe):
    run = cli("info", "--format", "json")
    assert run.code == 0
    data = json.loads(run.out)
    from agentprov.adapters.registry import REGISTRY

    assert data["registry"]["available"] is True and data["registry"]["sources"] == [r.source_id for r in REGISTRY]
    parts = {(p["source_id"], p["part"]): p for p in data["registry"]["parts"]}
    for registration in REGISTRY:
        for part in registration.capabilities:
            assert parts[(registration.source_id, part.part)]["import"] == part.import_status
    assert data["versions"] == VERSIONS
    assert data["readable"] == {"aer": ["aer/0.1", "aer/0.2"], "corpus_format": ["agentprov-corpus/0.1", "agentprov-corpus/0.2"]}
    assert data["host"]["isolation"]["grade"] == "watchdog"
    assert data["installation"]["interpreter"]["interpreter_advisory"] is None
    assert set(data["installation"]["extras"]) == {"live", "render", "shacl", "zenodo"}
    assert set(data["installation"]["tools"]) == {"git", "uv", "dot"}
    from agentprov.io.canonical import jcs_bytes

    assert run.out.encode() == jcs_bytes(data) + b"\n"


def test_info_markdown_format(cli, host_probe):
    run = cli("info", "--format", "markdown")
    assert run.code == 0 and run.out.startswith("# agentprov 0.1.0") and "\n## Host\n" in run.out


def test_info_json_flag_puts_the_summary_on_stdout_and_the_rendering_on_stderr(cli, host_probe, check_summary):
    run = cli("info", "--json")
    document = run.json()
    check_summary(document)
    from agentprov.adapters.registry import REGISTRY

    assert document["command"] == "info" and document["counters"]["sources_registered"] == len(REGISTRY)
    assert "SOURCE · PART" in run.err
    assert run.out.startswith("{") and run.out.count("\n") == 1  # stdout is the JSON document only


def test_info_quiet_json_prints_no_rendering(cli, host_probe):
    run = cli("info", "--json", "-q")
    assert "registry" not in run.err and run.json()["command"] == "info"


def test_info_alias_sources(cli, host_probe):
    assert cli("sources").out == cli("info").out


def test_info_reports_the_interpreter_advisory(cli, host_probe, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    run = cli("info", "--json")
    document = run.json()
    assert "interpreter_advisory  below 3.14.8" in run.err
    assert any("release mode refuses archive" in n for n in document["notices"])


def test_info_degraded_isolation_is_noticed(cli, host_probe):
    host_probe["isolation"]["grade"] = "degraded"
    host_probe["isolation"]["reasons"] = ["no process-tree kill"]
    run = cli("info", "--json")
    assert any("isolation grade is degraded" in n for n in run.json()["notices"])
    assert "no process-tree kill" in run.err


def test_info_lists_built_backend_environments_from_markers(cli, host_probe, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    env = tmp_path / "envs" / "agentdojo-c2748856"
    env.mkdir(parents=True)
    (env / "AGENTPROV_ENV.json").write_text(json.dumps({"commit": "c2748856", "python": "3.12.8", "ignored": "x"}))
    (tmp_path / "envs" / "broken").mkdir()
    (tmp_path / "envs" / "broken" / "AGENTPROV_ENV.json").write_text("{not json")
    data = json.loads(cli("info", "--format", "json").out)
    envs = {e["name"]: e for e in data["installation"]["backend_environments"]}
    assert envs["agentdojo-c2748856"]["marker"] is True and envs["agentdojo-c2748856"]["commit"] == "c2748856"
    assert "ignored" not in envs["agentdojo-c2748856"]
    assert envs["broken"]["marker"] == "unreadable"


def test_info_without_backend_environments_says_none_built(cli, host_probe, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    assert "backend envs      none built" in cli("info").out


@pytest.mark.parametrize("flags", [["--matrix"], ["--must-not-claim"]])
def test_info_claims_dependent_forms_are_refused_not_invented(cli, host_probe, flags):
    run = cli("info", *flags, "--json")
    assert run.code == 5
    assert run.json()["refusal"]["status"] == "the claims library is not part of this build"


@pytest.mark.parametrize("flags", [["agentdojo"], ["--source", "agentdojo"]])
def test_info_source_shows_parts_profiles_pins_and_licence(cli, host_probe, flags):
    run = cli("info", *flags)
    assert run.code == 0
    for token in ("2024-06: role source", "agentdojo-upstream v2 sha256", "pin 2024-06: git", "c274885610efaaafec38b6d3eb07152ba7ff3f94",
                  "policy include", "Evidence"):
        assert token in run.out
    data = json.loads(cli("info", *flags, "--format", "json").out)
    assert data["source_id"] == "agentdojo" and [p["part"] for p in data["parts"]][:2] == ["head", "2024-06"]


def test_info_renders_every_registry_string_whole():
    """CD-1: registry caveats run to ~1,000 characters; escaping (D.3.5 rule 3) must not truncate the honesty text."""
    from agentprov.adapters.registry import REGISTRY
    from agentprov.adapters.registry.render import registry_rows, source_detail
    from agentprov.cli.info import _escape

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from strings(v)
        elif isinstance(value, list):
            for v in value:
                yield from strings(v)

    longest = max(len(s) for s in strings(registry_rows()))
    assert longest > 500
    rendered = [_escape(registry_rows()), *(_escape(source_detail(r.source_id)) for r in REGISTRY)]
    assert not [s for d in rendered for s in strings(d) if "[truncated" in s]
    assert _escape("a\nb\u202e") == "a<U+000A>b<U+202E>"


def test_info_unknown_source_is_a_usage_error(cli, host_probe):
    assert cli("info", "no-such-source").code == 2


def test_info_source_and_option_must_agree(cli, host_probe):
    assert cli("info", "a", "--source", "b").code == 2


def test_info_real_subprocess_runs_the_host_probe_and_grades_isolation():
    done = subprocess.run([sys.executable, "-m", "agentprov", "info", "--format", "json", "-q"], capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr
    data = json.loads(done.stdout)
    assert data["host"]["isolation"]["grade"] in ("enforced", "watchdog", "degraded")
    assert data["host"]["profile"]["arch"]


# ---------------------------------------------------------------------------------------------- import
# Phase 6 replaced the registry-less stub (every source exit 5) by the real command. These checks keep the pre-flight
# contract: usage errors (2) and refusals (4, 5) before any input is read or any corpus written. ``foobench`` (registry
# status None) stands in for a source the status gate refuses.


def _import(cli, tmp_path, *extra, source="foobench"):
    return cli("import", source, "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), *extra)


def test_import_refuses_a_source_without_an_import_and_writes_nothing(cli, tmp_path, check_summary):
    run = _import(cli, tmp_path, "--json")
    assert run.code == 5
    document = run.json()
    check_summary(document)
    assert document["refusal"]["id"] == "foobench" and document["refusal"]["mode"] == "import"
    assert "agentprov: cannot import 'foobench': no import capability (part fixture)." in run.err
    assert "Nothing was read from the input and nothing was written." in run.err
    assert [p.name for p in tmp_path.iterdir()] == []  # no corpus, no .partial


def test_import_alias_convert(cli, tmp_path):
    assert cli("convert", "foobench", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path)).code == 5


def test_import_unknown_source_is_a_usage_error_with_the_id_escaped(cli, tmp_path):
    run = _import(cli, tmp_path, source="evil\x1b[31m\u202e")
    assert run.code == 2  # N.1.3: an unknown source id is a usage error (the stub refused every id with 5)
    assert "\x1b" not in run.err and "\u202e" not in run.err and "<U+001B>" in run.err


def test_import_spec_replaces_the_source_argument(cli, tmp_path):
    spec = tmp_path / "corpus.toml"
    spec.write_text("")
    run = cli("import", "--spec", str(spec), "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 5 and run.json()["refusal"]["id"] == str(spec)


def test_import_requires_a_corpus(cli, tmp_path):
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--input", str(tmp_path)).code == 2


def test_import_requires_a_source_unless_a_spec_is_given(cli, tmp_path):
    assert cli("import", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path)).code == 2


def test_import_requires_an_origin(cli, tmp_path):
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c")).code == 2


def test_import_input_must_exist(cli, tmp_path):
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path / "nope")).code == 2


@pytest.mark.parametrize("expression", ["noequals", "=v", "a=", "1a=b", "a=b=c"])
def test_import_select_syntax_is_checked(cli, tmp_path, expression):
    assert _import(cli, tmp_path, "--select", expression).code == 2


def test_import_select_accepts_or_lists_and_repeats(cli, tmp_path):
    run = _import(cli, tmp_path, "--select", "suite=a,b", "--select", "attack=c", "--json")
    assert run.code == 5
    assert run.json()["options"]["select"] == ["suite=a,b", "attack=c"]


@pytest.mark.parametrize("flags", [["--limit", "5"], ["--select", "a=b"], ["--suite", "s"], ["--attack", "a"], ["--pipeline", "p"], ["--variant", "v"]])
def test_import_release_forbids_limits_and_filters(cli, tmp_path, flags):
    assert _import(cli, tmp_path, "--release", *flags).code == 2


def test_import_release_with_in_process_is_refused(cli, tmp_path):
    run = _import(cli, tmp_path, "--release", "--in-process")
    assert run.code == 4 and "G.4.9" in run.err


def test_import_fetch_of_an_uncached_pin_without_allow_network_is_refused(cli, tmp_path):
    """D-220: --fetch without --allow-network serves the cache only; an empty cache refuses (raw.fetch.not_cached, 4)."""
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--fetch",
              "--cache-dir", str(tmp_path / "empty-cache"))
    assert run.code == 4 and "not in the fetch cache" in run.err


def test_import_verify_against_pin_goes_with_input(cli, tmp_path):
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--fetch", "--allow-network",
               "--verify-against-pin").code == 2


def test_import_numeric_options(cli, tmp_path):
    assert _import(cli, tmp_path, "--limit", "0", "--jobs", "0").code == 5  # 0 is valid for both
    assert _import(cli, tmp_path, "--limit", "-1").code == 2
    assert _import(cli, tmp_path, "--max-file-bytes", "0").code == 2
    assert _import(cli, tmp_path, "--max-json-depth", "0").code == 2


def test_import_until_choices(cli, tmp_path):
    assert _import(cli, tmp_path, "--until", "prov").code == 5
    assert _import(cli, tmp_path, "--until", "nonsense").code == 2
