"""Reverse CLI parity (D-700): every GUI setting and action has a CLI equivalent, and the GUI calls that equivalent
itself (one implementation). No Qt. ``tests/test_reverse_parity.py`` walks the built windows and checks each input,
button and menu action against this registry and the CLI's own parser; anything new fails until it is mapped.

* **Settings** (the Settings dialog): each pane declares ``KEYS``, an input widget's attribute (``name``, or
  ``name.key`` for a widget held in a dict attribute) to its ``agentprov settings`` key (``*`` for a family such
  as ``devrun.override.*``). The dialog's own fields are :data:`SETTINGS_EXCLUDED`, each with its reason: the
  presentational ones, and the checkout or installed program whose CLI the GUI runs.
* **Run Live** (the ``run`` dialog): an input whose attribute, or ``more_inputs`` key, is a field of
  ``FORMS["run"]`` is that field's option (forward parity, D-654, checks the option); the others are
  :data:`RUN_LIVE_INPUTS` (the ``run`` option they decide). A read-only widget only shows a value.
* **Actions** (buttons and menu actions, by accessible name, else text): a ``FORMS`` title is that form's command;
  the others are :data:`ACTIONS` (the command the action runs), :data:`PRESENTATIONAL` (navigation or a view of
  data the named command also shows, with its reason) or :data:`OUTSIDE_CLI` (D-880: the draft-only Zenodo uploader,
  which D-790 keeps out of the ``agentprov`` command, with the uploader options the action uses).
"""

from __future__ import annotations

from typing import Final

__all__ = ["ACTIONS", "OUTSIDE_CLI", "PRESENTATIONAL", "RUN_LIVE_INPUTS", "SETTINGS_EXCLUDED"]

#: Settings dialog fields that are not ``agentprov settings`` keys (D-700's exclusions)
SETTINGS_EXCLUDED: Final[dict[str, str]] = {
    "checkout": "the checkout whose CLI the GUI runs (the CLI is that checkout itself)",
    "cli_program": "the program installed from PyPI that the GUI runs without a checkout (the CLI is that program itself; D-1030)",
    "roots": "the Viewer's corpus roots (where the GUI looks; every command takes its corpus explicitly)",
    "theme": "presentational: light, dark or follow the system",
    "graph_colours": "presentational: the graph palette",
    "native": "presentational: the experimental native macOS toolbar",
    "show_tips": "presentational: whether the app shows tooltips and the graph's hover popover",
    "limit": "presentational: how much content text the Viewer shows (agentprov inspect takes --max-chars per call)",
    "sidebar": "navigation: the list of Settings panes picks the pane shown (no setting)",
}

#: Run Live inputs that are not one form field: the ``run`` option each decides
RUN_LIVE_INPUTS: Final[dict[str, tuple[str, str]]] = {
    "script": ("--llm-script", "the scripted transport's script"),
    "mode": ("--llm-script", "scripted gives --llm-script SCRIPT; real gives --endpoint and --model-id"),
    "version": ("--benchmark-version", "the backend's benchmark version"),
    "max_cost": ("--max-cost-usd", "the run's cost cap"),
    "max_tokens_mode": ("--max-tokens", "whether --max-tokens is given (D-656)"),
    "suites": ("--suite", "one --suite per ticked suite"),
    "attacks": ("--attack", "one --attack per ticked attack"),
    "conformance": ("--skip-prov-conformance", "unticked adds it (design §8.3a)"),
    "scope": ("--suite", "the full benchmark gives every suite and every attack that can be chosen (--suite, --attack), "
                         "as ticking them all does (D-1060)"),
}

