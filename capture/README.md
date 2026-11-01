# agentprov-capture

The `capture/0.1` raw-evidence event log of [AgentPROV](https://w3id.org/agentprov/): its model, the writer that live
backends use to record an agent run, the hash-chain verifier and the redaction of credentials. Standard library plus
`rfc8785` only, so it installs in the isolated backend environments (Python 3.12 and later) as well as in the core.

You normally get it as a dependency of [`agentprov`](https://pypi.org/project/agentprov/). The format is specified in
the AgentPROV repository (`docs/architecture/`, <https://github.com/nickjones39/AgentPROV>), and the user guide is at
<https://w3id.org/agentprov/docs/>.

MIT licence.
