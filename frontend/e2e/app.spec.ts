import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const routes = [
  ['Overview', '/#/overview?scenario=compressor_fouling&seed=42&i=48', 'overview'],
  ['Component detail', '/#/components/compressor?scenario=compressor_fouling&seed=42&i=48', 'components'],
  ['Evidence', '/#/evidence?scenario=compressor_fouling&seed=42&i=48', 'evidence'],
  ['Assistant', '/#/assistant?scenario=compressor_fouling&seed=42&i=48', 'assistant'],
] as const
const evidenceDir = resolve(process.cwd(), 'test-results/phase6-7-part1')

async function ready(page: import('@playwright/test').Page, kind: string) {
  if (kind === 'overview') await page.locator('.kpi-row').waitFor()
  else if (kind === 'components') await page.locator('.detail-kpis').waitFor()
  else if (kind === 'evidence') await page.locator('.evidence-search').waitFor()
  else await page.locator('.assistant-mode-segmented').waitFor()
}

async function openWithTheme(context: import('@playwright/test').BrowserContext, route: string, kind: string, theme: 'light' | 'dark') {
  const page = await context.newPage()
  await page.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
  await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await ready(page, kind)
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
  return page
}

test('Overview paints its Stage frame while run data is still loading', async ({ page }) => {
  let releaseRun!: () => void
  let confirmRunRequest!: () => void
  const runGate = new Promise<void>((resolve) => { releaseRun = resolve })
  const runRequested = new Promise<void>((resolve) => { confirmRunRequest = resolve })
  await page.route('**/api/twin/run*', async (route) => {
    confirmRunRequest()
    await runGate
    await route.continue()
  })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await runRequested
  await expect(page.getByRole('heading', { name: 'Stage' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Stage controls' })).toBeVisible()
  await expect(page.locator('.stage-viewport')).toHaveCSS('aspect-ratio', '4 / 3')
  await expect(page.getByRole('heading', { name: 'Component ledger' })).toBeVisible()
  await expect(page.locator('.component-ledger-skeleton')).toBeVisible()
  releaseRun()
  await expect(page.locator('.kpi-row')).toBeVisible()
})

async function tabUntil(page: import('@playwright/test').Page, target: import('@playwright/test').Locator, limit = 80) {
  for (let index = 0; index < limit; index += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return
    await page.keyboard.press('Tab')
  }
  throw new Error('Keyboard traversal did not reach the requested control.')
}

async function axe(page: import('@playwright/test').Page, route: string, theme: string, state: string, records: Array<Record<string, unknown>>) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const severe = result.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
  const findings = severe.flatMap((violation) => violation.nodes.map((node) => ({ id: violation.id, help: violation.help, target: node.target, html: node.html, failureSummary: node.failureSummary })))
  records.push({ route, theme, state, findings })
  console.log(`AXE ${theme} ${route} ${state}: ${findings.length} serious/critical`)
  expect(findings, `${theme} ${route} ${state} axe findings`).toEqual([])
}

test('axe audits all four routes, component tabs, and Cloud consent in both themes', async ({ context }) => {
  const records: Array<Record<string, unknown>> = []
  await context.route('**/models/turbine.glb', (route) => route.abort())
  for (const theme of ['light', 'dark'] as const) {
    for (const [name, route, kind] of routes) {
      const page = await openWithTheme(context, route, kind, theme)
      if (kind === 'overview') await expect(page.locator('.kpi-row')).toBeVisible()
      await axe(page, name, theme, 'default', records)
      if (kind === 'components') {
        for (const tab of ['Over time', 'Evidence']) {
          await page.getByRole('tab', { name: tab }).click()
          await axe(page, name, theme, tab, records)
        }
      }
      if (kind === 'overview') {
        await page.locator('.boundary-chip').click()
        await page.getByRole('dialog', { name: 'Boundary' }).waitFor()
        await axe(page, name, theme, 'Boundary sheet', records)
      }
      if (kind === 'assistant') {
        await page.getByRole('button', { name: 'Cloud' }).click()
        await page.getByRole('dialog', { name: 'Review Cloud sharing' }).waitFor()
        await axe(page, name, theme, 'Cloud consent', records)
      }
      await page.close()
    }
  }
  await mkdir(evidenceDir, { recursive: true })
  await writeFile(resolve(evidenceDir, 'axe-results.json'), JSON.stringify(records, null, 2))
})

test('Evidence restores URL searches and explains an honest no-evidence result', async ({ page }) => {
  await page.goto('/#/evidence?scenario=compressor_fouling&seed=42&i=48&q=Brayton&top_k=4')
  await ready(page, 'evidence')
  await expect(page.locator('.evidence-result').first()).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Search local documents' })).toHaveValue('Brayton')
  await expect(page.getByRole('spinbutton', { name: 'Maximum evidence results' })).toHaveValue('4')

  const missingQuery = 'zzzzzzzzqqqqqxyzzz'
  await page.goto(`/#/evidence?scenario=compressor_fouling&seed=42&i=48&q=${missingQuery}&top_k=4`)
  await expect(page.locator('.evidence-no-results p')).toHaveText(`No supporting passage found for ${missingQuery}.`)
  await expect(page.locator('.evidence-no-results small')).toContainText('Searched local technical documents using local lexical retrieval.')
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Reader' })).toBeVisible()
})

test('keyboard traversal covers tabs, evidence selection, consent, composer, and replay', async ({ page }) => {
  await page.goto('/#/components/compressor?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'components')
  const metricsTab = page.getByRole('tab', { name: 'Metrics' })
  await tabUntil(page, metricsTab)
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Over time' })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Over time' })).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Evidence' })).toBeFocused()

  await page.goto('/#/evidence?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'evidence')
  await page.getByRole('textbox', { name: 'Search local documents' }).fill('Brayton cycle')
  await page.getByRole('spinbutton', { name: 'Maximum evidence results' }).fill('5')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect.poll(() => page.locator('.evidence-result').count(), { timeout: 15000 }).toBeGreaterThan(1)
  expect(await page.locator('.evidence-result').count()).toBeLessThanOrEqual(5)
  await expect(page).toHaveURL(/q=Brayton\+cycle.*top_k=5/)
  const firstResult = page.locator('.evidence-result').first()
  await tabUntil(page, firstResult)
  await page.keyboard.press('ArrowDown')
  await expect(page.locator('.evidence-result').nth(1)).toBeFocused()
  await expect(page.locator('.evidence-result').nth(1)).toHaveAttribute('aria-selected', 'true')

  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  const cloud = page.getByRole('button', { name: 'Cloud' })
  await tabUntil(page, cloud)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Review Cloud sharing' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('assistant instructions and allowed-tool descriptions')
  await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  await expect(dialog.getByRole('button', { name: 'Continue to Cloud' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('checkbox')).toBeFocused()
  await page.keyboard.press('Space')
  await expect(dialog.getByRole('checkbox')).toBeChecked()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(cloud).toBeFocused()

  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  const composer = page.getByRole('textbox', { name: 'Ask TurbineIQ' })
  await tabUntil(page, composer)
  await page.keyboard.type('Explain the selected sample')
  await page.keyboard.press('Shift+Enter')
  await page.keyboard.type(' residual.')
  await expect(composer).toHaveValue('Explain the selected sample\n residual.')
  await page.keyboard.press('Enter')
  await expect(page.locator('.assistant-answer')).toBeVisible({ timeout: 20000 })

  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await ready(page, 'overview')
  const timeline = page.locator('.timeline-card')
  await tabUntil(page, timeline)
  const sample = page.getByRole('slider', { name: 'Scenario sample' })
  await page.keyboard.press('ArrowLeft')
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 72 of 96/)
  await page.keyboard.press('Shift+ArrowRight')
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 82 of 96/)
  await page.keyboard.press('Home')
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 1 of 96/)
  await page.keyboard.press('End')
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 96 of 96/)
  await expect(page.getByRole('button', { name: 'First flagged sample' })).toBeDisabled()
  await page.keyboard.press('f')
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Pause replay' })).toBeVisible()
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Play replay' })).toBeVisible()

  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  const boundaryChip = page.locator('.boundary-chip')
  await boundaryChip.click()
  const boundaryDialog = page.getByRole('dialog', { name: 'Boundary' })
  const boundaryClose = boundaryDialog.getByRole('button', { name: 'Close boundary' })
  await expect(boundaryClose).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(boundaryClose).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(boundaryDialog).not.toBeVisible()
  await expect(boundaryChip).toBeFocused()
})

