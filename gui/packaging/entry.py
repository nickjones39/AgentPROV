"""The frozen bundle's entry point (G5): the preview helper and the bundle's own ``agentprov`` run from the same
executable, chosen by the arguments before Qt is imported (a frozen app has no ``python -m``).

* ``--preview-helper HOME`` → ``agentprov_gui.preview.__main__.main`` (D-398);
* ``--cli ARGS`` → ``agentprov ARGS``, and the ``-I -m MODULE`` forms the core starts with ``sys.executable`` (a job's
  supervisor, the worker pool, the keychain helper, the Windows update helper), and ``--keychain-helper``
  (:func:`agentprov.cli.frozen.dispatch`, D-1130): the bundle carries the whole core, so it is also the command-line
  program, and a bundle update updates it too;
* anything else → the GUI (``agentprov_gui.app.main``).
"""

import multiprocessing
import sys

#: the first arguments of a CLI call (agentprov.cli.frozen.is_cli_call, repeated here so the GUI process never imports
#: the CLI, D-391; gui/tests/test_entry_point.py pins the two)
CLI_FIRST = frozenset({"--cli", "--keychain-helper", "-m", "-c", "-I", "-B", "-E", "-s", "-S", "-u"})


def run() -> int:
    multiprocessing.freeze_support()  # a spawned pool child (agentprov priors) runs its task and exits here
    if sys.argv[1:2] == ["--preview-helper"]:
        from agentprov_gui.preview.__main__ import main as preview

        return preview(sys.argv[2:])
    if sys.argv[1:2] and sys.argv[1] in CLI_FIRST:  # only then the core's dispatcher is imported (D-391)
        from agentprov.cli.frozen import dispatch

        code = dispatch(sys.argv[1:])
        return 0 if code is None else code
    from agentprov_gui.app import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(run())
