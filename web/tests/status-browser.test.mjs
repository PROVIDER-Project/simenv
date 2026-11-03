import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { origin, webUrl, run, scene, page as frames } from './playback-fixtures.mjs'

async function workshop(page, { referenceFailure = false } = {}) {
  const state = { referenceFailure, delay: null }
  await page.route(`${origin}/**`, async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/runs') return route.fulfill({ json: { items: [run('shock'), run('baseline')], total: 2 } })
    const [, , id, , scenario, kind] = url.pathname.split('/')
    if (kind === 'scene') return route.fulfill({ json: scene(id, Number(scenario)) })
    const start = Number(url.searchParams.get('start'))
    if (Number(scenario) === 0 && state.referenceFailure) return route.fulfill({ status: 503, json: { detail: 'Reference offline' } })
    if (Number(scenario) === 0 && state.delay) await state.delay
    const result = frames(id, Number(scenario), start)
    for (const frame of result.frames) {
      const disturbed = id === 'shock' && Number(scenario) === 1 && frame.period < 200
      frame.agents[0].values = { unit_price: 100, quantity_available: disturbed ? 50 : 100, active: 1 }
      frame.agents[1].values.soy_price = disturbed ? 150 : 100
      frame.agents[1].values.feed_price = disturbed ? 30 : 20
      frame.agents[1].values.total_soy_supply = disturbed ? 50 : 100
      frame.agents[1].values.transport_utilisation = .96
    }
    return route.fulfill({ json: result }).catch(() => {})
  })
  return state
}

async function pause(page) {
  await page.getByRole('slider', { name: 'Simulation step' }).waitFor()
  const button = page.getByRole('button', { name: 'Pause', exact: true })
  if (await button.isVisible()) await button.click()
}

test('day-zero disturbance, keyboard inspection, recovery and start-mode limitation agree', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await workshop(page)
    await page.goto(webUrl)
    await pause(page)
    const details = page.getByRole('region', { name: 'Component status' })
    await details.getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.match(await details.innerText(), /Severe/)
    const component = page.getByRole('combobox', { name: 'Inspect component' })
    await component.focus(); await page.keyboard.press('Home'); await page.keyboard.press('Enter')
    const slider = page.getByRole('slider', { name: 'Simulation step' })
    await slider.fill('250')
    await details.getByText('Supply availability up 0%', { exact: true }).waitFor()
    assert.match(await details.innerText(), /Near reference/)
    assert.equal(await details.getAttribute('data-period'), '250')
    const indicators = page.getByRole('group', { name: 'Network indicators' })
    assert.equal(await indicators.locator('[data-metric]').count(), 4)
    assert.equal(await indicators.getAttribute('data-period'), '250')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    await slider.fill('0')
    await details.getByText('Supply availability up 0%', { exact: true }).waitFor()
    assert.match(await page.getByText(/cannot reveal disturbances already present/).first().innerText(), /first/)
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('baseline')
    await details.getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    assert.ok(await page.evaluate(() => document.querySelector('.sim-app').scrollWidth <= innerWidth))
  } finally { await browser.close() }
})

test('reference failure keeps capacity and participation while retry restores relative evidence', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const state = await workshop(page, { referenceFailure: true })
    await page.route(`${origin}/runs/shock/scenarios/0/scene`, route => state.referenceFailure
      ? route.fulfill({ status: 503, json: { detail: 'Reference offline' } })
      : route.fulfill({ json: scene('shock', 0) }))
    await page.goto(webUrl); await pause(page)
    await page.getByRole('region', { name: 'Reference comparison' }).getByText('Reference offline', { exact: false }).waitFor()
    const details = page.getByRole('region', { name: 'Component status' })
    assert.match(await details.innerText(), /Unavailable/)
    assert.match(await details.innerText(), /active/)
    const transport = page.locator('[data-metric="transport_utilisation"]')
    assert.match(await transport.innerText(), /Severe/)
    state.referenceFailure = false
    await page.getByRole('button', { name: 'Retry reference' }).click()
    await details.getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.match(await details.innerText(), /Severe/)
  } finally { await browser.close() }
})

test('late reference cannot repaint a newer reference selection or seek', async () => {
  const browser = await chromium.launch({ headless: true })
  let release
  try {
    const page = await browser.newPage()
    const state = await workshop(page)
    await page.goto(webUrl); await pause(page)
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    state.delay = new Promise(resolve => { release = resolve })
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('baseline')
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    release(); state.delay = null
    const details = page.getByRole('region', { name: 'Component status' })
    await details.getByText('Supply availability up 100%', { exact: true }).waitFor()
    assert.equal(await details.getAttribute('data-period'), '250')
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'start')
  } finally { release?.(); await browser.close() }
})

test('switching away and back starts a fresh reference lifecycle after failure', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const state = await workshop(page, { referenceFailure: true })
    await page.route(`${origin}/runs/shock/scenarios/0/scene`, route => state.referenceFailure
      ? route.fulfill({ status: 503, json: { detail: 'Reference offline' } })
      : route.fulfill({ json: scene('shock', 0) }))
    await page.goto(webUrl); await pause(page)
    await page.getByRole('region', { name: 'Reference comparison' }).getByText(/Reference offline/).waitFor()
    state.referenceFailure = false
    const selector = page.getByRole('combobox', { name: 'Reference condition' })
    await selector.selectOption('start')
    await selector.selectOption('shock')
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.equal(await page.getByText(/Reference unavailable:/).count(), 0)
  } finally { await browser.close() }
})

test('refresh preserves the actual reference selection outside the refreshed catalogue page', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.goto(webUrl); await pause(page)
    const selector = page.getByRole('combobox', { name: 'Reference condition' })
    await selector.selectOption('baseline')
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    await page.route(`${origin}/runs?*`, route => route.fulfill({ json: { items: [run('shock')], total: 60 } }))
    const refreshed = page.waitForResponse(response => response.url().includes('/runs?'))
    await page.getByRole('button', { name: 'Refresh runs', exact: true }).click()
    await refreshed
    await page.waitForFunction(() => !document.querySelector('.sim-run-selector-controls button')?.disabled)
    assert.equal(await selector.inputValue(), 'baseline')
  } finally { await browser.close() }
})
