"""The ``[withhold]`` table of ``redcode-exec-qwencode`` (D-578 amendment of 2026-10-21; D-602's rule).

The deposit's supplementary zip, the profile's ``supp`` context pin, holds a real-format Hugging Face access token in an
unselected member (``environment/<seg>/.bash_history``; found by the bug pass's D-602 for the same zip pinned by
``redcode-exec-openhands``). The rule is D-602's: a plain pattern at object scope, so the decoded scan of sealing
(D-450/D-452) withholds the zip container and no execution (the default ``executions`` scope would cascade to every
execution citing a member of the container).

An archive context now imports (D-530), records its verification and seals as corpus/0.2 (D-221; pre-round review
PR-1): the same route is sealed end to end, with withholding and ``verify --level chain --release``, by
``tests/adapters/agentops/test_archive_context_seal_d221.py``. This file checks the policy as sealing reads it and runs
the same decoded scan over a synthetic zip of the deposit's shape. The token is assembled at run time and never written to a file.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Iterator

import qwencode_support as support

from agentprov.corpus.withhold import policy_of_profile, scan_chunks
from agentprov.corpus.withhold_scan import scan_archives

PROFILE = support.REPO / "src" / "agentprov" / "adapters" / "qwencode" / "profiles" / "redcode-exec-qwencode.profile.toml"
TOKEN = "hf" + "_" + "TESTSENTINEL" + "0123456789" + "abcdefghijkl"  # hf_ + 34, the shape of a real access token


def _policy():
    data = PROFILE.read_bytes()
    policy = policy_of_profile(data, profile_id="redcode-exec-qwencode", profile_version=2)
    assert policy is not None, "redcode-exec-qwencode declares no [withhold] table"
    return policy


def _supp(*, token: bool) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("results/Qwen/qwen3coder/S1/case_1/conversation_log/index.json", b'{"score": 3}')
        zf.writestr("OH_evaluation/execution_rules.md", b"# rules\n")
        zf.writestr("environment/seg/.bash_history", f"ls\nexport HF_TOKEN={TOKEN if token else 'unset'}\n".encode())
        zf.writestr("README.md", b"supplementary material\n")
    return buf.getvalue()


def _scan(data: bytes):
    sha = hashlib.sha256(data).hexdigest()

    def stream(_label: str) -> Iterator[bytes]:
        yield data

    return sha, scan_archives({sha: "agent-execution-decisions-supp.zip"}, stream, _policy().rules)


def test_the_policy_is_d602s_rule_at_object_scope():
    policy = _policy()
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [("hf-token-shape", "pattern", "object", "secret")]
    assert policy.scan_rules == ("huggingface-access-token",)  # the D-600 release-scan rule, which reads members too


def test_the_rule_matches_the_token_shape_only():
    rules = _policy().rules
    assert scan_chunks([f"export HF_TOKEN={TOKEN}\n".encode()], rules) == {"hf-token-shape"}
    assert scan_chunks([b"hf_short", b" hf_" + b"x" * 33], rules) == frozenset()


def test_the_decoded_scan_withholds_the_supplementary_zip_by_its_unselected_member():
    sha, scan = _scan(_supp(token=True))
    assert scan.hits == {sha: frozenset({"hf-token-shape"})} and scan.unscanned == {}
    assert TOKEN.encode() not in _supp(token=True)  # deflated: only the decoded scan can see it


def test_a_zip_without_the_token_is_not_withheld():
    _sha, scan = _scan(_supp(token=False))
    assert scan.hits == {} and scan.unscanned == {}
