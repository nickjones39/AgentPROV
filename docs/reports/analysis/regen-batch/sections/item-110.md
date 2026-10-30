## Item 110: phase 10p profile versions 3 and 4 (D-349 and its addendum; branch `phase-10p-redact`; HELD for the round, class 1)

`controlarena-persistent` version 3 replaces D-345's 36 `select.redaction_pending` holds with one D-182 redaction rule
(`[[family.inspect.redact]]`, scope `harness_text`, structural pattern `/Users/<segment>`, replacement
`/Users/account-{span12}`; user-approved 2026-10-14). Version 2 ships under `adapters/inspect/profiles/archive/`
(D-31). **Downstream:** no stored corpus uses the profile, but the profile and the archive file sit in
`adapters/inspect/`, so the inspect adapter code digest moves for every stored inspect-family corpus (the AgentHarm,
survey and whistlebench corpora): their `aer` stage `fn_digest` at the next re-map, no AER byte. Evidence:
`docs/reports/phase10p/README.md` §10 (trial t3, the account-segment scan, recompute, the seal).

Version 4 (2026-10-22, D-349 addendum; user decision under D-604) adds one object-scope `[[withhold.rules]]` entry,
`users-account-path` (reason `personal_data`), and archives version 3, which phase10p t3 records (D-31). It also
changes the redaction label to the D-604 form `/Users/acct-{span12}`. **Downstream:** the same inspect adapter code
digest move, and every family's `aer` `engine_code_sha256`: the change also edits the registry caveats
(`adapters/registry/__init__.py`, in `AER_CLOSURE`; pre-round verification V-5). Against a version 3 import, the AERs
of the 36 account-path logs differ only in the label text; no stored corpus records either version. At a release seal the rule withholds the raw objects that hold the account path. On t3
that is 9 released `header.json` objects plus 107 already withheld, with no change to execution counts.

