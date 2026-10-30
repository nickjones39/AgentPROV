"""Entry point: ``uv run --project gui agentprov-gui [CORPUS]`` (design §13, D-399).

Sets up the application (style, appearance), the single-instance guard (S10: a ``QLockFile`` in
``$AGENTPROV_HOME/gui/``), the GUI's own log (S12: metadata only, 4 × 1 MiB), core dumps off (``RLIMIT_CORE = 0``,
design §8.2) and the main window.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final

__all__ = ["main", "register_secret"]


def _no_core_dumps() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass


LOG_BYTES: Final = 1024 * 1024
LOG_BACKUPS: Final = 3


class RotatingLog(logging.FileHandler):
    """``gui.log`` rotated at 1 MiB, 4 files in all (S12). ``logging.handlers`` is not used: it imports ``socket``,
    and the GUI imports no network module (S11)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.stream is not None and self.stream.tell() >= LOG_BYTES:
                self.close()
                base = Path(self.baseFilename)
                for i in range(LOG_BACKUPS - 1, 0, -1):
                    older = base.with_name(f"{base.name}.{i}")
                    if older.exists():
                        os.replace(older, base.with_name(f"{base.name}.{i + 1}"))
                os.replace(base, base.with_name(f"{base.name}.1"))
                self.stream = self._open()
        except OSError:
            pass
        super().emit(record)


SECRET_MIN: Final = 8
_SECRETS: set[str] = set()


def register_secret(value: str) -> None:
    """Have ``gui.log`` replace *value* with ``[REDACTED]`` (S12, design §8.2). Values shorter than
    ``SECRET_MIN`` are ignored, so a mistaken registration cannot blank the log."""
    if len(value) >= SECRET_MIN:
        _SECRETS.add(value)


def _redact(text: str) -> str:
    for value in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


def _safe_str(obj: object) -> str:
    try:
        return str(obj)
    except Exception:
        return f"<unprintable {type(obj).__name__}>"


class RedactingFilter(logging.Filter):
    """The S12 key redaction filter: registered values never reach ``gui.log``. It sits on the handler, so records
    from child loggers (which skip the parent logger's filters) are covered too.

    Filters run outside ``Handler.emit``'s error handling, so this one never raises (GR-43): a record that cannot be
    formatted becomes ``<unformattable> msg args`` (redacted, args cleared, so ``handleError`` has no raw argument
    to dump). The traceback (``exc_info``) is rendered once into ``exc_text`` and redacted, and ``stack_info`` is
    redacted too; the formatter appends both after the filter has run."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not _SECRETS:
            return True
        try:
            message = record.getMessage()
        except Exception:
            args = record.args
            items: tuple[object, ...] = args if isinstance(args, tuple) else (args,) if args else ()
            parts = [_safe_str(record.msg), *(_safe_str(a) for a in items)]
            record.msg = "<unformattable> " + _redact(" ".join(parts))
            record.args = ()
        else:
            redacted = _redact(message)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        if record.exc_info:
            if not record.exc_text:
                try:
                    record.exc_text = logging.Formatter().formatException(record.exc_info)
                except Exception:
                    record.exc_text = "<unformattable traceback>"
            record.exc_info = None
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        if record.stack_info:
            record.stack_info = _redact(record.stack_info)
        return True


def _gui_log(directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingLog(directory / "gui.log", encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("agentprov_gui")
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentprov-gui", description="AgentPROV desktop GUI (read-only viewer)")
    parser.add_argument("corpus", nargs="?", help="a corpus directory to open (DIR or DIR.partial)")
    parser.add_argument("--smoke", action="store_true",
                        help="build the main window, run the event loop once and exit 0 (the G5 bundle check)")
    args = parser.parse_args(argv)
    _no_core_dumps()

    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication

    from agentprov_gui.paths import gui_dir
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import theme
    from agentprov_gui.ui.brand import app_icon
    from agentprov_gui.ui.mainwindow import MainWindow
    from agentprov_gui.ui.safe import safe_message_box

    app = QApplication(sys.argv[:1])
    app.setApplicationName("AgentPROV")
    app.setOrganizationName("AgentPROV")
    app.setApplicationDisplayName("AgentPROV")
    app.setWindowIcon(app_icon())  # title bars, the taskbar; the Dock for an unbundled run
    app.setDesktopFileName("org.agentprov.gui")  # Linux: matches gui/packaging/linux/org.agentprov.gui.desktop
    directory = gui_dir()
    _gui_log(directory)
    log = logging.getLogger("agentprov_gui")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(directory, 0o700)
    except OSError:
        pass
    lock = QLockFile(str(directory / "gui.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        safe_message_box(None, "AgentPROV", "AgentPROV is already running.",
                         informative="Only one GUI drives the job queue at a time (S10).").exec()
        return 1
    settings = Settings()
    theme.apply_scheme(settings.theme)
    window = MainWindow(settings)
    window.show()
    if args.smoke:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, app.quit)  # one turn of the event loop, then exit
        app.exec()
        lock.unlock()
        return 0
    log.info("start gui=%s", "0.1.0")
    if args.corpus:
        window.viewer.open_path(Path(args.corpus))
    code = app.exec()
    lock.unlock()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
