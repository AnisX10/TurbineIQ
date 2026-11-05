import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  timeout: 120000,
  reporter: [['list'], ['json', { outputFile: 'test-results/playwright-results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:8011',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
    launchOptions: { args: ['--disable-background-networking', '--disable-component-update'] },
  },
  webServer: {
    command: 'python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8011',
    cwd: '..',
    url: 'http://127.0.0.1:8011/api/health',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
  outputDir: './test-results',
})
