import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parse as parseYaml } from 'yaml';

export const STANDARD_FOLDERS = ['widgets', 'libraries', 'fetchers', 'daemons'];
const NODE_TYPES = new Set(['BoxLayout', 'ScrollView', 'Label', 'Button', 'Spacer']);
const PROPS = new Set([
  'text', 'color', 'background', 'padding', 'spacing', 'orientation',
  'font_size', 'class', 'width', 'height', 'min_height',
]);
const ACTIONS = new Set(['storage.set', 'emit', 'refresh']);
const BINDING = /\$\{([^{}]+)\}/g;
const ALLOWED_BINDING = /^(now|payload\..+|memory\.(private|settings|public)\..+)$/;
const DANGEROUS_TOKENS = ['__proto__', 'constructor', 'prototype'];

export function readLayout(file) {
  const text = readFileSync(file, 'utf8');
  return /\.ya?ml$/i.test(file) ? parseYaml(text) : JSON.parse(text);
}

function checkBindings(value, errors, where) {
  if (typeof value !== 'string') return;
  for (const match of value.matchAll(BINDING)) {
    const expression = (match[1] ?? '').trim();
    if (DANGEROUS_TOKENS.some((token) => expression.includes(token)) || !ALLOWED_BINDING.test(expression)) {
      errors.push(`${where}: invalid binding "${expression}"`);
    }
  }
}

function checkNode(node, errors, where) {
  if (!node || typeof node !== 'object' || Array.isArray(node)) {
    errors.push(`${where}: node must be an object`);
    return;
  }
  if (!NODE_TYPES.has(node.type)) errors.push(`${where}: unknown node type "${node.type}"`);
  for (const [name, value] of Object.entries(node.props ?? {})) {
    if (!PROPS.has(name)) errors.push(`${where}.props.${name}: unsupported property`);
    checkBindings(value, errors, `${where}.props.${name}`);
  }
  for (const action of node.on_press ?? []) {
    if (!ACTIONS.has(action?.action)) errors.push(`${where}.on_press: unknown action "${action?.action}"`);
    checkBindings(action?.value, errors, `${where}.on_press.value`);
  }
  (node.children ?? []).forEach((child, index) => checkNode(child, errors, `${where}.children[${index}]`));
}

export function validatePluginDir(dir, id) {
  const errors = [];
  const manifestPath = join(dir, 'manifest.json');
  if (!existsSync(manifestPath)) return ['missing manifest.json'];
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    return [`manifest.json: ${error.message}`];
  }
  if (manifest.id !== id) errors.push(`manifest id "${manifest.id}" does not match folder "${id}"`);
  for (const folder of STANDARD_FOLDERS) {
    if (!existsSync(join(dir, folder))) errors.push(`missing folder ${folder}/`);
  }
  for (const layoutPath of manifest.layouts ?? []) {
    const file = join(dir, layoutPath);
    if (!existsSync(file)) {
      errors.push(`missing layout ${layoutPath}`);
      continue;
    }
    try {
      const layout = readLayout(file);
      if (typeof layout?.name !== 'string') errors.push(`${layoutPath}: missing name`);
      checkNode(layout?.root, errors, `${layoutPath}.root`);
    } catch (error) {
      errors.push(`${layoutPath}: ${error.message}`);
    }
  }
  return errors;
}
