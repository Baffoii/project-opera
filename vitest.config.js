import { defineConfig } from 'vitest/config';

// OPERA frontend tests. Upstream's node:test runner only discovers *.test.mjs, so these use *.spec.js.
export default defineConfig({
  test: {
    include: ['tests/opera/**/*.spec.js'],
    environment: 'jsdom',
    globals: false,
  },
});
