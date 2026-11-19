import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests (T-050): a real browser against a real API.
 *
 * Nothing here touches the dev servers or the dev database. Playwright starts its own backend on
 * port 8020 with a throwaway SQLite file that is deleted and rebuilt on every run, filled by the
 * same synthetic seed script used for manual testing (backend/scripts/seed_dev.py), and its own
 * Vite server on port 5190 that proxies to it. Run with `npm run e2e`.
 */
const API_PORT = 8020;
const WEB_PORT = 5190;
const DB = '/tmp/pi360-playwright.sqlite3';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  // One database and a handful of tests that change settings: run them one after another.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // Locally the installed Google Chrome is used (no download); CI uses Playwright's own Chromium.
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: process.env.CI ? undefined : 'chrome',
      },
    },
  ],
  webServer: [
    {
      command: [
        `rm -f ${DB}`,
        `export DJANGO_DEBUG=1 DATABASE_URL=sqlite:///${DB} API_THROTTLE_LOGIN=1000/min API_THROTTLE_ANON=10000/min API_THROTTLE_USER=100000/min DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:${WEB_PORT}`,
        'uv run python manage.py migrate -v 0',
        'uv run python manage.py shell < scripts/seed_dev.py',
        `uv run python manage.py runserver ${API_PORT} --noreload`,
      ].join(' && '),
      cwd: '../backend',
      url: `http://localhost:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      env: { VITE_API_PROXY: `http://localhost:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
