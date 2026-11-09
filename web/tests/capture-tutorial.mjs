// Documentation artifacts: real static bundle for before/after, controlled
// recorded responses for bilingual impact guidance. No simulation is submitted.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

const baselineUrl = process.env.SIMENV_BASELINE_WEB_URL || 'http://127.0.0.1:5176'
const staticUrl = process.env.SIMENV_STATIC_WEB_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({ headless: true })
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(500)
  await page.screenshot({ path: `../docs/tutorial-${name}.png` })
}
async function pause(page) {
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('slider', { name: 'Simulation step' }).fill('100')
  await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '100')
}
try {
  const baselineBundle = await (await fetch(`${baselineUrl}/bundle.json`)).text()
  const afterBundle = await (await fetch(`${staticUrl}/bundle.json`)).text()
  assert.equal(afterBundle, baselineBundle, 'Before/after must use the same static bundle')
  console.log(`Static bundle SHA-256: ${createHash('sha256').update(afterBundle).digest('hex')}`)
  for (const [size, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    for (const [version, url] of [['before', baselineUrl], ['after', staticUrl]]) {
      const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
      await page.goto(url)
      await pause(page)
      if (version === 'before') {
        const open = page.getByRole('button', { name: 'Open', exact: true })
        if (await open.count()) await open.click()
      }
      const name = page.getByRole('textbox', { name: 'Scenario name' })
      await name.scrollIntoViewIfNeeded()
      if (version === 'after') {
        await page.getByRole('region', { name: 'Interactive tutorial' }).getByRole('heading', { name: 'Name your scenario' }).waitFor()
      } else {
        assert.equal(await page.getByRole('region', { name: 'Interactive tutorial' }).count(), 0)
      }
      if (size === 'mobile') await name.evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'instant' }))
      await capture(page, `${version}-${size}`)
      await page.close()
    }
  }
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  await mockPlayback(page, { tutorial: true })
  await page.goto(webUrl)
  await pause(page)
  const tour = page.getByRole('region', { name: 'Interactive tutorial' })
  for (let i = 0; i < 7; i++) await tour.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
  await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('brazil_farms')
  await page.locator('.sim-playback-sidebar').evaluate(el => { el.scrollTop += 320 })
  await tour.getByRole('heading', { name: 'Inspect component evidence' }).waitFor()
  await capture(page, 'impact-en')
  await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
  await tour.getByRole('heading', { name: 'Komponentendaten prüfen' }).waitFor()
  await capture(page, 'impact-de')
} finally { await browser.close() }
