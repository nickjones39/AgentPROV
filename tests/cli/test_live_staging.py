"""T0's literal-value secret scan of a staged session (G.6.4, R-51): which values it holds (UC-22) and which bytes it
reads (AU-LIVE-4). Fake keys only."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from agentprov_capture.redact import Redactor, Secret

from agentprov.cli.live.staging import holds_secret, scan_secrets, t0_secrets
from agentprov.ingest.limits import IngestLimits

PASSED = "sk-or-passed-to-t2-0123456789"
PARENT_KEY = "sk-parent-held-openai-0123456789"


def test_t0_holds_the_passed_keys_the_key_source_and_the_registry_key_variables_only():
    environ = {"OPENAI_API_VERSION": "2024-06-01-preview", "HF_HUB_CACHE": "/Users/someone/.cache/huggingface",
               "OPENAI_API_KEY": PARENT_KEY, "PATH": "/usr/bin:/bin"}
    values = {"OPENROUTER_API_KEY": PASSED, "DEEPSEEK_API_KEY": "sk-dotenv-unused-0123456789",
              "OPENROUTER_MODEL": "vendor/some-model-name"}
    redactor = Redactor(t0_secrets(environ, values, {"OPENROUTER_API_KEY": PASSED}))
    for held in (PASSED, PARENT_KEY, "sk-dotenv-unused-0123456789"):
        assert redactor.contains_secret(f"x {held} y".encode())
    for public in ("2024-06-01-preview", "/Users/someone/.cache/huggingface", "vendor/some-model-name"):
        assert not redactor.contains_secret(f"x {public} y".encode()), public


def test_a_scripted_run_holds_only_the_registry_key_variables_of_its_environment():
    assert t0_secrets({"OPENAI_API_VERSION": "2024-06-01-preview"}, {}, {}) == []


# ------------------------------------------------------------------------------------------------ AU-LIVE-4


KEY = "sk-test-FAKEFAKEFAKEFAKEFAKE1234567890"
REDACTOR = Redactor([Secret("OPENAI_API_KEY", KEY, "file_value")])


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _session(tmp_path: Path, files: dict[str, bytes]) -> Path:
    d = tmp_path / "sess"
    for label, data in files.items():
        p = d / label
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return d


def test_a_key_inside_a_deflated_eval_member_quarantines(tmp_path: Path):
    sample = b'{"error": {"message": "request failed", "traceback": "... api_key=' + KEY.encode() + b' ..."}}'
    data = _zip({"header.json": b'{"status": "error"}', "samples/1_epoch_1.json": sample})
    assert KEY.encode() not in data  # deflated: the bytes as stored never show it
    d = _session(tmp_path, {"raw/inspect/x.eval": data, "raw/inspect/clean.eval": _zip({"a.json": b"{}"})})
    assert scan_secrets(d, REDACTOR) == ["raw/inspect/x.eval"]
    assert holds_secret(data, REDACTOR) and not holds_secret(_zip({"a.json": b"{}"}), REDACTOR)


def test_a_zip_that_cannot_be_scanned_whole_within_the_limits_quarantines(tmp_path: Path):
    big = _zip({"samples/1.json": b"x" * 4096})
    small = IngestLimits().replace(max_member_bytes=1024)
    assert holds_secret(big, REDACTOR, small)  # a member over the limit is never read, so it is not known clean
    corrupt = b"PK\x03\x04" + b"\x00" * 64
    assert holds_secret(corrupt, REDACTOR)
    d = _session(tmp_path, {"raw/inspect/x.eval": big})
    assert scan_secrets(d, REDACTOR, limits=small) == ["raw/inspect/x.eval"]
    assert scan_secrets(d, REDACTOR) == []  # within the default limits it is read and clean
