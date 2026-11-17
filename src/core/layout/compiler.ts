import type { JsonObject, JsonValue, PluginBus, ScopedStorage } from '../types';
import { collectMemoryBindings, compileText, resolveExpression, type BindingContext } from './binding';
import { NODE_TYPES, type ActionVerb, type LayoutAction, type LayoutDocument, type LayoutNode } from './types';

const BINDING_PATTERN = /\$\{([^{}]+)\}/g;

export interface LayoutHost {
  storage: ScopedStorage;
  bus: PluginBus;
  onRefresh?: () => void;
  onDispose(listener: () => void): void;
}

export interface CompiledLayout {
  element: HTMLElement;
  update(payload: JsonObject): void;
  dispose(): void;
}

function tagFor(type: LayoutNode['type']): string {
  switch (type) {
    case NODE_TYPES.LABEL:
      return 'span';
    case NODE_TYPES.BUTTON:
      return 'button';
    default:
      return 'div';
  }
}

function px(value: string): string {
  return /^-?\d+(\.\d+)?$/.test(value.trim()) ? `${value.trim()}px` : value;
}

function applyProp(element: HTMLElement, name: string, value: string, type: LayoutNode['type']): void {
  switch (name) {
    case 'text':
      element.textContent = value;
      break;
    case 'color':
      element.style.color = value;
      break;
    case 'background':
      element.style.background = value;
      break;
    case 'padding':
      element.style.padding = px(value);
      break;
    case 'spacing':
      element.style.gap = px(value);
      break;
    case 'orientation':
      element.style.flexDirection = value === 'horizontal' ? 'row' : 'column';
      break;
    case 'font_size':
      element.style.fontSize = px(value);
      break;
    case 'class':
      element.className = value;
      break;
    case 'width':
      element.style.width = px(value);
      break;
    case 'height':
      element.style.height = px(value);
      break;
    case 'min_height':
      element.style.minHeight = px(value);
      break;
    default:
      break;
  }
  if (type === NODE_TYPES.LABEL) element.classList.add('decl-label');
  if (type === NODE_TYPES.BUTTON) element.classList.add('decl-button');
}

function resolveActionValue(raw: JsonValue | string | undefined, context: BindingContext): JsonValue {
  if (raw === undefined) return null;
  if (typeof raw !== 'string') return raw;
  const single = /^\$\{([^{}]+)\}$/.exec(raw);
  if (single) return resolveExpression(single[1] ?? '', context) ?? null;
  if (!raw.includes('${')) return raw;
  return raw.replace(BINDING_PATTERN, (_match: string, expression: string) => {
    const value = resolveExpression(expression, context);
    return value === undefined || value === null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  });
}

function runAction(action: LayoutAction, context: BindingContext, host: LayoutHost): void {
  const verb: ActionVerb = action.action;
  switch (verb) {
    case 'storage.set': {
      const tier = action.tier;
      const key = action.key;
      if (!tier || !key) return;
      host.storage[tier].set(key, resolveActionValue(action.value, context));
      break;
    }
    case 'emit': {
      const data: JsonObject = {};
      for (const [name, value] of Object.entries(action.data ?? {})) {
        data[name] = resolveActionValue(value, context);
      }
      host.bus.emit(action.event ?? 'layout.action', data);
      break;
    }
    case 'refresh':
      host.onRefresh?.();
      break;
    default: {
      const exhaustive: never = verb;
      throw new Error(`unsupported layout action: ${String(exhaustive)}`);
    }
  }
}

function buildNode(
  node: LayoutNode,
  host: LayoutHost,
  context: () => BindingContext,
  updaters: Array<() => void>,
): HTMLElement {
  const element = document.createElement(tagFor(node.type));

  switch (node.type) {
    case NODE_TYPES.BOX_LAYOUT:
      element.style.display = 'flex';
      element.style.flexDirection = 'column';
      break;
    case NODE_TYPES.SCROLL_VIEW:
      element.style.overflowY = 'auto';
      element.style.maxHeight = '240px';
      break;
    case NODE_TYPES.SPACER:
      element.style.flexGrow = '1';
      break;
    default:
      break;
  }
  if (node.id) element.dataset['widgetNode'] = node.id;

  for (const [name, raw] of Object.entries(node.props ?? {})) {
    const binding = compileText(raw);
    const apply = (): void => applyProp(element, name, binding(context()), node.type);
    apply();
    updaters.push(apply);
  }

  for (const child of node.children ?? []) element.append(buildNode(child, host, context, updaters));

  if (node.on_press) {
    element.addEventListener('click', () => {
      const current = context();
      for (const action of node.on_press ?? []) runAction(action, current, host);
    });
  }

  return element;
}

export function compileLayout(document: LayoutDocument, host: LayoutHost): CompiledLayout {
  const updaters: Array<() => void> = [];
  const unsubscribes: Array<() => void> = [];
  let payload: JsonObject = {};
  const context = (): BindingContext => ({ payload, storage: host.storage });

  const element = buildNode(document.root, host, context, updaters);
  const update = (nextPayload: JsonObject): void => {
    payload = nextPayload;
    for (const updater of updaters) updater();
  };

  for (const binding of collectMemoryBindings(document.root)) {
    unsubscribes.push(host.storage[binding.tier].subscribe(binding.key, () => update(payload)));
  }

  const dispose = (): void => {
    for (const unsubscribe of unsubscribes.splice(0)) unsubscribe();
  };
  host.onDispose(dispose);
  update({});
  return { element, update, dispose };
}
