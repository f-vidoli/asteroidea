# Asteroidea

A desktop-only, cold-swappable plugin launcher built with Tauri v2 and vanilla TypeScript. The shell itself is minimal: the launcher UI, plugin manager, widgets, fetchers and daemons are all replaceable modules.

## Architecture

- **Rust trusted core** (`src-tauri/src/main.rs`): owns IPC, boot configuration, filesystem access, ZIP installation and the three-tier JSON storage. Path handling rejects traversal, absolute paths and symlinks.
- **TypeScript bootstrapper** (`src/core/bootstrapper.ts`): reads boot state, loads the configured launcher and plugin manager modules, mounts the UI and records boot diagnostics. With safe mode enabled, a failing launcher falls back to the core launcher.
- **Swappable modules**: `launcher.js` and `manager.js` are Vite entry points. Plugins can declare `provides: ["launcher"]` or `provides: ["plugin-manager"]` and be selected from Settings.
- **Plugin runtime** (`src/core/plugin_manager.ts`): discovers plugins, compiles declarative layouts, imports plugin modules, registers widgets/fetchers/daemons and manages intervals and AbortSignals.
- **Storage**: `private/<plugin>.json`, `settings.json` and `public.json` under `<app-data>/storage/`. Tiers are scoped by convention through the SDK; they are not a security boundary.
- **Layouts**: JSON or YAML node trees compiled by `src/core/layout/parser.ts`, with `${...}` bindings to `now`, `payload.*` and `memory.(private|settings|public).*`.

The app has four screens: **main**, **feed**, **settings** and **manager**. Widgets declare a `surface` and `slot` (`default`, `settings`, `manager`); fetchers can emit payloads with the same metadata, which auto-mounts matching widgets.

No plugins are bundled in this repository. `src/plugins/` is an empty runtime directory mapped into app resources; install plugins from a ZIP or a GitHub repository from the Manager screen, or scaffold one locally.

## Requirements

- Node.js 20+ and npm
- Rust 1.77+ with the Tauri v2 prerequisites for your platform
- Linux desktop (this project is intentionally desktop-only; no Android/iOS targets are configured)

## Getting started

```sh
npm install
npm run dev          # Vite frontend only, http://localhost:1420
npm run tauri dev    # full desktop app
```

Build and package:

```sh
npm run build        # typecheck + Vite build into dist/
npm run tauri build  # deb, rpm and AppImage bundles
```

Bundles are written to `src-tauri/target/release/bundle/`. On first launch the app creates `<app-data>/plugins/` and `<app-data>/storage/`, then writes boot diagnostics into `storage/settings.json` (`boot_ok`, `boot_error`).

## Configuration

`src-tauri/src/boot_config.json` is compiled into the binary; a user override is read from `<app-data>/boot_config.json` and written by the Settings screen.

| Field | Meaning |
| --- | --- |
| `active_launcher` | Module path for the launcher (`launcher.js` or `plugins/<id>/<entry>.js`) |
| `active_plugin_manager` | Module path for the plugin manager (`manager.js` or a plugin entry) |
| `fallback_launcher` | Launcher used when the active one fails in safe mode |
| `safe_mode` | Enable launcher fallback |
| `plugins_dir` | Plugin directory relative to app data (`plugins`) |

Runtime data lives under `~/.local/share/com.asteroidea.launcher/` on Linux. `ASTEROIDEA_PLUGINS_DIR` adds an additional plugin search root.

## Writing plugins

```sh
npm run plugin:new -- my_plugin   # scaffold into src/plugins/my_plugin
npm run plugin:check -- my_plugin # validate manifest, folders and layouts
npm run build                     # compile plugin modules into dist/plugins
npm run plugin:pack -- my_plugin  # create dist/plugins/my_plugin.zip
```

A plugin directory must contain `manifest.json` and all four standard folders: `widgets/`, `libraries/`, `fetchers/`, `daemons/`. The manifest declares `id`, `name`, `version`, optional `api_version`, `provides`, `layouts` and `entry` (default `index.ts`). The compiled module default-exports a `PluginModule` with optional `widgets`, `fetchers`, `daemons`, `activate` and `deactivate` members. Use the helpers exported by `src/sdk/index.ts` (`defineWidget`, `defineFetcher`, `defineDaemon`, `buildPayload`, `sharedChannel`, `definePlugin`).

Layouts and manifest/layout JSON/YAML files are copied into `dist/plugins/<id>/` at build time. Installed (ZIP/GitHub) plugins are loaded from app data with relative asset imports rewritten to origin URLs; bundled plugins are imported directly from `dist/`.

## Security and trust model

Plugins are **trusted code**, not sandboxed. They run in the webview with access to the same Tauri IPC commands as the core, and installing a plugin is equivalent to granting it full access to the app and its app-data storage. Storage tiers provide namespacing for convenience, not isolation. Only install plugins from sources you trust; `csp` is disabled so locally supplied plugin modules can be imported.

ZIP installation enforces a single plugin root, safe path components, no symlinks and size limits (10 MiB archive, 2 MiB per entry). Boot configuration module paths are restricted to core modules or `plugins/<safe-id>/<safe-file>.js` so a plugin cannot silently replace the launcher with an arbitrary path. Always review a plugin's source before installing it.

## Verification

```sh
npx tsc --noEmit
npm test
npm run plugin:check
npm run build
cargo fmt --check --manifest-path src-tauri/Cargo.toml
cargo check --manifest-path src-tauri/Cargo.toml --bin asteroidea
cargo test --manifest-path src-tauri/Cargo.toml --bin asteroidea
cargo clippy --manifest-path src-tauri/Cargo.toml --bin asteroidea
```

A headless smoke test can be run with `xvfb-run -a ./src-tauri/target/release/asteroidea`; check `storage/settings.json` for `boot_ok: true` and a null `boot_error`.

## License

Apache-2.0. See [LICENSE](LICENSE).
