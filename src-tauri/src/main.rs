#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::{
    collections::BTreeMap,
    fs,
    io::{Cursor, Read},
    path::{Component, Path, PathBuf},
    sync::Mutex,
};
use tauri::{AppHandle, Manager, State};
use zip::ZipArchive;

const DEFAULT_BOOT_CONFIG: &str = include_str!("boot_config.json");
const STANDARD_FOLDERS: [&str; 4] = ["widgets", "libraries", "fetchers", "daemons"];
const MAX_ARCHIVE_BYTES: u64 = 10 * 1024 * 1024;
const MAX_ENTRY_BYTES: u64 = 2 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize)]
struct BootConfig {
    active_launcher: String,
    active_plugin_manager: String,
    #[serde(default = "default_plugins_dir")]
    plugins_dir: String,
    #[serde(default)]
    safe_mode: bool,
    #[serde(default)]
    fallback_launcher: Option<String>,
}

fn default_plugins_dir() -> String {
    "plugins".to_owned()
}

#[derive(Debug, Serialize)]
struct BootStateDto {
    config: BootConfig,
    plugins_root: String,
    app_data_dir: String,
}

#[derive(Debug, Serialize)]
struct PluginRecord {
    id: String,
    folders: Vec<String>,
    path: String,
    removable: bool,
}

#[derive(Debug, Serialize)]
struct StorageDump {
    private: BTreeMap<String, Value>,
    settings: Value,
    public: Value,
}

struct AppState {
    config: Mutex<BootConfig>,
    app_data_dir: PathBuf,
    resource_dir: PathBuf,
}

fn default_config() -> BootConfig {
    serde_json::from_str(DEFAULT_BOOT_CONFIG).expect("compiled boot_config.json must be valid")
}

fn read_boot_config(app_data_dir: &Path) -> BootConfig {
    let override_path = app_data_dir.join("boot_config.json");
    match fs::read_to_string(&override_path) {
        Ok(text) => serde_json::from_str(&text)
            .ok()
            .and_then(|config| validated_config(config).ok())
            .unwrap_or_else(default_config),
        Err(_) => default_config(),
    }
}

fn validated_config(config: BootConfig) -> Result<BootConfig, String> {
    if !is_safe_module_path(&config.active_launcher) {
        return Err(format!(
            "invalid active_launcher: {}",
            config.active_launcher
        ));
    }
    if !is_safe_module_path(&config.active_plugin_manager) {
        return Err(format!(
            "invalid active_plugin_manager: {}",
            config.active_plugin_manager
        ));
    }
    if let Some(fallback) = &config.fallback_launcher {
        if !is_safe_module_path(fallback) {
            return Err(format!("invalid fallback_launcher: {fallback}"));
        }
    }
    if !is_safe_plugins_dir(&config.plugins_dir) {
        return Err(format!("invalid plugins_dir: {}", config.plugins_dir));
    }
    Ok(config)
}

fn is_safe_module_path(value: &str) -> bool {
    if matches!(value, "launcher.js" | "manager.js") {
        return true;
    }
    let Some(rest) = value.strip_prefix("plugins/") else {
        return false;
    };
    let mut parts = rest.split('/');
    let id = parts.next().unwrap_or_default();
    let entry = parts.next().unwrap_or_default();
    parts.next().is_none()
        && is_safe_segment(id)
        && is_safe_segment(entry)
        && entry.ends_with(".js")
}

fn is_safe_plugins_dir(value: &str) -> bool {
    !value.is_empty() && value.split(['/', '\\']).all(is_safe_segment)
}

fn resolve_root(base: &Path, value: &str) -> PathBuf {
    let path = Path::new(value);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    }
}

fn is_safe_segment(segment: &str) -> bool {
    !segment.is_empty()
        && segment != "."
        && segment != ".."
        && !segment.contains('/')
        && !segment.contains('\\')
        && segment
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-' | '.'))
}

