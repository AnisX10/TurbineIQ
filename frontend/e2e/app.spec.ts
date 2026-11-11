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

function assistantStream(answer: string, mode = 'local', toolCalls: AssistantToolCall[] = []) {
  const response = { answer, mode, warning: null, tool_calls: toolCalls, synthetic_only: true }
  const event = (name: string, payload: unknown) => `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`
  return [
    event('status', { state: 'working', message: 'Preparing test context.' }),
    ...toolCalls.flatMap((call) => [
      event('tool_start', { name: call.name, arguments: call.arguments }),
      event('tool_result', call),
    ]),
    ...answer.match(/\S+\s*/g)!.map((text) => event('token', { text })),
    event('done', response),
  ].join('')
}

interface AssistantToolCall { name: string; arguments: Record<string, unknown>; result: Record<string, unknown> }

async function ready(page: import('@playwright/test').Page, kind: string) {
  if (kind === 'overview') await page.locator('.kpi-row').waitFor()
  else if (kind === 'components') await page.locator('.detail-kpis').waitFor()
  else if (kind === 'evidence') await page.locator('.evidence-search').waitFor()
  else await page.locator('.assistant-mode-segmented').first().waitFor()
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

test('Overview assistant code loads only when the dock or consent sheet opens', async ({ page }) => {
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await expect(page.locator('.kpi-row')).toBeVisible()
  const assistantChunks = () => page.evaluate(() => performance.getEntriesByType('resource').map((entry) => entry.name.split('/').pop() ?? '').filter((name) => /Assistant(Dock|Workspace|ConsentHost)/.test(name)))
  expect(await assistantChunks()).toEqual([])

  await page.locator('.assistant-header-ask').click()
  const dock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await expect(dock).toBeVisible()
  await expect.poll(async () => (await assistantChunks()).some((name) => name.startsWith('AssistantDock-'))).toBe(true)
  await expect.poll(async () => (await assistantChunks()).some((name) => name.startsWith('AssistantWorkspace-'))).toBe(true)
  await dock.getByRole('button', { name: 'Cloud' }).click()
  await expect(page.getByRole('dialog', { name: 'Review Cloud sharing' })).toBeVisible()
  await expect.poll(async () => (await assistantChunks()).some((name) => name.startsWith('AssistantConsentHost-'))).toBe(true)
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
        await page.locator('.assistant-header-ask').click()
        await page.getByRole('dialog', { name: 'Ask TurbineIQ' }).waitFor()
        await axe(page, name, theme, 'Assistant dock', records)
        await page.keyboard.press('Escape')
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
  await expect(page.locator('.assistant-page:not(.assistant-dock-page) .assistant-answer')).toBeVisible({ timeout: 20000 })

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
  await page.keyboard.press('Home')
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 1 of 96/)
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
  await page.locator('.assistant-page:not(.assistant-dock-page) .assistant-ask-button').click()
  const fullAssistant = page.locator('.assistant-page:not(.assistant-dock-page)')
  await expect(fullAssistant.locator('.assistant-answer')).toBeVisible({ timeout: 20000 })
  await expect(fullAssistant.locator('.assistant-answer')).toContainText('Local')
  expect([...origins].filter((origin) => origin !== new URL('http://127.0.0.1:8021').origin)).toEqual([])
  await mkdir(evidenceDir, { recursive: true })
  await writeFile(resolve(evidenceDir, 'network-origins.json'), JSON.stringify([...origins], null, 2))
})

