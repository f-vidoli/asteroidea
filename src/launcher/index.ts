import { createPluginContext } from '../core/context';
import type { PluginManager } from '../core/plugin_manager';
import type { StorageEngine } from '../core/storage_engine';
import {
  isFetcherPayload,
  pluginId,
  SCREEN_TARGETS,
  WIDGET_SLOTS,
  type ApiClient,
  type BootState,
  type FetcherPayload,
  type PluginBus,
  type WidgetDefinition,
} from '../core/types';
import { createManagerPanel } from './ui/manager_panel';
import { createNav } from './ui/nav';
import { Reader } from './ui/reader';
import { createSettingsPanel } from './ui/settings_panel';
import { WidgetHost } from './ui/widget_host';

export interface LauncherApi {
  bus: PluginBus;
  storage: StorageEngine;
  reader: Reader;
  manager: PluginManager;
  refreshFetchers(): void;
}

export interface LauncherModule {
  api: LauncherApi;
  mount(host: HTMLElement): void;
  unmount(): void;
}

export interface LauncherOptions {
  api: ApiClient;
  storage: StorageEngine;
  bus: PluginBus;
  boot: BootState;
  manager: PluginManager;
  refreshFetchers(): void;
}

export function createLauncher(options: LauncherOptions): LauncherModule {
  const { api, storage, bus, boot, manager, refreshFetchers } = options;
  const root = document.createElement('div');
  root.className = 'launcher';
  const context = createPluginContext({
    id: pluginId('core.launcher'),
    bus,
    storage: storage.scope('core.launcher'),
  });
  const reader = new Reader(root);
  const nav = createNav(root, (target) => reader.show(target));
  const widgets = new WidgetHost(api, storage, bus, refreshFetchers);
  const pending = new Set<string>();

  reader.slotElement(SCREEN_TARGETS.SETTINGS, WIDGET_SLOTS.DEFAULT)?.append(
    createSettingsPanel({
      api,
      boot,
      restart: () => manager.restart(),
    }),
  );
  reader.slotElement(SCREEN_TARGETS.MANAGER, WIDGET_SLOTS.DEFAULT)?.append(
    createManagerPanel({ api, manager }),
  );
  const settingsCoreSlot = reader.slotElement(SCREEN_TARGETS.SETTINGS, WIDGET_SLOTS.DEFAULT);
  const settingsPluginSlot = reader.slotElement(SCREEN_TARGETS.SETTINGS, WIDGET_SLOTS.SETTINGS);
  context.storage.settings.patch('ui', {
    screens: Object.values(SCREEN_TARGETS).length,
    settings: true,
    manager: true,
    plugin_settings_below_core: Boolean(
      settingsCoreSlot &&
        settingsPluginSlot &&
        settingsCoreSlot.compareDocumentPosition(settingsPluginSlot) & Node.DOCUMENT_POSITION_FOLLOWING,
    ),
  });

  const mountWidget = async (payload: FetcherPayload): Promise<void> => {
    if (reader.has(payload)) return;
    const slot = payload.slot ?? WIDGET_SLOTS.DEFAULT;
    const identity = `${payload.target}:${slot}:${payload.id ?? payload.widget_name}`;
    if (pending.has(identity)) return;
    pending.add(identity);
    try {
      const widget = await widgets.create(payload);
      if (!widget) {
        console.warn(`launcher: no widget registered as "${payload.widget_name}"`);
        return;
      }
      reader.append(payload.target, slot, widget, payload);
    } catch (error) {
      console.error(`launcher: failed to render "${payload.widget_name}"`, error);
    } finally {
      pending.delete(identity);
    }
  };

  const handlePayload = (payload: FetcherPayload): void => {
    if (!isFetcherPayload(payload)) {
      console.warn('launcher: rejected malformed fetcher payload', payload);
      return;
    }
    if (reader.has(payload)) {
      reader.update(payload);
      return;
    }
    void mountWidget(payload);
  };

  const mountSubscription = (definition: WidgetDefinition): void => {
    if (!definition.surface) return;
    const payload: FetcherPayload = {
      target: definition.surface,
      widget_name: definition.name,
      content: {},
      id: definition.name,
      slot: definition.slot ?? WIDGET_SLOTS.DEFAULT,
    };
    void mountWidget(payload);
  };

  const unsubscribePayload = bus.onPayload(handlePayload);
  const unsubscribeWidget = bus.onWidget(mountSubscription);

  bus.emit('core.launcher.ready', {
    screens: Object.values(SCREEN_TARGETS),
    slots: Object.values(WIDGET_SLOTS),
  });

  return {
    api: { bus, storage, reader, manager, refreshFetchers },
    mount(host: HTMLElement): void {
      host.append(root);
    },
    unmount(): void {
      unsubscribePayload();
      unsubscribeWidget();
      reader.dispose();
      context.dispose();
      nav.element.remove();
      root.remove();
    },
  };
}
