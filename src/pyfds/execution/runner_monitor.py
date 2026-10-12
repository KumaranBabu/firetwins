"""LiveMonitor: follows HRR and device files of a running simulation."""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


_HRR_RE   = re.compile(r'^\s*HRR\s+\(kW\)', re.IGNORECASE)


_TIMED_RE = re.compile(r'^\s*([\d.]+)\s+', re.IGNORECASE)


class LiveMonitor:
    """
    Poll FDS output files at a configurable interval while a simulation runs.

    Reads the ``<chid>_hrr.csv`` (or ``<chid>_devc.csv``) and ``.out`` log
    on each tick, extracting the latest HRR and device values, then emits
    events on the global EventBus.

    Events emitted
    --------------
    ``HRR_UPDATED``     — ``{"time": float, "hrr": float}``
    ``DEVICE_UPDATED``  — ``{"time": float, "devices": {name: value}}``

    Usage::

        monitor = LiveMonitor(
            output_dir="/scratch/runs/case01",
            chid="case01",
            poll_interval=2.0,
        )
        monitor.start()
        # ... simulation running ...
        monitor.stop()
        data = monitor.hrr_data   # list of (time, hrr) tuples
    """

    def __init__(
        self,
        output_dir: str,
        chid: str,
        *,
        poll_interval: float = 2.0,
        on_hrr: Optional[Callable[[float, float], None]] = None,
        on_devices: Optional[Callable[[float, Dict[str, float]], None]] = None,
    ) -> None:
        self._output_dir   = Path(output_dir)
        self._chid         = chid
        self._poll         = poll_interval
        self._on_hrr       = on_hrr
        self._on_devices   = on_devices
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Accumulated data
        self.hrr_data: List[Tuple[float, float]] = []
        self.device_data: Dict[str, List[Tuple[float, float]]] = {}

        # Track file positions to avoid re-reading from start
        self._hrr_offset   = 0
        self._devc_offset  = 0
        self._header: Optional[List[str]] = None

    def start(self) -> None:
        """Start the polling thread (non-blocking)."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name=f"pyfds-livemonitor-{self._chid}",
        )
        self._thread.start()
        logger.info("LiveMonitor: started for chid=%r in %s", self._chid, self._output_dir)

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._poll * 3)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        from pyfds.core.events import get_global_bus
        bus = get_global_bus()
        while not self._stop_event.is_set():
            try:
                self._read_hrr(bus)
                self._read_devc(bus)
            except Exception as exc:
                logger.debug("LiveMonitor poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll)

    def _read_hrr(self, bus) -> None:
        """Read new lines from the HRR CSV (``<chid>_hrr.csv``)."""
        hrr_path = self._output_dir / f"{self._chid}_hrr.csv"
        if not hrr_path.exists():
            return
        try:
            with open(hrr_path, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._hrr_offset)
                new_lines = fh.readlines()
                self._hrr_offset = fh.tell()
        except OSError:
            return

        for line in new_lines:
            line = line.strip()
            if not line or line.startswith("Time"):
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                t   = float(parts[0])
                hrr = float(parts[1])
                self.hrr_data.append((t, hrr))
                if self._on_hrr:
                    self._on_hrr(t, hrr)
                bus.emit("HRR_UPDATED", {"time": t, "hrr": hrr}, source="LiveMonitor")
            except (ValueError, IndexError):
                pass

    def _read_devc(self, bus) -> None:
        """Read new rows from the device CSV (``<chid>_devc.csv``)."""
        devc_path = self._output_dir / f"{self._chid}_devc.csv"
        if not devc_path.exists():
            return
        try:
            with open(devc_path, "r", encoding="utf-8", errors="replace") as fh:
                # Always read header if not yet captured
                if self._header is None:
                    for raw in fh:
                        stripped = raw.strip()
                        if stripped.lstrip('"').lower().startswith("time"):
                            self._header = [h.strip().strip('"') for h in stripped.split(",")]
                            self._devc_offset = fh.tell()
                            break
                else:
                    fh.seek(self._devc_offset)

                new_lines = fh.readlines()
                self._devc_offset = fh.tell()
        except OSError:
            return

        if self._header is None:
            return

        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip().strip('"') for p in line.split(",")]
            if not parts or not _is_numeric(parts[0]):
                continue
            try:
                t = float(parts[0])
                devices: Dict[str, float] = {}
                for i, name in enumerate(self._header[1:], start=1):
                    if i < len(parts) and _is_numeric(parts[i]):
                        val = float(parts[i])
                        devices[name] = val
                        self.device_data.setdefault(name, []).append((t, val))
                if devices:
                    if self._on_devices:
                        self._on_devices(t, devices)
                    bus.emit("DEVICE_UPDATED", {"time": t, "devices": devices},
                             source="LiveMonitor")
            except (ValueError, IndexError):
                pass


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False
