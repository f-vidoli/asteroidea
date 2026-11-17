from __future__ import annotations

import asyncio
import time

from core.plugin_api import BaseDaemon


class RssRefreshDaemon(BaseDaemon):
    """Periodically re-runs the RSS fetcher to refresh feed items."""

    name = "rss_refresh"

    def __init__(self, context) -> None:
        super().__init__(context)
        self._running = True

    async def run(self) -> None:
        try:
            from ..fetchers.rss_fetcher import fetch  # type: ignore
        except Exception:
            from fetchers.rss_fetcher import fetch  # type: ignore

        while self._running:
            settings = {}
            pm = getattr(getattr(self.context, "app", None), "plugin_manager", None)
            if pm:
                settings = pm.get_plugin_settings("rss_feed")
            try:
                minutes = max(1, int(settings.get("refresh_minutes", 15)))
            except Exception:
                minutes = 15

            # Skip refresh if last fetch was recent (persisted across runs)
            mem = self.context.get_memory()
            last = float(mem.get("last_fetch_ts", 0) or 0)
            now = time.time()
            wait_s = max(0, minutes * 60 - int(now - last))
            if wait_s > 0:
                await asyncio.sleep(wait_s)
            if not self._running:
                break
            try:
                payloads = await fetch(self.context) or []
                for p in payloads:
                    self.context.event_bus.emit(p)
            except Exception as exc:
                print(f"[rss_feed] refresh error: {exc}")

    async def stop(self) -> None:
        self._running = False
