import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const routes = [
  ['Overview', '/#/overview?scenario=compressor_fouling&seed=42&i=72'],
  ['Components', '/#/components/compressor?scenario=compressor_fouling&seed=42&i=72'],
  ['Evidence', '/#/evidence?scenario=compressor_fouling&seed=42&i=72'],
  ['Assistant', '/#/assistant?scenario=compressor_fouling&seed=42&i=72'],
] as const

async function openWithTheme(context: import('@playwright/test').BrowserContext, route: string, theme: 'light' | 'dark') {
  const page = await context.newPage()
  await page.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
  await page.goto(route)
  if (route.includes('/overview')) await page.locator('.kpi-row').waitFor()
  else if (route.includes('/components/')) await page.locator('.component-detail').waitFor()
  else if (route.includes('/evidence')) await page.getByRole('heading', { name: 'Local cited retrieval' }).waitFor()
  else await page.getByRole('heading', { name: 'TurbineIQ assistant' }).waitFor()
  return page
}

test('axe audits all destinations in both themes', async ({ context }) => {
  const records: Array<Record<string, unknown>> = []
  for (const theme of ['light', 'dark'] as const) {
    for (const [name, route] of routes) {
      const page = await openWithTheme(context, route, theme)
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
      const serious = result.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
      const legacy = serious.flatMap((violation) => violation.nodes.filter((node) => node.target.some((selector) => selector.includes('.legacy-page'))).map((node) => ({ id: violation.id, help: violation.help, target: node.target })))
      const newCode = serious.flatMap((violation) => violation.nodes.filter((node) => !node.target.some((selector) => selector.includes('.legacy-page'))).map((node) => ({ id: violation.id, help: violation.help, target: node.target })))
      records.push({ route: name, theme, seriousOrCritical: serious.map(({ id, help }) => ({ id, help })), legacy, newCode, details: serious.flatMap(({ nodes }) => nodes.map(({ failureSummary, html, target }) => ({ failureSummary, html, target }))) })
      console.log(`AXE ${theme} ${name}: ${newCode.length} new-scope serious/critical; ${legacy.length} legacy-scope nodes`)
      expect(newCode, `${theme} ${name} new-scope axe findings`).toEqual([])
      await page.close()
    }
  }
  await mkdir(resolve(process.cwd(), '../docs/redesign/phase2'), { recursive: true })
  await import('node:fs/promises').then(({ writeFile }) => writeFile(resolve(process.cwd(), '../docs/redesign/phase2/axe-results.json'), JSON.stringify(records, null, 2)))
})

