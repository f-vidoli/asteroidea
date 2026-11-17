import type { FetcherPayload, ScreenTarget, WidgetSlot } from '../../core/types';
import { SCREEN_TARGETS, WIDGET_SLOTS } from '../../core/types';
import type { MountedWidget } from './widget_host';

interface ReaderInstance {
  target: ScreenTarget;
  slot: WidgetSlot;
  widget: MountedWidget;
}

const MAX_ITEMS = 50;

const SCREEN_SLOTS: Record<ScreenTarget, readonly WidgetSlot[]> = {
  [SCREEN_TARGETS.MAIN]: [WIDGET_SLOTS.DEFAULT],
  [SCREEN_TARGETS.FEED]: [WIDGET_SLOTS.DEFAULT],
  [SCREEN_TARGETS.SETTINGS]: [WIDGET_SLOTS.DEFAULT, WIDGET_SLOTS.SETTINGS],
  [SCREEN_TARGETS.MANAGER]: [WIDGET_SLOTS.DEFAULT, WIDGET_SLOTS.MANAGER],
};

const SLOT_LABELS: Record<WidgetSlot, string> = {
  [WIDGET_SLOTS.DEFAULT]: '',
  [WIDGET_SLOTS.SETTINGS]: 'Plugin settings',
  [WIDGET_SLOTS.MANAGER]: 'Plugin manager extensions',
};

export class Reader {
  readonly element: HTMLElement;
  private readonly screens = new Map<ScreenTarget, HTMLElement>();
  private readonly lists = new Map<string, HTMLElement>();
  private readonly instances = new Map<string, ReaderInstance>();
  private readonly order: string[] = [];

  constructor(host: HTMLElement) {
    this.element = document.createElement('div');
    this.element.className = 'reader';

    for (const [target, slots] of Object.entries(SCREEN_SLOTS) as [ScreenTarget, readonly WidgetSlot[]][]) {
      const screen = document.createElement('section');
      screen.className = 'screen';
      screen.dataset['screen'] = target;

      const scroll = document.createElement('div');
      scroll.className = 'scroll-view';
      for (const slot of slots) {
        const label = SLOT_LABELS[slot];
        if (label) {
          const heading = document.createElement('h3');
          heading.className = 'slot-heading';
          heading.textContent = label;
          scroll.append(heading);
        }
        const list = document.createElement('div');
        list.className = 'widget-list';
        list.dataset['slot'] = slot;
        scroll.append(list);
        this.lists.set(`${target}:${slot}`, list);
      }

      screen.append(scroll);
      this.element.append(screen);
      this.screens.set(target, screen);
    }

    host.append(this.element);
    this.show(SCREEN_TARGETS.MAIN);
  }

  show(target: ScreenTarget): void {
    for (const [name, screen] of this.screens) screen.dataset['active'] = String(name === target);
  }

  slotElement(target: ScreenTarget, slot: WidgetSlot): HTMLElement | null {
    return this.lists.get(`${target}:${slot}`) ?? null;
  }

  private key(payload: FetcherPayload): string {
    return `${payload.target}:${payload.slot ?? WIDGET_SLOTS.DEFAULT}:${payload.id ?? payload.widget_name}`;
  }

  has(payload: FetcherPayload): boolean {
    return this.instances.has(this.key(payload));
  }

  append(target: ScreenTarget, slot: WidgetSlot, widget: MountedWidget, payload: FetcherPayload): void {
    const key = this.key({ ...payload, target, slot });
    this.instances.set(key, { target, slot, widget });
    this.order.push(key);
    this.lists.get(`${target}:${slot}`)?.append(widget.element);
    this.trim(target, slot);
  }

  update(payload: FetcherPayload): void {
    this.instances.get(this.key(payload))?.widget.update(payload);
  }

  dispose(): void {
    for (const instance of this.instances.values()) instance.widget.dispose();
    this.instances.clear();
    this.order.length = 0;
    this.element.remove();
  }

  private trim(target: ScreenTarget, slot: WidgetSlot): void {
    const keys = this.order.filter((key) => {
      const instance = this.instances.get(key);
      return instance?.target === target && instance.slot === slot;
    });
    while (keys.length > MAX_ITEMS) {
      const oldest = keys.shift();
      if (!oldest) break;
      this.instances.get(oldest)?.widget.dispose();
      this.instances.delete(oldest);
      const index = this.order.indexOf(oldest);
      if (index >= 0) this.order.splice(index, 1);
    }
  }
}
