import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd(), '..')
const outputDir = resolve(projectRoot, 'docs/redesign', process.env.STAGE_SCREENSHOT_DIR ?? 'phase5')
const baseUrl = process.env.TURBINEIQ_BASE_URL ?? 'http://127.0.0.1:8011'
const screenshotLabel = process.env.STAGE_SCREENSHOT_LABEL ?? 'after'

await mkdir(outputDir, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-background-networking', '--disable-component-update'] })
try {
  for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' })
    await context.addInitScript((value) => localStorage.setItem('turbineiq-theme', value), theme)
    const page = await context.newPage()
    await page.goto(`${baseUrl}/#/overview?scenario=compressor_fouling&seed=42&i=48`, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('.engine-button')?.getAttribute('aria-label')?.includes('connected'), null, { timeout: 30000 })
    await page.getByRole('status').filter({ hasText: 'Blender GLB' }).waitFor({ timeout: 30000 })
    if (screenshotLabel.toLowerCase().includes('after')) {
      await page.waitForFunction(() => document.querySelector('.viewer-selection-label')?.textContent?.trim().length, null, { timeout: 10000 })
    }
    await page.locator('.viewer-panel').screenshot({ path: resolve(outputDir, `stage-${screenshotLabel}-${theme}.png`), animations: 'disabled' })
    await context.close()
    console.log(`Captured ${theme} Stage ${screenshotLabel} selection treatment`)
  }
} finally {
  await browser.close()
}
