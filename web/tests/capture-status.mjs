// Review artifacts, deliberately labeled controlled data rather than real-run evidence.
// Run against Vite configured for the playback-fixtures origin (see docs/playback.md).
import { chromium } from 'playwright'
import { origin, webUrl, run, scene, page as framePage } from './playback-fixtures.mjs'
import { aimAtMarker } from './globe-browser-utils.mjs'

const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  await page.route(`${origin}/**`, route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/runs') return route.fulfill({ json: { items: [run('workshop-review')], total: 1 } })
    const [, , id, , scenario, kind] = url.pathname.split('/')
    if (kind === 'scene') {
      const result = scene(id, Number(scenario))
      result.nodes.push({ id: 'port', label: 'Port (unrecorded)', role: 'port', entityIds: ['port'], hasRecordedData: false,
        placements: [{ entityId: 'port', label: 'Port (unrecorded)', lat: -24, lng: -46, illustrative: false }] })
      result.edges.push({ id: 'farm-port', source: 'brazil_farms', target: 'port', isSeaCrossing: false })
      return route.fulfill({ json: result })
    }
    const start = Number(url.searchParams.get('start'))
    const result = framePage(id, Number(scenario), start)
    for (const frame of result.frames) {
      const disturbed = Number(scenario) === 1 && frame.period >= 50 && frame.period < 200
      const unknown = Number(scenario) === 1 && frame.period >= 280
      frame.agents[0].values = unknown ? {} : { unit_price: disturbed ? 135 : 100, quantity_available: disturbed ? 50 : 100, active: 1 }
      frame.agents[1].values = unknown ? {} : { soy_price: disturbed ? 150 : 100, feed_price: disturbed ? 28 : 20,
        total_soy_supply: disturbed ? 50 : 100, transport_utilisation: disturbed ? .96 : .6, shock_scale: disturbed ? .5 : 0 }
    }
    return route.fulfill({ json: result })
  })
  await page.goto(webUrl)
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('button', { name: 'Hide', exact: true }).click()
  for (const [label, step] of [['healthy', 0], ['disturbed', 100], ['recovered', 250], ['unavailable', 290]]) {
    await page.getByRole('slider', { name: 'Simulation step' }).fill(String(step))
    await page.waitForFunction(period => document.querySelector('[aria-label="Component status"]')?.dataset.period === String(period), step)
    await page.waitForFunction(() => !document.querySelector('[aria-label="Reference comparison"] [role="status"]'))
    await page.screenshot({ path: `../docs/status-${label}.png` })
    if (label === 'disturbed') {
      await page.locator('.sim-playback-sidebar').evaluate(panel => { panel.scrollTop = panel.scrollHeight })
      await page.screenshot({ path: '../docs/status-details.png' })
      await page.locator('.sim-playback-sidebar').evaluate(panel => { panel.scrollTop = 0 })
    }
  }
  await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
  await page.screenshot({ path: '../docs/status-sidebar-collapsed.png' })
  await page.getByRole('button', { name: 'Show disturbance impact' }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../docs/status-mobile.png', fullPage: true })
  if (process.env.SIMENV_STATIC_WEB_URL) {
    const demo = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
    await demo.goto(process.env.SIMENV_STATIC_WEB_URL)
    await demo.getByRole('button', { name: 'Pause', exact: true }).click()
    await demo.getByRole('slider', { name: 'Simulation step' }).fill('150')
    await demo.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '150')
    await demo.getByRole('button', { name: 'Hide', exact: true }).click()
    await demo.screenshot({ path: '../docs/status-static-network.png' })
    await demo.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await demo.screenshot({ path: '../docs/status-static-network-collapsed.png' })
    await demo.getByRole('button', { name: 'Show disturbance impact' }).click()
    // The reader chooses this scroll position before selecting another label.
    await demo.locator('.sim-playback-sidebar').evaluate(sidebar => {
      sidebar.scrollTop += sidebar.querySelector('[aria-label="Component status"]').getBoundingClientRect().top - sidebar.getBoundingClientRect().top - 12
    })
    await aimAtMarker(demo, 'argentina_farms')
    await demo.screenshot({ path: '../docs/status-label-selection-before.png' })
    await demo.getByRole('button', { name: 'Select Argentina soy farms', exact: true }).click()
    await demo.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'argentina_farms')
    await demo.getByRole('region', { name: 'Component status' }).getByRole('heading', { name: /Argentina soy farms/ }).waitFor()
    await demo.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await demo.screenshot({ path: '../docs/status-map-selection.png' })
  }
} finally { await browser.close() }
