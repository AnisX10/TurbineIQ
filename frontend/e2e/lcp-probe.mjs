import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-background-networking', '--disable-component-update'] })
const results = {}

for (const [preset, viewport] of [['mobile', { width: 390, height: 844 }], ['desktop', { width: 1350, height: 940 }]]) {
  const page = await browser.newPage({ viewport })
  await page.addInitScript(() => {
    window.__lcpEntries = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const element = entry.element
        window.__lcpEntries.push({
          startTime: entry.startTime,
          tag: element?.tagName,
          id: element?.id,
          className: typeof element?.className === 'string' ? element.className : '',
          text: element?.textContent?.trim().slice(0, 100),
        })
      }
    }).observe({ type: 'largest-contentful-paint', buffered: true })
  })
  await page.goto('http://127.0.0.1:8011/#/overview?scenario=compressor_fouling&seed=42&i=72', { waitUntil: 'load', timeout: 30000 })
  await page.locator('.kpi-row').waitFor()
  await page.waitForTimeout(2500)
  results[preset] = await page.evaluate(() => ({ entries: window.__lcpEntries, final: window.__lcpEntries.at(-1) }))
  await page.close()
}

await browser.close()
const outputPath = resolve(process.cwd(), '../docs/redesign/phase4/lcp-elements.json')
await mkdir(resolve(process.cwd(), '../docs/redesign/phase4'), { recursive: true })
await writeFile(outputPath, `${JSON.stringify(results, null, 2)}\n`)
console.log(JSON.stringify(results, null, 2))