test('keyboard navigation reaches skip link, menus, boundary dialog, and focus return', async ({ page }) => {
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await page.locator('.kpi-row').waitFor()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()

  await page.getByRole('button', { name: 'Local engine · connected' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('status').filter({ hasText: 'Local engine · connected' })).toBeVisible()

  await page.getByRole('button', { name: 'Theme: system' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menu')).toBeVisible()
  await expect(page.getByRole('menuitemradio', { name: 'System' })).toHaveAttribute('aria-checked', 'true')
  await page.getByRole('menuitemradio', { name: 'Dark' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  const chip = page.getByRole('button', { name: /Synthetic · seed 42/ })
  await chip.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Boundary' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'GE 6B.03 reference' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Close boundary' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Close boundary' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Close boundary' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(chip).toBeFocused()
})

test('replay keyboard map updates the selected sample and URL', async ({ page }) => {
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await page.locator('.kpi-row').waitFor()
  const timeline = page.locator('.timeline-card')
  const sample = page.getByRole('slider', { name: 'Scenario sample' })
  await timeline.focus()
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
  await expect(sample).toHaveAttribute('aria-valuetext', /Sample 96 of 96/)
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Pause replay' })).toBeVisible()
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Play replay' })).toBeVisible()
  await expect.poll(() => new URL(page.url()).hash).toContain('i=95')
})

test('overview replay, scenario, seed, mesh selection, evidence, and local assistant still work', async ({ page }) => {
  const origins = new Set<string>()
  page.on('request', (request) => {
    try { origins.add(new URL(request.url()).origin) } catch { return }
  })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await page.locator('.kpi-row').waitFor()
  await expect(page.getByText('26.30', { exact: false }).first()).toBeVisible()

  const seed = page.getByRole('textbox', { name: 'Seed' })
  await seed.fill('43')
  await seed.press('Enter')
  await expect(page).toHaveURL(/seed=43/)
  await seed.fill('-1')
  await seed.press('Enter')
  await expect(seed).toHaveAttribute('aria-invalid', 'true')
  await expect(page).toHaveURL(/seed=43/)
  await expect(page.getByRole('button', { name: /Synthetic · seed 43/ })).toBeVisible()

  const scenario = page.getByRole('combobox', { name: 'Scenario' })
  const options = await scenario.locator('option').count()
  if (options > 1) await scenario.selectOption({ index: 1 })
  const slider = page.getByRole('slider', { name: 'Scenario sample' })
  await page.getByRole('button', { name: 'Play replay' }).click()
  await expect.poll(async () => {
    const value = await slider.getAttribute('aria-valuetext')
    return Number(value?.match(/Sample (\d+)/)?.[1] ?? 0)
  }, { timeout: 5000 }).toBeGreaterThan(73)
  await page.getByRole('button', { name: 'Pause replay' }).click()

  const mesh = page.getByLabel(/Model sub-parts/)
  await expect(mesh).toBeEnabled({ timeout: 20000 })
  const meshOptions = await mesh.locator('option').count()
  if (meshOptions > 1) {
    await mesh.selectOption({ index: 1 })
    await expect(page).toHaveURL(/component=/)
  }

  const stageCanvas = page.locator('.viewer-stage canvas')
  const canvasBox = await stageCanvas.boundingBox()
  expect(canvasBox).not.toBeNull()
  await stageCanvas.click({ position: { x: canvasBox!.width * 0.72, y: canvasBox!.height * 0.5 } })
  await expect(page.locator('.component-row[aria-pressed="true"]')).toContainText('Generator', { timeout: 5000 })
  await expect(page).toHaveURL(/component=generator/)

  await page.getByRole('link', { name: 'Evidence' }).click()
  await page.getByRole('textbox', { name: 'Search local documents' }).fill('Brayton cycle')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.locator('.legacy-results')).not.toBeEmpty({ timeout: 15000 })

  await page.getByRole('link', { name: 'Assistant' }).click()
  await expect(page.getByRole('button', { name: 'Local · demo-safe' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.locator('.legacy-answer')).toBeVisible({ timeout: 20000 })
  expect([...origins].filter((origin) => origin !== new URL('http://127.0.0.1:8011').origin)).toEqual([])
  await mkdir(resolve(process.cwd(), '../docs/redesign/phase2'), { recursive: true })
  await import('node:fs/promises').then(({ writeFile }) => writeFile(resolve(process.cwd(), '../docs/redesign/phase2/network-origins.json'), JSON.stringify([...origins], null, 2)))
})

test('responsive screenshots in light and dark at planned widths', async ({ context }) => {
  const widths = [375, 768, 1024, 1440]
  for (const theme of ['light', 'dark'] as const) {
    for (const width of widths) {
      const page = await context.newPage()
      await page.setViewportSize({ width, height: 1000 })
      await page.addInitScript((savedTheme) => localStorage.setItem('turbineiq-theme', savedTheme), theme)
      await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
      await page.locator('.kpi-row').waitFor()
      await expect(page.getByLabel(/Model sub-parts/)).toBeEnabled({ timeout: 20000 })
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      const layout = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
      expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1)
      const path = resolve(process.cwd(), `../docs/redesign/phase2/${width}-${theme}.png`)
      await mkdir(resolve(path, '..'), { recursive: true })
      await mkdir(resolve(process.cwd(), '../docs/redesign/phase3'), { recursive: true })
      await page.screenshot({ path, fullPage: true, animations: 'disabled' })
      await page.screenshot({ path: resolve(process.cwd(), `../docs/redesign/phase3/${width}-${theme}.png`), fullPage: true, animations: 'disabled' })
      await page.close()
    }
  }
})

test('320px layout has no horizontal page scroll', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await page.locator('.kpi-row').waitFor()
  const layout = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1)
})

test('reduced motion keeps the rotor stopped and touch targets remain 44px', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=72')
  await page.locator('.kpi-row').waitFor()
  const navTarget = await page.locator('.mobile-nav-link').first().boundingBox()
  expect(navTarget?.width).toBeGreaterThanOrEqual(44)
  expect(navTarget?.height).toBeGreaterThanOrEqual(44)
  for (const selector of ['.filter-group', '.viewer-control-row button', '.replay-button', '.icon-action', '.timeline-chart-controls .text-control']) {
    const target = await page.locator(selector).first().boundingBox()
    expect(target?.height, `${selector} touch height`).toBeGreaterThanOrEqual(44)
  }
  await expect(page.getByRole('button', { name: 'Rotor motion' })).toBeDisabled()
  await page.setViewportSize({ width: 812, height: 375 })
  const landscape = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(landscape.scrollWidth).toBeLessThanOrEqual(landscape.clientWidth + 1)
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible()
})
