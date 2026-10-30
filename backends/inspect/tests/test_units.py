"""Unit tests of the Inspect harness pieces that need no model: plan, identity, provisioning, catalogue."""

import json
import re
import types

import pytest

from agentprov_backend_inspect.benchmarks import agentharm, for_backend
from agentprov_backend_inspect.identity import task_files, task_files_sha256
from agentprov_backend_inspect.plan import PlanError, load_plan
from agentprov_backend_inspect.provision import DatasetError, env_dataset_dir, provision_session, verify_dataset

IDS = {"inspect_evals/agentharm/test_public": [f"{i}-{j}" for i in range(1, 45) for j in range(1, 5)],
       "inspect_evals/agentharm/val": ["a-1", "a-2"]}

PLAN = """
[plan]
format = "agentprov-run-plan/0.1"
backend = "inspect-agentharm"
[inspect]
task = "inspect_evals/agentharm"
params = { split = "test_public", agent = "default", n_irrelevant_tools = 0 }
samples = { limit = 4 }
limits = { message_limit = 20, token_limit = 60000, time_limit_s = 600 }
cell_size = 3
[agent]
model_requested = "scripted-fake"
endpoint = "scripted"
transport = "scripted"
script = "llm-script.json"
[judges.refusal_judge]
model_requested = "scripted-judge"
endpoint = "scripted"
transport = "scripted"
script = "judge-script.json"
[judges.semantic_judge]
model_requested = "scripted-judge"
endpoint = "scripted"
transport = "scripted"
script = "judge-script.json"
"""


def test_a_plan_expands_to_cells_in_dataset_order():
    plan = load_plan(PLAN, agentharm, "inspect-agentharm", IDS)
    assert [c.sample_ids for c in plan.cells] == [("1-1", "1-2", "1-3"), ("1-4",)]
    assert re.fullmatch(r"[0-9a-f]{64}", plan.plan_sha256) and plan.limits["token_limit"] == 60000
    assert set(plan.judges) == {"refusal_judge", "semantic_judge"}
    assert load_plan(PLAN, agentharm, "inspect-agentharm", IDS).plan_sha256 == plan.plan_sha256  # deterministic


@pytest.mark.parametrize(("old", "new", "message"), [
    ('samples = { limit = 4 }', 'samples = { limit = 4, ids = ["1-1"] }', "exactly one"),
    ('samples = { limit = 4 }', 'samples = { ids = ["9-9"] }', "not in"),
    ('agent = "default"', 'agent = "evil"', "one of"),
    ('n_irrelevant_tools = 0', 'behavior_ids = ["1-1"]', "unknown key"),
    ('limits = { message_limit = 20, token_limit = 60000, time_limit_s = 600 }', 'limits = { message_limit = 20 }', "missing"),
    ('task = "inspect_evals/agentharm"', 'task = "inspect_evals/other"', "unknown task"),
    ('backend = "inspect-agentharm"', 'backend = "agentdojo"', "is for backend"),
    ('[judges.semantic_judge]\nmodel_requested = "scripted-judge"\nendpoint = "scripted"\ntransport = "scripted"\nscript = "judge-script.json"', '', "missing"),
    ('transport = "scripted"\nscript = "llm-script.json"', 'transport = "http"\nbase_url = "https://x.example/v1"\napi_key_env = "K"', "same transport"),
])
def test_plans_are_refused(old, new, message):
    assert old in PLAN
    with pytest.raises(PlanError, match=message):
        load_plan(PLAN.replace(old, new, 1), agentharm, "inspect-agentharm", IDS)


def test_backend_ids():
    assert for_backend("inspect-agentharm") is agentharm
    for bad in ("agentharm", "inspect-nope", "inspect-"):
        with pytest.raises(ValueError):
            for_backend(bad)


