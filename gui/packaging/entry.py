"""The frozen bundle's entry point (G5): the preview helper runs from the same executable, chosen by a flag before Qt
is imported (a frozen app has no ``python -m``). Keys need no helper here: ``agentprov keys`` and ``run --keychain`` of
the configured checkout's CLI run the keychain helper (D-702).

* ``--preview-helper HOME`` → ``agentprov_gui.preview.__main__.main`` (D-398);
* anything else → the GUI (``agentprov_gui.app.main``).
"""

import sys


def run() -> int:
    if sys.argv[1:2] == ["--preview-helper"]:
        from agentprov_gui.preview.__main__ import main as preview

        return preview(sys.argv[2:])
    from agentprov_gui.app import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(run())
