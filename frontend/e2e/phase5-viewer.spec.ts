import { test, expect, type Locator, type Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

async function tabUntil(page: Page, target: Locator, limit = 100) {
  for (let index = 0; index < limit; index += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return
    await page.keyboard.press('Tab')
  }
  throw new Error('Keyboard traversal did not reach the requested viewer control.')
}

async function installDrawProbe(page: Page) {
  await page.addInitScript(() => {
    let draws = 0
    Object.defineProperty(window, '__turbineDrawCount', { get: () => draws })
    const seen = new Set<object>()
    const names = ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced', 'drawRangeElements']
    for (const contextType of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
      const prototype = contextType?.prototype
      if (!prototype || seen.has(prototype)) continue
      seen.add(prototype)
      for (const name of names) {
        if (!Object.prototype.hasOwnProperty.call(prototype, name)) continue
        const original = prototype[name as keyof typeof prototype]
        if (typeof original !== 'function') continue
        prototype[name as keyof typeof prototype] = function (this: unknown, ...args: unknown[]) {
          draws += 1
          return (original as (...values: unknown[]) => unknown).apply(this, args)
        } as never
      }
    }
  })
}

async function drawCount(page: Page) {
  return page.evaluate(() => (window as Window & { __turbineDrawCount: number }).__turbineDrawCount)
}

async function waitForStableDrawCount(page: Page, stableForMs = 500, timeoutMs = 8000) {
  let lastCount = await drawCount(page)
  let stableSince = Date.now()
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    await page.waitForTimeout(100)
    const currentCount = await drawCount(page)
    if (currentCount !== lastCount) {
      lastCount = currentCount
      stableSince = Date.now()
    } else if (Date.now() - stableSince >= stableForMs) {
      return currentCount
    }
  }
  throw new Error(`The viewer did not become idle within ${timeoutMs} ms.`)
}

