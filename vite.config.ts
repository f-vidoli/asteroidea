import { fileURLToPath } from 'node:url';
import { readdirSync, statSync, mkdirSync, copyFileSync, existsSync, rmSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { defineConfig, type Plugin } from 'vite';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const pluginsRoot = resolve(rootDir, 'src/plugins');

function copyJsonTree(source: string, target: string): void {
  mkdirSync(target, { recursive: true });
  for (const entry of readdirSync(source)) {
    const from = join(source, entry);
    const to = join(target, entry);
    if (statSync(from).isDirectory()) {
      copyJsonTree(from, to);
    } else if (/\.(json|ya?ml)$/.test(entry)) {
      copyFileSync(from, to);
    }
  }
}

function cleanStalePluginResources(): void {
  for (const profile of ['debug', 'release']) {
    for (const relative of ['plugins', '_up_/src/plugins']) {
      rmSync(resolve(rootDir, 'src-tauri/target', profile, relative), { recursive: true, force: true });
    }
  }
}

function pluginAssets(): Plugin {
  return {
    name: 'asteroidea-plugin-assets',
    apply: 'build',
    buildStart() {
      cleanStalePluginResources();
    },
    closeBundle() {
      if (!existsSync(pluginsRoot)) return;
      for (const id of readdirSync(pluginsRoot)) {
        const source = join(pluginsRoot, id);
        if (statSync(source).isDirectory()) copyJsonTree(source, resolve(rootDir, 'dist/plugins', id));
      }
    },
  };
}

const inputs: Record<string, string> = {
  main: resolve(rootDir, 'index.html'),
  launcher: resolve(rootDir, 'src/launcher/index.ts'),
  manager: resolve(rootDir, 'src/core/plugin_manager.ts'),
};

if (existsSync(pluginsRoot)) {
  for (const id of readdirSync(pluginsRoot)) {
    const entry = join(pluginsRoot, id, 'index.ts');
    if (existsSync(entry)) inputs[`plugins/${id}/index`] = entry;
  }
}

export default defineConfig({
  plugins: [pluginAssets()],
  server: { port: 1420, strictPort: true },
  build: {
    target: 'es2022',
    rollupOptions: {
      input: inputs,
      preserveEntrySignatures: 'strict',
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
});
