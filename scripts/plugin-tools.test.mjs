import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { STANDARD_FOLDERS, validatePluginDir } from './plugin-tools.mjs';

const roots = [];

function pluginDir({ manifest = { id: 'sample', name: 'Sample', version: '0.1.0' }, layout } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'asteroidea-plugin-'));
  roots.push(root);
  const dir = join(root, 'sample');
  mkdirSync(dir);
  for (const folder of STANDARD_FOLDERS) mkdirSync(join(dir, folder));
  writeFileSync(join(dir, 'manifest.json'), JSON.stringify(manifest));
  if (layout !== undefined) {
    writeFileSync(join(dir, 'widgets/layout.json'), JSON.stringify(layout));
    manifest.layouts = ['widgets/layout.json'];
    writeFileSync(join(dir, 'manifest.json'), JSON.stringify(manifest));
  }
  return dir;
}

after(() => {
  for (const root of roots) rmSync(root, { recursive: true, force: true });
});

test('valid plugin directory passes validation', () => {
  const dir = pluginDir({
    layout: {
      name: 'Sample',
      root: {
        type: 'BoxLayout',
        props: { text: '${payload.value}', color: '${memory.public.theme}' },
      },
    },
  });
  assert.deepEqual(validatePluginDir(dir, 'sample'), []);
});

test('missing folders and id mismatch are reported', () => {
  const dir = pluginDir();
  rmSync(join(dir, 'daemons'), { recursive: true });
  const errors = validatePluginDir(dir, 'other');
  assert.ok(errors.some((error) => error.includes('manifest id')));
  assert.ok(errors.some((error) => error.includes('missing folder daemons')));
});

test('unsafe and malformed bindings are reported', () => {
  const dir = pluginDir({
    layout: {
      name: 'Sample',
      root: { type: 'Label', props: { text: '${memory.public.__proto__.x}' } },
    },
  });
  const errors = validatePluginDir(dir, 'sample');
  assert.ok(errors.some((error) => error.includes('invalid binding')));
});

test('missing declared layout is reported', () => {
  const dir = pluginDir({ manifest: { id: 'sample', name: 'Sample', version: '0.1.0', layouts: ['widgets/absent.json'] } });
  const errors = validatePluginDir(dir, 'sample');
  assert.ok(errors.some((error) => error.includes('missing layout')));
});
