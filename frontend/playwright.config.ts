import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: process.env.CI ? 1 : undefined,
  retries: 0,
  timeout: 120000,
  reporter: [['list'], ['json', { outputFile: 'test-results/playwright-results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:8021',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
    launchOptions: { args: ['--disable-background-networking', '--disable-component-update'] },
  },
  webServer: [
    {
      command: 'python e2e/fake_provider.py',
      cwd: '.',
      url: 'http://127.0.0.1:8022/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command: 'python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8021',
      cwd: '..',
      url: 'http://127.0.0.1:8021/api/health',
      env: {
        PYTHONPATH: 'src',
        TURBINEIQ_LLM_PROVIDER: 'custom',
        TURBINEIQ_LLM_BASE_URL: 'http://127.0.0.1:8022/v1',
        TURBINEIQ_LLM_MODEL: 'fake-gpt-oss-20b',
        TURBINEIQ_LLM_API_KEY: 'playwright-fake-key',
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
  outputDir: './test-results',
})
