from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable

from kivy.clock import Clock


class EventBus:
    """Async event bus for payloads emitted by fetchers/daemons.

    Producers may run in asyncio tasks; UI consumers must apply mutations on the
    Kivy main thread. `emit` is thread/UI-safe via Clock scheduling.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, payload: dict[str, Any]) -> None:
        """Schedule payload emission safely from any context."""
        wt = payload.get("widget_type") if isinstance(payload, dict) else None
        sc = payload.get("screen") if isinstance(payload, dict) else None
        print(f"[EventBus] emit payload screen={sc} widget_type={wt}")
        def _put(_dt: float) -> None:
            try:
                self._queue.put_nowait(payload)
            except Exception as exc:
                print(f"[EventBus] queue put failed: {exc}")

        Clock.schedule_once(_put, 0)

    async def put(self, payload: dict[str, Any]) -> None:
        await self._queue.put(payload)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            payload = await self._queue.get()
            yield payload

    def subscribe_ui(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback to be invoked on the Kivy main thread per event."""
        self._subscribers.append(callback)

    def dispatch_to_ui(self, payload: dict[str, Any]) -> None:
        def _dispatch(_dt: float) -> None:
            wt = payload.get("widget_type") if isinstance(payload, dict) else None
            print(f"[EventBus] dispatch_to_ui widget_type={wt} subscribers={len(self._subscribers)}")
            for cb in list(self._subscribers):
                try:
                    cb(payload)
                except Exception as exc:  # pragma: no cover - defensive UI guard
                    print(f"[EventBus] subscriber error: {exc}")

        Clock.schedule_once(_dispatch, 0)
