import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function sessionId(page: Page): Promise<string> {
  const id = await page.evaluate(() => sessionStorage.getItem('turbineiq-sim-session'))
  expect(id).toBeTruthy()
  return id!
}

/** Advance the shared session on the server (fast), then let the console poll once. */
async function advance(page: Page, seconds: number) {
  const id = await sessionId(page)
  for (let left = seconds; left > 0; left -= 120) {
    const response = await page.request.post(`/api/sim/sessions/${id}/advance`, { data: { seconds: Math.min(120, left) } })
    expect(response.ok()).toBe(true)
  }
  await page.getByRole('button', { name: '1×' }).click()
  await page.getByRole('button', { name: 'Run' }).click()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: 'Pause' }).click()
}

test('Twin: the app lands on the live twin console', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/#\/twin\?/)
  await expect(page.getByRole('heading', { level: 1, name: 'Live twin' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Start a live twin' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Live twin' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: 'Operate' })).toBeVisible()
})

test('Twin: create, start, load, switch modes, inject a fault and read the logs from one screen', async ({ page }) => {
  // About 13 simulated minutes with the supervisor ticking every second on the server.
  test.setTimeout(300000)
  const started = Date.now()
  const mark = (label: string) => console.log(`[twin e2e] ${label} at ${((Date.now() - started) / 1000).toFixed(1)} s`)
  await page.goto('/#/twin')
  await page.getByRole('group', { name: 'Layer mode' }).getByRole('button', { name: 'Advisory' }).click()
  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByTestId('twin-unit-state')).toHaveText('Standstill')
  await expect(page.getByTestId('health-fuel_valve')).toContainText('Not monitored')
  await expect(page.getByTestId('health-compressor_flow')).toContainText('—')
  await expect(page.getByTestId('no-recommendation')).toBeVisible()

  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await advance(page, 300)
  await expect(page.getByTestId('twin-unit-state')).toHaveText(/Loaded|Full speed, no load/)
  await page.getByRole('textbox', { name: 'Demand' }).fill('35')
  await page.getByRole('button', { name: 'Set', exact: true }).click()
  await expect(page.getByTestId('now-power')).toContainText('demand 35.0 MW')
  await advance(page, 480)
  mark('loaded')
  await expect.poll(async () => parseFloat((await page.getByTestId('now-power').locator('.twin-now-value').textContent()) ?? '0')).toBeGreaterThan(33)
  await expect(page.getByTestId('health-compressor_flow')).toContainText('±')
  await expect(page.getByTestId('callout-compressor')).toBeVisible({ timeout: 30000 })

  // Advisory: something waits for the operator; reject it and it leaves the card open-state.
  const rec = page.getByTestId('recommendation')
  await expect(rec).toBeVisible()
  await expect(rec.getByRole('button', { name: 'Reject' })).toBeVisible()
  await rec.getByRole('button', { name: 'Reject' }).click()
  await expect(rec.getByRole('button', { name: 'Reject' })).toHaveCount(0)

  const modes = page.getByRole('group', { name: 'Layer mode' })
  await modes.getByRole('button', { name: 'Manual' }).click()
  await expect(modes.getByRole('button', { name: 'Manual' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('now-mode')).toContainText('Manual')
  const id = await sessionId(page)
  expect((await (await page.request.get(`/api/sim/sessions/${id}/supervisor`)).json()).mode).toBe('manual')

  await page.getByRole('button', { name: 'Faults' }).click()
  const faults = page.getByRole('dialog', { name: 'Inject a fault' })
  await faults.getByLabel('Sensor', { exact: true }).selectOption('exhaust_temperature')
  await faults.getByLabel('Fault mode').selectOption('stuck')
  await faults.getByRole('button', { name: 'Inject sensor fault' }).click()
  await expect(faults.getByTestId('active-faults')).toContainText('Exhaust temperature')
  await faults.getByRole('button', { name: 'Close faults' }).click()

  mark('fault injected')
  await page.getByRole('button', { name: 'Log', exact: true }).click()
  const log = page.getByRole('dialog', { name: 'Decision and event log' })
  await expect(log.getByText(/Rejected/).first()).toBeVisible()
  await expect(log.getByText(/inject sensor fault/)).toBeVisible()
  await log.getByRole('button', { name: 'Close log' }).click()

  // The same unit is the one Operate shows.
  await page.getByRole('link', { name: 'Operate', exact: true }).first().click()
  await expect(page.getByTestId('unit-state')).toHaveText(/Loaded/)
})

test('Twin: no serious axe violations and no horizontal scroll on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/twin')
  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByTestId('twin-unit-state')).toBeVisible()
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme })
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(results.violations.map((v) => `${scheme}: ${v.id} ${v.nodes[0]?.target}`)).toEqual([])
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})
