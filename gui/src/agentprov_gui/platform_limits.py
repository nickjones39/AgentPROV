"""What the CLI refuses on this platform (D-1064), as ``agentprov info --format json`` reports it. No Qt, no network.

The core keeps one table of platform limits (``agentprov.platforms``): live runs on Windows, the AgentDojo-family backend
builds on Windows ARM64, ``--containment sandbox-exec`` off macOS and the job queue on Windows. ``info``'s ``platform``
member lists the ones that apply to the host the CLI runs on (``system``, ``machine`` and, per feature, its name, the
platform, where it works, the reason, the subjects it is narrowed to, the user-guide section and the message every
surface shows). The app disables the same features with the same message. It reads the configured CLI's answer rather
than the app's own copy of the table: the checkout's CLI can be another install, and on Windows the architecture that
counts is that CLI's interpreter's (D-867).

Until the CLI has answered (or when it cannot run, or is an older CLI without the member) nothing is known and nothing
is disabled here; the CLI still refuses with ``platform.unsupported``. :func:`current` is the app's one answer;
:func:`set_current` replaces it (the main window after each check, tests with a simulated platform).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov_gui import text as T

__all__ = ["FEATURES", "INFO_ARGV", "UNKNOWN", "Limit", "PlatformLimits", "current", "fetch", "parse", "set_current"]

INFO_ARGV: Final = ("info", "--format", "json")
#: the features the app gates (the core's table may name more; those are kept and ignored)
FEATURES: Final = ("live_runs", "backend_build", "sandbox_exec", "job_queue")
_LIMITS: Final = IngestLimits().replace(max_json_bytes=8 * 1024 * 1024, max_json_depth=16)
_GUIDE_PREFIX: Final = "docs/user-guide/"
#: a chapter of the user guide and an optional heading anchor, nothing else (the value is the CLI's, shown and followed)
_GUIDE: Final = re.compile(r"[0-9]{2}-[a-z0-9-]{1,80}\.md(?:#[a-z0-9-]{1,120})?")


@dataclass(frozen=True, slots=True)
class Limit:
    """One feature the CLI refuses here: ``message`` is the CLI's own sentence ("… available on macOS and Linux. On
    Windows … not available …: reason. See the user guide, …"), ``guide`` the chapter and anchor in the user guide
    (``07-live-runs.md#platforms``; empty when the CLI named none the app can follow)."""

    feature: str
    name: str
    platform: str
    works_on: str
    reason: str
    message: str
    guide: str = ""
    subjects: tuple[str, ...] = ()

    def applies(self, subject: str | None) -> bool:
        """Whether the limit covers ``subject`` (a backend id): a limit narrowed to subjects covers only those."""
        return not self.subjects or subject is None or subject in self.subjects

    @property
    def headline(self) -> str:
        return f"Not available on {self.platform}"

    @property
    def explanation(self) -> str:
        """The notice's sentence: where it works and why not here (the guide is the notice's link)."""
        return f"{self.name}: available on {self.works_on}. Not available on {self.platform}: {self.reason}."


@dataclass(frozen=True, slots=True)
class PlatformLimits:
    """The CLI's host and the features it refuses there; ``known`` is false until a CLI has answered."""

    system: str = ""
    machine: str = ""
    limits: tuple[Limit, ...] = field(default_factory=tuple)
    known: bool = False

    def get(self, feature: str, subject: str | None = None) -> Limit | None:
        """The limit that makes ``feature`` (for ``subject``, when narrowed) unavailable, or ``None``."""
        return next((x for x in self.limits if x.feature == feature and x.applies(subject)), None)

    def for_argv(self, argv: Sequence[str]) -> Limit | None:
        """The limit the CLI would refuse this subcommand argv with (``run …``, ``backends build ID …``, a
        ``sandbox-exec`` containment, ``jobs start --queue-cpu``), or ``None``. Mirrors the CLI's refusals: a host
        preset's ``run --dry-run`` and a backend build's ``--dry-run`` still plan."""
        args = list(argv)
        dry = "--dry-run" in args
        if args[:1] == ["run"]:
            preset = any(a in ("--m5ultra", "--preset") or a.startswith("--preset=") for a in args)
            if not (dry and preset) and (hit := self.get("live_runs")) is not None:
                return hit
            if _option(args, "--containment") == "sandbox-exec":
                return self.get("sandbox_exec")
            return None
        if args[:2] == ["backends", "build"] and not dry:
            backend = next((a for a in args[2:] if not a.startswith("-")), None)
            return self.get("backend_build", backend) if backend is not None else None
        if args[:2] == ["jobs", "start"] and "--queue-cpu" in args[: args.index("--") if "--" in args else None]:
            return self.get("job_queue")
        return None


def _option(args: list[str], name: str) -> str | None:
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


#: nothing known yet: nothing is disabled
UNKNOWN: Final = PlatformLimits()
_state: list[PlatformLimits] = [UNKNOWN]


def current() -> PlatformLimits:
    """The app's answer: the configured CLI's last ``info`` (:data:`UNKNOWN` until one arrived)."""
    return _state[0]


def set_current(limits: PlatformLimits | None) -> None:
    _state[0] = UNKNOWN if limits is None else limits


def _text(value: Any, limit: int = 600) -> str:
    return T.line(value, limit) if isinstance(value, str) else ""


def _guide(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    rel = value.strip().removeprefix(_GUIDE_PREFIX)
    return rel if _GUIDE.fullmatch(rel) else ""


def parse(code: int, out: bytes) -> PlatformLimits | None:
    """``info --format json``'s ``platform`` member; ``None`` when the command failed or the document has none (an older
    CLI). Every string is the CLI's, shown as plain escaped text (S1, S3)."""
    if code != 0 or not out.strip():
        return None
    try:
        doc = strict_json_loads(out.strip(), _LIMITS)
    except (IngestError, ValueError):
        return None
    member = doc.get("platform") if isinstance(doc, dict) else None
    if not isinstance(member, dict) or not isinstance(member.get("unavailable"), list):
        return None
    limits: list[Limit] = []
    for entry in member["unavailable"][:64]:
        if not isinstance(entry, dict) or not isinstance(entry.get("feature"), str):
            continue
        message = _text(entry.get("message"), 1200)
        if not message:
            continue
        subjects = entry.get("subjects")
        limits.append(Limit(
            feature=_text(entry["feature"], 60), name=_text(entry.get("name"), 200),
            platform=_text(entry.get("platform"), 60) or _text(member.get("system"), 60),
            works_on=_text(entry.get("works_on"), 120), reason=_text(entry.get("reason")), message=message,
            guide=_guide(entry.get("guide")),
            subjects=tuple(_text(s, 60) for s in subjects[:32] if isinstance(s, str)) if isinstance(subjects, list)
            else ()))
    return PlatformLimits(_text(member.get("system"), 60), _text(member.get("machine"), 60), tuple(limits), True)


def fetch(cli: Any) -> PlatformLimits | None:
    """Ask ``cli`` (a :class:`~agentprov_gui.jobs.manager.CliLocator`): ``info --format json``, parsed (:func:`parse`).
    Blocks for the CLI's run; the main window calls it in the background."""
    from agentprov_gui.live.cli import call

    code, out, _err = call(cli, INFO_ARGV, timeout=120)
    return parse(code, out)
