import { defineDaemon } from '../../../sdk/index';

export const sampleDaemon = defineDaemon({
  name: 'my_plugin.daemon',
  start(context) {
    const timer = window.setInterval(() => {
      if (context.signal.aborted) return;
      context.storage.public.set('my_plugin.ticks', (context.storage.public.get<number>('my_plugin.ticks') ?? 0) + 1);
    }, 3000);
    context.onDispose(() => window.clearInterval(timer));
  },
});
