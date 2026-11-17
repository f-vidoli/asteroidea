import { PluginBus } from './plugin_bus';
import { createApiClient } from './rpc';
import { StorageEngine } from './storage_engine';
import { SCREEN_TARGETS, type BootState } from './types';
import type { PluginManager, PluginManagerModule } from './plugin_manager';
import type { LauncherModule } from '../launcher/index';

const DEV_MODULE_PATHS: Record<string, string> = {
  'launcher.js': '/src/launcher/index.ts',
  'manager.js': '/src/core/plugin_manager.ts',
};

async function importModule<T>(path: string, dev: boolean): Promise<T> {
  const url = dev
    ? path.startsWith('plugins/')
      ? `/src/${path.replace(/\.js$/, '.ts')}`
      : (DEV_MODULE_PATHS[path] ?? `/${path.replace(/\.js$/, '.ts')}`)
    : `/${path}`;
  return (await import(/* @vite-ignore */ url)) as T;
}

interface LauncherEntrypoint {
  createLauncher(options: {
    api: ReturnType<typeof createApiClient>;
    storage: StorageEngine;
    bus: PluginBus;
    boot: BootState;
    manager: PluginManager;
    refreshFetchers(): void;
  }): LauncherModule;
}

function renderError(root: HTMLElement, api: ReturnType<typeof createApiClient>, error: unknown): void {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  void api.invoke<void>('storage_write', {
    tier: 'settings',
    owner: 'global',
    key: 'boot_ok',
    value: false,
  });
  void api.invoke<void>('storage_write', {
    tier: 'settings',
    owner: 'global',
    key: 'boot_error',
    value: message,
  });
  const panel = document.createElement('div');
  panel.className = 'boot-error';
  panel.textContent = `Bootstrap failed\n${message}`;
  root.replaceChildren(panel);
}

export async function bootstrap(): Promise<void> {
  const root = document.getElementById('app');
  if (!root) return;
  const api = createApiClient();
  let boot: BootState | undefined;

  try {
    boot = await api.invoke<BootState>('boot_state');
    const dev = import.meta.env.DEV;
    const storage = await StorageEngine.load(api);
    const bus = new PluginBus();
    let managerModule: PluginManagerModule;
    try {
      managerModule = await importModule<PluginManagerModule>(boot.config.active_plugin_manager, dev);
    } catch (error) {
      if (!boot.config.safe_mode) throw error;
      managerModule = await importModule<PluginManagerModule>('manager.js', dev);
    }
    const manager: PluginManager = managerModule.createManager({ api, bus, storage, dev });

    let launcherEntrypoint: LauncherEntrypoint;
    try {
      launcherEntrypoint = await importModule<LauncherEntrypoint>(boot.config.active_launcher, dev);
    } catch (error) {
      if (!boot.config.safe_mode || !boot.config.fallback_launcher) throw error;
      launcherEntrypoint = await importModule<LauncherEntrypoint>(boot.config.fallback_launcher, dev);
    }

    const launcher = launcherEntrypoint.createLauncher({
      api,
      storage,
      bus,
      boot,
      manager,
      refreshFetchers: () => manager.refreshFetchers(),
    });
    launcher.mount(root);
    await manager.discover();
    await api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'screens',
      value: Object.values(SCREEN_TARGETS),
    });
    await api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'widget_count',
      value: bus.widgets().length,
    });
    await api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'widget_subscriptions',
      value: bus
        .widgets()
        .filter((definition) => definition.surface !== undefined)
        .map((definition) => `${definition.owner ?? 'core'}:${definition.name}@${definition.surface}:${definition.slot ?? 'default'}`),
    });
    await api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'boot_ok',
      value: true,
    });
    await api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'boot_error',
      value: null,
    });
  } catch (error) {
    renderError(root, api, error);
  }
}
