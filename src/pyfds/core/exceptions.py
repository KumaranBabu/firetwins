"""
PyFDS Exception Hierarchy
=========================
All domain-specific exceptions derive from ``FdsError`` so callers can
catch the entire family with a single ``except FdsError``, or be selective.
"""
from __future__ import annotations
from typing import List, Optional


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class FdsError(Exception):
    """Base class for all PyFDS exceptions."""

    def __init__(self, message: str, *, context: Optional[str] = None) -> None:
        super().__init__(message)
        self.context = context      # optional: file path, entity name, etc.

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} [context: {self.context}]" if self.context else base


# ---------------------------------------------------------------------------
# Domain-specific subclasses
# ---------------------------------------------------------------------------

class FdsValidationError(FdsError):
    """
    Raised when a project fails structural or physics validation.

    Attributes
    ----------
    errors:
        List of human-readable error strings collected by the validator.
    """
    def __init__(self, message: str, errors: Optional[List[str]] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.errors: List[str] = errors or []

    def __str__(self) -> str:
        base = super().__str__()
        if self.errors:
            detail = "\n  - " + "\n  - ".join(self.errors)
            return f"{base}{detail}"
        return base


class FdsExecutionError(FdsError):
    """Raised when the FDS binary fails to start or returns a non-zero exit."""

    def __init__(self, message: str, *, returncode: Optional[int] = None,
                 stderr: Optional[str] = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.returncode = returncode
        self.stderr = stderr

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.returncode is not None:
            parts.append(f"returncode={self.returncode}")
        if self.stderr:
            parts.append(f"stderr={self.stderr[:200]!r}")
        return " | ".join(parts)


class FdsParseError(FdsError):
    """Raised when an FDS or SMV file cannot be parsed."""

    def __init__(self, message: str, *, filepath: Optional[str] = None,
                 line_number: Optional[int] = None, **kwargs) -> None:
        super().__init__(message, context=filepath, **kwargs)
        self.filepath = filepath
        self.line_number = line_number

    def __str__(self) -> str:
        base = super().__str__()
        if self.line_number is not None:
            return f"{base} (line {self.line_number})"
        return base


class FdsSerializationError(FdsError):
    """Raised when a project cannot be serialized to or deserialized from JSON."""


class FdsPluginError(FdsError):
    """Raised when a plugin fails to load, initialize, or execute."""

    def __init__(self, message: str, *, plugin_name: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.plugin_name = plugin_name


class FdsConfigError(FdsError):
    """Raised for invalid configuration values or missing required settings."""

    def __init__(self, message: str, *, key: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.key = key


class FdsJobError(FdsError):
    """Raised by the job queue or batch executor on job lifecycle failures."""

    def __init__(self, message: str, *, job_id: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.job_id = job_id


class FdsNotFoundError(FdsError):
    """Raised when a referenced entity, file, or resource does not exist."""

    def __init__(self, message: str, *, name: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.name = name


class FdsTimeoutError(FdsError):
    """Raised when a simulation or job exceeds its configured time limit."""

    def __init__(self, message: str, *, timeout_seconds: Optional[float] = None,
                 **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds


class FdsBinaryError(FdsError):
    """Raised when a Fortran unformatted binary file is corrupt or incompatible."""

    def __init__(self, message: str, *, filepath: Optional[str] = None,
                 offset: Optional[int] = None, **kwargs) -> None:
        super().__init__(message, context=filepath, **kwargs)
        self.filepath = filepath
        self.offset = offset
