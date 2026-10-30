"""Detached jobs and batches (D-704; GUI design §4, D-392; moved from the GUI so that ``agentprov jobs`` and
``agentprov batch`` are the one implementation the GUI calls).

* :mod:`.record` and :mod:`.follow`: read-only (job records, progress and log files); the GUI imports them (D-391);
* :mod:`.tiers`: the R0/R1/R2 rules of a job's argv (pure);
* :mod:`.manager` and :mod:`.supervisor`: spawn, stop, kill, drain, resume and prune (the CLI only);
* :mod:`.batch`: ordered job lists, driven by one ``agentprov batch run`` job each.

Outside every stage closure (class 0): nothing here feeds AER, SEM, PROV or a corpus.
"""