fn safe_join(root: &Path, plugin_id: &str, relative: &str) -> Result<PathBuf, String> {
    if !is_safe_segment(plugin_id) {
        return Err(format!("invalid plugin id: {plugin_id}"));
    }
    let relative_path = Path::new(relative);
    if relative_path.is_absolute() {
        return Err("absolute plugin paths are not allowed".to_owned());
    }
    let mut target = root.join(plugin_id);
    for component in relative_path.components() {
        match component {
            Component::Normal(segment) => {
                let segment = segment.to_string_lossy();
                if !is_safe_segment(&segment) {
                    return Err(format!("unsafe path component: {segment}"));
                }
                target.push(segment.as_ref());
            }
            _ => return Err(format!("unsafe plugin path: {relative}")),
        }
    }
    Ok(target)
}

fn plugin_roots(state: &AppState) -> Vec<PathBuf> {
    let plugins_dir = state
        .config
        .lock()
        .map(|config| config.plugins_dir.clone())
        .unwrap_or_else(|_| "plugins".to_owned());
    let mut roots = vec![
        resolve_root(&state.app_data_dir, &plugins_dir),
        state.resource_dir.join("plugins"),
        state.resource_dir.join("_up_/src/plugins"),
        state.resource_dir.join("src/plugins"),
        state.resource_dir.join("../src/plugins"),
        state.resource_dir.join("../../src/plugins"),
    ];
    if let Ok(current_dir) = std::env::current_dir() {
        roots.push(current_dir.join("src/plugins"));
        roots.push(current_dir.join("../src/plugins"));
    }
    if let Ok(override_dir) = std::env::var("ASTEROIDEA_PLUGINS_DIR") {
        roots.push(resolve_root(&state.app_data_dir, &override_dir));
    }
    roots.dedup();
    roots
}

fn storage_path(app_data_dir: &Path, tier: &str, owner: &str) -> Result<PathBuf, String> {
    if !matches!(tier, "private" | "settings" | "public") {
        return Err(format!("unknown memory tier: {tier}"));
    }
    let base = app_data_dir.join("storage");
    match tier {
        "private" => {
            if !is_safe_segment(owner) {
                return Err(format!("invalid plugin id: {owner}"));
            }
            Ok(base.join("private").join(format!("{owner}.json")))
        }
        "settings" => Ok(base.join("settings.json")),
        _ => Ok(base.join("public.json")),
    }
}

fn read_json_file(path: &Path, default: Value) -> Result<Value, String> {
    match fs::read_to_string(path) {
        Ok(text) if !text.trim().is_empty() => serde_json::from_str(&text)
            .map_err(|error| format!("invalid JSON in {}: {error}", path.display())),
        _ => Ok(default),
    }
}

fn write_json_file(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let temp = path.with_extension("json.tmp");
    let text = serde_json::to_string_pretty(value).map_err(|error| error.to_string())?;
    fs::write(&temp, text).map_err(|error| error.to_string())?;
    fs::rename(&temp, path).map_err(|error| error.to_string())
}

