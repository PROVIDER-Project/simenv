import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl, origin, page as framePage } from './playback-fixtures.mjs'

test('finds a playable run beyond page one, seeks and resets equal-length selections', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const requests = await mockPlayback(page, { beyondFirst: true })
    await page.goto(webUrl)
    await page.getByRole('slider', { name: 'Simulation step' }).waitFor()
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '250')
    assert.ok(requests.some(r => r.start === 200 && r.limit === 100))
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    assert.ok(Number(await page.getByRole('slider', { name: 'Simulation step' }).inputValue()) < 20)
    await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).selectOption('0')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value < 20)
    assert.ok(requests.some(r => r.id === 'second' && r.scenario === 0 && r.start === 0))
    assert.ok(requests.every(r => r.limit === 100))
  } finally { await browser.close() }
})

test('an empty catalogue keeps submission available and retry restores playback', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await page.route(`${origin}/**`, route => route.fulfill({ json: { items: [], total: 0 }, headers: { 'access-control-allow-origin': '*' } }))
    await page.goto(webUrl)
    await page.getByText('No recorded runs yet.').waitFor()
    assert.equal(await page.getByRole('button', { name: 'Run simulation', exact: true }).isVisible(), true)
    await page.unroute(`${origin}/**`)
    await mockPlayback(page)
    await page.getByRole('button', { name: 'Refresh runs', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).waitFor()
  } finally { await browser.close() }
})

test('late old selection and failed pages cannot replace the active frame', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    let fail = true
    await mockPlayback(page)
    await page.route(`${origin}/runs/first/scenarios/1/frames*`, async route => {
      const start = Number(new URL(route.request().url()).searchParams.get('start'))
      if (start === 200 && fail) return route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' }, headers: { 'access-control-allow-origin': '*' } })
      await route.fulfill({ json: framePage('first', 1, start), headers: { 'access-control-allow-origin': '*' } })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const previous = await page.getByRole('slider', { name: 'Simulation step' }).inputValue()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.getByRole('alert').waitFor()
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), previous)
    fail = false
    await page.getByRole('button', { name: 'Retry playback', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '250')
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
  } finally { await browser.close() }
})

test('a late old-run response is ignored after switching and seeking', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await mockPlayback(page)
    let release
    const blocked = new Promise(resolve => { release = resolve })
    await page.route(`${origin}/runs/first/scenarios/1/frames*`, async route => {
      await blocked
      await route.fulfill({ json: framePage('first', 1, 0), headers: { 'access-control-allow-origin': '*' } }).catch(() => {})
    })
    await page.goto(webUrl)
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '250')
    release()
    await page.waitForTimeout(500)
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '250')
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
  } finally { await browser.close() }
})

test('refresh retains a selected run beyond the refreshed first catalogue page', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await mockPlayback(page, { beyondFirst: true })
    await page.goto(webUrl)
    await page.getByRole('slider', { name: 'Simulation step' }).waitFor()
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await page.getByRole('button', { name: 'Refresh runs', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('.sim-run-selector button')?.disabled)
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
    assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).isEnabled(), true)
  } finally { await browser.close() }
})

test('mobile empty-state playback controls do not obstruct first-run submission', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    await page.route(`${origin}/**`, route => route.fulfill({ json: { items: [], total: 0 }, headers: { 'access-control-allow-origin': '*' } }))
    await page.goto(webUrl)
    await page.getByText('No recorded runs yet.').waitFor()
    await page.getByRole('button', { name: 'Open', exact: true }).click()
    const button = page.getByRole('button', { name: 'Run simulation', exact: true })
    assert.equal(await button.evaluate(element => {
      const r = element.getBoundingClientRect()
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return element === hit || element.contains(hit)
    }), true)
  } finally { await browser.close() }
})
