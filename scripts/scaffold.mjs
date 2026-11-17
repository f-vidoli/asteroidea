import { cpSync, existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const id = process.argv[2];
if (!id || !/^[A-Za-z][A-Za-z0-9_]*$/.test(id)) {
  console.error('usage: npm run plugin:new -- <plugin_id>  (letters, digits, underscores)');
  process.exit(1);
}

const root = resolve(import.meta.dirname, '..');
const template = join(root, 'templates/plugin-template');
const target = join(root, 'src/plugins', id);
if (existsSync(target)) {
  console.error(`plugin already exists: ${target}`);
  process.exit(1);
}

cpSync(template, target, { recursive: true });
const files = [];
const walk = (dir) => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path);
    else files.push(path);
  }
};
walk(target);
for (const file of files) {
  const text = readFileSync(file, 'utf8');
  writeFileSync(file, text.replaceAll('my_plugin', id).replaceAll('My Plugin', id));
}
console.log(`created ${target}`);
