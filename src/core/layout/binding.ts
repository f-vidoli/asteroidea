import type { JsonObject, JsonValue, MemoryTier, ScopedStorage } from '../types';
import type { LayoutNode } from './types';

const BINDING_PATTERN = /\$\{([^{}]+)\}/g;
const MEMORY_PATTERN = /memory\.(private|settings|public)\.([A-Za-z0-9_.-]+)/g;
const DANGEROUS_TOKENS = ['__proto__', 'constructor', 'prototype'];

export interface BindingContext {
  payload: JsonObject;
  storage: ScopedStorage;
}

export type TextBinding = (context: BindingContext) => string;

export interface MemoryBindingRef {
  tier: MemoryTier;
  key: string;
}

function lookupPath(root: JsonValue, parts: string[]): JsonValue | undefined {
  let current: JsonValue | undefined = root;
  for (const part of parts) {
    if (DANGEROUS_TOKENS.includes(part)) return undefined;
    if (typeof current !== 'object' || current === null || Array.isArray(current)) return undefined;
    current = (current as JsonObject)[part];
  }
  return current;
}

export function formatBindingValue(value: JsonValue | undefined): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function resolveExpression(expression: string, context: BindingContext): JsonValue | undefined {
  const trimmed = expression.trim();
  if (trimmed === 'now') return new Date().toISOString();
  if (trimmed.startsWith('payload.')) {
    return lookupPath(context.payload, trimmed.slice('payload.'.length).split('.'));
  }
  if (trimmed.startsWith('memory.')) {
    const [tier, ...keyParts] = trimmed.slice('memory.'.length).split('.');
    if (tier !== 'private' && tier !== 'settings' && tier !== 'public') return undefined;
    return context.storage[tier].get<JsonValue>(keyParts.join('.'));
  }
  return undefined;
}

export function compileText(value: string | number | boolean): TextBinding {
  if (typeof value !== 'string' || !value.includes('${')) return () => String(value);
  return (context: BindingContext): string =>
    value.replace(BINDING_PATTERN, (_match: string, expression: string) =>
      formatBindingValue(resolveExpression(expression, context)),
    );
}

export function collectMemoryBindings(node: LayoutNode, found: MemoryBindingRef[] = []): MemoryBindingRef[] {
  const seen = new Set(found.map((binding) => `${binding.tier}:${binding.key}`));
  const add = (text: string): void => {
    for (const match of text.matchAll(MEMORY_PATTERN)) {
      const tier = match[1] as MemoryTier;
      const key = match[2] ?? '';
      const identity = `${tier}:${key}`;
      if (!seen.has(identity)) {
        seen.add(identity);
        found.push({ tier, key });
      }
    }
  };

  for (const value of Object.values(node.props ?? {})) {
    if (typeof value === 'string') add(value);
  }
  for (const action of node.on_press ?? []) {
    if (typeof action.value === 'string') add(action.value);
    for (const value of Object.values(action.data ?? {})) {
      if (typeof value === 'string') add(value);
    }
  }
  for (const child of node.children ?? []) collectMemoryBindings(child, found);
  return found;
}
