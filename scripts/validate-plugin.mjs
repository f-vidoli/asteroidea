import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { validatePluginDir } from './plugin-tools.mjs';

const root = resolve(import.meta.dirname, '..');
const pluginsRoot = join(root, 'src/plugins');
const requested = process.argv[2];
const ids = requested
  ? [requested]
  : existsSync(pluginsRoot)
    ? readdirSync(pluginsRoot).filter((entry) => statSync(join(pluginsRoot, entry)).isDirectory())
    : [];

if (ids.length === 0) {
  console.error('no plugins found');
  process.exit(1);
}

let failed = false;
for (const id of ids) {
  const errors = validatePluginDir(join(pluginsRoot, id), id);
  if (errors.length === 0) {
    console.log(`${id}: OK`);
  } else {
    failed = true;
    console.error(`${id}:`);
    for (const error of errors) console.error(`  - ${error}`);
  }
}
process.exit(failed ? 1 : 0);
