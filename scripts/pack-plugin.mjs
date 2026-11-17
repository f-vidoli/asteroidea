import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { strToU8, zipSync } from 'fflate';
import { STANDARD_FOLDERS, validatePluginDir } from './plugin-tools.mjs';

const id = process.argv[2];
if (!id) {
  console.error('usage: npm run plugin:pack -- <plugin_id>');
  process.exit(1);
}

const root = resolve(import.meta.dirname, '..');
const source = join(root, 'src/plugins', id);
const errors = validatePluginDir(source, id);
if (errors.length > 0) {
  console.error(errors.map((error) => `  - ${error}`).join('\n'));
  process.exit(1);
}

const built = join(root, 'dist/plugins', id);
if (!existsSync(join(built, 'index.js'))) {
  console.error('run `npm run build` first so the plugin module is compiled');
  process.exit(1);
}

const files = {};
const addTree = (dir, prefix = '') => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) addTree(path, relative);
    else files[`${id}/${relative}`] = new Uint8Array(readFileSync(path));
  }
};

addTree(source);
files[`${id}/index.js`] = new Uint8Array(readFileSync(join(built, 'index.js')));
for (const folder of STANDARD_FOLDERS) files[`${id}/${folder}/.gitkeep`] = strToU8('');

const output = join(root, 'dist/plugins', `${id}.zip`);
mkdirSync(join(root, 'dist/plugins'), { recursive: true });
writeFileSync(output, zipSync(files, { level: 6 }));
console.log(`wrote ${output}`);
