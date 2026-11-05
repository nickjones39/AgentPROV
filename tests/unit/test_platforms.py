"""The platform-limit table (D-1064): which features are unavailable where, the message, and the host test.

The CLI refusals are tested with their commands (``tests/cli``); the job queue's in ``tests/jobs``. Here: the table
itself, the architecture of a Windows host (the interpreter's, not the emulating host's), and the claim behind the
backend-build entry, read from the backends' locks.
"""

from __future__ import annotations

import platform
import re
import sysconfig
import tomllib
from pathlib import Path

import pytest

from agentprov import platforms
from agentprov.platforms import LIMITS, PlatformUnsupported, refuse, unavailable, unavailable_here

REPO = Path(__file__).resolve().parents[2]
FEATURES = ("live_runs", "backend_build", "sandbox_exec", "job_queue")


def _host(monkeypatch: pytest.MonkeyPatch, system: str, machine: str, plat: str) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setattr(sysconfig, "get_platform", lambda: plat)


def test_the_table_lists_each_feature_once() -> None:
    assert tuple(limit.feature for limit in LIMITS) == FEATURES


@pytest.mark.parametrize(("system", "machine", "plat", "expected"), [
    ("Windows", "AMD64", "win-amd64", ("Windows", "x86_64")),
    ("Windows", "ARM64", "win-arm64", ("Windows", "arm64")),
    ("Windows", "ARM64", "win-amd64", ("Windows", "x86_64")),  # an x64 Python under emulation on ARM64 (D-867)
    ("Linux", "aarch64", "linux-aarch64", ("Linux", "arm64")),
    ("Linux", "x86_64", "linux-x86_64", ("Linux", "x86_64")),
    ("Darwin", "arm64", "macosx-15.0-arm64", ("Darwin", "arm64")),
])
def test_host_names_the_interpreter_architecture(monkeypatch, system, machine, plat, expected) -> None:
    _host(monkeypatch, system, machine, plat)
    assert platforms.host() == expected


@pytest.mark.parametrize(("system", "machine"), [("Darwin", "arm64"), ("Darwin", "x86_64"), ("Linux", "x86_64"),
                                                 ("Linux", "aarch64")])
def test_macos_and_linux_keep_live_runs_backend_builds_and_the_queue(system, machine) -> None:
    for feature in ("live_runs", "backend_build", "job_queue"):
        assert unavailable(feature, system, machine) is None, feature
    assert (unavailable("sandbox_exec", system, machine) is None) == (system == "Darwin")


def test_windows_x86_64() -> None:
    live = unavailable("live_runs", "Windows", "AMD64")
    assert live is not None and live.where.label == "Windows x86_64"
    assert live.message() == (
        "Live runs (agentprov run) are available on macOS and Linux. On Windows x86_64 they are not available yet: the "
        "backend environment builds, but the backend worker exits at start-up for a reason not yet diagnosed "
        "(AgentDojo itself is tested upstream on Linux only). See the user guide, chapter 7, Live runs, section "
        "Platforms (docs/user-guide/07-live-runs.md#platforms).")
    assert unavailable("backend_build", "Windows", "AMD64") is None  # it builds there; runs are what is refused
    assert unavailable("job_queue", "Windows", "AMD64") is not None
    assert unavailable("sandbox_exec", "Windows", "AMD64") is not None


def test_windows_arm64() -> None:
    live = unavailable("live_runs", "Windows", "ARM64")
    assert live is not None and live.where.label == "Windows ARM64"
    assert "cryptography 50.0.2 and cachebox 5.2.3 publish no Windows ARM64 wheels" in live.message()
    build = unavailable("backend_build", "Windows", "aarch64", subject="agentdojo")
    assert build is not None
    assert build.message() == (
        "Building the agentdojo, autodojo and agentdyn backend environments is available on macOS and Linux. On "
        "Windows ARM64 it is not available yet: its pinned dependencies cryptography 50.0.2 and cachebox 5.2.3 publish "
        "no Windows ARM64 wheels, and backends install from wheels only. See the user guide, chapter 7, Live runs, "
        "section Platforms (docs/user-guide/07-live-runs.md#platforms).")
    assert [hit.limit.feature for hit in unavailable_here("Windows", "ARM64")] == list(FEATURES)


def test_another_windows_architecture_still_has_no_live_runs() -> None:
    hit = unavailable("live_runs", "Windows", "x86")
    assert hit is not None and hit.where.label == "Windows"


def test_the_backend_build_limit_names_its_backends_only() -> None:
    assert unavailable("backend_build", "Windows", "ARM64", subject="inspect-agentharm") is None
    for backend in platforms.AGENTDOJO_FAMILY:
        assert unavailable("backend_build", "Windows", "ARM64", subject=backend) is not None


def test_every_message_says_where_the_feature_works() -> None:
    for limit in LIMITS:
        for where in limit.where:
            hit = unavailable(limit.feature, where.system, where.machines[0] if where.machines else "x86_64")
            assert hit is not None
            text = hit.message()
            works = "available on macOS only." if limit.feature == "sandbox_exec" else "available on macOS and Linux."
            assert works in text and f"On {where.label} " in text and "See the user guide" in text, text
            assert hit.to_json()["message"] == text and hit.to_json()["guide"].startswith("docs/user-guide/")


def test_refuse_raises_the_typed_refusal_on_this_host(monkeypatch) -> None:
    _host(monkeypatch, "Windows", "ARM64", "win-arm64")
    with pytest.raises(PlatformUnsupported) as exc:
        refuse("live_runs")
    assert exc.value.code == "platform.unsupported" and exc.value.exit_code == 4
    refuse("backend_build", subject="inspect-agentharm")  # not refused
    _host(monkeypatch, "Linux", "x86_64", "linux-x86_64")
    refuse("live_runs")


def _lock_packages(project: Path) -> dict[str, dict]:
    lock = tomllib.loads((project / "uv.lock").read_text(encoding="utf-8"))
    return {p["name"]: p for p in lock.get("package", [])}


def test_the_agentdojo_family_locks_pin_the_two_packages_without_windows_arm64_wheels() -> None:
    """The backend-build entry's reason, checked against the locks: the three AgentDojo-family backends pin
    cryptography 50.0.2 and cachebox 5.2.3, neither lists a win_arm64 wheel or an sdist the build would use (the
    backends build from wheels only), and the Inspect backend pins neither (so its build is not refused)."""
    for backend in platforms.AGENTDOJO_FAMILY:
        packages = _lock_packages(REPO / "backends" / backend)
        for name, version in (("cryptography", "50.0.2"), ("cachebox", "5.2.3")):
            assert packages[name]["version"] == version, (backend, name)
            wheels = [w["url"] for w in packages[name].get("wheels", [])]
            assert wheels and not any(re.search(r"win_arm64\.whl$", url) for url in wheels), (backend, name)
    inspect = _lock_packages(REPO / "backends" / "inspect" / "envs" / "agentharm")
    assert "cryptography" not in inspect and "cachebox" not in inspect
