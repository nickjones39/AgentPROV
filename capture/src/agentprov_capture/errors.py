"""Exceptions of ``agentprov_capture``. Each carries a stable dotted ``code``; messages never carry secret values."""

from __future__ import annotations

__all__ = ["CaptureError", "CaptureLogError", "CaptureWriteError", "RedactionError"]


class CaptureError(Exception):
    """Base class. ``code`` is stable and dotted (``cap.<area>.<what>``)."""

    code = "cap.error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class CaptureLogError(CaptureError):
    """The log file or its state does not allow the operation (exists, closed, poisoned, too large, ...)."""

    code = "cap.log.error"


class CaptureWriteError(CaptureError):
    """An event, blob or call violates the capture/0.1 model; nothing was written."""

    code = "cap.write.invalid"


class RedactionError(CaptureError):
    """Redaction failed or its configuration is unusable (G.6.4, fail closed): nothing was written.

    The message never includes the content being scanned; the original exception is deliberately not chained.
    """

    code = "cap.redact.failed"