test('viewer actions and every component mesh remain keyboard accessible', async ({ page }) => {
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.getByRole('heading', { name: 'Stage' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Blender GLB' })).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole('img', { name: /Interactive simplified gas turbine/ })).toBeVisible()

  const glb = page.getByRole('button', { name: 'GLB', exact: true })
  const schematic = page.getByRole('button', { name: 'Schematic', exact: true })
  await tabUntil(page, schematic)
  await page.keyboard.press('Enter')
  await expect(schematic).toHaveAttribute('aria-pressed', 'true')
  await tabUntil(page, glb)
  await page.keyboard.press('Enter')
  await expect(glb).toHaveAttribute('aria-pressed', 'true')

  const reset = page.getByRole('button', { name: 'Reset camera' })
  await tabUntil(page, reset)
  await page.keyboard.press('Enter')
  const explode = page.getByRole('button', { name: 'Explode view' })
  await tabUntil(page, explode)
  await page.keyboard.press('Enter')
  const reassemble = page.getByRole('button', { name: 'Reassemble model' })
  await expect(reassemble).toHaveAttribute('aria-pressed', 'true')
  await tabUntil(page, reassemble)
  await page.keyboard.press('Enter')
  const isolate = page.getByRole('button', { name: 'Isolate component' })
  await tabUntil(page, isolate)
  await page.keyboard.press('Enter')
  const showAll = page.getByRole('button', { name: 'Show all parts' })
  await expect(showAll).toHaveAttribute('aria-pressed', 'true')
  await tabUntil(page, showAll)
  await page.keyboard.press('Enter')
  const rotor = page.getByRole('button', { name: 'Rotor motion' })
  await tabUntil(page, rotor)
  await page.keyboard.press('Enter')
  const pauseRotor = page.getByRole('button', { name: 'Pause rotor motion' })
  await expect(pauseRotor).toHaveAttribute('aria-pressed', 'true')
  await tabUntil(page, pauseRotor)
  await page.keyboard.press('Enter')

  const components = [
    ['Air inlet', 'inlet'],
    ['Compressor', 'compressor'],
    ['Combustor', 'combustor'],
    ['Turbine', 'turbine'],
    ['Single shaft', 'shaft'],
    ['Generator', 'generator'],
  ] as const
  const picker = page.getByRole('combobox', { name: /Model sub-parts/ })
  for (const [label, id] of components) {
    const row = page.locator('.component-row').filter({ hasText: label })
    await tabUntil(page, row)
    await page.keyboard.press('Enter')
    await expect(row).toHaveAttribute('aria-pressed', 'true')
    await tabUntil(page, picker)
    await expect(picker).toBeEnabled()
    await expect.poll(() => picker.locator('option').count()).toBeGreaterThan(1)
    await page.keyboard.press('Home')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    await expect(picker).not.toHaveValue('')
    await expect(page.locator('.viewer-selection-label')).toBeVisible()
    await expect(page.locator('.part-component-tag')).toHaveText(id.toUpperCase())
  }

  await page.keyboard.press('Escape')
  await page.keyboard.press('Tab')
  await expect(picker).not.toBeFocused()
})

test('demand rendering stops while idle, animates camera and rotor only on request', async ({ page }) => {
  await installDrawProbe(page)
  const origins = new Set<string>()
  page.on('request', (request) => { try { origins.add(new URL(request.url()).origin) } catch { return } })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.getByRole('status').filter({ hasText: 'Blender GLB' })).toBeVisible({ timeout: 30000 })
  await page.locator('.viewer-selection-label').waitFor({ timeout: 30000 })
  await expect.poll(() => page.locator('#model-part-select option').count()).toBeGreaterThan(1)
  expect([...origins]).toEqual(['http://127.0.0.1:8011'])
  const evidenceDir = resolve(process.cwd(), '../docs/redesign/phase5')
  await mkdir(evidenceDir, { recursive: true })
  await writeFile(resolve(evidenceDir, 'viewer-network-origins.json'), JSON.stringify([...origins], null, 2))
  await page.waitForTimeout(700)
  await page.waitForTimeout(500)
  const idleStart = await drawCount(page)
  await page.waitForTimeout(700)
  const idleEnd = await drawCount(page)
  expect(idleEnd).toBe(idleStart)

  await page.getByRole('button', { name: 'Isolate component' }).click()
  await expect.poll(() => drawCount(page), { timeout: 5000 }).toBeGreaterThan(idleEnd)
  const settledCamera = await waitForStableDrawCount(page)

  await page.getByRole('button', { name: 'Rotor motion' }).click()
  await expect.poll(() => drawCount(page), { timeout: 5000 }).toBeGreaterThan(settledCamera)
  const spinningCount = await drawCount(page)
  await page.waitForTimeout(300)
  expect(await drawCount(page)).toBeGreaterThan(spinningCount)
  await page.getByRole('button', { name: 'Pause rotor motion' }).click()
  const paused = await waitForStableDrawCount(page)
  await page.waitForTimeout(500)
  expect(await drawCount(page)).toBe(paused)
})

test('reduced motion disables rotor animation and removes camera easing', async ({ page }) => {
  await installDrawProbe(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.getByRole('status').filter({ hasText: 'Blender GLB' })).toBeVisible({ timeout: 30000 })
  const rotor = page.getByRole('button', { name: 'Rotor motion' })
  await expect(rotor).toHaveAttribute('aria-disabled', 'true')
  await tabUntil(page, rotor)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: 'Rotor motion' })).toHaveAttribute('aria-pressed', 'false')
  const duration = await page.locator('html').evaluate((element) => getComputedStyle(element).getPropertyValue('--dur-slow').trim())
  const milliseconds = Number.parseFloat(duration) * (duration.endsWith('s') && !duration.endsWith('ms') ? 1000 : 1)
  expect(milliseconds).toBe(240)

  await page.waitForTimeout(300)
  await page.getByRole('button', { name: 'Isolate component' }).click()
  await page.waitForTimeout(200)
  const settled = await drawCount(page)
  await page.waitForTimeout(400)
  expect(await drawCount(page)).toBe(settled)
})

test('responsive stage resizes without browser runtime errors', async ({ page }) => {
  const errors: string[] = []
  let viewport = 'initial'
  page.on('pageerror', (error) => errors.push(`${viewport}: ${error.stack ?? error.message}`))
  page.on('console', (message) => { if (message.type() === 'error' && !message.location().url.endsWith('/favicon.ico')) errors.push(`${viewport}: ${message.text()} ${JSON.stringify(message.location())}`) })
  page.on('response', (response) => { if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) errors.push(`${viewport}: ${response.status()} ${response.url()}`) })
  await page.goto('/#/overview?scenario=compressor_fouling&seed=42&i=48')
  await expect(page.getByRole('status').filter({ hasText: 'Blender GLB' })).toBeVisible({ timeout: 30000 })
  await expect(page.locator('.viewer-selection-label')).toBeVisible({ timeout: 30000 })
  for (const [width, height] of [[1024, 768], [768, 1024], [375, 812], [1440, 900]]) {
    viewport = `${width}x${height}`
    await page.setViewportSize({ width, height })
    await page.waitForTimeout(300)
  }
  await writeFile(resolve(process.cwd(), '../docs/redesign/phase5/responsive-runtime-errors.json'), JSON.stringify(errors, null, 2))
  expect(errors).toEqual([])
})
