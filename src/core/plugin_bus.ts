import type {
  DaemonDefinition,
  FetcherDefinition,
  FetcherPayload,
  JsonValue,
  PluginBus as PluginBusContract,
  WidgetDefinition,
} from './types';

export class PluginBus implements PluginBusContract {
  private readonly widgetList: WidgetDefinition[] = [];
  private readonly fetcherList: FetcherDefinition[] = [];
  private readonly daemonList: DaemonDefinition[] = [];
  private readonly widgetListeners = new Set<(definition: WidgetDefinition) => void>();
  private readonly payloadListeners = new Set<(payload: FetcherPayload) => void>();
  private readonly eventListeners = new Map<string, Set<(data: JsonValue | undefined) => void>>();

  registerWidget(definition: WidgetDefinition): void {
    if (this.widgetList.some((widget) => widget.name === definition.name)) {
      throw new Error(`widget already registered: ${definition.name}`);
    }
    this.widgetList.push(definition);
    for (const listener of this.widgetListeners) listener(definition);
  }

  registerFetcher(definition: FetcherDefinition): void {
    this.fetcherList.push(definition);
  }

  registerDaemon(definition: DaemonDefinition): void {
    this.daemonList.push(definition);
  }

  widgets(): readonly WidgetDefinition[] {
    return this.widgetList;
  }

  fetchers(): readonly FetcherDefinition[] {
    return this.fetcherList;
  }

  daemons(): readonly DaemonDefinition[] {
    return this.daemonList;
  }

  findWidget(name: string): WidgetDefinition | undefined {
    return this.widgetList.find((widget) => widget.name === name);
  }

  onWidget(listener: (definition: WidgetDefinition) => void): () => void {
    this.widgetListeners.add(listener);
    for (const definition of this.widgetList) listener(definition);
    return () => this.widgetListeners.delete(listener);
  }

  onPayload(listener: (payload: FetcherPayload) => void): () => void {
    this.payloadListeners.add(listener);
    return () => this.payloadListeners.delete(listener);
  }

  emitPayload(payload: FetcherPayload): void {
    for (const listener of this.payloadListeners) listener(payload);
  }

  on(event: string, listener: (data: JsonValue | undefined) => void): () => void {
    const listeners = this.eventListeners.get(event) ?? new Set();
    listeners.add(listener);
    this.eventListeners.set(event, listeners);
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) this.eventListeners.delete(event);
    };
  }

  emit(event: string, data?: JsonValue): void {
    for (const listener of this.eventListeners.get(event) ?? []) listener(data);
  }
}
