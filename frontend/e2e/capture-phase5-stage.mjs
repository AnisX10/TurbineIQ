import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd(), '..')
const outputDir = resolve(projectRoot, 'docs/redesign', process.env.STAGE_SCREENSHOT_DIR ?? 'phase5')
const baseUrl = process.env.TURBINEIQ_BASE_URL ?? 'http://127.0.0.1:8011'
const screenshotLabel = process.env.STAGE_SCREENSHOT_LABEL ?? 'after'
const viewportWidth = Number(process.env.STAGE_SCREENSHOT_WIDTH ?? 1440)
const viewportHeight = Number(process.env.STAGE_SCREENSHOT_HEIGHT ?? 1100)

await mkdir(outputDir, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-background-networking', '--disable-component-update'] })
try {
  for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport: { width: viewportWidth, height: viewportHeight }, reducedMotion: 'reduce' })
    await context.addInitScript((value) => localStorage.setItem('turbineiq-theme', value), theme)
    const page = await context.newPage()
    await page.goto(`${baseUrl}/#/overview?scenario=compressor_fouling&seed=42&i=48`, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('.engine-button')?.getAttribute('aria-label')?.includes('connected'), null, { timeout: 30000 })
    await page.getByRole('status').filter({ hasText: 'Blender GLB' }).waitFor({ timeout: 30000 })
    await page.waitForFunction(() => [...document.querySelectorAll('.viewer-selection-label')].some((element) => element.classList.contains('viewer-selection-label--left') || element.classList.contains('viewer-selection-label--right')), null, { timeout: 30000 })
    if (screenshotLabel.toLowerCase().includes('after')) {
      await page.waitForFunction(() => document.querySelector('.viewer-selection-label')?.textContent?.trim().length, null, { timeout: 10000 })
    }
    await page.waitForTimeout(350)
    const callout = await page.locator('.viewer-selection-label').evaluate((element) => {
      const label = element.getBoundingClientRect()
      const stage = element.closest('.viewer-html-layer')?.getBoundingClientRect()
      const line = getComputedStyle(element, '::before')
      const style = getComputedStyle(element)
      return {
        text: element.textContent?.trim(),
        side: element.className,
        label: { left: label.left, right: label.right, top: label.top, bottom: label.bottom, width: label.width, height: label.height },
        stage: stage ? { left: stage.left, right: stage.right, top: stage.top, bottom: stage.bottom } : null,
        lineWidth: line.width,
        maxWidth: style.maxWidth,
        font: style.font,
        whiteSpace: style.whiteSpace,
        wordBreak: style.wordBreak,
      }
    })
    const labelBounds = callout.label
    const stageBounds = callout.stage
    if (!stageBounds || labelBounds.left < stageBounds.left || labelBounds.right > stageBounds.right || labelBounds.top < stageBounds.top || labelBounds.bottom > stageBounds.bottom) {
      throw new Error(`The selection label is outside the Stage bounds: ${JSON.stringify(callout)}`)
    }
    console.log(`Callout ${viewportWidth}px ${theme}: ${JSON.stringify(callout)}`)
    await page.locator('.viewer-panel').screenshot({ path: resolve(outputDir, `stage-${screenshotLabel}-${viewportWidth}-${theme}.png`), animations: 'disabled' })
    await context.close()
    console.log(`Captured ${theme} Stage ${screenshotLabel} selection treatment`)
  }
} finally {
  await browser.close()
}
