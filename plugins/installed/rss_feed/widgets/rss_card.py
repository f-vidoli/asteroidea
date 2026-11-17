from __future__ import annotations

from typing import Any

from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

FONT = "AppMono"
BG = (0x14 / 255, 0x14 / 255, 0x10 / 255, 1)
PRIMARY = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 1)
MUTED = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.7)


def _esc_markup(text: Any) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


class RssCard(BoxLayout):
    """Custom widget for RSS feed items."""

    widget_type = "RssCard"

    def __init__(
        self,
        title: str = "Untitled",
        summary: str = "",
        source: str = "",
        link: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            orientation="vertical",
            padding=["14dp", "12dp", "14dp", "12dp"],
            spacing="6dp",
            **kwargs,
        )
        self.size_hint_y = None
        self.height = "150dp"

        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            self._oline_c = Color(*PRIMARY)
            self._oline = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update_bg, size=self._update_bg)

        safe_title = _esc_markup(title or "Untitled")
        self.title_label = Label(
            text=f"[b]{safe_title}[/b]",
            markup=True,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height="30dp",
            color=PRIMARY,
            font_size="15sp",
            font_name=FONT,
            shorten=True,
            shorten_from="right",
        )
        self.title_label.bind(size=self._sync_text_size)

        body = str(summary or link or "")
        self.body_label = Label(
            text=body,
            markup=False,
            halign="left",
            valign="top",
            color=MUTED,
            font_size="12sp",
            font_name=FONT,
        )
        self.body_label.bind(size=self._sync_text_size)

        safe_source = _esc_markup(source or "")
        self.meta_label = Label(
            text=f"[size=11]{safe_source}[/size]" if safe_source else "",
            markup=True,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height="22dp",
            color=MUTED,
            font_name=FONT,
        )
        self.meta_label.bind(size=self._sync_text_size)

        self.add_widget(self.title_label)
        self.add_widget(self.body_label)
        self.add_widget(self.meta_label)

    def _update_bg(self, *_args: Any) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._oline.rectangle = (self.x, self.y, self.width, self.height)

    @staticmethod
    def _sync_text_size(instance: Label, _value: Any) -> None:
        instance.text_size = (instance.width, None)


def register_widgets(registry) -> None:
    registry.register("RssCard", RssCard)
