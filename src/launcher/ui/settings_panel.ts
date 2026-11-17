import type { ApiClient, BootConfig, BootState, PluginManifest, PluginRecord } from '../../core/types';

export interface SettingsPanelOptions {
  api: ApiClient;
  boot: BootState;
  restart(): Promise<void>;
}

interface ModuleOption {
  value: string;
  label: string;
}

async function moduleOptions(api: ApiClient, role: 'launcher' | 'plugin-manager'): Promise<ModuleOption[]> {
  const options: ModuleOption[] = [
    role === 'launcher'
      ? { value: 'launcher.js', label: 'Default launcher' }
      : { value: 'manager.js', label: 'Default plugin manager' },
  ];
  const records = await api.invoke<PluginRecord[]>('list_plugins');
  for (const record of records) {
    try {
      const raw = await api.readPluginFile(record.id, 'manifest.json');
      const manifest = JSON.parse(raw) as PluginManifest;
      if (!Array.isArray(manifest.provides) || !manifest.provides.includes(role)) continue;
      const entry = (manifest.entry ?? 'index.ts').replace(/\.ts$/, '.js');
      options.push({ value: `plugins/${manifest.id}/${entry}`, label: manifest.name });
    } catch {
      continue;
    }
  }
  return options;
}

function createModuleSelect(
  api: ApiClient,
  role: 'launcher' | 'plugin-manager',
  label: string,
  current: string,
): { row: HTMLElement; select: HTMLSelectElement } {
  const row = document.createElement('label');
  row.className = 'panel-field';
  const name = document.createElement('span');
  name.textContent = label;
  const select = document.createElement('select');
  select.className = 'panel-select';
  const placeholder = document.createElement('option');
  placeholder.value = current;
  placeholder.textContent = 'Loading modules...';
  select.append(placeholder);
  row.append(name, select);

  void moduleOptions(api, role)
    .then((options) => {
      select.replaceChildren();
      const seen = new Set<string>();
      for (const option of options) {
        if (seen.has(option.value)) continue;
        seen.add(option.value);
        const element = document.createElement('option');
        element.value = option.value;
        element.textContent = option.label;
        select.append(element);
      }
      if (!seen.has(current)) {
        const fallback = document.createElement('option');
        fallback.value = current;
        fallback.textContent = 'Current module';
        select.append(fallback);
      }
      select.value = current;
      void api.invoke<void>('storage_write', {
        tier: 'settings',
        owner: 'global',
        key: `ui.${role}_options`,
        value: options.map((option) => option.label),
      });
    })
    .catch(() => {
      select.replaceChildren();
      const fallback = document.createElement('option');
      fallback.value = current;
      fallback.textContent = 'Current module';
      select.append(fallback);
    });

  return { row, select };
}

export function createSettingsPanel(options: SettingsPanelOptions): HTMLElement {
  const { api, boot, restart } = options;
  const panel = document.createElement('section');
  panel.className = 'panel';
  const title = document.createElement('h2');
  title.textContent = 'Settings';
  panel.append(title);

  const launcher = createModuleSelect(api, 'launcher', 'Active launcher', boot.config.active_launcher);
  const manager = createModuleSelect(api, 'plugin-manager', 'Active plugin manager', boot.config.active_plugin_manager);
  panel.append(launcher.row, manager.row);

  const safeRow = document.createElement('label');
  safeRow.className = 'panel-field panel-check';
  const safeInput = document.createElement('input');
  safeInput.type = 'checkbox';
  safeInput.checked = boot.config.safe_mode;
  safeRow.append(safeInput, document.createTextNode('Safe mode'));
  panel.append(safeRow);

  const status = document.createElement('p');
  status.className = 'panel-status';
  status.textContent = 'Choose the active launcher and plugin manager.';
  panel.append(status);

  const actions = document.createElement('div');
  actions.className = 'panel-actions';
  const save = document.createElement('button');
  save.type = 'button';
  save.textContent = 'Save';
  const saveRestart = document.createElement('button');
  saveRestart.type = 'button';
  saveRestart.textContent = 'Save & restart';
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.textContent = 'Reset defaults';
  actions.append(save, saveRestart, reset);
  panel.append(actions);

  const collect = (): BootConfig => ({
    active_launcher: launcher.select.value || 'launcher.js',
    active_plugin_manager: manager.select.value || 'manager.js',
    fallback_launcher: boot.config.fallback_launcher ?? 'launcher.js',
    safe_mode: safeInput.checked,
    plugins_dir: boot.config.plugins_dir,
  });

  const apply = async (patch: Partial<BootConfig>): Promise<BootConfig> => {
    const updated = await api.invoke<BootConfig>('set_boot_config', { patch });
    Object.assign(boot.config, updated);
    const needsRestart = 'active_launcher' in patch || 'active_plugin_manager' in patch;
    status.textContent = needsRestart
      ? 'Boot configuration saved. Restart to apply module changes.'
      : 'Boot configuration saved.';
    return updated;
  };

  save.addEventListener('click', () => {
    void apply(collect()).catch((error: unknown) => {
      status.textContent = `Save failed: ${error instanceof Error ? error.message : String(error)}`;
    });
  });

  saveRestart.addEventListener('click', () => {
    void apply(collect())
      .then(restart)
      .catch((error: unknown) => {
        status.textContent = `Restart failed: ${error instanceof Error ? error.message : String(error)}`;
      });
  });

  reset.addEventListener('click', () => {
    launcher.select.value = 'launcher.js';
    manager.select.value = 'manager.js';
    safeInput.checked = true;
    void apply({
      active_launcher: 'launcher.js',
      active_plugin_manager: 'manager.js',
      fallback_launcher: 'launcher.js',
      safe_mode: true,
    }).catch((error: unknown) => {
      status.textContent = `Reset failed: ${error instanceof Error ? error.message : String(error)}`;
    });
  });

  return panel;
}
