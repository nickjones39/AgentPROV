"""Pre-round review PR-1: what ``snapshot.context[].verification`` records for each way a context tree is resolved.

The CLI gives a ``PinCheck`` only to a ``--context ROLE=PATH`` git copy; a download pin (``ArchiveTree``) and a git pin
read from the fetch cache (``GitPinTree``) verify themselves and come without one. D-221's seal refuses a context tree
whose verification is not ``{unverified: 0}``, so a self-verifying tree must record how it was vouched for, never null.
"""

from __future__ import annotations

from agentprov.adapters.runner.importer import (
    ArchiveTree,
    ContextTree,
    GitPinTree,
    LocalTree,
    PinCheck,
    _context_verification,
)

PIN = {"kind": "git", "role": "tasks", "repo": "https://github.com/example/tasks", "commit": "b" * 40}


def test_a_pin_check_gives_its_own_counts():
    check = PinCheck("blob", PIN, listing={})
    check.verified, check.unverified = 4, 1
    assert _context_verification(ContextTree("tasks", object(), check, pin=PIN), 5) == {
        "kind": "blob", "verified": 4, "unverified": 1}


def test_a_download_pins_archive_records_download():
    tree = object.__new__(ArchiveTree)
    assert _context_verification(ContextTree("supp", tree, None, pin=PIN), 7) == {
        "kind": "download", "verified": 7, "unverified": 0}


def test_a_cached_git_pin_records_blob():
    tree = object.__new__(GitPinTree)
    assert _context_verification(ContextTree("tasks", tree, None, pin=PIN), 3) == {
        "kind": "blob", "verified": 3, "unverified": 0}


def test_a_tree_nothing_vouched_for_records_none(tmp_path):
    assert _context_verification(ContextTree("tasks", LocalTree(tmp_path), None, pin=PIN), 2) is None
