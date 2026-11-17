import { definePlugin } from '../../sdk/index';
import { sampleFetcher } from './fetchers/sample_fetcher';
import { sampleDaemon } from './daemons/sample_daemon';

export default definePlugin({
  manifest: {
    id: 'my_plugin',
    name: 'My Plugin',
    version: '0.1.0',
    api_version: '1',
    entry: 'index.ts',
    layouts: ['widgets/layout.json'],
  },
  fetchers: [sampleFetcher],
  daemons: [sampleDaemon],
});
