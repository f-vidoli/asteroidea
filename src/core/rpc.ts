import { invoke } from '@tauri-apps/api/core';
import type { ApiClient } from './types';

export function createApiClient(): ApiClient {
  return {
    async invoke<T>(command: string, args: Record<string, unknown> = {}): Promise<T> {
      return invoke<T>(command, args);
    },
    async readPluginFile(pluginId: string, relativePath: string): Promise<string> {
      try {
        return await invoke<string>('read_plugin_file', { pluginId, relativePath });
      } catch {
        const prefixes = import.meta.env.DEV
          ? [`/src/plugins/${pluginId}/${relativePath}`, `/plugins/${pluginId}/${relativePath}`]
          : [`/plugins/${pluginId}/${relativePath}`];
        for (const prefix of prefixes) {
          const response = await fetch(new URL(prefix, window.location.origin));
          if (response.ok) return response.text();
        }
        throw new Error(`cannot read plugin file ${pluginId}/${relativePath}`);
      }
    },
  };
}
