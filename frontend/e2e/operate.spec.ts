import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('Operate: start a simulated unit, load it, and trip it', async ({ page }) => {
  await page.goto('/#/operate')
  await expect(page.getByText(/Simulated plant: Rowen-type dynamics/)).toBeVisible()

  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByTestId('unit-state')).toHaveText('Standstill')
  await expect(page.getByRole('button', { name: 'Normal stop' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Emergency trip' })).toBeDisabled()

  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await expect(page.getByTestId('unit-state')).toHaveText('Cranking')

  await page.getByRole('button', { name: '60×' }).click()
  await page.getByRole('button', { name: 'Run' }).click()
  await expect(page.getByTestId('unit-state')).toHaveText(/Full speed, no load|Loaded/, { timeout: 30000 })

  await page.getByLabel('Load setpoint (MW)').fill('30')
  await page.getByLabel('Ramp (MW/min)').fill('60')
  await page.getByRole('button', { name: 'Apply load' }).click()
  await expect(page.getByTestId('unit-state')).toHaveText('Loaded', { timeout: 30000 })
  await expect.poll(async () => parseFloat((await page.getByTestId('power').textContent()) ?? '0'), { timeout: 30000 }).toBeGreaterThan(25)

  await page.getByRole('button', { name: 'Emergency trip' }).click()
  await expect(page.getByTestId('unit-state')).toHaveText('Tripped')
  await expect(page.getByRole('status')).toContainText('Manual emergency trip')
  await expect(page.getByRole('button', { name: 'Reset trip' })).toBeEnabled({ timeout: 30000 })
  await expect(page.getByRole('img', { name: /Electrical power/ })).toBeVisible()
})

test('Operate: rejects out-of-range input with an accessible message and sends nothing', async ({ page }) => {
  await page.goto('/#/operate')
  await page.getByLabel('Ambient (°C)').fill('99')
  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByRole('alert')).toContainText('-40 to 55')
  await expect(page.getByLabel('Ambient (°C)')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByTestId('unit-state')).toHaveCount(0)
})

test('Operate: no serious axe violations and no horizontal scroll on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/operate')
  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByTestId('unit-state')).toBeVisible()
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme })
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(results.violations.map((v) => `${scheme}: ${v.id} ${v.nodes[0]?.target}`)).toEqual([])
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})

test('Operate: inject faults, read their ground truth, wash and clear them', async ({ page }) => {
  await page.goto('/#/operate')
  await page.getByRole('button', { name: 'Create unit' }).click()
  await expect(page.getByTestId('no-faults')).toBeVisible()

  await page.getByLabel('Sensor', { exact: true }).selectOption('exhaust_temperature')
  await page.getByLabel('Fault mode').selectOption('bias')
  await page.getByLabel('Magnitude (K)').fill('-20')
  await page.getByRole('button', { name: 'Inject sensor fault' }).click()
  await expect(page.getByTestId('active-faults')).toContainText('Exhaust temperature sensor bias -20 K')
  // Faults act from the next step: once the simulation runs, the reading sits about 20 K below the truth.
  const number = async (testId: string) => parseFloat((await page.getByTestId(testId).textContent()) ?? 'NaN')
  await page.getByRole('button', { name: 'Run' }).click()
  await expect.poll(async () => (await number('truth-exhaust_temperature')) - (await number('reading-exhaust_temperature'))).toBeGreaterThan(17)
  await page.getByRole('button', { name: 'Pause' }).click()

  await page.getByLabel('Severity (%)').fill('3')
  await page.getByRole('button', { name: 'Inject degradation' }).click()
  await expect(page.getByTestId('active-faults')).toContainText('Compressor fouling 3.00 %')
  await page.getByRole('button', { name: 'Offline compressor wash' }).click()
  await expect(page.getByTestId('active-faults')).not.toContainText('Compressor fouling')

  await page.getByRole('button', { name: 'Clear Exhaust temperature sensor' }).click()
  await expect(page.getByTestId('no-faults')).toBeVisible()

  await page.getByLabel('Magnitude (K)').fill('500')
  await page.getByRole('button', { name: 'Inject sensor fault' }).click()
  await expect(page.getByLabel('Magnitude (K)')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByTestId('no-faults')).toBeVisible()
})
