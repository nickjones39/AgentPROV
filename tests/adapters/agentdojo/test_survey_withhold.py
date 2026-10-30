"""D-771: the ``survey-runs@3`` ``[withhold]`` rule (post-check PC-ast-survey-agentdojo-13; user decision 2026-10-23,
option (a); CC-11 class, as D-456; D-604 object scope).

Five of the survey's eight console logs (context artefacts, never executions) hold traceback and warning paths under one
named third-party account's home directory. The rule withholds such an object at seal, digest kept; the executions stay
released. The unit tests use made-up account names only. The census test (marker ``full_corpus``) scans the pinned
snapshot in a local clone (``$AGENTPROV_SURVEY_CLONE``) and compares file labels and digests, never the path.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from agentprov.adapters.profiles import load_profile
from agentprov.corpus.withhold import policy_of_profile, scan_chunks
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
PROFILES = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles"
#: A made-up account name, assembled at run time.
ACCOUNT = "zq7" + "synthx"
#: The pinned snapshot's console logs that hold the account path (labels; sha256 and git blob id), census 2026-10-23.
WITHHELD = {
    "agentdojo/results/runs_gpt-oss_120b/console_attack_restart.log":
        ("2b736e23f89553e7f57853060dd468ad7bcd1b270f04a887539282af2c0eb4dc", "220a2be271cb7d7644919f7925c58e51be841dac"),
    "agentdojo/results/runs_gpt-oss_120b/console_attack.log":
        ("827662f31d682b095cbf0eb06c8d185981bf916acb9cf64a67493d9c8937f1cc", "7230661de9851d612d4f10f5ddc3a70171870a2e"),
    "agentdojo/results/runs_qwen3-coder_30b/console_attack.log":
        ("979bdc64963c3c3e7eb5ce3dff28887c3e96ec6f82e5fd8c11dbfb663a7121d4", "0d1e8237c8d9d686aef3e2c5d75e5ac34dc035e5"),
    "agentdojo/results/runs_gpt-oss_120b/console_attack_v2.log":
        ("bc1bc47b0262c2c16ff06647becf0dbd83b3f3c2ce9197ec72594c5713bdd6a4", "1087f096a9088157ee695e9aa5074275617c2455"),
    "agentdojo/results/runs_qwen3_14b/console_attack.log":
        ("d269cdc4106e121b6c15f16f959ff421b7e27e34b849a9d5f7ef86b35ccb9033", "0f5809fc80e3a3d57ef68fc8c8842395d0f27ab1"),
}
CLONE_ENV = "AGENTPROV_SURVEY_CLONE"
DEFAULT_CLONE = Path.home() / "Desktop/PhD/Labs/AgentPROV-upstream/agent-security-tools-survey"


def _policy(version: int = 3):
    data = (PROFILES / ("survey-runs.profile.toml" if version == 3 else f"archive/survey-runs.profile.v{version}.toml"))
    return policy_of_profile(data.read_bytes(), profile_id="survey-runs", profile_version=version)


def test_version_3_declares_one_object_scope_personal_data_rule():
    assert load_profile("survey-runs").version == 3
    policy = _policy()
    assert policy is not None
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("console-home-account-path", "pattern", "object", "personal_data")]


def test_the_rule_hits_the_traceback_and_warning_shapes_of_the_console_logs():
    rules = _policy().rules
    home = ("/ho" + "me/") + ACCOUNT
    assert scan_chunks([f'  File "{home}/codesafe/agentdojo/src/run.py", line 12, in main'.encode()], rules)
    assert scan_chunks([f"{home}/codesafe/.venv/lib/python3.12/site-packages/x.py:7: UserWarning: y".encode()], rules)


def test_the_rule_leaves_benchmark_content_and_placeholders_alone():
    rules = _policy().rules
    assert not scan_chunks([b'"content": "saved to /home/user/notes.txt"'], rules)  # a home path, not the run's project
    assert not scan_chunks([("/ho" + "me/").encode() + b"<account>/codesafe/x.py"], rules)  # a placeholder
    assert not scan_chunks([("/Us" + "ers/" + ACCOUNT + "/codesafe/x.py").encode()], rules)  # not a Linux home


def test_version_2_has_no_policy_so_a_corpus_recorded_under_it_must_never_be_sealed():
    """ast-survey-agentdojo-rg1 recorded survey-runs@2: it is kept as evidence and never sealed or deposited."""
    assert _policy(2) is None
    assert load_profile("survey-runs", 2).sha256 == (
        "5bcaf980f0893a91d5a9820bbc4a46a99e93fe7ae9a3c17775edd44d10c47b5f")  # as the rg1 corpus records it


def _clone() -> Path | None:
    root = Path(os.environ[CLONE_ENV]) if os.environ.get(CLONE_ENV) else DEFAULT_CLONE
    return root if (root / "agentdojo" / "results").is_dir() else None


@pytest.mark.full_corpus
def test_census_at_the_pin_withholds_exactly_the_five_console_logs_and_no_run_log():
    root = _clone()
    if root is None:
        pytest.skip(f"the survey clone at the pinned commit is absent (${CLONE_ENV})")
    rules = _policy().rules
    hit: dict[str, tuple[str, str]] = {}
    scanned = logs = 0
    for path in sorted((root / "agentdojo").rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        scanned += 1
        logs += path.suffix == ".json"
        if scan_chunks([data], rules):
            hit[path.relative_to(root).as_posix()] = (hashlib.sha256(data).hexdigest(), golden.git_blob_sha1(data))
    assert hit == WITHHELD
    assert logs >= 3243 and scanned >= 3243 + 8
