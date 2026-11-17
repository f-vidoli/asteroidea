from __future__ import annotations

from pathlib import Path
from typing import Any

from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager

from core.event_bus import EventBus
from core.widget_registry import WidgetRegistry
from .plugin_settings import PluginSettingsScreen
from .screens import FeedScreenView, MainScreenView

FONT = "AppMono"
BG = (0x14 / 255, 0x14 / 255, 0x10 / 255, 1)
PRIMARY = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 1)
MUTED = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.55)


class ReaderRoot(BoxLayout):
    """Reader with top icon navigation (Main/Feed/Settings)."""

    def __init__(
        self,
        widget_registry: WidgetRegistry,
        event_bus: EventBus,
        plugin_manager: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(orientation="vertical", spacing=0, **kwargs)
        self.widget_registry = widget_registry
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager

        with self.canvas.before:
            Color(*BG)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.screen_manager = ScreenManager(transition=NoTransition())

        self.main_view = MainScreenView()
        self.feed_view = FeedScreenView()
        self.settings_view = PluginSettingsScreen(plugin_manager) if plugin_manager else None

        self.main_screen = Screen(name="main")
        self.main_screen.add_widget(self.main_view)
        self.feed_screen = Screen(name="feed")
        self.feed_screen.add_widget(self.feed_view)
        self.settings_screen = Screen(name="settings")
        if self.settings_view:
            self.settings_screen.add_widget(self.settings_view)

        self.screen_manager.add_widget(self.main_screen)
        self.screen_manager.add_widget(self.feed_screen)
        if self.settings_view:
            self.screen_manager.add_widget(self.settings_screen)
        self.screen_manager.current = "main"

        self.add_widget(self._build_topbar())
        self.add_widget(self.screen_manager)

        self.event_bus.subscribe_ui(self.handle_payload)
        print(f"[Reader] subscribed to EventBus, known widgets={self.widget_registry.list_types()}")

    def _update_bg(self, *_args: Any) -> None:
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _build_topbar(self) -> BoxLayout:
        bar = BoxLayout(
            size_hint_y=None,
            height="58dp",
            padding=["14dp", "6dp", "10dp", "6dp"],
            spacing="8dp",
        )
        with bar.canvas.before:
            Color(*BG)
            bar._bg = Rectangle(pos=bar.pos, size=bar.size)
            Color(*PRIMARY)
            bar._line = Line(points=[bar.x, bar.y, bar.right, bar.y], width=1)
        bar.bind(
            pos=lambda *_: self._update_bar(bar),
            size=lambda *_: self._update_bar(bar),
        )

        self.title_label = Label(
            text="Main",
            bold=True,
            font_size="20sp",
            color=PRIMARY,
            halign="left",
            valign="middle",
            font_name=FONT,
        )
        self.title_label.bind(
            size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height))
        )
        bar.add_widget(self.title_label)

        btn_kwargs = dict(
            size_hint=(None, None),
            size=("46dp", "46dp"),
            background_normal="",
            background_down="",
            color=PRIMARY,
            font_size="22sp",
        )
        self.btn_main = Button(text="\u2302", on_release=lambda *_: self.switch_to("main"), **btn_kwargs)
        self.btn_feed = Button(text="\u2630", on_release=lambda *_: self.switch_to("feed"), **btn_kwargs)
        self.btn_settings = Button(text="\u2699", on_release=lambda *_: self.switch_to("settings"), **btn_kwargs)
        for b in (self.btn_main, self.btn_feed, self.btn_settings):
            with b.canvas.after:
                b._oline = Color(*PRIMARY)
                b._oborder = Line(rectangle=(b.x, b.y, b.width, b.height), width=1)
            b.bind(pos=lambda inst, *_: setattr(inst._oborder, "rectangle", (inst.x, inst.y, inst.width, inst.height)),
                   size=lambda inst, *_: setattr(inst._oborder, "rectangle", (inst.x, inst.y, inst.width, inst.height)))
        bar.add_widget(self.btn_main)
        bar.add_widget(self.btn_feed)
        bar.add_widget(self.btn_settings)
        self._update_nav_state()
        return bar

    @staticmethod
    def _update_bar(bar: BoxLayout) -> None:
        bar._bg.pos = bar.pos
        bar._bg.size = bar.size
        bar._line.points = [bar.x, bar.y, bar.right, bar.y]

    def switch_to(self, screen_name: str) -> None:
        valid = {"main", "feed"}
        if self.settings_view:
            valid.add("settings")
        if screen_name in valid:
            self.screen_manager.current = screen_name
            if screen_name == "settings" and self.settings_view:
                self.settings_view.refresh()
            self._update_nav_state()

    def _update_nav_state(self) -> None:
        current = self.screen_manager.current
        titles = {"main": "Main", "feed": "Feed", "settings": "Settings"}
        self.title_label.text = titles.get(current, "Asteroidea")

        for name, btn in (("main", self.btn_main), ("feed", self.btn_feed), ("settings", self.btn_settings)):
            selected = current == name
            btn.background_color = PRIMARY if selected else BG
            btn.color = BG if selected else PRIMARY
            if hasattr(btn, "_oline"):
                btn._oline.rgba = PRIMARY if selected else MUTED
        if not self.settings_view:
            self.btn_settings.disabled = True
            self.btn_settings.opacity = 0.5

    def handle_payload(self, payload: dict[str, Any]) -> None:
        try:
            screen = str(payload.get("screen", "main")).lower()
            widget_type = payload.get("widget_type")
            data = payload.get("data") or {}
            payload_id = payload.get("id")
            print(f"[Reader] handle_payload screen={screen} widget_type={widget_type} id={payload_id} keys={list(payload.keys())}")

            if screen not in ("main", "feed"):
                print(f"[Reader] invalid screen in payload: {screen}")
                return
            if not widget_type:
                print("[Reader] payload missing widget_type")
                return

            factory = self.widget_registry.resolve(str(widget_type))
            print(f"[Reader] resolve {widget_type} -> {factory} (known={self.widget_registry.list_types()})")
            if factory is None:
                notice = Label(
                    text=f"Unknown widget: {widget_type}",
                    size_hint_y=None,
                    height="40dp",
                    color=(0.95, 0.55, 0.55, 1),
                    font_name=FONT,
                )
                self._inject(screen, notice, payload_id)
                return

            widget = self.widget_registry.create(
                str(widget_type), data if isinstance(data, dict) else {}
            )
            print(f"[Reader] created widget {widget_type}: {widget}")
            self._inject(screen, widget, str(payload_id) if payload_id is not None else None)
            print(f"[Reader] injected {widget_type} into {screen}")
        except Exception as exc:
            import traceback
            print(f"[Reader] failed to handle payload: {exc}")
            traceback.print_exc()

    def _inject(self, screen: str, widget: Any, payload_id: str | None) -> None:
        target = self.main_view if screen == "main" else self.feed_view
        target.add_payload_widget(widget, payload_id)
