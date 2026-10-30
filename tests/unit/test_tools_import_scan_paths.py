"""The baseline-parity path helpers of ``tools/agentdojo/import_scan.py`` never yield a path that leaves the tree
(escaping audit F-14)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools" / "agentdojo"


@pytest.fixture(scope="module")
def scan():
    sys.path.insert(0, str(TOOLS))
    try:
        import import_scan

        yield import_scan
    finally:
        sys.path.remove(str(TOOLS))


def test_ordinary_names_map_as_in_the_baseline(scan) -> None:
    assert scan.pipeline_folder("gpt-4o-2024-05-13") == "gpt-4o-2024-05-13"
    assert scan.pipeline_folder("a b/c") == "a_b_c"
    assert scan.pipeline_folder("v1.2..x") == "v1.2..x"  # dots inside a name are kept
    assert scan.output_relpath("p", "banking", "user_task_0", None, None) == "p/prov/benign/banking_user_task_0_benign"
    assert (
        scan.output_relpath("p", "banking", "user_task_0", "important_instructions", "injection_task_1")
        == "p/prov/important_instructions/banking_user_task_0_x_injectiontask1_injection"
    )


@pytest.mark.parametrize("name", ["..", ".", ""])
def test_pipeline_folder_refuses_dot_components(scan, name: str) -> None:
    with pytest.raises(ValueError):
        scan.pipeline_folder(name)
    with pytest.raises(ValueError):
        scan.output_relpath(name, "banking", "user_task_0", None, None)


@pytest.mark.parametrize("attack", ["..", "/etc", "../x", "a/../../b", "/abs/path"])
def test_output_relpath_refuses_traversal_and_absolute_attack_names(scan, attack: str) -> None:
    with pytest.raises(ValueError):
        scan.output_relpath("p", "banking", "user_task_0", attack, "injection_task_1")
