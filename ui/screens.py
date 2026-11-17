from __future__ import annotations

from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

FONT = "AppMono"


class DynamicListScreen(BoxLayout):
    """A screen-like view with a scrollable dynamic widget list."""

    screen_name: str = "screen"

    def __init__(self, title: str, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", spacing=0, **kwargs)
        self.title_label = None
        self.scroll = ScrollView(do_scroll_x=False, bar_width="6dp", scroll_type=["bars", "content"])
        self.list_layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing="14dp",
            padding=["16dp", "16dp", "16dp", "20dp"],
        )
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)

        self._widgets_by_id: dict[str, Any] = {}

    def add_payload_widget(self, widget: Any, payload_id: str | None = None) -> None:
        if getattr(widget, "size_hint_y", None) is None or widget.size_hint_y == 1:
            widget.size_hint_y = None
        if not getattr(widget, "height", None) or widget.height < 10:
            widget.height = "100dp"

        if payload_id and payload_id in self._widgets_by_id:
            old = self._widgets_by_id[payload_id]
            try:
                idx = self.list_layout.children.index(old)
                self.list_layout.remove_widget(old)
                self.list_layout.add_widget(widget, index=idx)
            except ValueError:
                self.list_layout.add_widget(widget)
            self._widgets_by_id[payload_id] = widget
            return

        self.list_layout.add_widget(widget)
        if payload_id:
            self._widgets_by_id[payload_id] = widget

    def clear_items(self) -> None:
        self.list_layout.clear_widgets()
        self._widgets_by_id.clear()


class MainScreenView(DynamicListScreen):
    screen_name = "main"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(title="Main", **kwargs)


class FeedScreenView(DynamicListScreen):
    screen_name = "feed"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(title="Feed", **kwargs)
