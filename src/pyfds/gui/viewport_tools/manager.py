"""ToolManager: owns the tools and the active one; the viewport widget talks only to this."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .base import Hit, Preview, Tool, ToolContext, ToolProps
from .draw import BoxTool, WallTool
from .measure_paint import MeasureTool, PaintTool, PickTool

SELECT = "select"


class SelectTool(Tool):
    """The default: clicks select objects (the widget does that), so the tool itself does nothing."""
    name = SELECT
    label = "Select"
    hint = "Click an object to select it (Ctrl-click adds)"


class ToolManager:
    def __init__(self, api: Any, props: Optional[ToolProps] = None,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        self.ctx = ToolContext(api, props)
        self._listeners: List[Callable[[], None]] = [on_change] if on_change else []
        self.tools: Dict[str, Tool] = {SELECT: SelectTool(self.ctx)}
        for kind in BoxTool.LABELS:
            self.tools[kind] = BoxTool(self.ctx, kind)
        for tool in (WallTool(self.ctx), MeasureTool(self.ctx), PickTool(self.ctx), PaintTool(self.ctx)):
            self.tools[tool.name] = tool
        self.current: Tool = self.tools[SELECT]

    @property
    def props(self) -> ToolProps:
        return self.ctx.props

    def names(self) -> List[str]:
        return list(self.tools)

    def activate(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"unknown tool {name!r}; choose from {', '.join(self.tools)}")
        self.current.cancel()
        self.current = self.tools[name]
        self.current.cancel()
        self._changed()
        return self.current

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Call *listener* whenever the active tool, its preview or its state changes (viewport and toolbars both do)."""
        self._listeners.append(listener)

    def _changed(self) -> None:
        for fn in list(self._listeners):
            fn()

    # -- events from the widget ------------------------------------------------------------------------------
    def click(self, hit: Hit) -> Any:
        result = self.current.click(hit)
        self._changed()
        return result

    def move(self, hit: Hit) -> None:
        self.current.move(hit)
        if self.current.active():
            self._changed()

    def finish(self) -> List[Any]:
        made = self.current.finish()
        self._changed()
        return made

    def escape(self) -> bool:
        """Esc: cancel a half-done drawing, else go back to Select. True when the tool changed."""
        if self.current.active():
            self.current.cancel()
            self._changed()
            return False
        if self.current.name != SELECT:
            self.activate(SELECT)
            return True
        return False

    def preview(self) -> Preview:
        return self.current.preview()

    def take_messages(self) -> List[str]:
        msgs, self.ctx.messages = self.ctx.messages, []
        return msgs
