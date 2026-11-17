import type { ApiClient, FetcherPayload, PluginBus } from '../../core/types';
import { pluginId } from '../../core/types';
import { createPluginContext } from '../../core/context';
import { parseLayout } from '../../core/layout/parser';
import type { LayoutDocument } from '../../core/layout/types';
import { compileLayout } from '../../core/layout/compiler';
import type { StorageEngine } from '../../core/storage_engine';

export interface MountedWidget {
  name: string;
  element: HTMLElement;
  update(payload: FetcherPayload): void;
  dispose(): void;
}

export class WidgetHost {
  private readonly layoutCache = new Map<string, LayoutDocument>();

  constructor(
    private readonly api: ApiClient,
    private readonly storage: StorageEngine,
    private readonly bus: PluginBus,
    private readonly refresh: () => void,
  ) {}

  private record(owner: string, name: string, element: HTMLElement): void {
    this.storage.scope(owner).settings.patch('ui.rendered_text', {
      [name]: (element.textContent ?? '').slice(0, 300),
    });
  }

  async create(payload: FetcherPayload): Promise<MountedWidget | null> {
    const definition = this.bus.findWidget(payload.widget_name);
    if (!definition) return null;
    const owner = definition.owner ?? 'core';
    const context = createPluginContext({ id: pluginId(owner), bus: this.bus, storage: this.storage.scope(owner) });
    this.storage.scope(owner).settings.patch('ui.rendered', { [definition.name]: true });

    if (definition.kind === 'factory') {
      const widgetContext = Object.assign(context, { content: payload.content });
      const element = definition.create(widgetContext);
      this.record(owner, definition.name, element);
      return {
        name: definition.name,
        element,
        update: (next: FetcherPayload): void => {
          widgetContext.content = next.content;
        },
        dispose: (): void => {
          context.dispose();
          element.remove();
        },
      };
    }

    const cacheKey = `${owner}:${definition.layoutPath}`;
    let document = this.layoutCache.get(cacheKey);
    if (!document) {
      const text = await this.api.readPluginFile(owner, definition.layoutPath);
      document = parseLayout(text, definition.layoutPath);
      this.layoutCache.set(cacheKey, document);
    }
    const compiled = compileLayout(document, {
      storage: this.storage.scope(owner),
      bus: this.bus,
      onRefresh: this.refresh,
      onDispose: (listener: () => void): void => context.onDispose(listener),
    });
    compiled.update(payload.content);
    this.record(owner, definition.name, compiled.element);
    return {
      name: definition.name,
      element: compiled.element,
      update: (next: FetcherPayload): void => compiled.update(next.content),
      dispose: (): void => {
        compiled.dispose();
        context.dispose();
        compiled.element.remove();
      },
    };
  }
}
