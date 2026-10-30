# Golden fixtures: licence statement (J.2.3)

These files are test data, committed to the private repository only and never shipped in the sdist or wheel (U-06,
Addendum B-2). Model-provider terms for redistributing model outputs were not assessed.

| Group | Rights holder and licence | SPDX | Notice |
|---|---|---|---|
| `generated/` (R01-R10) | The author's AgentDojo-PROV captures. Release data declared CC-BY-4.0, code MIT. The traces embed AgentDojo benchmark text (system prompt, task prompts, environment data, attack templates), which is MIT | `CC-BY-4.0 AND MIT` | `../../LICENSES/CC-BY-4.0.txt`, `../../LICENSES/AgentDojo-MIT.txt` |
| `converted/` (C01-C09) | Derived from AgentDojo run logs, messages copied verbatim. MIT, Copyright (c) 2024 Debenedetti, Zhang, Balunovic, Beurer-Kellner, Fischer, Tramer. The baseline converted manifests stamp CC-BY-4.0 without the MIT notice (open issue J.7.2 item 10; user decision U-03) | `MIT` | `../../LICENSES/AgentDojo-MIT.txt` |
| `../../agentdojo/v0.k11/runs/` (N-C01-N-C09) | AgentDojo upstream `runs/` at ethz-spylab/agentdojo commit c274885610efaaafec38b6d3eb07152ba7ff3f94. MIT, no separate data licence ("MIT by repository; data licence not separately stated", U-03) | `MIT` | `../../LICENSES/AgentDojo-MIT.txt` |

Origin, selection rule and digests of every file are in `SOURCE.json` and `golden_index.json`. Review this statement again
before any public release.
