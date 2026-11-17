# Asteroidea

Modular, asynchronous Kivy desktop application (Buildozer-ready for Android) with a plugin-driven architecture.

## Pillars

1. **Widget Library / Registry** (`core/widget_registry.py`)  
   Standard custom Kivy widgets can be registered dynamically by plugins (explicit `register_widgets` hook and/or auto-discovery of `kivy.uix.widget.Widget` subclasses).

2. **Plugin Manager** (`core/plugin_manager.py`, `core/plugin_api.py`)  
   Core manager ingests plugins from local `.zip` files or GitHub repositories (HTTP archive download, no `git` CLI).  
   Each plugin directory must contain:
   - `plugin.json` (manifest: `id`, `name`, `version`, ...)
   - `widgets/` (Kivy UI components)
   - `libraries/` (Python helper packages)
   - `fetchers/` (async functions that fetch/generate content)
   - `daemons/` (background tasks/processes)

   *Note:* a swappable (startup-time, non-hot) plugin-provided Plugin Manager is intentionally deferred; the app is routed through the `IPluginManager` contract/hook points for a future addition.

3. **Reader** (`ui/reader.py`, `ui/screens.py`, `ui/plugin_settings.py`)  
   Dual-screen interface with a top icon navigation bar toggling **Main**, **Feed**, and **Settings**. Each content screen contains a `ScrollView` with a dynamic vertical list. JSON payloads are parsed and the corresponding registered widget is instantiated and injected into the target screen. The Settings page includes an in-app Plugin Manager (install local zip / GitHub repo, reload/remove with confirmation) and renders editable parameters or custom settings widgets declared in each plugin's `plugin.json`. The UI uses a two-tone terminal theme (background `#141410`, primary `#F7D142`) with outlined elements and a monospace font.

## Async runtime

- Kivy runs integrated with Python `asyncio` (`asyncio.run(app.app_main())` / `App.async_run(async_lib="asyncio")`).
- Fetchers and daemons execute as non-blocking asyncio tasks.
- UI mutations are dispatched on the Kivy main thread via a Clock-scheduled event bus bridge.

## Payload schema

Fetchers/daemons emit payloads (dict or list of dicts):

```json
{
  "screen": "main",
  "widget_type": "TextCard",
  "data": {"title": "...", "body": "..."},
  "id": "optional-stable-id"
}
```

- `screen`: `"main"` or `"feed"`
- `widget_type`: name registered in the widget registry
- `data`: kwargs passed to the widget factory/constructor
- `id` (optional): if provided, replaces the existing widget with the same id in that screen

## Project structure

```text
.
├── main.py
├── requirements.txt
├── buildozer.spec
├── core/
│   ├── app.py              # app wiring & async lifecycle
│   ├── event_bus.py        # async queue + UI-thread dispatch
│   ├── plugin_api.py       # contracts/interfaces (future manager hook)
│   ├── plugin_manager.py   # core ingest/validate/load/start/stop + persistence
│   └── widget_registry.py  # dynamic widget registry
├── ui/
│   ├── reader.py           # top icon nav + payload injection
│   ├── screens.py          # Main/Feed ScrollView + dynamic lists
│   └── plugin_settings.py  # plugin parameter/custom settings UI from manifests
└── plugins/
    ├── cache/              # downloaded archives/cache
    ├── settings.json       # persisted plugin settings (created at runtime)
    ├── memory/             # persisted plugin memory (per-plugin + shared, runtime)
    └── installed/
        ├── rss_feed/       # RSS feed plugin (custom feed/settings widgets)
        └── weather_home/   # next-5-hours weather home widget
```

## Run (desktop)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

UI is built with pure **Kivy** widgets (no KivyMD dependency). Plugins can register any Kivy `Widget` subclass/factory in the shared registry.

Bundled plugins: `rss_feed` (RSS/Atom fetch + refresh daemon, custom settings widget) and `weather_home` (Open-Meteo next 5 hours). Install/load/remove plugins in-app from **Settings → Plugin Manager** (local zip path or GitHub `owner/repo@ref`); reload/remove per plugin and settings/memory persist across restarts.