test('Cloud consent always precedes a mocked provider request and document excerpts are opt-in', async ({ page }) => {
  const bodies: Array<Record<string, unknown>> = []
  await page.route('**/api/assistant/stream', async (route) => {
    bodies.push(route.request().postDataJSON() as Record<string, unknown>)
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: assistantStream('Mocked cloud response.', 'cloud') })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  await page.getByRole('button', { name: 'Cloud' }).click()
  const dialog = page.getByRole('dialog', { name: 'Review Cloud sharing' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  await dialog.getByRole('button', { name: 'Continue to Cloud' }).click()
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Summarize this sample.')
  await page.locator('.assistant-page:not(.assistant-dock-page) .assistant-ask-button').click()
  await expect(page.locator('.assistant-page:not(.assistant-dock-page)').getByText('Mocked cloud response.')).toBeVisible()
  expect(bodies[0]).toMatchObject({ enable_cloud: true, allow_cloud_document_context: false })

  await page.evaluate(() => sessionStorage.removeItem('turbineiq-cloud-consent'))
  await page.reload()
  await ready(page, 'assistant')
  await page.getByRole('button', { name: 'Cloud' }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Continue to Cloud' }).click()
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Find an excerpt for this question.')
  await page.locator('.assistant-page:not(.assistant-dock-page) .assistant-ask-button').click()
  await expect(page.locator('.assistant-page:not(.assistant-dock-page)').getByText('Mocked cloud response.')).toBeVisible()
  expect(bodies[1]).toMatchObject({ enable_cloud: true, allow_cloud_document_context: true })
})

test('Assistant request failures expose a retry action', async ({ page }) => {
  let attempts = 0
  await page.route('**/api/assistant/stream', async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Local assistant is temporarily unavailable.' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: assistantStream('Recovered local response.') })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain this synthetic sample.')
  const fullAssistant = page.locator('.assistant-page:not(.assistant-dock-page)')
  await fullAssistant.locator('.assistant-ask-button').click()
  await fullAssistant.getByRole('button', { name: 'Retry question' }).click()
  await expect(fullAssistant.getByText('Recovered local response.')).toBeVisible()
  expect(attempts).toBe(2)
})

test('Assistant shows its scenario name and busy rule only during a local request', async ({ page }) => {
  let releaseRequest!: () => void
  const requestGate = new Promise<void>((resolve) => { releaseRequest = resolve })
  await page.route('**/api/assistant/stream', async (route) => {
    await requestGate
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: assistantStream('Local test response.') })
  })
  await page.goto('/#/assistant?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'assistant')
  const fullAssistant = page.locator('.assistant-page:not(.assistant-dock-page)')
  await expect(page.getByRole('button', { name: /Local engine.*connected/ })).toBeVisible()
  await expect(fullAssistant.locator('.assistant-context')).toContainText('Compressor-performance drift')
  await expect(fullAssistant.locator('.assistant-progress')).toHaveCount(0)
  await page.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Explain this sample.')
  await fullAssistant.locator('.assistant-ask-button').click()
  await expect(fullAssistant.locator('.assistant-progress')).toBeVisible()
  await expect(fullAssistant.locator('.assistant-composer')).toHaveClass(/is-waiting/)
  releaseRequest()
  await expect(fullAssistant.getByText('Local test response.')).toBeVisible()
  await expect(fullAssistant.locator('.assistant-progress')).toHaveCount(0)
  await expect(fullAssistant.locator('.assistant-composer')).not.toHaveClass(/is-waiting/)
})

test('Overview A shortcut opens the shared dock and Esc returns focus to Ask', async ({ page }) => {
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await expect(page.locator('.kpi-row')).toBeVisible()
  const dashboardWidth = (await page.locator('.main-area').boundingBox())?.width
  await page.keyboard.press('a')
  const dialog = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await expect(dialog).toBeVisible()
  const composer = dialog.getByRole('textbox', { name: 'Ask TurbineIQ' })
  await expect(composer).toBeFocused()
  expect((await page.locator('.main-area').boundingBox())?.width).toBe(dashboardWidth)
  await composer.fill('Explain the selected synthetic sample.')
  await dialog.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(dialog.locator('.assistant-answer')).toContainText('26.30 MW', { timeout: 20000 })
  await expect(dialog.locator('.assistant-trace')).toBeVisible()
  await expect(dialog.locator('.assistant-trace')).not.toHaveAttribute('open', '')
  await dialog.getByText(/^Tool trace/).click()
  await expect(dialog.locator('.assistant-trace')).toHaveAttribute('open', '')
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.assistant-header-ask')).toBeFocused()
  await page.keyboard.press('a')
  await expect(page.getByRole('dialog', { name: 'Ask TurbineIQ' })).toContainText('26.30 MW')
  await page.keyboard.press('Escape')
  await page.getByRole('link', { name: 'Assistant' }).click()
  await expect(page.locator('.assistant-page:not(.assistant-dock-page) .assistant-answer')).toContainText('26.30 MW')
})

test('cloud dock names the fake provider, streams tool results, links citations and labels local fallback', async ({ page }) => {
  const browserOrigins = new Set<string>()
  page.on('request', (request) => { browserOrigins.add(new URL(request.url()).origin) })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await expect(page.locator('.kpi-row')).toBeVisible()
  await page.locator('.assistant-header-ask').click()
  const dock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await dock.getByRole('button', { name: 'Cloud' }).click()
  const consent = page.getByRole('dialog', { name: 'Review Cloud sharing' })
  await expect(consent).toContainText('custom · 127.0.0.1 · fake-gpt-oss-20b')
  await expect(consent.getByRole('checkbox')).not.toBeChecked()
  await consent.getByRole('checkbox').check()
  await consent.getByRole('button', { name: 'Continue to Cloud' }).click()
  await dock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('Find a citation for Brayton cycle assumptions.')
  await dock.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(dock.locator('.assistant-answer')).toContainText('supporting passage', { timeout: 30000 })
  await expect(dock.locator('.assistant-trace')).toContainText('search_technical_documents')
  await expect(dock.locator('.assistant-citations .citation-chip').first()).toBeVisible()
  await dock.locator('.assistant-citations .citation-chip').first().click()
  await expect(page).toHaveURL(/#\/evidence\?/)
  await expect(page.locator('.evidence-reader .citation-chip')).toBeVisible({ timeout: 20000 })
  expect([...browserOrigins].filter((origin) => origin !== new URL('http://127.0.0.1:8021').origin)).toEqual([])

  await page.getByRole('link', { name: 'Overview' }).click()
  await expect(page.locator('.kpi-row')).toBeVisible()
  await page.locator('.assistant-header-ask').click()
  const reopened = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await reopened.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('force fallback for this test')
  await reopened.getByRole('button', { name: 'Ask', exact: true }).click()
  const fallbackTurn = reopened.locator('.assistant-turn').last()
  await expect(fallbackTurn.locator('.assistant-answer-meta')).toContainText('Local fallback', { timeout: 45000 })
})

test('assistant dock can stop a slow cloud response and retry a failed stream', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('turbineiq-cloud-consent', 'accepted'))
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await expect(page.locator('.kpi-row')).toBeVisible()
  await page.locator('.assistant-header-ask').click()
  const dock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await dock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('slow response for stop testing')
  await dock.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(dock.getByRole('button', { name: 'Stop response' })).toBeVisible()
  await dock.getByRole('button', { name: 'Stop response' }).click()
  await expect(dock.getByText('Stopped before the answer was complete.')).toBeVisible()

  let attempts = 0
  await page.route('**/api/assistant/stream', async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Temporary fake error.' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: assistantStream('Recovered with the retry.') })
  })
  await dock.getByRole('textbox', { name: 'Ask TurbineIQ' }).fill('retry this request')
  await dock.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(dock.getByText('Temporary fake error.')).toBeVisible()
  await dock.getByRole('button', { name: 'Retry question' }).last().click()
  await expect(dock.getByText('Recovered with the retry.')).toBeVisible()
  expect(attempts).toBe(2)
})

