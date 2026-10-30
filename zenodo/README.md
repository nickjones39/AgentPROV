# agentprov-zenodo

AgentPROV's draft-only Zenodo uploader (D-790, D-870, D-880). It turns a deposit draft made by
`agentprov package --deposit` into an **unpublished** Zenodo draft, and can place drafts in a community and cross-link
the records of a collection by their reserved DOIs. It never publishes, edits a published record or deletes anything:
you review each draft on Zenodo's website and press Publish yourself.

    python -I -m agentprov_zenodo DEPOSIT_DIR --target sandbox --check
    python -I -m agentprov_zenodo --help

The user guide's chapter 5 ("Creating an unpublished Zenodo draft") is the manual. It is a separate distribution so
that the `agentprov` package stays offline for releases (HL H.10.1(1)); install it with `pip install agentprov[zenodo]`
or, in a checkout, `uv sync`.
