// Documentation captures only: matched controlled responses, no simulation job.
// Serve the clean 6add5ef baseline in recorded mode, separately from the followup.
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

const baselineUrl = process.env.SIMENV_BASELINE_WEB_URL || 'http://127.0.0.1:5181'
const viewport = { width: 1275, height: 605 }
const browser = await chromium.launch({ headless: true })
async function setup(url, tutorial = false) {
  // The original physical screenshot was approximately 1912 x 907 at 150%.
  // Use CSS pixels for layout and DPR 1 for directly comparable review images.
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  await mockPlayback(page, { tutorial }) // also uses browser-setup's completion seed
  await page.goto(url)
  await page.getByRole('region', { name: 'Component status' }).waitFor()
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('slider', { name: 'Simulation step' }).fill('100')
  await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
  await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('brazil_farms')
  const open = page.getByRole('button', { name: 'Open', exact: true })
  if (await open.count()) await open.click()
  return page
}
async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready)
  if (name === 'expanded' || name.startsWith('tutorial-')) {
    await page.locator('.sim-network-indicators [data-metric]').last().scrollIntoViewIfNeeded()
  }
  await page.waitForTimeout(600)
  await page.screenshot({ path: `../docs/responsive-${name}-medium.png` })
  const boxes = await page.evaluate(() => Object.fromEntries(
    ['.sim-playback-sidebar', '.sim-timeline', '.sim-configurator'].map(selector => {
      const { x, y, width, height } = document.querySelector(selector).getBoundingClientRect()
      return [selector, { x, y, width, height }]
    })))
  console.log(name, JSON.stringify({ viewport, deviceScaleFactor: 1, boxes }))
}
try {
  const before = await setup(baselineUrl)
  assert.equal(await before.getByRole('button', { name: 'Show indicators', exact: true }).count(), 0,
    'Baseline must predate the responsive indicator toggle')
  await capture(before, 'before')
  await before.close()
  const after = await setup(webUrl)
  const show = after.getByRole('button', { name: 'Show indicators', exact: true })
  assert.equal(await show.getAttribute('aria-expanded'), 'false')
  await capture(after, 'after')
  await show.click()
  await after.getByRole('group', { name: 'Network indicators' }).waitFor()
  await capture(after, 'expanded')
  await after.close()
  const page = await setup(webUrl, true)
  const tour = page.getByRole('region', { name: 'Interactive tutorial' })
  while (await tour.getAttribute('data-step') !== 'indicators') await tour.getByRole('button', { name: 'Next', exact: true }).click()
  await tour.getByRole('heading', { name: 'Read network indicators', exact: true }).waitFor()
  await page.getByRole('group', { name: 'Network indicators' }).waitFor()
  await capture(page, 'tutorial-en')
  await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
  await tour.getByRole('heading', { name: 'Netzwerkindikatoren lesen', exact: true }).waitFor()
  await capture(page, 'tutorial-de')
} finally { await browser.close() }
