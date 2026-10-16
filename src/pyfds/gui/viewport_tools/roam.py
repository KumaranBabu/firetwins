"""First-person ("roam") camera maths (plan step F2, UX-20), free of Qt and VTK.

The camera stands at ``position`` looking along a direction given by ``yaw`` (0 = +X, counter-clockwise from above, in
degrees) and ``pitch`` (0 = level, + = up). The world is Z-up, so the camera never rolls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

Vec = Tuple[float, float, float]


@dataclass
class RoamCamera:
    position: Vec = (0.0, 0.0, 1.7)
    yaw: float = 0.0
    pitch: float = 0.0
    step: float = 0.25                  # metres per key press / wheel notch
    turn: float = 3.0                   # degrees per arrow-key press

    # -- directions ------------------------------------------------------------------------------------
    def forward(self) -> Vec:
        y, p = math.radians(self.yaw), math.radians(self.pitch)
        return (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p))

    def right(self) -> Vec:
        y = math.radians(self.yaw)
        return (math.sin(y), -math.cos(y), 0.0)

    def focal_point(self, distance: float = 1.0) -> Vec:
        f = self.forward()
        return tuple(self.position[i] + f[i] * distance for i in range(3))      # type: ignore[return-value]

    # -- movement --------------------------------------------------------------------------------------
    def move(self, forward: float = 0.0, right: float = 0.0, up: float = 0.0) -> None:
        """Walk *forward* / strafe *right* / rise *up* (in multiples of ``step``). Walking follows the view
        direction, so looking down and moving forward descends."""
        f, r = self.forward(), self.right()
        self.position = tuple(self.position[i] + self.step * (forward * f[i] + right * r[i] + (up if i == 2 else 0.0))
                              for i in range(3))                                  # type: ignore[assignment]

    def look(self, d_yaw: float = 0.0, d_pitch: float = 0.0) -> None:
        self.yaw = (self.yaw + d_yaw) % 360.0
        self.pitch = max(-89.0, min(89.0, self.pitch + d_pitch))

    def set_step_for_model(self, extent: Sequence[float]) -> None:
        """Scale the step to the model so a tunnel and a room both feel right (about 1/60 of the diagonal)."""
        diag = math.dist((extent[0], extent[2], extent[4]), (extent[1], extent[3], extent[5]))
        self.step = max(0.05, diag / 60.0)

    @classmethod
    def looking(cls, position: Sequence[float], target: Sequence[float]) -> "RoamCamera":
        """A camera at *position* facing *target* (for entering roam mode from the current view)."""
        d = [target[i] - position[i] for i in range(3)]
        flat = math.hypot(d[0], d[1])
        return cls(tuple(position), math.degrees(math.atan2(d[1], d[0])) % 360.0,    # type: ignore[arg-type]
                   math.degrees(math.atan2(d[2], flat)) if flat or d[2] else 0.0)
