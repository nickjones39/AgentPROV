"""The ``adprov-v1`` registry entry, profile and job wiring (docs/architecture D.3, D.4, D.2.9; I.0.2; DoD Q.2)."""

from __future__ import annotations

import subprocess
import sys

from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.adapters.registry import MAPPERS, READERS, REGISTRY, get_source
from agentprov.adapters.runner import resolve_factory
from agentprov.errors import ProfileError
from agentprov.io.workers import JOB_KINDS


def test_statuses_are_the_gated_values_not_the_targets():
    source = get_source("adprov-v1")
    parts = {c.part: c for c in source.capabilities}
    release, converted = parts["release"], parts["converted-legacy"]
    assert release.import_status in ("partial", "supported") and release.target_import_status == "supported" and release.caveat
    if release.import_status == "supported":  # D.3.2: only with the full pinned snapshot imported and recorded (HON-10)
        from pathlib import Path

        assert (Path(__file__).resolve().parents[3] / "docs" / "reports" / "adprov" / "import-cli-release.json").is_file()
    else:
        assert "full snapshot not yet imported" in release.caveat
    assert converted.role == "compat_oracle" and converted.import_status is None and converted.owner == "agentdojo"
    assert "adprov-v1" in [s.source_id for s in REGISTRY]  # further sources join with their importers (phase 6 onwards)


def test_factories_are_lazy_agentprov_strings_that_resolve():
    for path in (*READERS.values(), *MAPPERS.values()):
        assert path.startswith("agentprov.adapters.")
        assert callable(resolve_factory(path))


def test_importing_the_registry_imports_no_family():
    code = "import sys, agentprov.adapters.registry; print(any(m.startswith('agentprov.adapters.adprov') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"


def test_the_map_job_kind_is_registered():
    assert JOB_KINDS["map"] == "agentprov.adapters.runner:job_map"


def test_profile_is_package_data_with_a_digest_and_no_status():
    profile = load_profile("adprov-v1")
    assert profile.version == 2 and len(profile.sha256) == 64 and profile.family == "adprov"  # D-31
    assert profile.data["import"]["dialect"] == "adprov.transcript_v1"
    assert "status" not in profile.data
    for bad in (b'[profile]\nid="x"\n[status]\na=1\n', b"[profile]\nid = 1\n", b"not toml ["):
        try:
            parse_profile(bad)
        except ProfileError:
            continue
        raise AssertionError("a malformed profile was accepted")
