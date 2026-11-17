// Documentation capture only: mocked API responses, no real simulation.
// Writes only the two current step 3/4 screenshots; preserves historical PNGs.
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1275, height: 605 }, deviceScaleFactor: 1 })
  await mockPlayback(page, { tutorial: true })
  let submissions = 0
  await page.route('**/api/simulations', route => {
    assert.equal(route.request().method(), 'POST')
    submissions++
    return route.fulfill({ status: 202, json: {
      id: 'second', label: 'Mocked documentation capture', status: 'completed', error: null,
      progress: { scenario_id: 1, step: 300, scenario_total_steps: 300, completed_steps: 300, total_steps: 300, percent_complete: 100 },
    } })
  })
  await page.goto(webUrl)
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  const tour = page.getByRole('region', { name: 'Interactive tutorial' })
  while (await tour.getAttribute('data-step') !== 'execution') await tour.getByRole('button', { name: 'Next', exact: true }).click()
  async function capture(target, filename) {
    assert.equal(await tour.getAttribute('data-step'), target)
    await page.waitForFunction(id => {
      const target = document.querySelector(`[data-tutorial="${id}"]`)
      const highlight = document.querySelector('.sim-tutorial-highlight')
      if (!target || !highlight) return false
      const r = target.getBoundingClientRect(), h = highlight.getBoundingClientRect()
      return r.top >= 0 && r.bottom <= innerHeight && Math.abs(h.y - (r.y - 4)) < 2
    }, target)
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(500)
    await page.screenshot({ path: `../docs/${filename}.png` })
    console.log(`Captured ${filename}.png: ${target}, mocked fixtures, 1275x605`)
  }
  await tour.getByRole('heading', { name: 'Execute and monitor', exact: true }).waitFor()
  await capture('execution', 'tutorial-execution-auto-advance')
  assert.equal(submissions, 0)
  await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
  await tour.getByRole('heading', { name: 'Open the completed run', exact: true }).waitFor()
  await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
  await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
  await tour.getByRole('heading', { name: 'Abgeschlossenen Lauf öffnen', exact: true }).waitFor()
  await capture('results', 'tutorial-results-auto-advance')
  await page.getByRole('button', { name: 'View results', exact: true }).click()
  await tour.getByRole('heading', { name: 'Aufzeichnung auswählen', exact: true }).waitFor()
  assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
  assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
  assert.equal(submissions, 1)
  console.log('Verified explicit mocked submission: 3→4; successful exact results selection: 4→5 (second, scenario 1)')
} finally { await browser.close() }
