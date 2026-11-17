from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from kivy.app import App

from .event_bus import EventBus
from .plugin_manager import CorePluginManager
from .widget_registry import WidgetRegistry
from ui.reader import ReaderRoot


class AsteroideaApp(App):
    """Main Kivy application with async plugin-driven architecture."""

    def __init__(self, base_dir: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        self.widget_registry = WidgetRegistry()
        self.event_bus = EventBus()
        self.plugin_manager = CorePluginManager(
            context_app=self,
            widget_registry=self.widget_registry,
            event_bus=self.event_bus,
            base_dir=self.base_dir,
        )
        self.reader: ReaderRoot | None = None
        self._dispatch_task: asyncio.Task[Any] | None = None

    def build(self):
        self.title = "Asteroidea Reader"
        try:
            from kivy.core.window import Window

            Window.clearcolor = (0.08, 0.09, 0.11, 1)
        except Exception:
            pass
        self.reader = ReaderRoot(self.widget_registry, self.event_bus, self.plugin_manager)
        return self.reader

    async def app_main(self) -> None:
        """Async lifecycle: load plugins, start tasks, run UI, then shutdown."""
        loop = asyncio.get_running_loop()
        self.event_bus.bind_loop(loop)
        await self.plugin_manager.setup()
        await self.plugin_manager.load_installed_plugins()

        # Bridge queue events -> UI subscribers (payload injection on main thread)
        self._dispatch_task = asyncio.create_task(self._event_dispatch_loop())

        await self.plugin_manager.start()

        try:
            # Run Kivy within the asyncio loop
            await self.async_run(async_lib="asyncio")
        finally:
            await self.shutdown_async()

    async def _event_dispatch_loop(self) -> None:
        print("[AsteroideaApp] event dispatch loop started")
        try:
            async for payload in self.event_bus.events():
                wt = payload.get("widget_type") if isinstance(payload, dict) else None
                print(f"[AsteroideaApp] dequeued payload widget_type={wt}")
                self.event_bus.dispatch_to_ui(payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[AsteroideaApp] event dispatch loop error: {exc}")

    async def shutdown_async(self) -> None:
        await self.plugin_manager.stop()
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except Exception:
                pass
        self._dispatch_task = None

    def on_stop(self) -> None:
        # Best-effort: ensure plugin tasks are cancelled if app exits externally
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.plugin_manager.stop())
        except Exception:
            pass
