import type { DomAttributes, PluginBus, PluginContext, PluginId, ScopedStorage } from './types';

export interface DisposableContext extends PluginContext {
  dispose(): void;
}

export function createPluginContext(options: {
  id: PluginId;
  bus: PluginBus;
  storage: ScopedStorage;
}): DisposableContext {
  const disposers: Array<() => void> = [];
  const { id, bus, storage } = options;

  return {
    id,
    bus,
    storage,
    onDispose(listener: () => void): void {
      disposers.push(listener);
    },
    el(tag: string, attributes: DomAttributes = {}): HTMLElement {
      const element = document.createElement(tag);
      for (const [name, value] of Object.entries(attributes)) {
        if (value === undefined) continue;
        if (name === 'text') {
          element.textContent = String(value);
        } else if (name === 'class') {
          element.className = String(value);
        } else {
          element.setAttribute(name, String(value));
        }
      }
      return element;
    },
    dispose(): void {
      for (const listener of disposers.splice(0)) listener();
    },
  };
}