#[tauri::command]
fn boot_state(state: State<'_, AppState>) -> Result<BootStateDto, String> {
    let config = state
        .config
        .lock()
        .map_err(|error| error.to_string())?
        .clone();
    Ok(BootStateDto {
        config,
        plugins_root: plugin_roots(&state)
            .first()
            .map(|path| path.to_string_lossy().to_string())
            .unwrap_or_default(),
        app_data_dir: state.app_data_dir.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn list_plugins(state: State<'_, AppState>) -> Result<Vec<PluginRecord>, String> {
    let mut found: BTreeMap<String, PluginRecord> = BTreeMap::new();
    let local_root = resolve_root(
        &state.app_data_dir,
        &state
            .config
            .lock()
            .map_err(|error| error.to_string())?
            .plugins_dir,
    );
    let canonical_local = fs::canonicalize(&local_root).ok();
    for root in plugin_roots(&state) {
        let entries = match fs::read_dir(&root) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let id = entry.file_name().to_string_lossy().to_string();
            if !is_safe_segment(&id) || found.contains_key(&id) {
                continue;
            }
            let folders = STANDARD_FOLDERS
                .iter()
                .filter(|folder| path.join(folder).is_dir())
                .map(|folder| (*folder).to_owned())
                .collect::<Vec<_>>();
            if folders.len() == STANDARD_FOLDERS.len() {
                let removable = canonical_local
                    .as_ref()
                    .and_then(|local| {
                        fs::canonicalize(&path)
                            .ok()
                            .map(|path| path.starts_with(local))
                    })
                    .unwrap_or(false);
                found.insert(
                    id.clone(),
                    PluginRecord {
                        id,
                        folders,
                        path: path.to_string_lossy().to_string(),
                        removable,
                    },
                );
            }
        }
    }
    Ok(found.into_values().collect())
}

#[tauri::command]
fn read_plugin_file(
    plugin_id: String,
    relative_path: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    for root in plugin_roots(&state) {
        if let Ok(path) = safe_join(&root, &plugin_id, &relative_path) {
            if let Ok(bytes) = fs::read(&path) {
                return String::from_utf8(bytes).map_err(|error| error.to_string());
            }
        }
    }
    Err(format!(
        "plugin file not found: {plugin_id}/{relative_path}"
    ))
}

#[tauri::command]
fn storage_dump(state: State<'_, AppState>) -> Result<StorageDump, String> {
    let private_dir = state.app_data_dir.join("storage/private");
    let mut private = BTreeMap::new();
    if let Ok(entries) = fs::read_dir(&private_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let id = path
                .file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or_default();
            private.insert(
                id.to_owned(),
                read_json_file(&path, Value::Object(Map::new()))?,
            );
        }
    }
    Ok(StorageDump {
        private,
        settings: read_json_file(
            &storage_path(&state.app_data_dir, "settings", "global")?,
            Value::Object(Map::new()),
        )?,
        public: read_json_file(
            &storage_path(&state.app_data_dir, "public", "global")?,
            Value::Object(Map::new()),
        )?,
    })
}

#[tauri::command]
fn storage_read(
    tier: String,
    owner: String,
    key: String,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    if !is_safe_segment(&key) {
        return Err(format!("invalid storage key: {key}"));
    }
    let path = storage_path(&state.app_data_dir, &tier, &owner)?;
    let document = read_json_file(&path, Value::Object(Map::new()))?;
    Ok(document.get(&key).cloned().unwrap_or(Value::Null))
}

#[tauri::command]
fn storage_write(
    tier: String,
    owner: String,
    key: String,
    value: Value,
    state: State<'_, AppState>,
) -> Result<(), String> {
    if !is_safe_segment(&key) {
        return Err(format!("invalid storage key: {key}"));
    }
    let path = storage_path(&state.app_data_dir, &tier, &owner)?;
    let mut document = read_json_file(&path, Value::Object(Map::new()))?;
    let object = document
        .as_object_mut()
        .ok_or_else(|| "storage root must be an object".to_owned())?;
    object.insert(key, value);
    write_json_file(&path, &document)
}

#[tauri::command]
fn storage_remove(
    tier: String,
    owner: String,
    key: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    if !is_safe_segment(&key) {
        return Err(format!("invalid storage key: {key}"));
    }
    let path = storage_path(&state.app_data_dir, &tier, &owner)?;
    let mut document = read_json_file(&path, Value::Object(Map::new()))?;
    if let Some(object) = document.as_object_mut() {
        object.remove(&key);
    }
    write_json_file(&path, &document)
}

#[tauri::command]
fn install_zip(bytes: Vec<u8>, state: State<'_, AppState>) -> Result<String, String> {
    if bytes.len() as u64 > MAX_ARCHIVE_BYTES {
        return Err("archive exceeds size limit".to_owned());
    }
    let mut archive = ZipArchive::new(Cursor::new(bytes)).map_err(|error| error.to_string())?;
    let root = resolve_root(
        &state.app_data_dir,
        &state
            .config
            .lock()
            .map_err(|error| error.to_string())?
            .plugins_dir,
    );
    fs::create_dir_all(&root).map_err(|error| error.to_string())?;
    let canonical_root = fs::canonicalize(&root).map_err(|error| error.to_string())?;
    let mut plugin_id: Option<String> = None;
    let mut total = 0_u64;

    for index in 0..archive.len() {
        let entry = archive.by_index(index).map_err(|error| error.to_string())?;
        let enclosed = entry
            .enclosed_name()
            .ok_or_else(|| "unsafe archive entry".to_owned())?;
        let parts = enclosed.components().collect::<Vec<_>>();
        let first = parts
            .first()
            .and_then(|component| match component {
                Component::Normal(value) => value.to_str(),
                _ => None,
            })
            .ok_or_else(|| "archive entry outside plugin root".to_owned())?;
        let id = plugin_id.get_or_insert_with(|| first.to_owned());
        if id.as_str() != first {
            return Err("archive must contain a single plugin root".to_owned());
        }
        if !is_safe_segment(id) {
            return Err(format!("invalid plugin id in archive: {id}"));
        }
        if let Some(mode) = entry.unix_mode() {
            if mode & 0o170000 == 0o120000 {
                return Err("symlinks are not allowed in plugin archives".to_owned());
            }
        }
        let destination = canonical_root.join(enclosed);
        if !destination.starts_with(&canonical_root) {
            return Err("archive entry escapes plugins directory".to_owned());
        }
        if entry.is_dir() {
            fs::create_dir_all(&destination).map_err(|error| error.to_string())?;
            continue;
        }
        let declared_size = entry.size();
        if declared_size > MAX_ENTRY_BYTES {
            return Err("archive entry exceeds size limit".to_owned());
        }
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        let mut content = Vec::with_capacity(declared_size as usize);
        let mut limited = entry.take(MAX_ENTRY_BYTES + 1);
        limited
            .read_to_end(&mut content)
            .map_err(|error| error.to_string())?;
        if content.len() as u64 > MAX_ENTRY_BYTES {
            return Err("archive entry exceeds size limit".to_owned());
        }
        total = total.saturating_add(content.len() as u64);
        if total > MAX_ARCHIVE_BYTES {
            return Err("archive exceeds size limit".to_owned());
        }
        fs::write(&destination, content).map_err(|error| error.to_string())?;
    }

    let id = plugin_id.ok_or_else(|| "archive is empty".to_owned())?;
    let plugin_dir = canonical_root.join(&id);
    let missing = STANDARD_FOLDERS
        .iter()
        .filter(|folder| !plugin_dir.join(folder).is_dir())
        .map(|folder| (*folder).to_owned())
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!(
            "plugin package is missing folders: {}",
            missing.join(", ")
        ));
    }
    Ok(id)
}

