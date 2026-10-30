import subprocess
import sys


def test_package_imports_without_agentprov():
    code = (
        "import sys, agentprov_backend, agentprov_backend.testing\n"
        "assert agentprov_backend.__version__ == '0.1.0'\n"
        "bad = [m for m in sys.modules if m == 'agentprov' or m.startswith('agentprov.') or m == 'agentdojo']\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-I", "-B", "-c", code], check=True)
