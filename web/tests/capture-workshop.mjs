// Issue #82 acceptance evidence. Run from web/ with two recorded-mode servers:
// clean d5f02ab: VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --port 5192
// current:       VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --port 5182
// SIMENV_BASELINE_WEB_URL=http://127.0.0.1:5192 SIMENV_WEB_URL=http://127.0.0.1:5182 \
//   node tests/capture-workshop.mjs
// All images are explicitly labeled controlled API fixtures, not simulation runs.
// Assertions run after capture so a geometry failure still leaves review evidence.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { mockPlayback, origin, scene, page as frames, webUrl } from './playback-fixtures.mjs'

export const workshopButtons = ['Previous simulation step', 'Next simulation step', 'Slower playback', 'Faster playback']
const sizes = [['desktop', { width: 1275, height: 605 }], ['mobile', { width: 320, height: 568 }]]
const output = new URL('../../docs/screenshots/issue82/', import.meta.url)

export async function controlledState(page) {
  await page.getByRole('region', { name: 'Component status' }).waitFor()
  const pause = page.getByRole('button', { name: 'Pause', exact: true })
  if (await pause.count()) await pause.click()
  // An explicit first/0 reference prevents automatic-reference preparation.
  await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('first')
  await page.getByRole('slider', { name: 'Simulation step' }).fill('100')
  await page.waitForFunction(() => document.querySelector('[aria-label="Component status"]')?.dataset.period === '100')
  const hide = page.getByRole('button', { name: 'Hide indicators', exact: true })
  if (await hide.count()) await hide.click()
  assert.equal(await page.getByRole('button', { name: 'Show indicators', exact: true }).getAttribute('aria-expanded'), 'false')
  const open = page.getByRole('button', { name: 'Open', exact: true })
  if (await open.count()) await open.click()
  await page.evaluate(() => document.fonts.ready)
}

export async function timelineGeometry(page) {
  return page.evaluate(() => {
    const box = selector => {
      const { x, y, width, height, right, bottom } = document.querySelector(selector).getBoundingClientRect()
      return { x, y, width, height, right, bottom }
    }
    const readout = document.querySelector('.sim-timeline-readout')
    const rows = new Set([...readout.children].filter(el => el.textContent.trim()).map(el => Math.round(el.getBoundingClientRect().top)))
    return {
      timeline: box('.sim-timeline'), readout: box('.sim-timeline-readout'), readoutRows: rows.size,
      scrubber: box('.sim-timeline-track input'), heading: box('.sim-frame-heading'),
      title: box('.sim-frame-heading h1'), restart: box('.sim-tutorial-restart'), configurator: box('.sim-configurator'),
      horizontalOverflow: document.querySelector('.sim-app').scrollWidth > document.querySelector('.sim-app').clientWidth,
    }
  })
}

async function capture(page, name, label) {
  await page.evaluate(label => {
    document.querySelector('#workshop-capture-label')?.remove()
    const badge = document.createElement('div')
    badge.id = 'workshop-capture-label'
    badge.textContent = `CONTROLLED API FIXTURE · ${label} · paused 100 · reference first/0 · indicators collapsed`
    badge.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:100;pointer-events:none;background:#071321ed;color:#fff;font:9px/1.3 monospace;padding:2px 5px;text-align:center'
    document.body.append(badge)
  }, label)
  await page.waitForTimeout(600)
  const path = fileURLToPath(new URL(`${name}.png`, output))
  await page.screenshot({ path, animations: 'disabled' })
  console.log(`Screenshot: ${path}`)
}

// Capture-only graph: real placed farm -> unrecorded export port -> EU port.
// Both ports remain explicitly unrecorded in the matched before/after fixture.
// Status/renderer behavior is covered separately by status-browser.test.mjs.
async function laneFixture(page) {
  await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
    const parts = new URL(route.request().url()).pathname.split('/')
    const result = scene(parts[2], Number(parts[4]))
    for (const [id, label, lat, lng] of [
      ['santos_port', 'Workshop export port', -24, -46], ['rotterdam_port', 'Workshop import port', 52, 4],
    ]) result.nodes.push({ id, label, role: 'land_transport', entityIds: [id], hasRecordedData: false,
      placements: [{ entityId: id, label, lat, lng, illustrative: false }] })
    result.edges = [{ id: 'farm-port', source: 'brazil_farms', target: 'santos_port', isSeaCrossing: false },
      { id: 'ocean', source: 'santos_port', target: 'rotterdam_port', isSeaCrossing: true }]
    return route.fulfill({ json: result })
  })
  await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
    const url = new URL(route.request().url()), parts = url.pathname.split('/')
    const scenario = Number(parts[4])
    const result = frames(parts[2], scenario, Number(url.searchParams.get('start')))
    for (const frame of result.frames) {
      frame.agents[0].values = { unit_price: 100, quantity_available: scenario === 1 ? 50 : 100, active: 1 }
    }
    return route.fulfill({ json: result })
  })
}

