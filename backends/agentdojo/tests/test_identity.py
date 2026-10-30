import importlib.metadata
import importlib.util

import pytest

pytestmark = pytest.mark.backend_agentdojo


def test_agentdojo_version_pin():
    assert importlib.metadata.version("agentdojo") == "0.1.35"


def test_agentprov_not_importable():
    assert importlib.util.find_spec("agentprov") is None
