"""Detector / sprinkler property sets (&PROP) and raw text blocks."""
from __future__ import annotations

from typing import Any, Optional

from .base import _CollectionManager
from .species import _unique


class PropManager(_CollectionManager):
    """Device property sets: ``api.props``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Prop
        super().__init__(api, Prop)

    def add_prop(self, name: Optional[str] = None, **fields) -> Any:
        from pyfds.domain.model import Prop
        if name and self.get(name) is not None:
            raise ValueError(f"prop {name!r} already exists")
        prop = Prop(name=name or _unique(self, "PROP"), **fields)
        self.add(prop)
        return prop

    def add_sprinkler(self, name: Optional[str] = None, rti: float = 50.0, c_factor: float = 0.7,
                      activation_temperature: Optional[float] = None, **fields) -> Any:
        """Sprinkler property set (RTI, C-factor, activation temperature in C)."""
        return self.add_prop(name, quantity="SPRINKLER LINK TEMPERATURE", rti=rti,
                             c_factor=c_factor, activation_temperature=activation_temperature,
                             **fields)

    def add_heat_detector(self, name: Optional[str] = None, rti: float = 5.0,
                          activation_temperature: float = 74.0, **fields) -> Any:
        """Heat detector property set (RTI, activation temperature in C)."""
        return self.add_prop(name, quantity="LINK TEMPERATURE", rti=rti,
                             activation_temperature=activation_temperature, **fields)

    def add_smoke_detector(self, name: Optional[str] = None, activation_obscuration: float = 3.28,
                           **fields) -> Any:
        return self.add_prop(name, quantity="CHAMBER OBSCURATION",
                             activation_obscuration=activation_obscuration, **fields)


class TextManager(_CollectionManager):
    """Verbatim FDS text blocks: ``api.texts`` (items have no name; address by index)."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Text
        super().__init__(api, Text)

    def add_text(self, content: str) -> Any:
        from pyfds.domain.model import Text
        text = Text(content=content)
        self.add(text)
        return text

    def get(self, index) -> Optional[Any]:     # type: ignore[override]
        items = self.all()
        return items[index] if isinstance(index, int) and -len(items) <= index < len(items) else None