async function main() {
  const baselineUrl = process.env.SIMENV_BASELINE_WEB_URL || 'http://127.0.0.1:5192'
  await mkdir(output, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const failures = []
  const check = fn => { try { fn() } catch (error) { failures.push(error.message) } }
  async function setup(url, viewport, lane = false) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
    page.setDefaultTimeout(10000)
    await mockPlayback(page)
    if (lane) await laneFixture(page)
    await page.goto(url)
    await controlledState(page)
    return page
  }
  try {
    for (const [size, viewport] of sizes) {
      const measurements = {}
      for (const [version, url] of [['before', baselineUrl], ['after', webUrl]]) {
        const page = await setup(url, viewport)
        assert.equal(await page.getByRole('button', { name: 'Faster playback', exact: true }).count(), version === 'before' ? 0 : 1,
          'Baseline must be clean d5f02ab; current must contain workshop controls')
        if (size === 'mobile') await page.locator('.sim-timeline').evaluate(el => el.scrollIntoView({ block: 'center', behavior: 'instant' }))
        else await page.locator('.sim-app').evaluate(el => { el.scrollTop = 0 })
        measurements[version] = await timelineGeometry(page)
        await capture(page, `compact-${size}-${version}`, `${version === 'before' ? 'd5f02ab BEFORE' : 'Issue82 AFTER'} · ${viewport.width}×${viewport.height}`)
        await page.close()
      }
      console.log(`${size} geometry: ${JSON.stringify(measurements)}`)
      const { before, after } = measurements
      check(() => assert.ok(after.timeline.width <= before.timeline.width + .1, `${size}: timeline width increased`))
      check(() => assert.ok(after.timeline.height <= before.timeline.height + .1, `${size}: collapsed timeline height ${before.timeline.height} -> ${after.timeline.height}`))
      check(() => assert.ok(after.readoutRows <= before.readoutRows, `${size}: readout rows ${before.readoutRows} -> ${after.readoutRows}`))
      check(() => assert.ok(after.scrubber.width >= 120, `${size}: scrubber is too short`))
      check(() => assert.equal(after.horizontalOverflow, false, `${size}: horizontal application overflow`))
      check(() => assert.ok(after.title.right <= after.restart.x && after.restart.y < after.title.bottom && after.title.y < after.restart.bottom, `${size}: restart shares title row without overlap`))
      if (size === 'desktop') check(() => assert.ok(Math.abs(after.configurator.x - after.restart.right - 16) <= 1, 'restart anchors 16px from configurator'))
    }
    // First-step heading stays focused in both captures: outline difference is real.
    for (const [version, url] of [['before', baselineUrl], ['after', webUrl]]) {
      const page = await setup(url, sizes[0][1])
      await page.getByRole('button', { name: 'Restart tutorial', exact: true }).click()
      const heading = page.getByRole('region', { name: 'Interactive tutorial' }).getByRole('heading')
      // Keyboard modality reproduces the reported focus-visible outline.
      await page.keyboard.press('Tab')
      await heading.focus()
      const focus = await heading.evaluate(el => ({ focused: document.activeElement === el, outline: getComputedStyle(el).outline, outlineStyle: getComputedStyle(el).outlineStyle, boxShadow: getComputedStyle(el).boxShadow }))
      console.log(`First tutorial heading ${version}:`, focus)
      if (version === 'after') check(() => assert.ok(focus.focused && focus.outlineStyle === 'none' && focus.boxShadow === 'none', 'focused tutorial heading has no textbox-like outline'))
      await capture(page, `first-tutorial-desktop-${version}`, `${version === 'before' ? 'd5f02ab BEFORE' : 'Issue82 AFTER'} · focused first heading · 1275×605`)
      await page.close()
    }
    for (const [size, viewport] of sizes) {
      const page = await setup(webUrl, viewport)
      await page.getByRole('button', { name: 'Restart tutorial', exact: true }).click()
      const tour = page.getByRole('region', { name: 'Interactive tutorial' })
      for (const [step, language] of [['speed', 'en'], ['speed', 'de'], ['stepping', 'en'], ['stepping', 'de']]) {
        while (await tour.getAttribute('data-step') !== step) await tour.getByRole('button', { name: /^(Next|Weiter)$/, exact: true }).click()
        await tour.getByRole('button', { name: language === 'de' ? 'Deutsch' : 'English', exact: true }).click()
        await capture(page, `tutorial-${step}-${language}-${size}`, `Issue82 AFTER · ${step} ${language.toUpperCase()} · ${viewport.width}×${viewport.height}`)
      }
      await page.close()
    }
    for (const [version, url] of [['before', baselineUrl], ['after', webUrl]]) {
      const page = await setup(url, sizes[0][1], true)
      await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('santos_port')
      const details = page.getByRole('region', { name: 'Component status' })
      if (version === 'after') await details.getByRole('region', { name: 'Connection inference' }).waitFor()
      // Keep the local Unavailable heading and actual lane visible in both
      // versions; the current view separately explains the upstream inference.
      await details.locator('h3').evaluate(el => el.scrollIntoView({ block: 'start', behavior: 'instant' }))
      await capture(page, `lane-inferred-desktop-${version}`, `${version === 'before' ? 'd5f02ab BEFORE' : 'Issue82 AFTER'} · unrecorded ports, local measurements unavailable · 1275×605`)
      console.log(`Lane ${version} details: ${await details.innerText()}`)
      await page.close()
    }
  } finally { await browser.close() }
  assert.deepEqual(failures, [], 'Issue82 geometry acceptance failures (screenshots retained)')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
