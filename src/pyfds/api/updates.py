"""Is a newer version available? ``api.updates`` (Help > Check for Updates). See ``pyfds.core.updates`` for how the check works."""
from __future__ import annotations

from typing import Any, Optional


class UpdatesManager:
    def __init__(self, api: Any) -> None:
        self._api = api

    def check(self, timeout: float = 20.0, branch: str = "main") -> Any:
        """Compare this checkout with the remote (read-only; never pulls). Returns an ``UpdateStatus`` with
        ``state`` (up_to_date, behind, ahead, diverged, unknown), ``message``, ``local``, ``remote``, ``behind``, ``ahead``."""
        from pyfds.core.updates import check_for_updates
        return check_for_updates(timeout=timeout, branch=branch)

    @staticmethod
    def unknown(message: str) -> Any:
        """A status for when the check itself could not run."""
        from pyfds.core.updates import UpdateStatus
        return UpdateStatus("unknown", message)