test('overview scenario, seed, replay, mesh inspection, Evidence search, and Local Assistant still work', async ({ page }) => {
  const origins = new Set<string>()
  page.on('request', (request) => { try { origins.add(new URL(request.url()).origin) } catch { return } })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await ready(page, 'overview')
  await expect(page.getByText('26.30', { exact: false }).first()).toBeVisible()
  const efficiency = page.locator('.component-row').filter({ hasText: 'Compressor' }).locator('.component-primary')
  await expect(efficiency).toHaveAttribute('title', /81\.2 %/)
  await expect(efficiency.locator('.unit')).toHaveText('%')
  await expect(page.locator('.station-row').first()).toContainText('284.2')
  await expect(page.locator('.station-row').first()).toContainText('101.3 kPa')
  await expect(page.getByText('Reference model', { exact: true }).first()).toBeVisible()
  const statusLabels = await page.locator('.neutral-status').allTextContents()
  expect(statusLabels).toEqual(expect.arrayContaining(['Drift', 'Modelled', 'Comparison']))
  expect(statusLabels.every((label) => !label.includes('…'))).toBe(true)

  const seed = page.getByRole('textbox', { name: 'Seed' })
  await seed.fill('43')
  await seed.press('Enter')
  await expect(page).toHaveURL(/seed=43/)
  await seed.fill('-1')
  await seed.press('Enter')
  await expect(seed).toHaveAttribute('aria-invalid', 'true')
  await expect(page).toHaveURL(/seed=43/)
  await expect(page.getByRole('button', { name: /Synthetic.*seed 43/ })).toBeVisible()

  const scenario = page.getByRole('combobox', { name: 'Scenario' })
  const options = await scenario.locator('option').count()
  if (options > 1) await scenario.selectOption({ index: 1 })
  const slider = page.getByRole('slider', { name: 'Scenario sample' })
  await page.getByRole('button', { name: 'Play replay' }).click()
  await expect.poll(async () => Number((await slider.getAttribute('aria-valuetext'))?.match(/Sample (\d+)/)?.[1] ?? 0), { timeout: 5000 }).toBeGreaterThan(73)
  await page.getByRole('button', { name: 'Pause replay' }).click()

  const mesh = page.getByLabel(/Model sub-parts/)
  await expect(mesh).toBeEnabled({ timeout: 20000 })
  expect(await mesh.locator('option').count()).toBeGreaterThan(1)
  await mesh.selectOption({ index: 1 })
  await expect(page).toHaveURL(/component=/)
  await expect(page.locator('.component-row[aria-pressed="true"]')).toBeVisible()
  await expect(page.locator('.part-inspection')).toContainText('Selected model part')

  await page.getByRole('link', { name: 'Evidence' }).click()
  await page.getByRole('textbox', { name: 'Search local documents' }).fill('Brayton cycle')
  await page.getByRole('spinbutton', { name: 'Maximum evidence results' }).fill('4')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect.poll(() => page.locator('.evidence-result').count(), { timeout: 15000 }).toBeGreaterThan(0)
  expect(await page.locator('.evidence-result').count()).toBeLessThanOrEqual(4)
  await expect(page).toHaveURL(/q=Brayton\+cycle.*top_k=4/)

  await page.getByRole('link', { name: 'Assistant' }).click()
  await expect(page.getByRole('button', { name: /Local.*demo-safe/ })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain the current synthetic sample.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.locator('.assistant-answer')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.assistant-answer')).toContainText('Local')
  expect([...origins].filter((origin) => origin !== new URL('http://127.0.0.1:8011').origin)).toEqual([])
  await mkdir(evidenceDir, { recursive: true })
  await writeFile(resolve(evidenceDir, 'network-origins.json'), JSON.stringify([...origins], null, 2))
})

test('Cloud consent always precedes a mocked provider request and document excerpts are opt-in', async ({ page }) => {
  const bodies: Array<Record<string, unknown>> = []
  await page.route('**/api/assistant/ask', async (route) => {
    bodies.push(route.request().postDataJSON() as Record<string, unknown>)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ answer: 'Mocked cloud response.', mode: 'cloud', warning: null, tool_calls: [], synthetic_only: true }) })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  await page.getByRole('button', { name: 'Cloud' }).click()
  const dialog = page.getByRole('dialog', { name: 'Review Cloud sharing' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  await dialog.getByRole('button', { name: 'Continue to Cloud' }).click()
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Summarize this sample.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Mocked cloud response.')).toBeVisible()
  expect(bodies[0]).toMatchObject({ enable_cloud: true, allow_cloud_document_context: false })

  await page.getByRole('button', { name: /Local.*demo-safe/ }).click()
  await page.getByRole('button', { name: 'Cloud' }).click()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Continue to Cloud' }).click()
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Find an excerpt for this question.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Mocked cloud response.').last()).toBeVisible()
  expect(bodies[1]).toMatchObject({ enable_cloud: true, allow_cloud_document_context: true })
})

test('Assistant request failures expose a retry action', async ({ page }) => {
  let attempts = 0
  await page.route('**/api/assistant/ask', async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Local assistant is temporarily unavailable.' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ answer: 'Recovered local response.', mode: 'local', warning: null, tool_calls: [], synthetic_only: true }) })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain this synthetic sample.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByRole('button', { name: 'Retry question' }).click()
  await expect(page.getByText('Recovered local response.')).toBeVisible()
  expect(attempts).toBe(2)
})

test('Assistant shows its scenario name and busy rule only during a local request', async ({ page }) => {
  let releaseRequest!: () => void
  const requestGate = new Promise<void>((resolve) => { releaseRequest = resolve })
  await page.route('**/api/assistant/ask', async (route) => {
    await requestGate
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ answer: 'Local test response.', mode: 'local', warning: null, tool_calls: [], synthetic_only: true }) })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  await expect(page.getByRole('button', { name: /Local engine.*connected/ })).toBeVisible()
  await expect(page.locator('.assistant-context')).toContainText('Compressor-performance drift')
  await expect(page.locator('.assistant-progress')).toHaveCount(0)
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain this sample.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.locator('.assistant-progress')).toBeVisible()
  await expect(page.locator('.assistant-composer')).toHaveClass(/is-waiting/)
  releaseRequest()
  await expect(page.getByText('Local test response.')).toBeVisible()
  await expect(page.locator('.assistant-progress')).toHaveCount(0)
  await expect(page.locator('.assistant-composer')).not.toHaveClass(/is-waiting/)
})