fn remove_plugin_dir(root: &Path, plugin_id: &str) -> Result<(), String> {
    if !is_safe_segment(plugin_id) {
        return Err(format!("invalid plugin id: {plugin_id}"));
    }
    fs::create_dir_all(root).map_err(|error| error.to_string())?;
    let canonical_root = fs::canonicalize(root).map_err(|error| error.to_string())?;
    let target = canonical_root.join(plugin_id);
    let canonical_target =
        fs::canonicalize(&target).map_err(|_| "plugin is not installed locally".to_owned())?;
    if canonical_target == canonical_root || !canonical_target.starts_with(&canonical_root) {
        return Err("plugin path escapes plugins directory".to_owned());
    }
    if canonical_target.is_dir() {
        fs::remove_dir_all(&canonical_target).map_err(|error| error.to_string())?;
    } else {
        fs::remove_file(&canonical_target).map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn uninstall_plugin(plugin_id: String, state: State<'_, AppState>) -> Result<(), String> {
    let root = resolve_root(
        &state.app_data_dir,
        &state
            .config
            .lock()
            .map_err(|error| error.to_string())?
            .plugins_dir,
    );
    remove_plugin_dir(&root, &plugin_id)
}

#[tauri::command]
fn set_boot_config(patch: Value, state: State<'_, AppState>) -> Result<BootConfig, String> {
    let current = read_boot_config(&state.app_data_dir);
    let mut merged = serde_json::to_value(&current).map_err(|error| error.to_string())?;
    let patch_object = patch
        .as_object()
        .ok_or_else(|| "boot config patch must be an object".to_owned())?;
    let merged_object = merged
        .as_object_mut()
        .ok_or_else(|| "boot config must be an object".to_owned())?;
    for (key, value) in patch_object {
        merged_object.insert(key.clone(), value.clone());
    }
    let config: BootConfig = serde_json::from_value(merged).map_err(|error| error.to_string())?;
    let config = validated_config(config)?;
    write_json_file(
        &state.app_data_dir.join("boot_config.json"),
        &serde_json::to_value(&config).map_err(|error| error.to_string())?,
    )?;
    let mut stored = state.config.lock().map_err(|error| error.to_string())?;
    *stored = config.clone();
    Ok(config)
}

#[tauri::command]
fn restart_app(app: AppHandle) {
    app.restart()
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let app_data_dir = app.path().app_data_dir()?;
            let resource_dir = app.path().resource_dir()?;
            fs::create_dir_all(app_data_dir.join("plugins"))?;
            fs::create_dir_all(app_data_dir.join("storage/private"))?;
            let config = read_boot_config(&app_data_dir);
            app.manage(AppState {
                config: Mutex::new(config),
                app_data_dir,
                resource_dir,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            boot_state,
            list_plugins,
            read_plugin_file,
            storage_dump,
            storage_read,
            storage_write,
            storage_remove,
            install_zip,
            uninstall_plugin,
            set_boot_config,
            restart_app
        ])
        .run(tauri::generate_context!())
        .expect("failed to start application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_valid() {
        let config = default_config();
        assert_eq!(config.active_launcher, "launcher.js");
        assert_eq!(config.active_plugin_manager, "manager.js");
        assert_eq!(config.fallback_launcher.as_deref(), Some("launcher.js"));
        assert_eq!(config.plugins_dir, "plugins");
        assert!(config.safe_mode);
    }

    #[test]
    fn root_resolution_handles_relative_and_absolute_paths() {
        let base = Path::new("/tmp/app-data");
        assert_eq!(
            resolve_root(base, "plugins"),
            PathBuf::from("/tmp/app-data/plugins")
        );
        assert_eq!(
            resolve_root(base, "/opt/plugins"),
            PathBuf::from("/opt/plugins")
        );
    }

    #[test]
    fn unsafe_ids_and_paths_are_rejected() {
        assert!(!is_safe_segment(".."));
        assert!(!is_safe_segment("../evil"));
        assert!(safe_join(Path::new("/plugins"), "clock", "../../etc/passwd").is_err());
        assert!(safe_join(Path::new("/plugins"), "clock", "/etc/passwd").is_err());
        assert!(safe_join(Path::new("/plugins"), "clock", "widgets/layout.json").is_ok());
    }

    #[test]
    fn module_paths_and_plugin_dirs_are_restricted() {
        assert!(is_safe_module_path("launcher.js"));
        assert!(is_safe_module_path("manager.js"));
        assert!(is_safe_module_path("plugins/my_plugin/index.js"));
        assert!(!is_safe_module_path("../../evil.js"));
        assert!(!is_safe_module_path("plugins/my_plugin/../../evil.js"));
        assert!(!is_safe_module_path("plugins/my_plugin/index.ts"));
        assert!(!is_safe_module_path("/opt/evil.js"));
        assert!(is_safe_plugins_dir("plugins"));
        assert!(is_safe_plugins_dir("data/plugins"));
        assert!(!is_safe_plugins_dir("/tmp/plugins"));
        assert!(!is_safe_plugins_dir("../plugins"));
        assert!(validated_config(default_config()).is_ok());
        let mut invalid = default_config();
        invalid.active_launcher = "../../evil.js".to_owned();
        assert!(validated_config(invalid).is_err());
    }

    #[test]
    fn storage_paths_are_scoped_by_tier_and_owner() {
        let base = Path::new("/tmp/data");
        assert_eq!(
            storage_path(base, "private", "clock").unwrap(),
            base.join("storage/private/clock.json")
        );
        assert_eq!(
            storage_path(base, "public", "global").unwrap(),
            base.join("storage/public.json")
        );
        assert!(storage_path(base, "unknown", "clock").is_err());
        assert!(storage_path(base, "private", "../evil").is_err());
    }

    #[test]
    fn plugin_directories_can_be_removed_safely() {
        let base = std::env::temp_dir().join(format!(
            "asteroidea-uninstall-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let plugin = base.join("sample");
        fs::create_dir_all(&plugin).unwrap();
        fs::write(plugin.join("manifest.json"), "{}").unwrap();

        assert!(remove_plugin_dir(&base, "../escape").is_err());
        assert!(remove_plugin_dir(&base, "missing").is_err());
        remove_plugin_dir(&base, "sample").unwrap();
        assert!(!plugin.exists());
        fs::remove_dir_all(&base).ok();
    }
}
