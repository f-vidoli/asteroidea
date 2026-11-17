from __future__ import annotations

from typing import Any

from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

FONT = "AppMono"
BG = (0x14 / 255, 0x14 / 255, 0x10 / 255, 1)
PRIMARY = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 1)
MUTED = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.7)


def _outline(widget, color=PRIMARY):
    with widget.canvas.after:
        widget._oc = Color(*color)
        widget._ol = Line(rectangle=(widget.x, widget.y, widget.width, widget.height), width=1)
    widget.bind(
        pos=lambda inst, *_: setattr(inst._ol, "rectangle", (inst.x, inst.y, inst.width, inst.height)),
        size=lambda inst, *_: setattr(inst._ol, "rectangle", (inst.x, inst.y, inst.width, inst.height)),
    )


class BoolToggle(Button):
    def __init__(self, active: bool = False, **kwargs: Any) -> None:
        super().__init__(
            text="ON" if active else "OFF",
            size_hint=(None, None),
            size=("72dp", "32dp"),
            background_normal="",
            background_down="",
            font_name=FONT,
            bold=True,
            **kwargs,
        )
        self._active = bool(active)
        _outline(self, PRIMARY)
        self.bind(on_release=self._toggle)
        self._sync_style()

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = bool(value)
        self._sync_style()

    def _toggle(self, *_a: Any) -> None:
        self._active = not self._active
        self._sync_style()

    def _sync_style(self) -> None:
        self.text = "ON" if self._active else "OFF"
        self.background_color = PRIMARY if self._active else BG
        self.color = BG if self._active else PRIMARY


class RssSettingsWidget(BoxLayout):
    """Custom settings widget provided by the RSS plugin."""

    widget_type = "RssSettingsWidget"

    def __init__(self, plugin_id: str = "", plugin_manager: Any = None, **kwargs: Any) -> None:
        kwargs.pop("manifest", None)
        if plugin_manager is None:
            plugin_manager = kwargs.pop("plugin_manager", None)
        if not plugin_id:
            plugin_id = str(kwargs.pop("plugin_id", "rss_feed"))

        super().__init__(orientation="vertical", spacing=dp(8), padding=[dp(12), dp(10), dp(12), dp(10)], size_hint_y=None, **kwargs)
        self.plugin_id = plugin_id
        self.plugin_manager = plugin_manager
        self.height = dp(230)

        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            self._oc = Color(*MUTED)
            self._ol = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=lambda *_: self._upd(), size=lambda *_: self._upd())

        settings = plugin_manager.get_plugin_settings(plugin_id)

        title = Label(
            text="[b]CUSTOM RSS SETTINGS[/b]",
            markup=True,
            size_hint_y=None,
            height="24dp",
            halign="left",
            valign="middle",
            color=PRIMARY,
            font_name=FONT,
        )
        title.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        self.add_widget(title)

        self.enabled = BoolToggle(active=bool(settings.get("enabled", True)))
        self.add_widget(self._row("Enable RSS feed", self.enabled, switch=True))

        self.feed_url = self._input(str(settings.get("feed_url", "")))
        self.add_widget(self._labeled("Feed URL", self.feed_url))
        self.max_items = self._input(str(settings.get("max_items", 5)), "int")
        self.refresh_minutes = self._input(str(settings.get("refresh_minutes", 15)), "int")
        nums = BoxLayout(size_hint_y=None, height="64dp", spacing="8dp")
        nums.add_widget(self._labeled("Max items", self.max_items))
        nums.add_widget(self._labeled("Refresh (min)", self.refresh_minutes))
        self.add_widget(nums)
        self.height = dp(230)

    def _upd(self):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ol.rectangle = (self.x, self.y, self.width, self.height)

    def _row(self, label: str, widget: Any, switch: bool = False) -> BoxLayout:
        row = BoxLayout(size_hint_y=None, height="34dp")
        lbl = Label(text=label, halign="left", valign="middle", color=MUTED, font_name=FONT)
        lbl.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        row.add_widget(lbl)
        if switch:
            w = BoxLayout(size_hint_x=None, width="70dp")
            w.add_widget(widget)
            row.add_widget(w)
        else:
            row.add_widget(widget)
        return row

    def _labeled(self, label: str, widget: Any) -> BoxLayout:
        col = BoxLayout(orientation="vertical", spacing="4dp")
        lbl = Label(text=label, size_hint_y=None, height="18dp", halign="left", valign="middle", color=MUTED, font_name=FONT)
        lbl.bind(size=lambda i, _v: setattr(i, "text_size", (i.width, i.height)))
        col.add_widget(lbl)
        col.add_widget(widget)
        return col

    def _input(self, text: str, input_filter: str | None = None) -> TextInput:
        ti = TextInput(
            text=text,
            multiline=False,
            size_hint_y=None,
            height="36dp",
            background_normal="",
            background_active="",
            background_color=BG,
            foreground_color=PRIMARY,
            cursor_color=PRIMARY,
            padding=["10dp", "8dp"],
            font_name=FONT,
        )
        _outline(ti, MUTED)
        if input_filter:
            ti.input_filter = input_filter
        return ti

    def save(self) -> None:
        pm = self.plugin_manager
        pm.set_plugin_setting(self.plugin_id, "enabled", bool(self.enabled.active))
        pm.set_plugin_setting(self.plugin_id, "feed_url", self.feed_url.text.strip())
        try:
            pm.set_plugin_setting(self.plugin_id, "max_items", max(1, int(self.max_items.text or "5")))
        except Exception:
            pm.set_plugin_setting(self.plugin_id, "max_items", 5)
        try:
            pm.set_plugin_setting(self.plugin_id, "refresh_minutes", max(1, int(self.refresh_minutes.text or "15")))
        except Exception:
            pm.set_plugin_setting(self.plugin_id, "refresh_minutes", 15)
        pm.context.data.setdefault("plugin_settings", {})[self.plugin_id] = pm.get_plugin_settings(self.plugin_id)
        print(f"[RssSettingsWidget] saved settings for '{self.plugin_id}'")


def register_widgets(registry) -> None:
    registry.register("RssSettingsWidget", RssSettingsWidget)
