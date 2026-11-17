import { parse as parseYaml } from 'yaml';
import type { JsonObject, JsonValue, MemoryTier, ScreenTarget, WidgetSlot } from '../types';
import { MEMORY_TIERS, SCREEN_TARGETS, WIDGET_SLOTS } from '../types';
import {
  ACTION_VERBS,
  LAYOUT_PROPS,
  NODE_TYPES,
  type ActionVerb,
  type LayoutAction,
  type LayoutDocument,
  type LayoutNode,
  type LayoutPropValue,
} from './types';

const BINDING = /\$\{([^{}]+)\}/g;
const DANGEROUS_TOKENS = ['__proto__', 'constructor', 'prototype'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNodeType(value: unknown): value is LayoutNode['type'] {
  return Object.values(NODE_TYPES).includes(value as LayoutNode['type']);
}

function isActionVerb(value: unknown): value is ActionVerb {
  return Object.values(ACTION_VERBS).includes(value as ActionVerb);
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return true;
  if (Array.isArray(value)) return value.every(isJsonValue);
  return isRecord(value) && Object.values(value).every(isJsonValue);
}

function validateExpression(expression: string, path: string): void {
  const trimmed = expression.trim();
  if (DANGEROUS_TOKENS.some((token) => trimmed.includes(token))) {
    throw new Error(`${path}: unsafe binding expression "${trimmed}"`);
  }
  if (trimmed === 'now') return;
  if (trimmed.startsWith('payload.')) {
    if (trimmed.length <= 'payload.'.length) throw new Error(`${path}: empty payload binding`);
    return;
  }
  const memoryPrefix = 'memory.';
  if (trimmed.startsWith(memoryPrefix)) {
    const [tier, ...rest] = trimmed.slice(memoryPrefix.length).split('.');
    if (!Object.values(MEMORY_TIERS).includes(tier as MemoryTier) || rest.length === 0) {
      throw new Error(`${path}: invalid memory binding "${trimmed}"`);
    }
    return;
  }
  throw new Error(`${path}: unsupported binding "${trimmed}"`);
}

function validateString(value: string, path: string): void {
  BINDING.lastIndex = 0;
  let match: RegExpExecArray | null;
  let plain = value;
  while ((match = BINDING.exec(value)) !== null) {
    validateExpression(match[1] ?? '', path);
    plain = plain.replace(match[0], '');
  }
  if (plain.includes('${') || plain.includes('}')) {
    throw new Error(`${path}: malformed binding expression`);
  }
}

function validatePropValue(value: unknown, path: string): LayoutPropValue {
  if (typeof value === 'string') {
    validateString(value, path);
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  throw new Error(`${path}: property must be a string, number or boolean`);
}

function validateAction(value: unknown, path: string): LayoutAction {
  if (!isRecord(value)) throw new Error(`${path}: action must be an object`);
  if (!isActionVerb(value['action'])) throw new Error(`${path}: unknown action "${String(value['action'])}"`);
  const action = value['action'];

  if (action === ACTION_VERBS.STORAGE_SET) {
    const tier = value['tier'];
    const key = value['key'];
    if (typeof tier !== 'string' || !Object.values(MEMORY_TIERS).includes(tier as MemoryTier)) {
      throw new Error(`${path}: storage.set requires a valid tier`);
    }
    if (typeof key !== 'string' || key.length === 0 || key.includes('/')) {
      throw new Error(`${path}: storage.set requires a valid key`);
    }
    const raw = value['value'];
    if (typeof raw === 'string') validateString(raw, `${path}.value`);
    if (!isJsonValue(raw)) throw new Error(`${path}: storage.set requires a JSON value`);
    return { action, tier: tier as MemoryTier, key, value: raw as JsonValue | string };
  }

  if (action === ACTION_VERBS.EMIT) {
    const event = value['event'];
    if (typeof event !== 'string' || event.length === 0) throw new Error(`${path}: emit requires an event name`);
    const data = value['data'] ?? {};
    if (!isRecord(data)) throw new Error(`${path}: emit data must be an object`);
    for (const [name, field] of Object.entries(data)) {
      if (typeof field === 'string') validateString(field, `${path}.data.${name}`);
      else if (!isJsonValue(field)) throw new Error(`${path}.data.${name}: invalid JSON value`);
    }
    return { action, event, data: data as JsonObject };
  }

  return { action: ACTION_VERBS.REFRESH };
}

function validateNode(value: unknown, path: string): LayoutNode {
  if (!isRecord(value)) throw new Error(`${path}: node must be an object`);
  if (!isNodeType(value['type'])) throw new Error(`${path}: unknown node type "${String(value['type'])}"`);
  const node: LayoutNode = { type: value['type'] };

  if (value['id'] !== undefined) {
    if (typeof value['id'] !== 'string') throw new Error(`${path}.id must be a string`);
    node.id = value['id'];
  }

  if (value['props'] !== undefined) {
    if (!isRecord(value['props'])) throw new Error(`${path}.props must be an object`);
    node.props = {};
    for (const [name, propValue] of Object.entries(value['props'])) {
      if (!LAYOUT_PROPS.includes(name as (typeof LAYOUT_PROPS)[number])) {
        throw new Error(`${path}.props.${name}: unsupported property`);
      }
      node.props[name] = validatePropValue(propValue, `${path}.props.${name}`);
    }
  }

  if (value['children'] !== undefined) {
    if (!Array.isArray(value['children'])) throw new Error(`${path}.children must be an array`);
    node.children = value['children'].map((child, index) => validateNode(child, `${path}.children[${index}]`));
  }

  if (value['on_press'] !== undefined) {
    if (!Array.isArray(value['on_press'])) throw new Error(`${path}.on_press must be an array`);
    node.on_press = value['on_press'].map((action, index) => validateAction(action, `${path}.on_press[${index}]`));
  }

  return node;
}

export function parseLayout(text: string, fileName: string): LayoutDocument {
  let raw: unknown;
  try {
    raw = /\.ya?ml$/i.test(fileName) ? parseYaml(text) : JSON.parse(text);
  } catch (error) {
    throw new Error(`${fileName}: cannot parse layout (${error instanceof Error ? error.message : String(error)})`);
  }
  if (!isRecord(raw)) throw new Error(`${fileName}: layout root must be an object`);
  if (typeof raw['name'] !== 'string' || raw['name'].length === 0) {
    throw new Error(`${fileName}: layout requires a name`);
  }
  if (DANGEROUS_TOKENS.some((token) => (raw['name'] as string).includes(token))) {
    throw new Error(`${fileName}: unsafe layout name`);
  }

  const document: LayoutDocument = { name: raw['name'], root: validateNode(raw['root'], `${fileName}.root`) };
  if (raw['surface'] !== undefined) {
    if (!Object.values(SCREEN_TARGETS).includes(raw['surface'] as ScreenTarget)) {
      throw new Error(`${fileName}: unknown surface "${String(raw['surface'])}"`);
    }
    document.surface = raw['surface'] as ScreenTarget;
  }
  if (raw['slot'] !== undefined) {
    if (!Object.values(WIDGET_SLOTS).includes(raw['slot'] as WidgetSlot)) {
      throw new Error(`${fileName}: unknown slot "${String(raw['slot'])}"`);
    }
    document.slot = raw['slot'] as WidgetSlot;
  }
  return document;
}