#: buttons and menu actions, by accessible name (else text): the command each runs
ACTIONS: Final[dict[str, tuple[str, ...]]] = {
    # Runs
    "New Job…": ("jobs", "start"), "New Job": ("jobs", "start"), "New job": ("jobs", "start"),
    "Dev Run…": ("devrun", "start"), "Dev Run": ("devrun", "start"), "Start a dev run": ("devrun", "start"),
    "Run Live…": ("run",), "Run live": ("run",), "Start a live dev run": ("run",), "Start the live run": ("run",),
    "Run the preflight probe only": ("run",), "Tune the concurrency with a host preset": ("run",),
    "Build cost figures from my corpora": ("priors", "build"),  # D-1062: Run Live's quote card
    # the model picker (D-700): every list, refresh and identity is one agentprov models call
    "Refresh the provider's model list (network)": ("models",), "Show the local model's identity record": ("models",),
    "Confirm the held steps of the selected batch": ("batch", "resume"),
    "Stop the selected batch": ("batch", "stop"), "Stop the dev run": ("batch", "stop"),  # --steps; a live one: jobs stop
    "Stop the job": ("jobs", "stop"), "Force kill the job": ("jobs", "kill"), "Pause the job": ("jobs", "drain"),
    "Resume the job as a new job": ("jobs", "resume"), "Open the job log": ("jobs", "follow"),  # --log
    "Cancel the job": ("jobs", "cancel"),  # D-1061: the stop, and resume refuses it
    "Send the message to the Assistant": ("assist",),  # D-1010: the conversation on stdin
    "Refresh the server's model list": ("assist",),  # --list-models
    "Copy the job command": ("jobs", "show"), "Open the live preview (off by default)": ("jobs", "follow"),
    "Open the written corpus in the viewer": ("inspect",),
    # Package (each step starts a FORMS job)
    "Check and Dry Run": ("package",), "Seal…": ("package",), "Verify (chain, release)": ("verify",),
    "Build Deposit…": ("package",),
    # Viewer
    "Revalidate this corpus with a full recompute into a new corpus": ("recompute",),
    "Open Corpus…": ("inspect",), "Open Corpus": ("inspect",), "Reload": ("inspect",),
    "Reload corpora list": ("inspect",),
    "Open a corpus folder": ("inspect",),  # D-1060: the corpora list's Open Folder… (as Open Corpus…)
    "Export this execution's graph with agentprov render": ("render",),  # D-706: the render job form, --ex
    "Copy the CLI selection": ("stats",),  # D-706: the filter as agentprov stats --select
    "Verify this corpus": ("verify",),  # D-1060: the Viewer notice's Verify… opens the verify form (G.8.6)
    # Settings
    "OK": ("settings", "set"), "Reset dev run settings to defaults": ("settings", "unset"),
    "Check the keychain": ("keys", "status"), "Store the selected key": ("keys", "set"),
    "Delete the selected key": ("keys", "delete"), "Store the endpoint key": ("keys", "set"),
    "List the local server's models": ("models",), "Find the model's folder": ("models",),  # D-828
    "Clear the model's settings": ("settings", "unset"),
    "Add a price override": ("prices", "set"), "Remove the selected override": ("prices", "unset"),
    # Help
    "About AgentPROV": ("info",),
    # D-1065: Check for Updates (About, Help › Check for Updates…, the start-up notice)
    "Check for Updates…": ("update", "check"), "Check for Updates": ("update", "check"),
    "Download and Install…": ("update", "download"),  # then, after the confirmation, update install --confirm
    "Show the Upgrade Command": ("update", "install"),  # without --bundle: prints the command, installs nothing
    "Update Now": ("update", "download"),  # the notice: About's Download and Install…
    "Skip This Version": ("settings", "set"),  # update.last_notified X.Y.Z
}