test('assistant dock becomes a bottom sheet at 375px', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await expect(page.locator('.kpi-row')).toBeVisible()
  await page.locator('.assistant-header-ask').click()
  const dock = page.getByRole('dialog', { name: 'Ask TurbineIQ' })
  await expect(dock).toBeVisible()
  const box = await dock.boundingBox()
  expect(box?.width).toBe(375)
  expect(box?.y).toBeGreaterThan(0)
  if (!box) throw new Error('Assistant dock has no layout box at mobile width.')
  expect(box.y + box.height).toBeGreaterThanOrEqual(810)
})

test('Offline engine guidance uses a portable command with shell activation and copy action', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'offline for test' }) }))
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.locator('.kpi-row')).toBeVisible()
  const main = page.locator('main')
  await expect(main.locator('.engine-banner')).toContainText('python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000')
  await expect(main.locator('.engine-banner')).toContainText('.\\.venv\\Scripts\\Activate.ps1')
  await expect(main.locator('.engine-banner')).toContainText('source .venv/bin/activate')
  const copyButton = main.getByRole('button', { name: 'Copy API start command' })
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

test('layouts keep all routes, tabs, and sheets inside 320px and 200%-equivalent viewports', async ({ browser }) => {
  const states = [
    ['Overview', routes[0][1], 'overview'],
    ['Component Metrics', routes[1][1], 'components'],
    ['Evidence', routes[2][1], 'evidence'],
    ['Assistant', routes[3][1], 'assistant'],
  ] as const
  const layouts: Array<Record<string, unknown>> = []
  for (const theme of ['light', 'dark'] as const) {
    for (const layout of [{ width: 320, dpr: 1, name: '320px' }, { width: 720, dpr: 2, name: '200%-equivalent' }]) {
      const context = await browser.newContext({ viewport: { width: layout.width, height: 900 }, deviceScaleFactor: layout.dpr })
      await context.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
      await context.route('**/models/turbine.glb', (request) => request.abort())
      const page = await context.newPage()
      const checkLayout = async (name: string) => {
        const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
        layouts.push({ theme, viewport: layout.name, state: name, ...dimensions })
        expect(dimensions.scrollWidth, `${theme} ${layout.name} ${name}`).toBeLessThanOrEqual(dimensions.clientWidth + 1)
      }
      for (const [name, route, kind] of states) {
        await page.goto(route)
        await ready(page, kind)
        if (kind === 'components') {
          for (const tab of ['Metrics', 'Over time', 'Evidence']) {
            if (tab !== 'Metrics') await page.getByRole('tab', { name: tab }).click()
            await checkLayout(`${name} ${tab}`)
          }
        } else {
          await checkLayout(name)
          if (kind === 'overview') {
            await page.locator('.boundary-chip').click()
            await page.getByRole('dialog', { name: 'Boundary' }).waitFor()
            await checkLayout('Boundary sheet')
            await page.keyboard.press('Escape')
            await expect(page.getByRole('dialog', { name: 'Boundary' })).not.toBeVisible()
          }
          if (kind === 'assistant') {
            await page.getByRole('button', { name: 'Cloud' }).click()
            await page.getByRole('dialog', { name: 'Review Cloud sharing' }).waitFor()
            await checkLayout('Cloud consent sheet')
            await page.keyboard.press('Escape')
            await expect(page.getByRole('dialog', { name: 'Review Cloud sharing' })).not.toBeVisible()
          }
        }
      }
      await context.close()
    }
  }
  await mkdir(evidenceDir, { recursive: true })
  await writeFile(resolve(evidenceDir, 'responsive-zoom.json'), JSON.stringify(layouts, null, 2))
})

