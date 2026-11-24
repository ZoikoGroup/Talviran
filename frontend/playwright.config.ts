import { defineConfig, devices } from '@playwright/test'

/**
 * G09 remediation (UAT gap analysis): a committed, repeatable Playwright
 * suite proving the Watchlists header reflows at mobile widths instead of
 * clipping the "New Watchlist" button, plus basic keyboard/screen-reader
 * coverage for the icon-only buttons fixed alongside it.
 *
 * `webServer` reuses whatever is already serving http://localhost:5173
 * (the normal `npm run dev` process) rather than racing it for the port -
 * see CLAUDE.md's "Only run one `uvicorn --reload` instance at a time"
 * sharp edge, which applies just as much to Vite's dev server on Windows.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
