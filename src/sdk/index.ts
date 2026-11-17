export {
  MEMORY_TIERS,
  SCREEN_TARGETS,
  WIDGET_SLOTS,
  pluginId,
  isFetcherPayload,
} from '../core/types';

export type {
  BootConfig,
  BootState,
  DaemonContext,
  DaemonDefinition,
  FactoryWidgetDefinition,
  FetcherContext,
  FetcherDefinition,
  FetcherPayload,
  JsonObject,
  JsonValue,
  MemoryStore,
  MemoryTier,
  PluginBus,
  PluginContext,
  PluginId,
  PluginManifest,
  PluginModule,
  ScopedStorage,
  ScreenTarget,
  WidgetContext,
  WidgetDefinition,
  WidgetSlot,
  WidgetSubscription,
} from '../core/types';

import type {
  DaemonContext,
  DaemonDefinition,
  FactoryWidgetDefinition,
  FetcherContext,
  FetcherDefinition,
  FetcherPayload,
  JsonObject,
  JsonValue,
  PluginModule,
  ScopedStorage,
  ScreenTarget,
  WidgetContext,
  WidgetSlot,
  WidgetSubscription,
} from '../core/types';

export interface WidgetOptions<T extends JsonObject> extends WidgetSubscription {
  name: string;
  create(context: WidgetContext & { content: T }): HTMLElement;
}

export function defineWidget<T extends JsonObject>(options: WidgetOptions<T>): FactoryWidgetDefinition {
  return {
    kind: 'factory',
    name: options.name,
    surface: options.surface,
    slot: options.slot,
    create: (context) => options.create(context as WidgetContext & { content: T }),
  };
}

type FetcherResult = FetcherPayload | FetcherPayload[] | null;
type FetcherRun = (context: FetcherContext) => Promise<FetcherResult> | FetcherResult;

export function defineFetcher(options: {
  name: string;
  intervalMs: number;
  run: FetcherRun;
}): FetcherDefinition {
  return { name: options.name, intervalMs: options.intervalMs, run: options.run };
}

export function defineDaemon(options: {
  name: string;
  start(context: DaemonContext): Promise<void> | void;
}): DaemonDefinition {
  return { name: options.name, start: options.start };
}

export function buildPayload(
  target: ScreenTarget,
  widgetName: string,
  content: JsonObject,
  id?: string,
  slot?: WidgetSlot,
): FetcherPayload {
  return {
    target,
    widget_name: widgetName,
    content,
    ...(id === undefined ? {} : { id }),
    ...(slot === undefined ? {} : { slot }),
  };
}

export function definePlugin(module: PluginModule): PluginModule {
  return module;
}

export interface SharedMessage<T extends JsonValue = JsonValue> {
  id: string;
  from: string;
  at: string;
  data: T;
}

export interface SharedChannel<T extends JsonValue> {
  send(data: T): void;
  onMessage(listener: (message: SharedMessage<T>) => void): () => void;
  history(): SharedMessage<T>[];
  clear(): void;
}

function readMessages<T extends JsonValue>(storage: ScopedStorage, key: string): SharedMessage<T>[] {
  const value = storage.public.get<JsonValue>(key);
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is JsonObject =>
      typeof item === 'object' && item !== null && !Array.isArray(item) && typeof item['id'] === 'string',
  ) as unknown as SharedMessage<T>[];
}

export function sharedChannel<T extends JsonValue>(
  storage: ScopedStorage,
  name: string,
  from: string,
): SharedChannel<T> {
  const key = `channels.${name}`;
  return {
    send(data: T): void {
      const message: SharedMessage<T> = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        from,
        at: new Date().toISOString(),
        data,
      };
      storage.public.set(key, [...readMessages<T>(storage, key), message].slice(-100) as unknown as JsonValue[]);
    },
    onMessage(listener: (message: SharedMessage<T>) => void): () => void {
      return storage.public.subscribe(key, (value) => {
        const messages = readMessages<T>(storage, key);
        const latest = Array.isArray(value) ? messages[messages.length - 1] : undefined;
        if (latest) listener(latest);
      });
    },
    history(): SharedMessage<T>[] {
      return readMessages<T>(storage, key);
    },
    clear(): void {
      storage.public.remove(key);
    },
  };
}
