"""Sandbox ``env_vars`` never reach an AER, SEM, PROV file or report (docs/architecture D.16.13; D.16.14 test 9).

A configuration built here with sentinel ``env_vars`` (synthetic keys and values; nothing real) joins a real fixture run;
the whole import (raw store excepted: raw bytes are never edited, D.16.13) is searched for every key and value. The
derived fixtures are checked against the pinned blobs when the staging tree is present (``full_corpus``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import dtap_support as support
import pytest

SENTINEL_KEYS = ("DTAPTEST_USER_ACCESS_TOKEN", "DTAPTEST_CLIENT_SECRET")
SENTINEL_VALUES = ("sentinel-value-7c1f3a9e", "sentinel-value-0b5d2e44")
STAGING = Path(os.environ.get("AGENTPROV_DTAP_STAGING", str(Path.home() / ".agentprov" / "staging" / "dtap")))


def _config_with_env_vars() -> bytes:
    """F03's configuration (verbatim, no env_vars) with a server carrying sentinel env_vars, as YAML flow text."""
    from agentprov.ingest import yamlsafe

    path = "travel/malicious/indirect/payment-credential-collection/005/config.yaml"
    document = yamlsafe.safe_load(support.tasks_files()[path])
    document.setdefault("Agent", {})["mcp_servers"] = [
        {"name": "travel-suite", "enabled": True, "env_vars": dict(zip(SENTINEL_KEYS, SENTINEL_VALUES, strict=True))}]
    document["Task"]["env_vars"] = {SENTINEL_KEYS[0]: SENTINEL_VALUES[0]}  # even inside an allowlisted table
    return json.dumps(document).encode()  # JSON is YAML: safe_load reads it unchanged


def test_sandbox_credentials_reach_no_derived_output(tmp_path):  # (the name keeps "env_vars" out of tmp paths)
    path = "travel/malicious/indirect/payment-credential-collection/005/config.yaml"
    runs = {k: v for k, v in support.runs_files().items() if k.startswith(support.F["F03"].rsplit("/", 1)[0])}
    imp = support.run_import(tmp_path, runs, {path: _config_with_env_vars()})
    assert imp.report.counters["validated"] == 1
    head = imp.headers()[support.F["F03"]]
    assert head["ext"]["dtap"]["join"]["tier"] == "A"  # the configuration was read and used for run content
    files = support.tree_bytes(imp.partial)
    derived = {rel: data for rel, data in files.items() if not rel.startswith("raw/")}
    assert any(rel.startswith("aer/") for rel in derived) and any(rel.startswith("sem/") for rel in derived)
    assert any(rel.startswith("prov/") for rel in derived)
    for rel, data in derived.items():
        for needle in (*SENTINEL_KEYS, *SENTINEL_VALUES, "env_vars"):
            assert needle.encode() not in data, (rel, needle)
    raw = [rel for rel, data in files.items() if rel.startswith("raw/objects/") and SENTINEL_VALUES[0].encode() in data]
    assert len(raw) == 1  # the configuration's raw bytes are stored unedited (invariant 3); only derived records are clean
    assert SENTINEL_VALUES[0] not in json.dumps(imp.report.register) and SENTINEL_VALUES[0] not in json.dumps(imp.report.counters)


def test_committed_configuration_fixtures_hold_no_env_vars():
    from agentprov.ingest import yamlsafe

    for path, data in support.tasks_files().items():
        assert b"env_vars" not in data, path
        assert isinstance(yamlsafe.safe_load(data), dict), path
    derived = [e for e in support.source_entries() if str(e["sample_file"]).startswith("derived/")]
    assert derived and all(e["modified"] is True and e["transformation"].startswith("drop_env_vars") for e in derived)
    assert all(set(e["derived_from"]) == {"sha256", "git_blob_sha1", "path", "revision"} for e in derived)


@pytest.mark.full_corpus
def test_derived_fixtures_equal_the_pinned_blobs_without_env_vars():
    from agentprov.ingest import yamlsafe

    tasks = STAGING / f"DecodingTrust-Agent-Platform-{support.TASKS_COMMIT}"
    if not tasks.is_dir():
        pytest.skip(f"the DTap tasks staging tree is absent ({tasks})")

    def without(value):
        if isinstance(value, dict):
            return {k: without(v) for k, v in value.items() if k != "env_vars"}
        if isinstance(value, list):
            return [without(v) for v in value]
        return value

    for e in (e for e in support.source_entries() if str(e["sample_file"]).startswith("derived/")):
        pinned = (tasks / e["derived_from"]["path"]).read_bytes()
        assert support.git_blob_sha1(pinned) == e["derived_from"]["git_blob_sha1"]
        derived = (support.FIXTURES / e["sample_file"]).read_bytes()
        assert without(yamlsafe.safe_load(pinned)) == yamlsafe.safe_load(derived)