test('Offline engine guidance uses a portable command with shell activation and copy action', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'offline for test' }) }))
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.locator('.kpi-row')).toBeVisible()
  await expect(page.locator('.engine-banner')).toContainText('python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000')
  await expect(page.locator('.engine-banner')).toContainText('.\\.venv\\Scripts\\Activate.ps1')
  await expect(page.locator('.engine-banner')).toContainText('source .venv/bin/activate')
  const copyButton = page.getByRole('button', { name: 'Copy API start command' })
  await expect(copyButton).toBeVisible()
  await copyButton.click()
  await expect(copyButton).toContainText('Copied')
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000')
})

test('Component ledger formats sample time and percentage values without duplicated reference provenance', async ({ page }) => {
  await page.goto('/#/components/compressor?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'components')
  await expect(page.locator('.detail-panel-heading')).toContainText(/Sample 49 · \d{2}:\d{2} UTC/)
  const efficiencyRow = page.locator('.metric-ledger tbody tr').filter({ hasText: /efficiency/i }).first()
  await expect(efficiencyRow.locator('td:nth-child(2)')).toHaveText(/\d+\.\d%/)
  await expect(efficiencyRow.locator('td:nth-child(3)')).toHaveText(/\d+\.\d%/)
  await expect(efficiencyRow.locator('td:nth-child(5)')).not.toContainText('Reference')
})

test('viewport screenshots cover every route, width, and theme without horizontal page scroll', async ({ context }) => {
  const widths = [375, 768, 1024, 1440]
  for (const theme of ['light', 'dark'] as const) {
    for (const width of widths) {
      for (const [name, route, kind] of routes) {
        const page = await context.newPage()
        await page.setViewportSize({ width, height: width <= 768 ? 900 : 1000 })
        await page.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
        await page.goto(route)
        await ready(page, kind)
        if (kind === 'overview') await expect(page.getByLabel(/Model sub-parts/)).toBeEnabled({ timeout: 20000 })
        const layout = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
        expect(layout.scrollWidth, `${name} ${width}px ${theme} page scroll`).toBeLessThanOrEqual(layout.clientWidth + 1)
        const slug = name.toLowerCase().replaceAll(' ', '-')
        const path = resolve(evidenceDir, `${slug}-${width}-${theme}.png`)
        await mkdir(evidenceDir, { recursive: true })
        await page.screenshot({ path, fullPage: false, animations: 'disabled' })
        if (name === 'Overview' && width === 1440 && theme === 'dark') {
          await expect(page.getByText(/Loaded locally in this browser/)).toBeVisible({ timeout: 20000 })
          await page.locator('.stage-viewport').screenshot({ path: resolve(evidenceDir, 'stage-dark-after.png'), animations: 'disabled' })
        }
        await page.close()
      }
    }
  }
})

test('320px layouts have no horizontal page scroll and reduced motion disables rotor motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 320, height: 800 })
  for (const [, route, kind] of routes) {
    await page.goto(route)
    await ready(page, kind)
    const layout = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
    expect(layout.scrollWidth, `${kind} 320px page scroll`).toBeLessThanOrEqual(layout.clientWidth + 1)
  }
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  await expect(page.getByRole('button', { name: 'Rotor motion' })).toHaveAttribute('aria-disabled', 'true')
  for (const locator of [page.locator('.stage-icon-button').first(), page.locator('.replay-button'), page.locator('.timeline-chart-controls .text-control').first()]) {
    const box = await locator.boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }
})