test('mobile targets are at least 44px in both themes', async ({ browser }) => {
  const smallTargets: Array<Record<string, unknown>> = []
  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ viewport: { width: 375, height: 900 } })
    await context.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
    await context.route('**/models/turbine.glb', (request) => request.abort())
    const page = await context.newPage()
    for (const [name, route, kind] of routes) {
      await page.goto(route)
      await ready(page, kind)
      if (kind === 'components') {
        for (const tab of ['Metrics', 'Over time', 'Evidence']) {
          if (tab !== 'Metrics') await page.getByRole('tab', { name: tab }).click()
          await collectSmallTargets(page, name, tab, theme, smallTargets)
        }
      } else {
        await collectSmallTargets(page, name, 'default', theme, smallTargets)
        if (kind === 'overview') {
          await page.locator('.boundary-chip').click()
          await collectSmallTargets(page, name, 'Boundary sheet', theme, smallTargets, true)
          await page.keyboard.press('Escape')
        }
        if (kind === 'assistant') {
          await page.getByRole('button', { name: 'Cloud' }).click()
          await collectSmallTargets(page, name, 'Cloud consent', theme, smallTargets, true)
          await page.keyboard.press('Escape')
        }
      }
    }
    await context.close()
  }
  console.log(`TOUCH TARGETS UNDER 44px: ${JSON.stringify(smallTargets)}`)
  expect(smallTargets).toEqual([])
})

test('mobile navigation accessible names match the visible destination labels', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  const navigation = page.getByRole('navigation', { name: 'Primary navigation' })
  const parts = navigation.getByRole('link', { name: 'Parts', exact: true })
  await expect(parts).toBeVisible()
  await parts.click()
  await expect(parts).toHaveAttribute('aria-current', 'page')
})

async function collectSmallTargets(page: import('@playwright/test').Page, route: string, state: string, theme: string, output: Array<Record<string, unknown>>, dialogOnly = false) {
  const under = await page.evaluate((onlyDialog) => {
    const scope: ParentNode = onlyDialog ? document.querySelector('dialog[open]') ?? document : document
    return [...scope.querySelectorAll('a[href],button,input,select,textarea,summary,[role="tab"],[role="slider"]')]
      .filter((element) => {
        const style = getComputedStyle(element)
        const box = element.getBoundingClientRect()
        return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0
      })
      .map((element) => {
        const box = element.getBoundingClientRect()
        return {
          tag: element.tagName,
          name: (element.getAttribute('aria-label') || element.textContent || element.getAttribute('placeholder') || '').trim().replaceAll(/\s+/g, ' ').slice(0, 64),
          width: Math.round(box.width),
          height: Math.round(box.height),
        }
      })
      .filter((element) => element.width < 44 || element.height < 44)
  }, dialogOnly)
  output.push(...under.map((element) => ({ route, state, theme, ...element })))
}

