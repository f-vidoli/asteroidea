from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol, runtime_checkable

from .event_bus import EventBus
from .widget_registry import WidgetRegistry


@dataclass
class PluginContext:
    """Runtime context passed to plugin components."""

    app: Any
    event_bus: EventBus
    widget_registry: WidgetRegistry
    plugins_dir: Path
    cache_dir: Path
    plugin_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def _manager(self) -> Any:
        return getattr(self.app, "plugin_manager", None)

    def get_memory(self) -> dict[str, Any]:
        if self._manager and self.plugin_id:
            return self._manager.get_plugin_memory(self.plugin_id)
        return {}

    def set_memory(self, key: str, value: Any, save: bool = True) -> None:
        if self._manager and self.plugin_id:
            self._manager.set_plugin_memory(self.plugin_id, key, value, save=save)

    def save_memory(self) -> None:
        if self._manager and self.plugin_id:
            self._manager.save_plugin_memory(self.plugin_id)

    def get_shared_memory(self) -> dict[str, Any]:
        if self._manager:
            return self._manager.get_shared_memory()
        return {}

    def set_shared_memory(self, key: str, value: Any, save: bool = True) -> None:
        if self._manager:
            self._manager.set_shared_memory(key, value, save=save)

    def save_shared_memory(self) -> None:
        if self._manager:
            self._manager.save_shared_memory()


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    entrypoints: dict[str, Any] = field(default_factory=dict)
    settings: list[dict[str, Any]] = field(default_factory=list)
    path: Path | None = None


class BaseDaemon(abc.ABC):
    """Long-running background component managed by the plugin system."""

    name: str = "daemon"

    def __init__(self, context: PluginContext) -> None:
        self.context = context

    @abc.abstractmethod
    async def run(self) -> None:
        """Run until cancelled/stopped."""

    async def stop(self) -> None:
        """Optional cleanup hook."""


@runtime_checkable
class IPluginManager(Protocol):
    """Core plugin manager contract.

    NOTE: Swappable (startup-time, non-hot) plugin-provided manager is a future
    addition. The app routes lifecycle through this interface so a replacement
    can be selected at startup later without refactoring.
    """

    async def setup(self) -> None: ...

    async def load_installed_plugins(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def install_from_zip(self, zip_path: str | Path) -> Path | None: ...

    async def install_from_github(
        self, repo: str, ref: str = "main"
    ) -> Path | None: ...


# Fetchers are async callables: async def fetch(context) -> dict | list[dict]
Fetcher = Callable[[PluginContext], Awaitable[dict[str, Any] | list[dict[str, Any]]]]
