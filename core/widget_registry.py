from __future__ import annotations

from typing import Callable, Dict, Type

from kivy.uix.widget import Widget


WidgetFactory = Callable[..., Widget]


class WidgetRegistry:
    """Registry mapping widget type names to Kivy widget classes/factories."""

    def __init__(self) -> None:
        self._registry: Dict[str, WidgetFactory] = {}

    def register(self, widget_type: str, factory: WidgetFactory) -> None:
        if not widget_type:
            raise ValueError("widget_type must be non-empty")
        if not callable(factory):
            raise TypeError(f"Factory for '{widget_type}' must be callable")
        self._registry[widget_type] = factory

    def unregister(self, widget_type: str) -> None:
        self._registry.pop(widget_type, None)

    def resolve(self, widget_type: str) -> WidgetFactory | None:
        return self._registry.get(widget_type)

    def create(self, widget_type: str, data: dict | None = None) -> Widget:
        factory = self.resolve(widget_type)
        if factory is None:
            raise KeyError(f"Unknown widget_type: {widget_type}")
        data = data or {}
        return factory(**data)

    def list_types(self) -> list[str]:
        return sorted(self._registry.keys())
