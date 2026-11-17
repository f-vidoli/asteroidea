import type { PluginManager } from '../../core/plugin_manager';
import type { ApiClient, PluginRecord } from '../../core/types';
import { confirmDialog } from './confirm_dialog';

export interface ManagerPanelOptions {
  api: ApiClient;
  manager: PluginManager;
}

function trashIcon(): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'trash-icon');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.8');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.append(path);
  return svg;
}

async function describe(api: ApiClient, record: PluginRecord): Promise<string> {
  try {
    const raw = await api.readPluginFile(record.id, 'manifest.json');
    const manifest: unknown = JSON.parse(raw);
    if (typeof manifest === 'object' && manifest !== null) {
      const name = (manifest as Record<string, unknown>)['name'];
      const version = (manifest as Record<string, unknown>)['version'];
      if (typeof name === 'string' && typeof version === 'string') return `${name} ${version}`;
    }
  } catch {
    return record.id;
  }
  return record.id;
}

export function createManagerPanel(options: ManagerPanelOptions): HTMLElement {
  const { api, manager } = options;
  const panel = document.createElement('section');
  panel.className = 'panel';
  const title = document.createElement('h2');
  title.textContent = 'Plugin manager';
  panel.append(title);

  const status = document.createElement('p');
  status.className = 'panel-status';
  status.textContent = 'Loading plugins...';
  panel.append(status);

  const toolbar = document.createElement('div');
  toolbar.className = 'panel-actions';
  const refreshButton = document.createElement('button');
  refreshButton.type = 'button';
  refreshButton.textContent = 'Refresh list';
  const restartButton = document.createElement('button');
  restartButton.type = 'button';
  restartButton.textContent = 'Restart app';
  toolbar.append(refreshButton, restartButton);
  panel.append(toolbar);

  const list = document.createElement('div');
  list.className = 'plugin-list';
  panel.append(list);

  const installTitle = document.createElement('h3');
  installTitle.textContent = 'Install';
  panel.append(installTitle);

  const zipRow = document.createElement('div');
  zipRow.className = 'panel-actions';
  const zipInput = document.createElement('input');
  zipInput.type = 'file';
  zipInput.accept = '.zip,application/zip';
  const zipButton = document.createElement('button');
  zipButton.type = 'button';
  zipButton.textContent = 'Install ZIP';
  zipRow.append(zipInput, zipButton);

  const repoInput = document.createElement('input');
  repoInput.type = 'text';
  repoInput.placeholder = 'owner/repository';
  const refInput = document.createElement('input');
  refInput.type = 'text';
  refInput.value = 'main';
  refInput.placeholder = 'ref';
  const githubButton = document.createElement('button');
  githubButton.type = 'button';
  githubButton.textContent = 'Install from GitHub';
  const repoRow = document.createElement('div');
  repoRow.className = 'panel-actions';
  repoRow.append(repoInput, refInput, githubButton);

  panel.append(zipRow, repoRow);

  const setStatus = (message: string): void => {
    status.textContent = message;
  };

  const refresh = async (): Promise<void> => {
    const records = await api.invoke<PluginRecord[]>('list_plugins');
    list.replaceChildren();
    for (const record of records) {
      const item = document.createElement('div');
      item.className = 'plugin-item';
      const header = document.createElement('div');
      header.className = 'plugin-item-header';
      const name = document.createElement('strong');
      name.textContent = await describe(api, record);
      header.append(name);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'icon-button';
      remove.title = record.removable ? `Delete ${record.id}` : 'Bundled plugin';
      remove.setAttribute('aria-label', remove.title);
      remove.disabled = !record.removable;
      remove.append(trashIcon());
      remove.addEventListener('click', () => {
        void confirmDialog({
          title: 'Delete plugin',
          message: `Are you sure you want to delete ${record.id}?`,
          confirmLabel: 'Delete',
        })
          .then(async (confirmed) => {
            if (!confirmed) return;
            await manager.uninstall(record.id);
            setStatus(`Deleted ${record.id}. Restart to unload it.`);
            await refresh();
          })
          .catch((error: unknown) => setStatus(`Delete failed: ${String(error)}`));
      });
      header.append(remove);
      const detail = document.createElement('span');
      detail.textContent = `${record.id} - ${record.folders.join(', ')}`;
      item.append(header, detail);
      list.append(item);
    }
    setStatus(`${records.length} plugin(s) installed.`);
    void api.invoke<void>('storage_write', {
      tier: 'settings',
      owner: 'global',
      key: 'ui.plugin_records',
      value: records.map((record) => record.id),
    });
  };

  refreshButton.addEventListener('click', () => {
    void refresh().catch((error: unknown) => setStatus(`Refresh failed: ${String(error)}`));
  });

  restartButton.addEventListener('click', () => {
    void manager.restart().catch((error: unknown) => setStatus(`Restart failed: ${String(error)}`));
  });

  zipButton.addEventListener('click', () => {
    const file = zipInput.files?.[0];
    if (!file) {
      setStatus('Choose a .zip file first.');
      return;
    }
    void file
      .arrayBuffer()
      .then((buffer) => manager.installZip(new Uint8Array(buffer)))
      .then((id) => {
        setStatus(`Installed ${id}.`);
        return refresh();
      })
      .catch((error: unknown) => setStatus(`Install failed: ${String(error)}`));
  });

  githubButton.addEventListener('click', () => {
    void manager
      .installFromGithub(repoInput.value.trim(), refInput.value.trim() || 'main')
      .then((id) => {
        setStatus(`Installed ${id}.`);
        return refresh();
      })
      .catch((error: unknown) => setStatus(`Install failed: ${String(error)}`));
  });

  void refresh().catch((error: unknown) => setStatus(`Refresh failed: ${String(error)}`));

  return panel;
}
