// Drive a short live-twin demo and capture the console (1440x900 light/dark, 390x844).
// Usage: node e2e/capture-twin-console.mjs [baseURL] [outDir]
// Set PW_CHROMIUM_PATH to use a preinstalled Chromium. Needs the API serving frontend/dist (python -m uvicorn turbineiq.api.main:app).
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const base = process.argv[2] ?? 'http://127.0.0.1:8021'
const out = resolve(process.argv[3] ?? '../docs/redesign/twin-console')
await mkdir(out, { recursive: true })

const browser = await chromium.launch({
  ...(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {}),
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })

async function advance(page, seconds) {
  const id = await page.evaluate(() => sessionStorage.getItem('turbineiq-sim-session'))
  let left = seconds
  while (left > 0) {
    const chunk = Math.min(120, left)
    const r = await page.request.post(`${base}/api/sim/sessions/${id}/advance`, { data: { seconds: chunk } })
    if (!r.ok()) throw new Error(await r.text())
    left -= chunk
  }
  return id
}

async function refresh(page) {
  // Let the console poll once at 1x so it shows the advanced state.
  await page.getByRole('button', { name: '1×' }).click()
  await page.getByRole('button', { name: 'Run' }).click()
  await page.waitForTimeout(1600)
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.waitForTimeout(400)
}

const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' })
const page = await context.newPage()
await page.goto(`${base}/`)
await page.getByRole('heading', { name: 'Start a live twin' }).waitFor()
await page.screenshot({ path: `${out}/00-start-light-1440.png` })
await page.getByRole('group', { name: 'Layer mode' }).getByRole('button', { name: 'Autonomous' }).click()
await page.getByRole('button', { name: 'Create unit' }).click()
await page.getByTestId('twin-unit-state').waitFor()
await page.getByRole('button', { name: 'Start', exact: true }).click()
await advance(page, 300)
await refresh(page)
await page.getByRole('textbox', { name: 'Demand' }).fill('35')
await page.getByRole('button', { name: 'Set', exact: true }).click()
await advance(page, 480)
await refresh(page)
await page.waitForTimeout(1500)
await page.screenshot({ path: `${out}/01-loaded-light-1440.png` })

// Fault: exhaust thermocouple stuck, then raise the load so the reading and the twin part ways.
await page.getByRole('button', { name: 'Faults' }).click()
await page.getByLabel('Sensor', { exact: true }).selectOption('exhaust_temperature')
await page.getByLabel('Fault mode').selectOption('stuck')
await page.getByRole('button', { name: 'Inject sensor fault' }).click()
await page.getByRole('button', { name: 'Close faults' }).click()
await page.getByRole('textbox', { name: 'Demand' }).fill('40')
await page.getByRole('button', { name: 'Set', exact: true }).click()
let reacted = false
for (let i = 0; i < 12 && !reacted; i += 1) {
  const id = await advance(page, 60)
  const sup = await (await page.request.get(`${base}/api/sim/sessions/${id}/supervisor`)).json()
  reacted = sup.substitute_active || sup.recent_decisions.some((d) => d.problem === 'exhaust_feedback')
}
await advance(page, 30)
await refresh(page)
await page.waitForTimeout(1500)
await page.screenshot({ path: `${out}/02-fault-light-1440.png` })

await page.emulateMedia({ colorScheme: 'dark' })
await page.waitForTimeout(1200)
await page.screenshot({ path: `${out}/03-fault-dark-1440.png` })
await page.getByRole('button', { name: 'Log', exact: true }).click()
await page.waitForTimeout(800)
await page.screenshot({ path: `${out}/04-log-dark-1440.png` })
await page.getByRole('button', { name: 'Close log' }).click()

// Phone: the same tab session (sessionStorage) is resumed in a new page of this context.
await page.emulateMedia({ colorScheme: 'light' })
await page.setViewportSize({ width: 390, height: 844 })
await page.reload()
await page.getByTestId('twin-unit-state').waitFor()
await page.waitForTimeout(2500)
await page.screenshot({ path: `${out}/05-fault-light-390.png` })
await page.screenshot({ path: `${out}/06-fault-light-390-full.png`, fullPage: true })

await browser.close()
console.log(`saved to ${out}`)
