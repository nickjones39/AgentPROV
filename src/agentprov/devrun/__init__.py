"""Dev runs (D-705; GUI design §19; D-544): a few samples of every chosen corpus part imported into fresh scratch
corpora under ``$AGENTPROV_HOME/dev-runs/<UTC stamp>/`` and checked, as one batch (D-704) of three steps per part.

* :mod:`.plan`: the settings, the part plan, the per-part summary and the run listing (read-only; the GUI imports it);
* ``agentprov devrun plan|start|list|prune`` (``cli/devrun.py``): everything that writes.

Outside every stage closure (class 0): a dev run writes only scratch corpora, never a stored one, never ``--release``.
"""