def test_task_files_digest_is_content_only(tmp_path):
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "sub" / "b.json").write_text("{}")
    (tmp_path / "pkg" / "__pycache__").mkdir()
    (tmp_path / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    digest, n = task_files_sha256(tmp_path / "pkg")
    assert n == 2 and set(task_files(tmp_path / "pkg")) == {"a.py", "sub/b.json"}
    (tmp_path / "pkg" / "a.py").write_text("x = 2\n")  # a patched working copy is told apart
    assert task_files_sha256(tmp_path / "pkg")[0] != digest


def _fake_bench(files):
    import hashlib
    return types.SimpleNamespace(
        BENCHMARK="fake", DATASET_REVISION="0" * 40, CACHE_SUBDIR="fake_dataset/Fake",
        DATASET_FILES={rel: (hashlib.sha256(data).hexdigest(), len(data)) for rel, data in files.items()})


def test_provisioning_checks_every_digest(tmp_path):
    files = {"benchmark/a.json": b'{"behaviors": []}', "benchmark/b.json": b"[]"}
    bench = _fake_bench(files)
    root = env_dataset_dir(bench, str(tmp_path / "env"))
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    digests = provision_session(bench, tmp_path / "cache", prefix=str(tmp_path / "env"))
    assert set(digests) == set(files)
    assert (tmp_path / "cache" / "fake_dataset" / "Fake" / "benchmark" / "a.json").read_bytes() == files["benchmark/a.json"]
    (root / "benchmark/b.json").write_bytes(b"[1]")
    with pytest.raises(DatasetError, match="does not match"):
        verify_dataset(root, bench.DATASET_FILES)
    (root / "benchmark/b.json").unlink()
    with pytest.raises(DatasetError, match="lacks"):
        provision_session(bench, tmp_path / "cache2", prefix=str(tmp_path / "env"))


def test_the_catalogue_holds_names_and_counts_only(agentharm_prefix):
    pytest.importorskip("inspect_evals")
    from agentprov_backend_inspect.catalogue import CATALOGUE_FORMAT, build_catalogue

    doc = build_catalogue(agentharm, "inspect-agentharm", prefix=agentharm_prefix)
    assert doc["format"] == CATALOGUE_FORMAT and doc["inspect_ai"] == "0.3.263"
    tasks = {t["name"]: t for t in doc["tasks"]}
    assert set(tasks) == {"inspect_evals/agentharm", "inspect_evals/agentharm_benign"}
    for task in tasks.values():
        assert {s["name"]: s["samples"] for s in task["splits"]} == {"test_public": 176, "val": 32}
        assert all(0 < s["tool_definition_chars"]["mean"] <= s["tool_definition_chars"]["max"] for s in task["splits"])
        roles = [r["role"] for s in task["scorers"] for r in s["judge_roles"]]
        assert roles == ["refusal_judge", "semantic_judge"]
    # no behaviour text: the catalogue's strings are short labels, and no dataset prompt appears in it
    text = json.dumps(doc)
    root = env_dataset_dir(agentharm, agentharm_prefix)
    for rel in agentharm.DATASET_FILES:
        for b in json.loads((root / rel).read_bytes())["behaviors"]:
            assert b["prompt"][:40] not in text


def test_task_files_digest_matches_the_core_vector(tmp_path):
    """The same vector as tests/cli/test_backend_kinds.py: T0 (cli/live/envs.py) and the worker compute one value."""
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__pycache__").mkdir()
    (pkg / "a.py").write_bytes(b"x = 1\n")
    (pkg / "sub" / "b.json").write_bytes(b"{}")
    (pkg / "__pycache__" / "a.pyc").write_bytes(b"\0")
    assert task_files_sha256(pkg) == ("sha256:3d990265afa7131bef8f42050ddc4675dec8e787ee980e294286be1ca05fd5f6", 2)


def test_the_env_project_recipe_equals_the_descriptor_pins():
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "envs" / "agentharm" / "pyproject.toml"
    recipe = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["agentprov"]["dataset"]
    assert (recipe["repo"], recipe["revision"]) == (agentharm.DATASET_REPO, agentharm.DATASET_REVISION)
    assert {f["path"]: (f["sha256"], f["bytes"]) for f in recipe["files"]} == agentharm.DATASET_FILES


# ------------------------------------------------------------------------------------------------ D-740: the cell bound
def _core_bound() -> tuple[str, int, int, int]:
    """T0's ``_AGENTHARM_020`` (``src/agentprov/cli/live/envs.py``) and ``INSPECT_MAX_RETRIES``, read as text."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "src" / "agentprov" / "cli" / "live" / "envs.py").read_text()
    digest, per_agent_call, per_sample = re.search(
        r'_AGENTHARM_020: Final = InspectCallBound\("inspect_evals/agentharm",\s*"(sha256:[0-9a-f]{64})", (\d+), (\d+)\)',
        text).groups()
    (retries,) = re.findall(r"^INSPECT_MAX_RETRIES: Final = (\d+)$", text, re.MULTILINE)
    return digest, int(per_agent_call), int(per_sample), int(retries)


def _agentharm_dir():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("inspect_evals")
    assert spec is not None and spec.submodule_search_locations
    return Path(next(iter(spec.submodule_search_locations))) / "agentharm"


def test_the_core_call_bound_is_derived_from_this_task_code():
    """D-740: T0's per-task bound is valid for the pinned code only. Re-derive it here, where the code is installed:
    the digest, at most ``per_sample`` semantic-judge call sites per grading function (none in a loop, none reached
    indirectly), and one refusal-judge call per assistant message (``per_agent_call``)."""
    import ast

    digest, per_agent_call, per_sample, _retries = _core_bound()
    pkg = _agentharm_dir()
    assert task_files_sha256(pkg)[0] == digest
    loops = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

    def name(call: ast.Call) -> str:
        return getattr(call.func, "id", getattr(call.func, "attr", ""))

    for module in ("harmful_grading_functions.py", "benign_grading_functions.py"):
        tree = ast.parse((pkg / "benchmark" / module).read_text(encoding="utf-8"))
        functions = [f for f in tree.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
        judging = {f.name for f in functions if any(isinstance(c, ast.Call) and name(c) == "semantic_judge"
                                                    for c in ast.walk(f))}
        for fn in functions:
            calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)]
            assert sum(1 for c in calls if name(c) == "semantic_judge") <= per_sample, (module, fn.name)
            assert not any(name(c) in judging - {fn.name} for c in calls), (module, fn.name)  # no indirect judge call
            for loop in (n for n in ast.walk(fn) if isinstance(n, loops)):
                assert not any(isinstance(c, ast.Call) and name(c) == "semantic_judge" for c in ast.walk(loop))
    utils = ast.parse((pkg / "benchmark" / "grading_utils.py").read_text(encoding="utf-8"))
    (judge,) = [f for f in utils.body if isinstance(f, ast.AsyncFunctionDef) and f.name == "semantic_judge"]
    assert sum(1 for c in ast.walk(judge) if isinstance(c, ast.Call) and name(c) == "generate") == 1
    scorer = ast.parse((pkg / "scorer.py").read_text(encoding="utf-8"))
    (check,) = [f for c in scorer.body if isinstance(c, ast.ClassDef) for f in c.body
                if isinstance(f, ast.AsyncFunctionDef) and f.name == "check_refusal"]
    assert sum(1 for c in ast.walk(check) if isinstance(c, ast.Call) and name(c) == "generate") == 1
    refusal_calls = [c for c in ast.walk(scorer) if isinstance(c, ast.Call) and name(c) == "check_refusal"]
    assert len(refusal_calls) == per_agent_call == 1  # once per assistant message, in the loop over state.messages


def test_every_model_call_is_retried_at_most_the_core_bound(tmp_path):
    """D-740: Inspect's ``max_retries`` is the core's ``INSPECT_MAX_RETRIES`` and the SDK client's own retries are off."""
    from agentprov_backend_inspect.models import MAX_RETRIES, build_model
    from agentprov_backend_inspect.plan import ModelSpec
    from agentprov_backend_inspect.wire import WireObserver

    assert MAX_RETRIES == _core_bound()[3]
    (tmp_path / "s.json").write_text(json.dumps([{"reply": "text", "content": "hi"}]))
    model = build_model(ModelSpec(model="gpt-4o-mini", endpoint="openai", transport="scripted", script="s.json"),
                        WireObserver(None, role="agent", actor="agent", configured={}), session_dir=tmp_path,
                        environ={})
    assert model.config.max_retries == MAX_RETRIES and model.api.client.max_retries == 0


def test_every_build_is_a_new_model_with_its_own_client(tmp_path):
    """D-743: Inspect memoizes ``get_model`` on a key without the injected ``http_client``; a judge on the agent's model,
    or the next cell, must still get its own ``Model``, client and observer."""
    from agentprov_backend_inspect.models import build_model
    from agentprov_backend_inspect.plan import ModelSpec
    from agentprov_backend_inspect.wire import WireObserver

    (tmp_path / "s.json").write_text(json.dumps({"agent": [{"reply": "text", "content": "hi"}],
                                                 "judges": {"refusal_judge": [{"reply": "text", "content": "No"}]}}))
    spec = ModelSpec(model="gpt-4o-mini", endpoint="openai", transport="scripted", script="s.json")
    models = [build_model(spec, WireObserver(None, role=role, actor=actor, configured={}), session_dir=tmp_path,
                          environ={}, role=judge)
              for role, actor, judge in (("agent", "agent", "agent"), ("auxiliary", "judge0", "refusal_judge"),
                                         ("agent", "agent", "agent"))]
    assert len({id(m) for m in models}) == 3 and len({id(m.api.client) for m in models}) == 3


def test_the_inspect_worker_overrides_every_shared_op():
    """D-742: a shared op the Inspect worker inherits would run AgentDojo-family code (the shared probe imports
    ``agentdojo``, absent from an Inspect environment); every op is the Inspect worker's own."""
    from agentprov_backend.worker import Worker

    from agentprov_backend_inspect.worker import InspectWorker

    shared = {name for name in vars(Worker) if name.startswith("op_")}
    assert shared and all(name in vars(InspectWorker) for name in shared), sorted(shared - set(vars(InspectWorker)))
