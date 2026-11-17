from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import json
import pkgutil
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ssl
from urllib.request import urlopen

from kivy.uix.widget import Widget

from .event_bus import EventBus
from .plugin_api import BaseDaemon, Fetcher, PluginContext, PluginManifest
from .widget_registry import WidgetRegistry



def _urlopen(req_or_url, timeout=15):
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            ctx = ssl.create_default_context()
        except Exception:
            ctx = None
    try:
        if ctx is not None:
            return urlopen(req_or_url, timeout=timeout, context=ctx)
        return urlopen(req_or_url, timeout=timeout)
    except Exception as e:
        msg = str(e).lower()
        if 'cert' in msg or 'ssl' in msg:
            try:
                return urlopen(req_or_url, timeout=timeout, context=ssl._create_unverified_context())
            except Exception:
                pass
        raise


REQUIRED_SUBFOLDERS = ("widgets", "libraries", "fetchers", "daemons")


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    path: Path
    context: PluginContext | None = None
    fetchers: list[Fetcher] = field(default_factory=list)
    daemons: list[BaseDaemon] = field(default_factory=list)
    daemon_tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    fetcher_tasks: list[asyncio.Task[Any]] = field(default_factory=list)


class CorePluginManager:
    """Core plugin manager: ingest (zip/GitHub), validate, load, and run plugins."""

    def __init__(
        self,
        context_app: Any,
        widget_registry: WidgetRegistry,
        event_bus: EventBus,
        base_dir: Path,
    ) -> None:
        self.app = context_app
        self.widget_registry = widget_registry
        self.event_bus = event_bus
        self.base_dir = base_dir
        self.plugins_dir = base_dir / "plugins" / "installed"
        self.cache_dir = base_dir / "plugins" / "cache"
        self.settings_path = base_dir / "plugins" / "settings.json"
        self.memory_dir = base_dir / "plugins" / "memory"
        self.shared_memory_path = self.memory_dir / "shared.json"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.settings: dict[str, dict[str, Any]] = {}
        self.plugin_memories: dict[str, dict[str, Any]] = {}
        self.shared_memory: dict[str, Any] = {}
        self.context = PluginContext(
            app=context_app,
            event_bus=event_bus,
            widget_registry=widget_registry,
            plugins_dir=self.plugins_dir,
            cache_dir=self.cache_dir,
        )
        self.loaded: dict[str, LoadedPlugin] = {}
        self._started = False
        self._load_settings()
        self._load_shared_memory()

    async def setup(self) -> None:
        # Placeholder for future startup-time manager swap hook.
        return None

    # ---------- Ingest ----------
    async def install_from_zip(self, zip_path: str | Path, load: bool = True) -> Path | None:
        zip_path = Path(zip_path)
        if not zip_path.exists():
            print(f"[PluginManager] zip not found: {zip_path}")
            return None
        dest = await asyncio.to_thread(self._install_zip_sync, zip_path)
        if dest and load:
            manifest = self._read_manifest(dest)
            if manifest and self._validate_structure(dest):
                await self.unload_plugin(manifest.plugin_id)
                await self._load_plugin(dest, manifest)
                loaded = self.loaded.get(manifest.plugin_id)
                if loaded and self._started:
                    self._start_plugin_tasks(loaded)
        return dest

    def _install_zip_sync(self, zip_path: Path) -> Path | None:
        try:
            with tempfile.TemporaryDirectory(dir=self.cache_dir) as tmp:
                tmp_path = Path(tmp)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp_path)
                plugin_root = self._detect_plugin_root(tmp_path)
                if not plugin_root:
                    print(f"[PluginManager] invalid plugin zip: {zip_path}")
                    return None
                manifest = self._read_manifest(plugin_root)
                if not manifest:
                    print(f"[PluginManager] missing/invalid plugin.json in: {zip_path}")
                    return None
                dest = self.plugins_dir / manifest.plugin_id
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(plugin_root, dest)
                print(f"[PluginManager] installed plugin '{manifest.plugin_id}' from zip")
                return dest
        except Exception as exc:
            print(f"[PluginManager] failed to install zip {zip_path}: {exc}")
            return None

    async def install_from_github(self, repo: str, ref: str = "main", load: bool = True) -> Path | None:
        dest = await asyncio.to_thread(self._install_github_sync, repo, ref)
        if dest and load:
            manifest = self._read_manifest(dest)
            if manifest and self._validate_structure(dest):
                await self.unload_plugin(manifest.plugin_id)
                await self._load_plugin(dest, manifest)
        return dest

    def _install_github_sync(self, repo: str, ref: str) -> Path | None:
        # repo formats: "owner/name" or full https URL
        if repo.startswith("http://") or repo.startswith("https://"):
            base = repo.rstrip("/")
            if base.endswith(".git"):
                base = base[:-4]
            # expect https://github.com/owner/name
            parts = base.split("/")
            if len(parts) < 2:
                print(f"[PluginManager] invalid GitHub URL: {repo}")
                return None
            owner, name = parts[-2], parts[-1]
        else:
            if "/" not in repo:
                print(f"[PluginManager] invalid repo (expected owner/name): {repo}")
                return None
            owner, name = repo.split("/", 1)

        url = f"https://codeload.github.com/{owner}/{name}/zip/refs/heads/{ref}"
        try:
            cache_zip = self.cache_dir / f"{owner}-{name}-{ref}.zip"
            with _urlopen(url, timeout=20) as resp, open(cache_zip, "wb") as f:
                shutil.copyfileobj(resp, f)
            return self._install_zip_sync(cache_zip)
        except Exception as exc:
            print(f"[PluginManager] failed GitHub install {repo}@{ref}: {exc}")
            return None

    # ---------- Discovery / Load ----------
    async def load_installed_plugins(self) -> None:
        for child in sorted(self.plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = self._read_manifest(child)
            if not manifest:
                continue
            if not self._validate_structure(child):
                print(f"[PluginManager] plugin '{child.name}' missing required folders")
                continue
            try:
                await self._load_plugin(child, manifest)
            except Exception as exc:
                print(f"[PluginManager] failed loading '{manifest.plugin_id}': {exc}")

    async def _load_plugin(self, path: Path, manifest: PluginManifest) -> None:
        if manifest.plugin_id in self.loaded:
            return
        plugin_pkg_name = f"asteroidea_plugin_{manifest.plugin_id}"
        self._ensure_package_on_path(path, plugin_pkg_name)

        # Per-plugin context so plugins get their own memory namespace
        plugin_ctx = PluginContext(
            app=self.app,
            event_bus=self.event_bus,
            widget_registry=self.widget_registry,
            plugins_dir=self.plugins_dir,
            cache_dir=self.cache_dir,
            plugin_id=manifest.plugin_id,
            data={
                "plugin_path": path,
                "settings": self.get_plugin_settings(manifest.plugin_id),
                "memory": self.get_plugin_memory(manifest.plugin_id),
                "shared_memory": self.shared_memory,
            },
        )
        loaded = LoadedPlugin(manifest=manifest, path=path, context=plugin_ctx)

        # Load widgets
        print(f"[PluginManager] loading plugin '{manifest.plugin_id}' from {path}")
        self._load_widgets(path, plugin_pkg_name)
        libs = self._import_all_modules(path / "libraries", f"{plugin_pkg_name}.libraries")
        loaded.fetchers = self._load_fetchers(path, plugin_pkg_name, plugin_ctx)
        loaded.daemons = self._load_daemons(path, plugin_pkg_name, plugin_ctx)

        self.loaded[manifest.plugin_id] = loaded
        self.context.data.setdefault("plugin_settings", {})[manifest.plugin_id] = self.get_plugin_settings(manifest.plugin_id)
        print(
            f"[PluginManager] loaded '{manifest.plugin_id}' "
            f"(widget_types={len(self.widget_registry.list_types())} {self.widget_registry.list_types()}, "
            f"libs={len(libs)}, fetchers={len(loaded.fetchers)}, daemons={len(loaded.daemons)})"
        )

        if self._started:
            self._start_plugin_tasks(loaded)

    def _ensure_package_on_path(self, path: Path, pkg_name: str) -> None:
        parent = str(path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        # Also add plugin dir itself to allow intra-plugin imports in simple cases
        pstr = str(path)
        if pstr not in sys.path:
            sys.path.insert(0, pstr)

        init_file = path / "__init__.py"
        if not init_file.exists():
            try:
                init_file.write_text("", encoding="utf-8")
            except Exception:
                pass

        # Register as a package-like module alias pointing to path for namespaced imports
        if pkg_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                pkg_name, init_file, submodule_search_locations=[str(path)]
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[pkg_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as exc:
                    print(f"[PluginManager] failed to exec root package {pkg_name}: {exc}")

    def _load_widgets(self, path: Path, pkg_name: str) -> None:
        widgets_dir = path / "widgets"
        modules = self._import_all_modules(widgets_dir, f"{pkg_name}.widgets")
        print(f"[PluginManager] widget modules in {path.name}: {[m.__name__ for m in modules]}")
        for mod in modules:
            hook = getattr(mod, "register_widgets", None)
            if callable(hook):
                try:
                    hook(self.widget_registry)
                    print(f"[PluginManager] register_widgets hook ok in {mod.__name__}")
                except Exception as exc:
                    print(f"[PluginManager] widget hook error in {mod.__name__}: {exc}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(obj, Widget) or obj is Widget:
                    continue
                if obj.__module__ != mod.__name__:
                    continue
                widget_type = getattr(obj, "widget_type", None) or obj.__name__
                try:
                    self.widget_registry.register(str(widget_type), obj)
                    print(f"[PluginManager] auto-registered widget '{widget_type}' from {mod.__name__}")
                except Exception as exc:
                    print(f"[PluginManager] register {widget_type} failed: {exc}")

    def _load_fetchers(self, path: Path, pkg_name: str, context: PluginContext | None = None) -> list[Fetcher]:
        ctx = context or self.context
        fetchers_dir = path / "fetchers"
        modules = self._import_all_modules(fetchers_dir, f"{pkg_name}.fetchers")
        print(f"[PluginManager] fetcher modules in {path.name}: {[m.__name__ for m in modules]}")
        found: list[Fetcher] = []
        for mod in modules:
            hook = getattr(mod, "get_fetchers", None)
            if callable(hook):
                try:
                    result = hook(ctx)
                    if result:
                        for f in result:
                            if callable(f):
                                found.append(f)  # type: ignore[arg-type]
                except Exception as exc:
                    print(f"[PluginManager] fetcher hook error in {mod.__name__}: {exc}")
            func = getattr(mod, "fetch", None)
            if callable(func):
                found.append(func)  # type: ignore[arg-type]
        print(f"[PluginManager] discovered {len(found)} fetchers in {path.name}")
        return found

    def _load_daemons(self, path: Path, pkg_name: str, context: PluginContext | None = None) -> list[BaseDaemon]:
        ctx = context or self.context
        daemons_dir = path / "daemons"
        modules = self._import_all_modules(daemons_dir, f"{pkg_name}.daemons")
        print(f"[PluginManager] daemon modules in {path.name}: {[m.__name__ for m in modules]}")
        found: list[BaseDaemon] = []
        for mod in modules:
            hook = getattr(mod, "get_daemons", None)
            if callable(hook):
                try:
                    result = hook(ctx)
                    if result:
                        for d in result:
                            if isinstance(d, BaseDaemon):
                                found.append(d)
                except Exception as exc:
                    print(f"[PluginManager] daemon hook error in {mod.__name__}: {exc}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(obj, BaseDaemon) or obj is BaseDaemon:
                    continue
                if obj.__module__ != mod.__name__:
                    continue
                try:
                    inst = obj(ctx)
                    found.append(inst)
                except Exception as exc:
                    print(f"[PluginManager] daemon init error {obj}: {exc}")
        print(f"[PluginManager] discovered {len(found)} daemons in {path.name}")
        return found

    def _import_all_modules(self, folder: Path, pkg_prefix: str) -> list[Any]:
        modules: list[Any] = []
        if not folder.exists():
            print(f"[PluginManager] skip import, folder missing: {folder}")
            return modules
        try:
            contents = [p.name for p in folder.iterdir()]
            print(f"[PluginManager] folder contents {folder}: {contents}")
        except Exception as exc:
            print(f"[PluginManager] cannot list folder {folder}: {exc}")
        init = folder / "__init__.py"
        if not init.exists():
            try:
                init.write_text("", encoding="utf-8")
            except Exception:
                pass
        # Ensure the folder package itself is registered so submodule imports resolve (important on Android)
        if pkg_prefix not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(
                    pkg_prefix, init, submodule_search_locations=[str(folder)]
                )
                if spec and spec.loader:
                    pkg_mod = importlib.util.module_from_spec(spec)
                    sys.modules[pkg_prefix] = pkg_mod
                    spec.loader.exec_module(pkg_mod)
                else:
                    import types
                    pkg_mod = types.ModuleType(pkg_prefix)
                    pkg_mod.__path__ = [str(folder)]
                    pkg_mod.__package__ = pkg_prefix
                    sys.modules[pkg_prefix] = pkg_mod
                parent_name, _, child = pkg_prefix.rpartition(".")
                if parent_name and parent_name in sys.modules:
                    setattr(sys.modules[parent_name], child, sys.modules[pkg_prefix])
            except Exception as exc:
                print(f"[PluginManager] failed to init package {pkg_prefix}: {exc}")

        # Discover modules from .py/.pyc and via pkgutil (Android/buildozer may ship bytecode only)
        names: list[str] = []
        try:
            for _finder, name, ispkg in pkgutil.iter_modules([str(folder)]):
                if not ispkg and name != "__init__":
                    names.append(name)
        except Exception as exc:
            print(f"[PluginManager] pkgutil.iter_modules failed for {folder}: {exc}")
        try:
            for p in sorted(folder.iterdir()):
                if p.is_dir() and p.name == "__pycache__":
                    for c in sorted(p.iterdir()):
                        if c.suffix in (".pyc", ".pyo"):
                            stem = c.stem
                            if "." in stem:
                                stem = stem.split(".", 1)[0]
                            if stem != "__init__":
                                names.append(stem)
                    continue
                if p.name == "__init__.py" or p.name.startswith("__init__."):
                    continue
                if p.is_dir():
                    continue
                if p.suffix == ".py":
                    names.append(p.stem)
                elif p.suffix in (".pyc", ".pyo"):
                    stem = p.stem
                    # e.g. mod.cpython-311 -> mod
                    if "." in stem:
                        stem = stem.split(".", 1)[0]
                    if stem != "__init__":
                        names.append(stem)
        except Exception as exc:
            print(f"[PluginManager] folder scan failed for {folder}: {exc}")

        mod_names = []
        seen = set()
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            mod_names.append(n)
        print(f"[PluginManager] importing {len(mod_names)} modules from {folder} as {pkg_prefix}: {mod_names}")
        for short in mod_names:
            mod_name = f"{pkg_prefix}.{short}"
            try:
                if mod_name in sys.modules:
                    modules.append(sys.modules[mod_name])
                    continue
                module = importlib.import_module(mod_name)
                modules.append(module)
            except Exception as exc:
                # Fallback to explicit file-based import for .py sources
                try:
                    py = folder / f"{short}.py"
                    if py.exists():
                        spec = importlib.util.spec_from_file_location(mod_name, py)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[mod_name] = module
                            spec.loader.exec_module(module)
                            modules.append(module)
                            continue
                    print(f"[PluginManager] import failed {mod_name}: {exc}")
                except Exception as exc2:
                    print(f"[PluginManager] import failed {mod_name}: {exc} / fallback: {exc2}")
        return modules

    # ---------- Lifecycle ----------
    async def start(self) -> None:
        self._started = True
        print(f"[PluginManager] starting {len(self.loaded)} loaded plugins")
        for loaded in self.loaded.values():
            self._start_plugin_tasks(loaded)

    def _start_plugin_tasks(self, loaded: LoadedPlugin) -> None:
        print(f"[PluginManager] start tasks for '{loaded.manifest.plugin_id}' fetchers={len(loaded.fetchers)} daemons={len(loaded.daemons)}")
        # Start daemons
        for daemon in loaded.daemons:
            if any(getattr(t, "_daemon_ref", None) is daemon for t in loaded.daemon_tasks):
                continue
            task = asyncio.create_task(self._run_daemon(daemon), name=f"daemon:{loaded.manifest.plugin_id}:{daemon.name}")
            task._daemon_ref = daemon  # type: ignore[attr-defined]
            loaded.daemon_tasks.append(task)
        # Run fetchers once (they may emit multiple payloads)
        if not loaded.fetcher_tasks and loaded.fetchers:
            ctx = loaded.context or self.context
            for fetcher in loaded.fetchers:
                fname = getattr(fetcher, '__name__', 'fetch')
                print(f"[PluginManager] launching fetcher {loaded.manifest.plugin_id}:{fname}")
                task = asyncio.create_task(
                    self._run_fetcher(fetcher, ctx),
                    name=f"fetcher:{loaded.manifest.plugin_id}:{fname}",
                )
                loaded.fetcher_tasks.append(task)

    async def _run_daemon(self, daemon: BaseDaemon) -> None:
        try:
            print(f"[PluginManager] starting daemon {daemon.name}")
            await daemon.run()
        except asyncio.CancelledError:
            print(f"[PluginManager] daemon {daemon.name} cancelled")
        except Exception as exc:
            import traceback
            print(f"[PluginManager] daemon '{daemon.name}' error: {exc}")
            traceback.print_exc()
        finally:
            try:
                await daemon.stop()
            except Exception:
                pass

    async def _run_fetcher(self, fetcher: Fetcher, context: PluginContext | None = None) -> None:
        fname = getattr(fetcher, "__name__", "fetch")
        try:
            print(f"[PluginManager] running fetcher {fname}")
            result = await fetcher(context or self.context)
            print(f"[PluginManager] fetcher {fname} result type={type(result).__name__}")
            if result is None:
                return
            payloads = result if isinstance(result, list) else [result]
            for payload in payloads:
                if isinstance(payload, dict):
                    self.event_bus.emit(payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            import traceback
            print(f"[PluginManager] fetcher {fname} error: {exc}")
            traceback.print_exc()

    async def stop(self) -> None:
        self._started = False
        for plugin_id in list(self.loaded.keys()):
            await self.unload_plugin(plugin_id, _remove_loaded=False)
        self.loaded.clear()

    async def unload_plugin(self, plugin_id: str, _remove_loaded: bool = True) -> bool:
        loaded = self.loaded.get(plugin_id)
        if not loaded:
            return False
        tasks = list(loaded.daemon_tasks) + list(loaded.fetcher_tasks)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for daemon in loaded.daemons:
            try:
                await daemon.stop()
            except Exception:
                pass
        loaded.daemon_tasks.clear()
        loaded.fetcher_tasks.clear()
        if _remove_loaded:
            self.loaded.pop(plugin_id, None)
        return True

    async def remove_plugin(self, plugin_id: str) -> bool:
        await self.unload_plugin(plugin_id)
        path = self.plugins_dir / plugin_id
        try:
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as exc:
            print(f"[PluginManager] failed to remove plugin files {plugin_id}: {exc}")
            return False
        # Remove persisted settings/memory for a clean uninstall
        self.settings.pop(plugin_id, None)
        self._save_settings()
        self.plugin_memories.pop(plugin_id, None)
        try:
            mp = self._plugin_memory_path(plugin_id)
            if mp.exists():
                mp.unlink()
        except Exception:
            pass
        return True

    async def reload_plugin(self, plugin_id: str) -> bool:
        path = self.plugins_dir / plugin_id
        if not path.exists():
            return False
        await self.unload_plugin(plugin_id)
        manifest = self._read_manifest(path)
        if not manifest or not self._validate_structure(path):
            return False
        await self._load_plugin(path, manifest)
        return plugin_id in self.loaded

    # ---------- Settings ----------
    def _load_settings(self) -> None:
        if self.settings_path.exists():
            try:
                self.settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
            except Exception:
                self.settings = {}
        if not isinstance(self.settings, dict):
            self.settings = {}

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(
                json.dumps(self.settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[PluginManager] failed to save settings: {exc}")

    def get_plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        values = self.settings.get(plugin_id)
        if not isinstance(values, dict):
            values = {}
        manifest = None
        loaded = self.loaded.get(plugin_id)
        if loaded:
            manifest = loaded.manifest
        else:
            mpath = self.plugins_dir / plugin_id
            if mpath.exists():
                manifest = self._read_manifest(mpath)
        merged: dict[str, Any] = {}
        if manifest:
            for param in manifest.settings or []:
                key = str(param.get("key", "")).strip()
                if not key:
                    continue
                merged[key] = values.get(key, param.get("default"))
        for k, v in values.items():
            merged.setdefault(k, v)
        return merged

    def set_plugin_setting(self, plugin_id: str, key: str, value: Any) -> None:
        if plugin_id not in self.settings or not isinstance(self.settings.get(plugin_id), dict):
            self.settings[plugin_id] = {}
        self.settings[plugin_id][key] = value
        self._save_settings()
        self.context.data.setdefault("plugin_settings", {})[plugin_id] = self.get_plugin_settings(plugin_id)
        loaded = self.loaded.get(plugin_id)
        if loaded and loaded.context:
            loaded.context.data["settings"] = self.get_plugin_settings(plugin_id)

    def list_plugin_manifests(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for child in sorted(self.plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            m = self._read_manifest(child)
            if m:
                manifests.append(m)
        return manifests

    # ---------- Memory (persistent) ----------
    def _plugin_memory_path(self, plugin_id: str) -> Path:
        return self.memory_dir / f"{plugin_id}.json"

    def _load_shared_memory(self) -> None:
        if self.shared_memory_path.exists():
            try:
                data = json.loads(self.shared_memory_path.read_text(encoding="utf-8"))
                self.shared_memory = data if isinstance(data, dict) else {}
            except Exception:
                self.shared_memory = {}
        else:
            self.shared_memory = {}

    def save_shared_memory(self) -> None:
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self.shared_memory_path.write_text(
                json.dumps(self.shared_memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[PluginManager] failed to save shared memory: {exc}")

    def get_shared_memory(self) -> dict[str, Any]:
        return self.shared_memory

    def set_shared_memory(self, key: str, value: Any, save: bool = True) -> None:
        self.shared_memory[key] = value
        if save:
            self.save_shared_memory()

    def get_plugin_memory(self, plugin_id: str) -> dict[str, Any]:
        if plugin_id in self.plugin_memories:
            return self.plugin_memories[plugin_id]
        path = self._plugin_memory_path(plugin_id)
        mem: dict[str, Any] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                mem = data if isinstance(data, dict) else {}
            except Exception:
                mem = {}
        self.plugin_memories[plugin_id] = mem
        return mem

    def save_plugin_memory(self, plugin_id: str) -> None:
        mem = self.plugin_memories.get(plugin_id, {})
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self._plugin_memory_path(plugin_id).write_text(
                json.dumps(mem, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[PluginManager] failed to save memory for {plugin_id}: {exc}")

    def set_plugin_memory(self, plugin_id: str, key: str, value: Any, save: bool = True) -> None:
        mem = self.get_plugin_memory(plugin_id)
        mem[key] = value
        self.plugin_memories[plugin_id] = mem
        if save:
            self.save_plugin_memory(plugin_id)

    # ---------- Helpers ----------
    def _read_manifest(self, path: Path) -> PluginManifest | None:
        mf = path / "plugin.json"
        if not mf.exists():
            return None
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            plugin_id = str(data.get("id") or path.name)
            settings = data.get("settings") or []
            if not isinstance(settings, list):
                settings = []
            return PluginManifest(
                plugin_id=plugin_id,
                name=str(data.get("name") or plugin_id),
                version=str(data.get("version") or "0.1.0"),
                description=str(data.get("description") or ""),
                entrypoints=data.get("entrypoints") or {},
                settings=settings,
                path=path,
            )
        except Exception as exc:
            print(f"[PluginManager] bad manifest {mf}: {exc}")
            return None

    def _validate_structure(self, path: Path) -> bool:
        return all((path / sub).is_dir() for sub in REQUIRED_SUBFOLDERS)

    def _detect_plugin_root(self, extracted: Path) -> Path | None:
        # Direct
        if (extracted / "plugin.json").exists() and self._validate_structure(extracted):
            return extracted
        # Single top-level dir
        dirs = [p for p in extracted.iterdir() if p.is_dir()]
        if len(dirs) == 1:
            cand = dirs[0]
            if (cand / "plugin.json").exists() and self._validate_structure(cand):
                return cand
        # Search shallow
        for cand in extracted.rglob("plugin.json"):
            root = cand.parent
            if self._validate_structure(root):
                return root
        return None