#: buttons and menu actions that only navigate or change how data is shown
PRESENTATIONAL: Final[dict[str, str]] = {
    **{page: "navigation: shows a page of the window" for page in
       ("Viewer", "Runs", "Logs", "System", "Licences", "Package", "Docs", "Assistant")},
    # Help (D-1010): reading the checkout's user guide is not a command; the Assistant's Send is (ACTIONS)
    "AgentPROV Help": "navigation: shows the Docs page", "Ask the Assistant": "navigation: opens or shows the Assistant tab (D-1040)",
    "Back to the previous chapter": "navigation: the Docs page's previous chapter",
    # D-1064: a platform notice's link (agentprov info lists the limits; the guide says where each feature works)
    "Open the user guide on how to run it": "navigation: opens the user guide's section on a platform limit",
    "Open Settings to set the AgentPROV checkout": "opens the Settings dialog (each setting is mapped there)",
    "Open Settings to set up the Assistant": "opens the Settings dialog on its Assistant pane (assistant.* settings)",
    "Clear the chat and start a new one": "presentational: forgets the conversation the GUI holds (agentprov assist "
                                          "keeps none; each call carries its conversation on stdin)",
    "Settings…": "opens the Settings dialog (each setting is mapped there)",
    "Browse for the model's folder": "a folder picker: fills the Folder field (the local_models model_dir setting)",
    "Cancel": "closes a dialog without running anything",
    "Close": "closes the About window (a running update command goes on in the background)",
    "Later": "closes the update notice; the start-up check asks again next time (agentprov update check --if-stale)",
    "Copy the update commands": "copies the agentprov update commands About shows (each button runs its own)",
    # D-1060: the Settings window's form style
    "Show advanced settings": "presentational: shows or hides a Settings pane's rarely used settings",
    "Copy the Settings terminal commands": "copies the commands a Settings pane shows (agentprov settings, agentprov "
                                           "prices, agentprov keys); OK runs the pending ones",
    "Choose the AgentPROV checkout folder": "a folder picker: fills the checkout field (the CLI the GUI runs)",
    "Choose the agentprov program": "a file picker: fills the field naming the installed program (the CLI the GUI runs)",
    "Close Window": "closes the window",
    "Toggle Sidebar": "presentational: shows or hides the sidebar",
    "Bigger": "presentational: text size", "Smaller": "presentational: text size", "Default": "presentational: text size",
    "Main": "presentational: shows or hides the toolbar",
    "Keyboard Shortcuts": "help text about the GUI itself",
    "Previous step": "navigation: the Package steps", "Next step": "navigation: the Package steps",
    "Show more run options": "presentational: shows the rest of run's options",
    # D-1060: the form style's presentational controls in Run Live
    "Show task selection and repeats": "presentational: shows the task selection and repeats of run",
    "Show the plan by suite": "a view of agentprov estimate's breakdown by suite and attack (the same command's lines)",
    "Copy the terminal command": "copies the agentprov estimate and agentprov run commands the dialog shows",
    "Fill the cost cap from the quote's upper figure": "fills --max-cost-usd from agentprov estimate's p90 cost",
    "Choose the script file": "a file picker: fills the script field (--llm-script)",
    "Choose the working corpus folder": "a folder picker: fills the working corpus field (--corpus)",
    # D-1060: the Package page's presentational controls
    "Choose the corpus spec file": "a file picker: fills the corpus spec field (package --spec)",
    "Choose the deposit folder": "a folder picker: fills the deposit folder field (package --deposit)",
    "Choose the release.toml file": "a file picker: fills the release.toml field (package --metadata)",
    "Show the step's output as text": "presentational: shows a Package step's checks and job status as plain text",
    "Copy the selected rows": "copies log rows already shown (agentprov jobs follow --log prints them)",
    **{f"Show {level} records": "a log view filter (agentprov jobs follow --log prints every record)"
       for level in ("debug", "info", "warning", "error")},
    "Follow the end of the log": "keeps the log view at its end (agentprov jobs follow --log follows it)",
    "Show content in the AER pane": "a content view switch (agentprov inspect --show-content)",
    "Show content in the PROV-JSON pane": "a content view switch (agentprov inspect --show-content)",
    "Show content in the graph popover and inspector": "a content view switch (agentprov inspect --show-content)",
    "Zoom out": "presentational: graph zoom", "Zoom in": "presentational: graph zoom",
    "Actual size": "presentational: graph zoom", "Fit to window": "presentational: graph zoom",
    "Focus on selection": "presentational: graph view",
    "More graph tools": "presentational: shows the graph tools a narrow inspector has no room for",
    "Show core bundle": "a graph view filter (agentprov inspect --view prov --bundle core)",
    "Show inference bundle": "a graph view filter (agentprov inspect --view prov --bundle inference)",
    "Show assessment bundle": "a graph view filter (agentprov inspect --view prov --bundle assessment)",
    "Collapse assessment mentions": "presentational: graph layout",
    "Show selection in PROV-JSON": "navigation: the same record in another tab",
    # D-1060: the terminal command card of the preview and of each execution tab
    "Copy this execution's terminal commands": "copies the agentprov inspect and agentprov render commands the "
                                               "execution tab shows",
    # D-1060: the Viewer's three panes: showing a pane, the corpus facts, the filters and the terminal commands
    **{label: "presentational: shows or hides a side pane of the Viewer" for label in
       ("Hide Corpora", "Show Corpora", "Hide Inspector", "Show Inspector", "Show or hide the corpora list",
        "Show or hide the inspector", "Show the corpora list", "Show the inspector")},
    "Show the corpus details": "a view of the open corpus's manifest (corpus.json), which the corpora list read",
    "Add filter": "a view filter (agentprov stats --select; the terminal command for this view shows it)",
    "Clear all filters": "a view filter (agentprov stats without --select)",
    **{f"Remove the {facet} filter": "a view filter (agentprov stats --select; the terminal command shows it)" for facet
       in ("status", "completeness", "source", "record type", "issue", "suite", "attack", "injection task", "defence",
           "model requested", "utility", "attack succeeded", "id contains")},
    "Show the terminal command for this view": "presentational: shows the agentprov stats command of the rows shown",
    "Show the terminal command for this execution": "presentational: shows the agentprov inspect and render commands",
    # D-845: the Viewer's execution tabs show what agentprov inspect ID --corpus DIR prints; opening one reads only
    **{label: "navigation: Viewer execution tabs (D-840..D-845)" for label in
       ("Open in New Tab", "Close Tab", "Close Other Tabs", "Corpora", "Next Tab", "Previous Tab",
        "Open this execution in a new Viewer tab", "Show this execution in the Corpora tab")},
}

#: D-880: actions that are deliberately not an ``agentprov`` command. The Zenodo uploader is ``agentprov_zenodo``
#: (``python -I -m agentprov_zenodo``), outside the agentprov package (H.10.1(1), D-790); each entry names the uploader
#: options the action passes (checked against its parser) and why.
OUTSIDE_CLI: Final[dict[str, tuple[tuple[str, ...], str]]] = {
    "Create Zenodo drafts…": (("--target", "--create-draft", "--resume", "--keychain", "--community", "--root-digest",
                               "--cross-link", "--umbrella", "--member"),
                              "runs the draft-only uploader under a pseudo-terminal; never publishes"),
    "Start the Zenodo draft uploader": (("--create-draft", "--cross-link", "--keychain"),
                                        "starts the collection's uploader runs in the terminal pane"),
    "Send the typed line to the uploader": ((), "types the confirmation phrase at the uploader's terminal"),
    "Stop the Zenodo draft uploader": ((), "stops the running uploader (SIGTERM); it never publishes"),
    "Write release.toml from the Zenodo settings…": ((), "writes a release.toml template for package --deposit "
                                                          "--metadata from the zenodo settings, never over a file"),
}
