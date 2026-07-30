import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const backend = loadEnv(mode, '.', '').BACKEND_BASE_URL || 'http://localhost:8080';
  const proxy = { target: backend, changeOrigin: false, xfwd: true };

  return {
    plugins: [tailwindcss(), sveltekit()],
    server: {
      proxy: {
        '/api': proxy,
        '/oauth2': proxy,
        '/login': proxy,
        '/logout': proxy
      }
    },
    // ECharts 6 and zrender declare an old nested tslib whose ESM wrapper is
    // incorrectly prebundled by Vite as a missing default export. Force one
    // modern tslib instance for all chart modules.
    resolve: {
      conditions: ['browser'],
      dedupe: ['tslib']
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test-setup.ts'],
      include: ['src/**/*.test.ts']
    }
  };
});
