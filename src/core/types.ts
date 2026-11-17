export type Brand<T, B extends string> = T & { readonly __brand: B };

export type PluginId = Brand<string, 'PluginId'>;

export const pluginId = (value: string): PluginId => value as PluginId;

export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonValue[] | JsonObject;

export interface JsonObject {
  [key: string]: JsonValue;
}

export const MEMORY_TIERS = {
  PRIVATE: 'private',
  SETTINGS: 'settings',
  PUBLIC: 'public',
} as const;

export type MemoryTier = (typeof MEMORY_TIERS)[keyof typeof MEMORY_TIERS];

export const SCREEN_TARGETS = {
  MAIN: 'main',
  FEED: 'feed',
  SETTINGS: 'settings',
  MANAGER: 'manager',
} as const;

export type ScreenTarget = (typeof SCREEN_TARGETS)[keyof typeof SCREEN_TARGETS];

export const WIDGET_SLOTS = {
  DEFAULT: 'default',
  SETTINGS: 'settings',
  MANAGER: 'manager',
} as const;

export type WidgetSlot = (typeof WIDGET_SLOTS)[keyof typeof WIDGET_SLOTS];

export interface FetcherPayload {
  target: ScreenTarget;
  widget_name: string;
  content: JsonObject;
  id?: string;
  slot?: WidgetSlot;
}

export function isFetcherPayload(value: unknown): value is FetcherPayload {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    Object.values(SCREEN_TARGETS).includes(candidate['target'] as ScreenTarget) &&
    typeof candidate['widget_name'] === 'string' &&
    candidate['widget_name'].length > 0 &&
    typeof candidate['content'] === 'object' &&
    candidate['content'] !== null &&
    !Array.isArray(candidate['content']) &&
    (candidate['slot'] === undefined || Object.values(WIDGET_SLOTS).includes(candidate['slot'] as WidgetSlot))
  );
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  api_version?: string;
  provides?: string[];
  layouts?: string[];
  entry?: string;
}

export interface BootConfig {
  active_launcher: string;
  active_plugin_manager: string;
  fallback_launcher: string | null;
  safe_mode: boolean;
  plugins_dir: string;
}

export interface BootState {
  config: BootConfig;
  plugins_root: string;
  app_data_dir: string;
}

export interface PluginRecord {
  id: string;
  folders: string[];
  path: string;
  removable: boolean;
}

export interface StorageDump {
  private: Record<string, JsonObject>;
  settings: JsonObject;
  public: JsonObject;
}

export interface MemoryStore {
  get<T extends JsonValue>(key: string): T | null;
  set<T extends JsonValue>(key: string, value: T): void;
  patch(key: string, patch: JsonObject): void;
  remove(key: string): void;
  subscribe(key: string, listener: (value: JsonValue | null) => void): () => void;
}

export interface ScopedStorage {
  private: MemoryStore;
  settings: MemoryStore;
  public: MemoryStore;
}

export type DomAttributes = Record<string, string | number | boolean | undefined>;

export interface PluginContext {
  id: PluginId;
  bus: PluginBus;
  storage: ScopedStorage;
  onDispose(listener: () => void): void;
  el(tag: string, attributes?: DomAttributes): HTMLElement;
}

export interface WidgetContext extends PluginContext {
  content: JsonObject;
}

export interface WidgetSubscription {
  surface?: ScreenTarget;
  slot?: WidgetSlot;
}

export interface FactoryWidgetDefinition extends WidgetSubscription {
  kind: 'factory';
  name: string;
  owner?: string;
  create(context: WidgetContext): HTMLElement;
}

export interface DeclarativeWidgetDefinition extends WidgetSubscription {
  kind: 'declarative';
  name: string;
  owner?: string;
  layoutPath: string;
}

export type WidgetDefinition = FactoryWidgetDefinition | DeclarativeWidgetDefinition;

export interface FetcherContext extends PluginContext {
  emit(payload: FetcherPayload): void;
}

export interface FetcherDefinition {
  name: string;
  owner?: string;
  intervalMs: number;
  run(context: FetcherContext): Promise<FetcherPayload | FetcherPayload[] | null> | FetcherPayload | FetcherPayload[] | null;
}

export interface DaemonContext extends PluginContext {
  signal: AbortSignal;
}

export interface DaemonDefinition {
  name: string;
  owner?: string;
  start(context: DaemonContext): Promise<void> | void;
}

export interface PluginModule {
  manifest: PluginManifest;
  widgets?: WidgetDefinition[];
  fetchers?: FetcherDefinition[];
  daemons?: DaemonDefinition[];
  activate?(context: PluginContext): void | Promise<void>;
  deactivate?(): void | Promise<void>;
}

export interface PluginBus {
  registerWidget(definition: WidgetDefinition): void;
  registerFetcher(definition: FetcherDefinition): void;
  registerDaemon(definition: DaemonDefinition): void;
  widgets(): readonly WidgetDefinition[];
  fetchers(): readonly FetcherDefinition[];
  daemons(): readonly DaemonDefinition[];
  findWidget(name: string): WidgetDefinition | undefined;
  onWidget(listener: (definition: WidgetDefinition) => void): () => void;
  onPayload(listener: (payload: FetcherPayload) => void): () => void;
  emitPayload(payload: FetcherPayload): void;
  on(event: string, listener: (data: JsonValue | undefined) => void): () => void;
  emit(event: string, data?: JsonValue): void;
}

export interface ApiClient {
  invoke<T>(command: string, args?: Record<string, unknown>): Promise<T>;
  readPluginFile(pluginId: string, relativePath: string): Promise<string>;
}
