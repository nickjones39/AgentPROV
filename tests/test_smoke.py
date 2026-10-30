from agentprov import VERSIONS, __version__
from agentprov.cli.main import main


def test_versions_are_independent_axes():
    assert __version__ == "0.1.0"
    assert VERSIONS["aer"] == "aer/0.2"
    assert len(set(VERSIONS.values())) == len(VERSIONS)


def test_cli_info(capsys):
    assert main(["info"]) == 0
    assert "aer/0.2" in capsys.readouterr().out
