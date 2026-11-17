from __future__ import annotations

from typing import Any

from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

FONT = "AppMono"
BG = (0x14 / 255, 0x14 / 255, 0x10 / 255, 1)
PRIMARY = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 1)
MUTED = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.7)


class WeatherCard(BoxLayout):
    """Custom home widget showing next hours weather."""

    widget_type = "WeatherCard"

    def __init__(
        self,
        location: str = "Weather",
        current_temp: str = "",
        summary: str = "",
        hours: list[dict[str, Any]] | None = None,
        source: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            orientation="vertical",
            padding=["14dp", "12dp", "14dp", "12dp"],
            spacing="8dp",
            **kwargs,
        )
        self.size_hint_y = None
        self.height = "210dp"
        hours = hours or []

        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            self._oline_c = Color(*PRIMARY)
            self._oline = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update_bg, size=self._update_bg)

        header = BoxLayout(size_hint_y=None, height="34dp")
        title = Label(
            text=f"[b]{location}[/b]",
            markup=True,
            halign="left",
            valign="middle",
            color=PRIMARY,
            font_size="16sp",
            font_name=FONT,
        )
        title.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        temp = Label(
            text=current_temp,
            halign="right",
            valign="middle",
            color=PRIMARY,
            font_size="18sp",
            bold=True,
            font_name=FONT,
            size_hint_x=None,
            width="90dp",
        )
        temp.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        header.add_widget(title)
        header.add_widget(temp)
        self.add_widget(header)

        sub = Label(
            text=summary,
            size_hint_y=None,
            height="22dp",
            halign="left",
            valign="middle",
            color=MUTED,
            font_size="12sp",
            font_name=FONT,
        )
        sub.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        self.add_widget(sub)

        row = BoxLayout(spacing="8dp", size_hint_y=None, height="90dp")
        for h in hours[:5]:
            cell = BoxLayout(orientation="vertical", padding=["6dp", "6dp"])
            with cell.canvas.before:
                Color(*BG)
                cell._bg = Rectangle(pos=cell.pos, size=cell.size)
            with cell.canvas.after:
                cell._oc = Color(*MUTED)
                cell._ol = Line(rectangle=(cell.x, cell.y, cell.width, cell.height), width=1)
            cell.bind(pos=lambda inst, *_: self._upd_cell(inst), size=lambda inst, *_: self._upd_cell(inst))
            t = Label(text=str(h.get("time", "")), font_size="11sp", color=MUTED, font_name=FONT)
            v = Label(text=str(h.get("temp", "")), font_size="13sp", bold=True, color=PRIMARY, font_name=FONT)
            d = Label(text=str(h.get("desc", "")), font_size="10sp", color=MUTED, font_name=FONT)
            for lbl in (t, v, d):
                lbl.halign = "center"
                lbl.valign = "middle"
                lbl.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
            cell.add_widget(t)
            cell.add_widget(v)
            cell.add_widget(d)
            row.add_widget(cell)
        if not hours:
            row.add_widget(Label(text="No forecast data", color=MUTED, font_name=FONT))
        self.add_widget(row)

        meta = Label(
            text=source,
            size_hint_y=None,
            height="20dp",
            halign="left",
            valign="middle",
            color=MUTED,
            font_size="10sp",
            font_name=FONT,
        )
        meta.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        self.add_widget(meta)

    @staticmethod
    def _upd_cell(inst):
        inst._bg.pos = inst.pos
        inst._bg.size = inst.size
        inst._ol.rectangle = (inst.x, inst.y, inst.width, inst.height)

    def _update_bg(self, *_args: Any) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._oline.rectangle = (self.x, self.y, self.width, self.height)


def register_widgets(registry) -> None:
    registry.register("WeatherCard", WeatherCard)
