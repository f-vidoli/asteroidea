import { buildPayload, defineFetcher } from '../../../sdk/index';

export const sampleFetcher = defineFetcher({
  name: 'my_plugin.fetcher',
  intervalMs: 5000,
  run() {
    return buildPayload('feed', 'my_plugin.card', { value: new Date().toISOString() }, 'my_plugin-card');
  },
});
