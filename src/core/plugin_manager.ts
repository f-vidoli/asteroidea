import { createPluginContext, type DisposableContext } from './context';
import { parseLayout } from './layout/parser';
import type { StorageEngine } from './storage_engine';
import {
  isFetcherPayload,
  pluginId,
  type ApiClient,
  type DaemonContext,
  type DaemonDefinition,
  type FetcherContext,
  type FetcherDefinition,
  type PluginBus,
  type PluginContext,
  type PluginManifest,
  type PluginModule,
  type PluginRecord,
  type WidgetDefinition,
} from './types';

function rewriteAssetImports(source: string): string {
  return source.replace(
    /(\bfrom\s*|\bimport\s*)(["'])(\.\.\/)+assets\/([^"']+)\2/g,
    (_match, prefix: string, quote: string, _dots: string, asset: string) =>
      `${prefix}${quote}${new URL(`/assets/${asset}`, window.location.origin).href}${quote}`,
  );
}

export interface PluginManagerOptions {
  api: ApiClient;
  bus: PluginBus;
  storage: StorageEngine;
  dev: boolean;
}

export interface PluginManager {
  discover(): Promise<string[]>;
  installZip(bytes: Uint8Array): Promise<string>;
  installFromGithub(repository: string, ref?: string): Promise<string>;
  uninstall(pluginId: string): Promise<void>;
  refreshFetchers(): void;
  restart(): Promise<void>;
  dispose(): void;
}

export interface PluginManagerModule {
  readonly apiVersion: string;
  createManager(options: PluginManagerOptions): PluginManager;
}

const STANDARD_FOLDERS = ['widgets', 'libraries', 'fetchers', 'daemons'];

function isManifest(value: unknown): value is PluginManifest {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate['id'] === 'string' &&
    typeof candidate['name'] === 'string' &&
    typeof candidate['version'] === 'string' &&
    (candidate['provides'] === undefined ||
      (Array.isArray(candidate['provides']) && candidate['provides'].every((item) => typeof item === 'string'))) &&
    (candidate['layouts'] === undefined ||
      (Array.isArray(candidate['layouts']) && candidate['layouts'].every((item) => typeof item === 'string')))
  );
}

export function createManager(options: PluginManagerOptions): PluginManager {
  const { api, bus, storage, dev } = options;
  const contexts: DisposableContext[] = [];
  const ownerContexts = new Map<string, DisposableContext>();
  const timers: number[] = [];
  const controller = new AbortController();
  const startedFetchers = new Set<string>();
  const startedDaemons = new Set<string>();
  const loaded = new Set<string>();
  const fetchers: FetcherDefinition[] = [];
  const daemons: DaemonDefinition[] = [];
  const modules: PluginModule[] = [];
  let disposed = false;

  const contextFor = (owner: string): DisposableContext => {
    let context = ownerContexts.get(owner);
    if (!context) {
      context = createPluginContext({ id: pluginId(owner), bus, storage: storage.scope(owner) });
      ownerContexts.set(owner, context);
      contexts.push(context);
    }
    return context;
  };

  const runFetcher = (fetcher: FetcherDefinition): void => {
    const owner = fetcher.owner ?? 'core';
    const context = Object.assign(contextFor(owner), {
      emit: (payload: unknown): void => {
        if (isFetcherPayload(payload)) bus.emitPayload(payload);
        else console.warn(`fetcher ${owner}:${fetcher.name} emitted an invalid payload`, payload);
      },
    }) as FetcherContext;
    void Promise.resolve(fetcher.run(context))
      .then((payloads) => {
        const list = payloads === null ? [] : Array.isArray(payloads) ? payloads : [payloads];
        for (const payload of list) context.emit(payload);
      })
      .catch((error: unknown) => console.error(`fetcher ${owner}:${fetcher.name} failed`, error));
  };

  const startRuntimes = (): void => {
    for (const fetcher of fetchers) {
      const identity = `${fetcher.owner ?? 'core'}:${fetcher.name}`;
      if (startedFetchers.has(identity)) continue;
      startedFetchers.add(identity);
      runFetcher(fetcher);
      if (fetcher.intervalMs > 0) {
        timers.push(window.setInterval(() => runFetcher(fetcher), fetcher.intervalMs));
      }
    }
    for (const daemon of daemons) {
      const identity = `${daemon.owner ?? 'core'}:${daemon.name}`;
      if (startedDaemons.has(identity)) continue;
      startedDaemons.add(identity);
      const context = Object.assign(contextFor(daemon.owner ?? 'core'), {
        signal: controller.signal,
      }) as DaemonContext;
      void Promise.resolve(daemon.start(context)).catch((error: unknown) =>
        console.error(`daemon ${identity} failed`, error),
      );
    }
  };

  const discover = async (): Promise<string[]> => {
    const records = await api.invoke<PluginRecord[]>('list_plugins');
    const installed: string[] = [];

    for (const record of records) {
      if (disposed) break;
      if (loaded.has(record.id)) continue;
      if (!STANDARD_FOLDERS.every((folder) => record.folders.includes(folder))) {
        console.warn(`plugin ${record.id}: missing standard folders`);
        continue;
      }
      try {
        const manifestRaw = await api.readPluginFile(record.id, 'manifest.json');
        const manifest: unknown = JSON.parse(manifestRaw);
        if (!isManifest(manifest)) throw new Error('invalid manifest');
        const owner = manifest.id;
        const context = contextFor(owner);

        for (const layoutPath of manifest.layouts ?? []) {
          const text = await api.readPluginFile(owner, layoutPath);
          const layout = parseLayout(text, layoutPath);
          bus.registerWidget({
            kind: 'declarative',
            name: layout.name,
            layoutPath,
            owner,
            surface: layout.surface,
            slot: layout.slot,
          });
        }

        const entry = manifest.entry ?? 'index.ts';
        let imported: { default?: PluginModule };
        if (record.removable) {
          const source = await api.readPluginFile(owner, entry.replace(/\.ts$/, '.js'));
          const url = URL.createObjectURL(
            new Blob([rewriteAssetImports(source)], { type: 'text/javascript' }),
          );
          try {
            imported = (await import(/* @vite-ignore */ url)) as { default?: PluginModule };
          } finally {
            URL.revokeObjectURL(url);
          }
        } else {
          const url = dev
            ? `/src/plugins/${owner}/${entry}`
            : `/plugins/${owner}/${entry.replace(/\.ts$/, '.js')}`;
          imported = (await import(/* @vite-ignore */ url)) as { default?: PluginModule };
        }
        const module = imported.default;
        if (!module) throw new Error(`plugin ${owner} has no default export`);

        for (const definition of module.widgets ?? []) {
          bus.registerWidget({ ...definition, owner } as WidgetDefinition);
        }
        for (const definition of module.fetchers ?? []) fetchers.push({ ...definition, owner });
        for (const definition of module.daemons ?? []) daemons.push({ ...definition, owner });
        await module.activate?.(context as PluginContext);
        modules.push(module);
        loaded.add(record.id);
        installed.push(owner);
      } catch (error) {
        console.error(`plugin ${record.id} failed to load`, error);
        void api.invoke<void>('storage_write', {
          tier: 'settings',
          owner: 'global',
          key: `plugin_error_${record.id}`,
          value: error instanceof Error ? error.message : String(error),
        });
      }
    }

    startRuntimes();
    return installed;
  };

  const installZip = async (bytes: Uint8Array): Promise<string> => {
    const id = await api.invoke<string>('install_zip', { bytes: Array.from(bytes) });
    await discover();
    return id;
  };

  return {
    discover,
    installZip,
    async installFromGithub(repository: string, ref = 'main'): Promise<string> {
      if (!/^[\w.-]+\/[\w.-]+$/.test(repository)) throw new Error('repository must be owner/repo');
      const url = `https://codeload.github.com/${repository}/zip/${encodeURIComponent(ref)}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`GitHub download failed: ${response.status}`);
      return installZip(new Uint8Array(await response.arrayBuffer()));
    },
    async uninstall(pluginId: string): Promise<void> {
      await api.invoke<void>('uninstall_plugin', { pluginId });
    },
    refreshFetchers(): void {
      for (const fetcher of fetchers) runFetcher(fetcher);
    },
    async restart(): Promise<void> {
      await api.invoke<void>('restart_app');
    },
    dispose(): void {
      disposed = true;
      controller.abort();
      for (const timer of timers) window.clearInterval(timer);
      for (const module of modules.splice(0)) {
        void Promise.resolve(module.deactivate?.()).catch((error: unknown) =>
          console.error('plugin deactivation failed', error),
        );
      }
      for (const context of contexts.splice(0)) context.dispose();
    },
  };
}

const module: PluginManagerModule = { apiVersion: '1', createManager };
export default module;
