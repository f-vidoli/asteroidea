import type {
  ApiClient,
  JsonObject,
  JsonValue,
  MemoryStore,
  MemoryTier,
  ScopedStorage,
  StorageDump,
} from './types';
import { MEMORY_TIERS } from './types';

type StorageListener = (value: JsonValue | null) => void;

function isJsonObject(value: JsonValue | null): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

class TierStore implements MemoryStore {
  private readonly listeners = new Map<string, Set<StorageListener>>();

  constructor(
    private readonly data: JsonObject,
    private readonly tier: MemoryTier,
    private readonly owner: string,
    private readonly client: ApiClient,
  ) {}

  get<T extends JsonValue>(key: string): T | null {
    return (this.data[key] ?? null) as T | null;
  }

  snapshot(): JsonObject {
    return { ...this.data };
  }

  set<T extends JsonValue>(key: string, value: T): void {
    this.data[key] = value;
    void this.client.invoke<void>('storage_write', { tier: this.tier, owner: this.owner, key, value });
    this.notify(key);
  }

  patch(key: string, patch: JsonObject): void {
    const current = this.get<JsonValue>(key);
    const base: JsonObject = isJsonObject(current) ? current : {};
    this.set(key, { ...base, ...patch });
  }

  remove(key: string): void {
    delete this.data[key];
    void this.client.invoke<void>('storage_remove', { tier: this.tier, owner: this.owner, key });
    this.notify(key);
  }

  subscribe(key: string, listener: StorageListener): () => void {
    const listeners = this.listeners.get(key) ?? new Set<StorageListener>();
    listeners.add(listener);
    this.listeners.set(key, listeners);
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) this.listeners.delete(key);
    };
  }

  private notify(key: string): void {
    const value = this.get<JsonValue>(key);
    for (const listener of this.listeners.get(key) ?? []) listener(value);
  }
}

export class StorageEngine {
  private readonly privateStores = new Map<string, TierStore>();
  private readonly settings: TierStore;
  private readonly publicStore: TierStore;

  private constructor(dump: StorageDump, private readonly client: ApiClient) {
    this.settings = new TierStore(dump.settings, MEMORY_TIERS.SETTINGS, 'global', client);
    this.publicStore = new TierStore(dump.public, MEMORY_TIERS.PUBLIC, 'global', client);
    for (const [id, data] of Object.entries(dump.private)) {
      this.privateStores.set(id, new TierStore(data, MEMORY_TIERS.PRIVATE, id, client));
    }
  }

  static async load(client: ApiClient): Promise<StorageEngine> {
    const dump = await client.invoke<StorageDump>('storage_dump');
    return new StorageEngine(dump, client);
  }

  dump(): StorageDump {
    const privateData: Record<string, JsonObject> = {};
    for (const [id, store] of this.privateStores) privateData[id] = { ...store.snapshot() };
    return { private: privateData, settings: { ...this.settings.snapshot() }, public: { ...this.publicStore.snapshot() } };
  }

  scope(pluginId: string): ScopedStorage {
    let store = this.privateStores.get(pluginId);
    if (!store) {
      store = new TierStore({}, MEMORY_TIERS.PRIVATE, pluginId, this.client);
      this.privateStores.set(pluginId, store);
    }
    return { private: store, settings: this.settings, public: this.publicStore };
  }
}
