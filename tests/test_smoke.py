import tomllib
from pathlib import Path

from agentprov import VERSIONS, __version__
from agentprov.cli.main import main

_PYPROJECT_VERSION = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_versions_are_independent_axes():
    assert __version__ == _PYPROJECT_VERSION
    assert VERSIONS["aer"] == "aer/0.2"
    assert len(set(VERSIONS.values())) == len(VERSIONS)


def test_cli_info(capsys):
    assert main(["info"]) == 0
    assert "aer/0.2" in capsys.readouterr().out
