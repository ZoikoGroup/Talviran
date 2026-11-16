import path from 'path'
import { defineConfig, configDefaults } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'node',
    // frontend/tests/** holds the Playwright E2E suite (playwright.config.ts
    // points `testDir` there) - it must stay out of vitest's own discovery,
    // which otherwise matches its *.spec.ts files too and fails with
    // "Playwright Test did not expect test.describe() to be called here."
    exclude: [...configDefaults.exclude, 'tests/**'],
  },
})
