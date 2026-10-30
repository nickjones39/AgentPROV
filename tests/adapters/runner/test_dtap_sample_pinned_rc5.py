"""RC-5 (pre-round re-check of PR-8; D-529 x D-530 item 6): on a reader without multi-execution files (DTap), an LFS
pointer passes a sample exactly when its pinned object does.

PR-8 let every pointer pass the sample. On DTap a pointer whose object was sampled out then disposed its sibling judge
file as the auxiliary of a file that is not an execution: a register row the full import does not have. The sampled
import's register must be a subset of the full import's, and the pointer's own row appears iff its object is sampled.
Inputs: the committed DTap fixtures (loaded, never printed). No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentprov.adapters.runner.importer import ImportSample

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dtap"))
import dtap_support as support  # noqa: E402
from test_import import _object  # noqa: E402

KEEP = ("F21", "F01", "F03", "F06")


def _rows(imp: support.Imported) -> set[tuple[str, str, str]]:
    return {(r["code"], str(sorted(r["subject"].items())), str(r.get("detail"))) for r in imp.register}


#: draws that sample the pinned object in ("first") and out (seeds "b" and "c" over these fixtures)
@pytest.mark.parametrize(("n", "mode", "seed"), [(1, "first", None), (2, "random", "b"), (3, "random", "c")])
def test_a_pointer_passes_a_sample_exactly_with_its_pinned_object(tmp_path, n, mode, seed):
    dirs = [support.F[f].rsplit("/", 1)[0] for f in KEEP]
    runs = {k: v for k, v in support.runs_files().items() if any(k.startswith(d) for d in dirs)}
    full = support.run_import(tmp_path / "full", runs, support.tasks_files(), objects=[_object(tmp_path)], name="full")
    sampled = support.run_import(tmp_path / "s", runs, support.tasks_files(), objects=[_object(tmp_path)], name="s",
                                 sample=ImportSample(n, mode, seed))
    assert len(sampled.rows) == n
    assert _rows(sampled) <= _rows(full)  # no row a full import does not write
    pointer = [r for r in sampled.register if r["subject"].get("path") == support.F["F21"]]
    object_sampled = support.F["F21"] in sampled.headers()
    assert bool(pointer) == object_sampled
    assert object_sampled == (mode == "first")  # the draws keep covering both cases