test('theme preference changes live and System follows OS changes before app paint', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.addInitScript(() => localStorage.setItem('turbineiq-theme', 'system'))
  let earlyTheme: string | null = null
  page.on('domcontentloaded', async () => {
    earlyTheme = await page.locator('html').getAttribute('data-theme')
  })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.+/)
  await expect.poll(() => page.locator('html').evaluate((root) => getComputedStyle(root).getPropertyValue('--ground').trim())).toBe('#f2f4f7')
  await expect(page.getByText(/Loaded locally in this browser/)).toBeVisible({ timeout: 30000 })
  const lightStage = await page.locator('.stage-viewport').screenshot({ animations: 'disabled' })

  await page.emulateMedia({ colorScheme: 'dark' })
  await expect.poll(() => page.locator('html').evaluate((root) => getComputedStyle(root).getPropertyValue('--ground').trim())).toBe('#0e0f11')
  await expect.poll(async () => (await page.locator('.stage-viewport').screenshot({ animations: 'disabled' })).equals(lightStage)).toBe(false)

  await page.getByRole('button', { name: 'Theme: system' }).click()
  await page.getByRole('menuitemradio', { name: 'Light' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Theme: light' }).click()
  await page.getByRole('menuitemradio', { name: 'Dark' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('button', { name: 'Theme: dark' }).click()
  await page.getByRole('menuitemradio', { name: 'System' }).click()
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.+/)
  expect(earlyTheme).toBeNull()
})

test('saved light and dark themes are applied by the head script before first paint', async ({ browser }) => {
  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ viewport: { width: 1024, height: 900 } })
    await context.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
    const page = await context.newPage()
    await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48', { waitUntil: 'domcontentloaded' })
    const earlyTheme = await page.locator('html').getAttribute('data-theme')
    expect(earlyTheme, `${theme} theme head-script mutation`).toBe(theme)
    const ground = await page.locator('html').evaluate((root) => getComputedStyle(root).getPropertyValue('--ground').trim())
    expect(ground, `${theme} theme ground token`).toBe(theme === 'dark' ? '#0e0f11' : '#f2f4f7')
    await context.close()
  }
})

test('forced colors preserve visible focus, control borders, and segmented selections', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' })
  for (const [name, route, kind] of routes) {
    await page.goto(route)
    await ready(page, kind)
    const focusTarget = kind === 'components' ? page.getByRole('tab', { name: 'Metrics' }) : page.locator('.boundary-chip')
    await focusTarget.focus()
    const outline = await focusTarget.evaluate((element) => getComputedStyle(element).outlineStyle)
    expect(outline, `${name} focus ring`).not.toBe('none')
    if (kind === 'overview') {
      const borders = await page.locator('.stage-segmented').evaluate((element) => ({ style: getComputedStyle(element).borderTopStyle, color: getComputedStyle(element).borderTopColor }))
      expect(borders.style).not.toBe('none')
      expect(borders.color).not.toBe('rgba(0, 0, 0, 0)')
    }
    if (kind === 'assistant') {
      const selection = await page.getByRole('button', { name: 'Local demo-safe' }).getAttribute('aria-pressed')
      expect(selection).toBe('true')
    }
  }
})

test('a failed GLB request leaves the visible interactive schematic fallback', async ({ page }) => {
  await page.route('**/models/turbine.glb', (request) => request.fulfill({ status: 404, body: 'missing' }))
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  await expect(page.getByText('The 3D model is unavailable; showing the interactive schematic.')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('.viewer-stage canvas')).toBeVisible()
  await expect(page.locator('.model-state')).toHaveText('Schematic fallback')
})

test('unavailable WebGL keeps the static schematic visible and explains the fallback', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function getContext(type: string, ...args: unknown[]) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null
      return original.call(this, type, ...args as [never])
    }
  })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await ready(page, 'overview')
  await expect(page.getByRole('img', { name: 'Simplified gas turbine schematic. WebGL is unavailable; showing the static schematic.' })).toBeVisible()
  await expect(page.locator('.model-state')).toHaveText('Static schematic')
  await expect(page.locator('.viewer-note')).toHaveText('WebGL is unavailable; showing the static schematic.')
})
