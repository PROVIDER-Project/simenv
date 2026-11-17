import { test } from 'node:test'
import assert from 'node:assert/strict'
import { setTimeout as sleep } from 'node:timers/promises'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'
import { origin, webUrl, run, scene, page as frames, mockPlayback } from './playback-fixtures.mjs'

const slider = page => page.getByRole('slider', { name: 'Simulation step', exact: true })
const button = (page, name) => page.getByRole('button', { name, exact: true })
async function at(page, period) {
  for (let i = 0; i < 200; i++) {
    if (await slider(page).inputValue() === String(period) &&
      await page.getByRole('region', { name: 'Component status' }).getAttribute('data-period') === String(period)) return
    await sleep(10)
  }
  assert.equal(await slider(page).inputValue(), String(period))
  assert.equal(await page.getByRole('region', { name: 'Component status' }).getAttribute('data-period'), String(period))
}
async function pause(page) { await button(page, 'Pause').click() }

test('speed presets change actual pacing, preserve pause, and survive run changes', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await mockPlayback(page); await page.goto(webUrl); await pause(page)
    const speed = page.getByRole('status', { name: 'Playback speed', exact: true })
    assert.equal(await speed.textContent({ timeout: 2000 }), '1×')
    await slider(page).fill('10'); await at(page, 10)
    await button(page, 'Slower playback').click()
    assert.equal(await speed.textContent(), '0.5×')
    await button(page, 'Slower playback').click()
    assert.equal(await speed.textContent(), '0.25×')
    assert.equal(await button(page, 'Slower playback').isDisabled(), true)
    assert.equal(await button(page, 'Play').isVisible(), true)

    await page.clock.install({ time: new Date('2030-01-01T00:00:00Z') })
    await page.clock.pauseAt(new Date('2030-01-01T00:00:01Z'))
    for (const [multiplier, delay] of [['0.25×', 240], ['0.5×', 120], ['1×', 60], ['2×', 30], ['4×', 15]]) {
      assert.equal(await speed.textContent(), multiplier)
      await slider(page).fill('10'); await at(page, 10)
      await button(page, 'Play').click()
      await page.clock.runFor(delay - 1)
      assert.equal(await slider(page).inputValue(), '10', 'must wait the selected interval')
      await page.clock.runFor(1); await at(page, 11)
      await pause(page)
      if (multiplier !== '4×') await button(page, 'Faster playback').click()
    }
    assert.equal(await button(page, 'Faster playback').isDisabled(), true)
    await page.clock.resume()
    await page.getByLabel('Recorded run', { exact: true }).selectOption('second')
    await pause(page)
    assert.equal(await speed.textContent(), '4×')
    await page.getByLabel('Recorded scenario', { exact: true }).selectOption('0')
    await pause(page)
    assert.equal(await speed.textContent(), '4×')
  } finally { await browser.close() }
})

for (const blockedScenario of [0, 1]) {
  test(`manual steps accumulate and reverse while ${blockedScenario ? 'current' : 'reference'} data loads`, async () => {
    const browser = await chromium.launch({ headless: true })
    let release
    const held = new Promise(resolve => { release = resolve })
    try {
      const page = await browser.newPage()
      await dismissInitialTutorial(page)
      await page.route(`${origin}/**`, async route => {
        const url = new URL(route.request().url())
        if (url.pathname === '/runs') return route.fulfill({ json: { items: [run('first')], total: 1 } })
        const [, , id, , scenario, kind] = url.pathname.split('/')
        if (kind === 'scene') return route.fulfill({ json: scene(id, Number(scenario)) })
        const start = Number(url.searchParams.get('start'))
        if (Number(scenario) === blockedScenario && start === 100) await held
        return route.fulfill({ json: frames(id, Number(scenario), start) }).catch(() => {})
      })
      await page.goto(webUrl); await pause(page)
      await slider(page).fill('99'); await at(page, 99)
      await button(page, 'Play').click()
      // The pending automatic target is 100, while the committed frame stays 99.
      await page.getByText('Buffering playback…', { exact: true }).waitFor()
      await button(page, 'Next simulation step').click({ timeout: 2000 })
      await button(page, 'Next simulation step').click()
      await button(page, 'Previous simulation step').click()
      assert.equal(await button(page, 'Play').isVisible(), true)
      assert.equal(await slider(page).inputValue(), '99')
      release(); await at(page, 101)
      await sleep(180)
      assert.equal(await slider(page).inputValue(), '101', 'loading must not resume autoplay')
      await button(page, 'Previous simulation step').click(); await at(page, 100)
      await button(page, 'Next simulation step').click(); await at(page, 101)
    } finally { release(); await browser.close() }
  })
}

test('manual stepping clamps at nonzero scene boundaries and still pauses autoplay', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await mockPlayback(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const [, , id, , scenario] = new URL(route.request().url()).pathname.split('/')
      const result = scene(id, Number(scenario)); result.min_period = 10; result.max_period = 12
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    await page.clock.install({ time: new Date('2030-01-01T00:00:00Z') })
    await page.clock.pauseAt(new Date('2030-01-01T00:00:01Z'))
    for (const [period, name] of [[10, 'Previous simulation step'], [12, 'Next simulation step']]) {
      await slider(page).fill(String(period)); await at(page, period)
      await button(page, 'Play').click()
      await button(page, name).click({ timeout: 2000 })
      assert.equal(await button(page, 'Play').isVisible(), true)
      await page.clock.runFor(500)
      assert.equal(await slider(page).inputValue(), String(period))
    }
  } finally { await browser.close() }
})
