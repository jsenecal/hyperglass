/// <reference types="vitest" />

import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    coverage: {
      provider: 'v8',
      // text-summary prints the overall totals in the CI log; text lists
      // per-file lines; lcov is emitted for any external coverage tooling.
      reporter: ['text', 'text-summary', 'lcov'],
      // Report on application source only; skip tests, config, generated
      // build output, and type-only declarations.
      include: ['components/**', 'hooks/**', 'pages/**', 'util/**', 'types/**'],
      exclude: [
        '**/*.test.{ts,tsx}',
        '**/*.d.ts',
        '**/__tests__/**',
        '.next/**',
        'out/**',
        'node_modules/**',
      ],
    },
  },
  resolve: {
    alias: {
      '~': path.resolve(__dirname, './'),
    },
  },
});