## Install plugins

- **Local zip:** ensure the archive contains a plugin root with `plugin.json` and the four required folders, then install programmatically (e.g. from a REPL/script):
  ```python
  import asyncio
  from pathlib import Path
  from core.app import AsteroideaApp
  app = AsteroideaApp(Path('.'))
  asyncio.run(app.plugin_manager.install_from_zip('path/to/plugin.zip'))
  ```
- **GitHub:** `install_from_github('owner/repo', ref='main')` downloads the branch archive via HTTPS into `plugins/cache/` and installs it.

Installed plugins in `plugins/installed/` are discovered and loaded on startup.

## Buildozer (Android)

A starter `buildozer.spec` is included (Kivy, pure-Python). Java 17 is required; newer JDKs break Gradle.

```bash
pip install buildozer cython
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 PATH="$JAVA_HOME/bin:$PATH" \
    buildozer -v android debug
```

python-for-android sometimes needs two local workarounds (corrupted bootstrap `pip` venv and Android-only `charset-normalizer` wheels). The script below applies them idempotently; run it after the first build attempt has downloaded p4a, then rebuild:

```bash
python scripts/apply_p4a_patches.py
```

The APK is written to `bin/asteroidea-*-debug.apk`.

Notes: runtime plugin install/download uses app storage and requires network permission for GitHub fetch (`android.permissions = INTERNET` is set). Prefer pure-Python plugin dependencies for Android; compiled deps require python-for-android recipes. Dynamic import of plugin code from app storage is supported on Android with care; iOS has additional restrictions (not a primary target here).

## Creating a plugin

Minimal layout:

```text
my_plugin/
  plugin.json
  widgets/__init__.py
  widgets/my_widget.py      # Widget subclass and/or register_widgets(registry)
  libraries/__init__.py
  libraries/helpers.py
  fetchers/__init__.py
  fetchers/my_fetcher.py    # async def fetch(context) -> dict|list[dict]
  daemons/__init__.py
  daemons/my_daemon.py      # subclass of core.plugin_api.BaseDaemon
```

### Manifest settings

Plugins can declare configurable parameters in `plugin.json` under `settings`:

```json
"settings": [
  {"key": "enabled", "type": "bool", "label": "Enable plugin output", "default": true},
  {"key": "ticker_interval", "type": "int", "label": "Ticker interval (seconds)", "default": 5},
  {"key": "card_prefix", "type": "string", "label": "Card title prefix", "default": "Sample"}
]
```

Supported types: `bool`, `string`, `int`/`float`, `choice` (with `options`). Values are persisted to `plugins/settings.json` and exposed to plugins via `context.app.plugin_manager.get_plugin_settings(plugin_id)` (and `context.data["plugin_settings"]`/`context.data["settings"]` at load time).

A plugin may also declare `"settings_widget": "WidgetType"` in `plugin.json` to provide a custom settings UI widget (registered from its `widgets/`); `ui/plugin_settings.py` will render it instead of the auto form.

### Persistence & memory

- **Settings:** saved in `plugins/settings.json` and reloaded on startup.
- **Plugins:** installed plugin folders under `plugins/installed/` are discovered/loaded on startup (manager supports local zip and GitHub HTTP archive ingest).
- **Per-plugin memory:** persisted in `plugins/memory/<plugin_id>.json` (`context.get_memory() / set_memory() / save_memory()` or `plugin_manager.get_plugin_memory`).
- **Shared memory:** persisted in `plugins/memory/shared.json` for cross-plugin data (`context.get_shared_memory() / set_shared_memory()` or `plugin_manager.get_shared_memory`).

See `plugins/installed/rss_feed/` and `plugins/installed/weather_home/` for working examples.

## License

MIT © 2026 Federico Vidoli. See [LICENSE](LICENSE).
