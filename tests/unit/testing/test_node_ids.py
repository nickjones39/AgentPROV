"""Short test ids (``tests/conftest.py``, :func:`short_param_id`).

pytest sets ``PYTEST_CURRENT_TEST`` to the node id at every phase of every test, and Windows refuses an environment
variable over 32,767 characters: the 0.2.0 Windows CI run errored at the setup and teardown of each test whose
parameter was a megabyte string or ``bytes(range(256)) * 9000`` (``ValueError: the environment variable is longer than
32767 characters``). The conftest abbreviates a long ``str`` / ``bytes`` parameter's id; the guard below keeps every
collected node id far under that limit, whatever a new parametrisation passes."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("agentprov_tests_conftest_node_ids", REPO / "tests" / "conftest.py")
assert _spec is not None and _spec.loader is not None
cf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cf)

#: The longest node id the suite may collect: the Windows limit is 32,767 characters for the whole variable (the node
#: id, its ``@<xdist group>`` and `` (teardown)``); ids this short are also still readable in a report.
MAX_NODE_ID = 1000


def test_a_short_value_keeps_pytest_s_own_id() -> None:
    for val in ("", "abc", "x" * cf.PARAM_ID_CHARS, b"\x00" * (cf.PARAM_ID_CHARS // 4), 7, None, 1.5, ("a" * 999,)):
        assert cf.short_param_id(val) is None


def test_a_long_value_gets_a_short_distinct_ascii_id_that_is_the_same_every_time() -> None:
    values = ["x" * 2**20, "x" * 2**20 + "\ud83d", "/home/alice/x " + "y" * 2**20, bytes(range(256)) * 9000,
              "\x00\né" * 100]
    ids = [cf.short_param_id(val) for val in values]
    assert all(i is not None and len(i) < 100 and i.isascii() and i.isprintable() for i in ids), ids
    assert len(set(ids)) == len(ids)
    assert ids == [cf.short_param_id(val) for val in values]
    assert ids[2] is not None and ids[2].startswith("/home/alice/x yyy")
    assert ids[3] is not None and ids[3].startswith(r"\x00\x01\x02") and "<2304000 bytes sha256:" in ids[3]


@pytest.mark.slow  # collects the whole suite once (about 15 s)
def test_every_collected_node_id_is_short() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "AGENTPROV_SHARD", "AGENTPROV_SHARDS")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # nothing written into the checkout
    done = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                          cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=900)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    ids = [line for line in done.stdout.splitlines() if "::" in line and not line[:1].isspace()]
    assert len(ids) > 1000
    long = sorted((len(nid), nid[:200]) for nid in ids if len(nid) > MAX_NODE_ID)
    assert not long, long
