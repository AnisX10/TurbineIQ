import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'

const output = resolve(process.cwd(), 'test-results/assistant-dock-captures')
const viewports = [
  ['1440', 1440, 960],
  ['1024', 1024, 900],
  ['768', 768, 900],
  ['375', 375, 844],
] as const

test.skip(process.env.CAPTURE_DOCK !== '1', 'Set CAPTURE_DOCK=1 to refresh the documented dock screenshots.')

test('capture five assistant dock states at all widths and themes', async ({ page }) => {
  test.setTimeout(300000)
  await mkdir(output, { recursive: true })
  for (const theme of ['light', 'dark'] as const) {
    if (page.url().startsWith('http')) {
      await page.evaluate((value) => {
        localStorage.setItem('turbineiq-theme', value)
        sessionStorage.removeItem('turbineiq-cloud-consent')
      }, theme)
    }
    await page.setViewportSize({ width: 1440, height: 960 })
    await page.addInitScript((value) => localStorage.setItem('turbineiq-theme', value), theme)
    await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
    await page.evaluate(() => sessionStorage.clear())
    await page.reload()
    await expect(page.locator('.kpi-row')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Stage' })).toBeVisible()

    await captureWidths(page, theme, 'dock-closed')

    await page.locator('.assistant-header-ask').click()
    const dock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
    await dock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain the compressor output at this synthetic sample.')
    await dock.getByRole('button', { name: 'Ask', exact: true }).click()
    await expect(dock.locator('.assistant-answer').first()).toContainText('26.30 MW', { timeout: 30000 })
    await dock.locator('.assistant-trace summary').first().click()
    await expect(dock.locator('.assistant-trace').first()).toHaveAttribute('open', '')
    await captureWidths(page, theme, 'answer-tool-trace')

    await dock.getByRole('button', { name: 'Cloud' }).click()
    const consent = page.getByRole('dialog', { name: 'Review Cloud sharing' })
    await expect(consent).toBeVisible()
    await captureWidths(page, theme, 'cloud-consent')
    await consent.getByRole('button', { name: 'Continue to Cloud' }).click()

    await page.route('**/api/assistant/stream', async (route) => {
      const event = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`
      const answer = {
        answer: 'The configured provider was rate limited; this is the deterministic local response.',
        mode: 'local_fallback',
        warning: 'Provider temporarily unavailable (rate_limit).',
        tool_calls: [],
        synthetic_only: true,
      }
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          event('status', { state: 'working', message: 'Using the deterministic local fallback.' }),
          event('token', { text: answer.answer }),
          event('done', answer),
        ].join(''),
      })
    })
    await dock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Show a provider fallback for the screenshot.')
    await dock.getByRole('button', { name: 'Ask', exact: true }).click()
    await expect(dock.locator('.assistant-turn').last().locator('.assistant-answer-meta')).toContainText('Local fallback')
    await captureWidths(page, theme, 'local-fallback')
    await page.unroute('**/api/assistant/stream')

    await page.evaluate(() => sessionStorage.setItem('turbineiq-cloud-consent', 'accepted'))
    await page.reload()
    await expect(page.locator('.kpi-row')).toBeVisible()
    await page.locator('.assistant-header-ask').click()
    const streamingDock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
    await streamingDock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('slow response for capture')
    await streamingDock.getByRole('button', { name: 'Ask', exact: true }).click()
    await expect(streamingDock.getByRole('button', { name: 'Stop response' })).toBeVisible()
    await captureWidths(page, theme, 'streaming')
    await streamingDock.getByRole('button', { name: 'Stop response' }).click()
    await page.keyboard.press('Escape')
    await expect(streamingDock).not.toBeVisible()
  }
})

async function captureWidths(page: import('@playwright/test').Page, theme: string, state: string) {
  for (const [widthLabel, width, height] of viewports) {
    await page.setViewportSize({ width, height })
    await page.screenshot({
      path: resolve(output, `${state}-${widthLabel}-${theme}.png`),
      fullPage: false,
      animations: 'disabled',
    })
  }
}
