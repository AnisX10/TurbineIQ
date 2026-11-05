import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const evidenceDir = resolve(root, 'docs/redesign/phase5/states')
const baseUrl = process.env.TURBINEIQ_BASE_URL ?? 'http://127.0.0.1:8011'
const origin = new URL(baseUrl).origin
const records = []

await mkdir(evidenceDir, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-background-networking', '--disable-component-update'] })

async function createPage(width, theme, route, requestMock, expectOffline) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
  await context.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
  const page = await context.newPage()
  const requestOrigins = new Set()
  page.on('request', (request) => {
    try { requestOrigins.add(new URL(request.url()).origin) } catch { return }
  })
  if (requestMock) await requestMock(page)
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' })
  await page.locator('.engine-button').waitFor({ state: 'attached' })
  if (!expectOffline) {
    await page.waitForFunction(() => document.querySelector('.engine-button')?.getAttribute('aria-label')?.includes('connected'), null, { timeout: 30000 })
  } else {
    await page.waitForFunction(() => document.querySelector('.engine-button')?.getAttribute('aria-label')?.includes('offline'), null, { timeout: 30000 })
  }
  if (width <= 768) await page.addStyleTag({ content: '.mobile-bottom-bar { display: none !important; } .main-area { padding-bottom: 0 !important; }' })
  return { context, page, requestOrigins }
}

async function capture(state, width, theme, route, prepare, options = {}) {
  const { context, page, requestOrigins } = await createPage(width, theme, route, options.requestMock, options.expectOffline ?? false)
  try {
    await prepare(page)
    const engineStatus = await page.locator('.engine-button').getAttribute('aria-label')
    const file = `${state}-${width}-${theme}.png`
    const path = resolve(evidenceDir, file)
    await page.screenshot({ path, fullPage: options.fullPage ?? !options.dialog, animations: 'disabled' })
    const unexpectedOrigins = [...requestOrigins].filter((requestOrigin) => requestOrigin !== origin)
    if (unexpectedOrigins.length > 0) throw new Error(`${state} contacted another origin: ${unexpectedOrigins.join(', ')}`)
    records.push({ state, width, theme, engineStatus, file, requestOrigins: [...requestOrigins], mocked: options.mocked ?? false })
    console.log(`${state} ${width}px ${theme}: ${engineStatus} -> ${file}`)
  } finally {
    await context.close()
  }
}

for (const theme of ['light', 'dark']) {
  for (const width of [1440, 375]) {
    await capture('evidence-results-reader-selected', width, theme, '/#/evidence?scenario=compressor_fouling&seed=42&i=48&q=Brayton&top_k=4', async (page) => {
      await page.locator('.evidence-result[aria-selected="true"]').waitFor()
      await page.locator('.evidence-excerpt').waitFor()
    })

    await capture('evidence-no-result', width, theme, '/#/evidence?scenario=compressor_fouling&seed=42&i=48&q=zzzzzzzzqqqqqxyzzz&top_k=4', async (page) => {
      await page.locator('.evidence-no-results').waitFor()
    })

    await capture('component-over-time', width, theme, '/#/components/compressor?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.getByRole('tab', { name: 'Over time' }).click()
      await page.locator('.component-trends svg').first().waitFor()
    })

    await capture('component-evidence', width, theme, '/#/components/compressor?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.getByRole('tab', { name: 'Evidence' }).click()
      await page.locator('.evidence-result, .evidence-no-results').first().waitFor()
    })

    await capture('assistant-answer-tool-trace-expanded', width, theme, '/#/assistant?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain the residual for the selected synthetic sample.')
      await page.getByRole('button', { name: 'Ask', exact: true }).click()
      const trace = page.locator('.assistant-trace').first()
      await trace.waitFor({ timeout: 30000 })
      await trace.locator('summary').click()
      await trace.locator('pre').first().waitFor()
    })

    await capture('cloud-consent-sheet', width, theme, '/#/assistant?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.getByRole('button', { name: 'Cloud' }).click()
      await page.locator('.sheet-consent[open]').waitFor()
    }, { dialog: true })

    await capture('assistant-local-fallback', width, theme, '/#/assistant?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain the current sample.')
      await page.getByRole('button', { name: 'Ask', exact: true }).click()
      await page.locator('.assistant-answer').waitFor()
    }, {
      mocked: true,
      requestMock: async (page) => page.route('**/api/assistant/ask', (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ answer: 'The local assistant response is shown because the configured cloud provider did not return an answer.', mode: 'local_fallback', warning: 'Cloud service unavailable; local response returned.', tool_calls: [], synthetic_only: true }),
      })),
    })

    await capture('engine-offline', width, theme, '/#/overview?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.locator('.engine-banner').waitFor()
      await page.locator('.engine-banner').getByRole('button', { name: 'Copy API start command' }).waitFor()
    }, {
      mocked: true,
      expectOffline: true,
      requestMock: async (page) => page.route('**/api/health', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Offline state capture.' }) })),
    })

    await capture('request-failed-retry', width, theme, '/#/overview?scenario=compressor_fouling&seed=42&i=48', async (page) => {
      await page.locator('.request-banner').waitFor()
      await page.locator('.request-banner').getByRole('button', { name: 'Retry' }).waitFor()
    }, {
      mocked: true,
      requestMock: async (page) => page.route('**/api/twin/run*', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic request failed for the state capture.' }) })),
    })
  }
}

await writeFile(resolve(evidenceDir, 'capture-manifest.json'), JSON.stringify(records, null, 2))
await browser.close()
