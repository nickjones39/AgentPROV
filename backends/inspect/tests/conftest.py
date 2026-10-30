import os
import shutil
from pathlib import Path

import pytest

from agentprov_backend_inspect.benchmarks import agentharm
from agentprov_backend_inspect.provision import env_dataset_dir


@pytest.fixture
def agentharm_prefix(tmp_path):
    """A fake environment prefix holding the pinned AgentHarm dataset, copied from AgentPROV's fetch cache (skipped
    when the cache does not hold the snapshot: the dataset is never committed, D-668)."""
    home = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
    cache = home / "cache" / "hf" / agentharm.DATASET_REPO / agentharm.DATASET_REVISION
    if not all((cache / rel).is_file() for rel in agentharm.DATASET_FILES):
        pytest.skip("the AgentHarm snapshot is not in the fetch cache")
    dest = env_dataset_dir(agentharm, str(tmp_path))
    for rel in agentharm.DATASET_FILES:
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache / rel, dest / rel)
    return str(tmp_path)
