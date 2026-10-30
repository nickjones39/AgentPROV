# Bug-pass reproductions (evidence)

One folder per finding (`BF-nn_<reviewer id>`), as the verifier ran it against origin/main `0949cb18`. The files are
stored as `.py.txt` so that ruff, mypy and pytest do not collect them; copy one out of the tree, drop the `.txt` and run
it with `uv run python tools/suite_queue.py --targeted -- pytest <copy>/test_repro.py -q -p no:cacheprovider`. Each one
fails on the code it was written against; fixed findings carry a proper regression test under `tests/` instead.
`<scratch>` stands for the verifier's scratch directory. BF-21 (B-4) loads `src/agentprov/adapters/inspect/redact.py`
from the `regen-items-2-12` branch (`git show regen-items-2-12:src/agentprov/adapters/inspect/redact.py`).
All inputs are synthetic; none reads `tests/fixtures/`.
