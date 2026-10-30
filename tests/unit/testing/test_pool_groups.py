"""The host-sized ``pools`` xdist groups of ``tests/conftest.py`` (D-401): k = max(2, CPUs // 6) groups, balanced by
measured seconds, so at most k host-default worker pools run at once."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("agentprov_tests_conftest_view", REPO / "tests" / "conftest.py")
assert _spec is not None and _spec.loader is not None
cf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cf)


def test_every_listed_pool_file_exists_and_is_not_also_in_the_serial_group() -> None:
    serial = {prefix for prefix, _ in cf.XDIST_GROUPS}
    for path in cf.POOL_FILES:
        assert (REPO / path).is_file(), path
        assert path not in serial, path


def test_the_group_count_follows_the_host_and_the_override() -> None:
    assert cf.pool_group_count({}, 12) == 2 and cf.pool_group_count({}, 8) == 2
    assert cf.pool_group_count({}, 24) == 4 and cf.pool_group_count({}, 32) == 5
    assert cf.pool_group_count({"AGENTPROV_TEST_POOL_GROUPS": "3"}, 32) == 3


def test_the_assignment_is_deterministic_complete_and_balanced() -> None:
    for k in (1, 2, 3, 5, 8):
        groups = cf.assign_pool_groups(cf.POOL_FILES, k)
        assert groups == cf.assign_pool_groups(dict(reversed(list(cf.POOL_FILES.items()))), k)
        assert set(groups) == set(cf.POOL_FILES) and set(groups.values()) <= {f"pools-{i + 1}" for i in range(k)}
        loads: dict[str, float] = {}
        for path, group in groups.items():
            loads[group] = loads.get(group, 0.0) + cf.POOL_FILES[path]
        # longest-first greedy: no group exceeds the ideal share by more than the largest single file
        assert max(loads.values()) <= sum(cf.POOL_FILES.values()) / k + max(cf.POOL_FILES.values())
