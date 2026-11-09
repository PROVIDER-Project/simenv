import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'
import { origin, webUrl, run, scene, page as frames } from './playback-fixtures.mjs'

async function fixture(page, { blockedScenario } = {}) {
  await dismissInitialTutorial(page)
  let release
  const blocked = new Promise(resolve => { release = resolve })
  let requested
  const requestedPage = new Promise(resolve => { requested = resolve })
  await page.route(`${origin}/**`, async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/runs') return route.fulfill({ json: { items: [run('first'), run('second')], total: 2 } })
    const [, , id, , scenario, kind] = url.pathname.split('/')
    if (kind === 'scene') {
      const result = scene(id, Number(scenario))
      result.nodes.push({ id: 'port', label: 'Port', role: 'port', entityIds: ['port'], hasRecordedData: false,
        placements: [{ entityId: 'port', label: 'Port', lat: -24, lng: -46, illustrative: false }] })
      result.edges.push({ id: 'link', source: 'brazil_farms', target: 'port', isSeaCrossing: false })
      return route.fulfill({ json: result })
    }
    const start = Number(url.searchParams.get('start'))
    if (Number(scenario) === blockedScenario && start === 100) { requested(); await blocked }
    const result = frames(id, Number(scenario), start)
    for (const frame of result.frames) {
      const reference = Number(scenario) === 0
      frame.agents[0].values = { unit_price: reference ? 100 : frame.period % 2 ? 130.123 : 100,
        quantity_available: reference ? 100 : 50, active: 1 }
      Object.assign(frame.agents[1].values, { soy_price: reference ? 100 : frame.period % 2 ? 999.123 : 100,
        feed_price: reference ? 20 : frame.period % 2 ? 2000 : 20, total_soy_supply: reference ? 100 : 50 })
    }
    return route.fulfill({ json: result }).catch(() => {})
  })
  return { release, requestedPage }
}

async function pause(page) {
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
}

async function observe(page) {
  await page.evaluate(() => {
    window.stabilitySamples = []
    const sample = () => {
      const root = document.querySelector('#root')
      const fiber = root[Object.keys(root).find(key => key.startsWith('__reactContainer'))]
      function props(node) {
        if (!node) return null
        if (node.type?.name === 'GlobeView') return node.memoizedProps
        return props(node.child) || props(node.sibling)
      }
      const globe = props(fiber.stateNode?.current ?? fiber)
      const bounds = element => {
        const r = element.getBoundingClientRect()
        return [r.x, r.y, r.width, r.height]
      }
      const timeline = document.querySelector('.sim-timeline')
      if (!timeline || !globe) return
      window.stabilitySamples.push({ period: Number(document.querySelector('[aria-label="Simulation step"]').value),
        details: Number(document.querySelector('[aria-label="Component status"]').dataset.period),
        indicators: Number(document.querySelector('[aria-label="Network indicators"]').dataset.period),
        marker: globe.markerIntensity.brazil_farms, edge: globe.edgeIntensity.link,
        loading: !!document.querySelector('[aria-label="Reference comparison"] [role="status"]') || !!document.querySelector('.sim-playback-message'),
        layout: [timeline, ...document.querySelectorAll('[data-metric]'), document.querySelector('.sim-component-status h3'),
          document.querySelector('.sim-metric'), document.querySelector('.sim-metric-values')].map(bounds) })
    }
    new MutationObserver(sample).observe(document.querySelector('#root'), { subtree: true, attributes: true, childList: true, characterData: true })
    const tick = () => { sample(); window.stabilityAnimation = requestAnimationFrame(tick) }
    tick()
  })
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
test(`cached continuous playback has stable colors and layout at ${viewport.width}px`, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport })
    await fixture(page); await page.goto(webUrl); await pause(page)
    await page.getByRole('slider', { name: 'Simulation step' }).fill('8')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '8')
    await observe(page)
    await page.getByRole('button', { name: 'Play', exact: true }).click()
    await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) >= 20)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const samples = await page.evaluate(() => window.stabilitySamples.filter(sample => sample.period >= 9 && sample.period <= 20))
    assert.ok(samples.length > 10)
    assert.equal(samples.filter(sample => sample.marker === null || sample.edge === null).length, 0, 'known cached evidence must not flash gray between commits')
    assert.equal(samples.filter(sample => sample.loading).length, 0, 'cache hits must not insert loading messages')
    assert.ok(samples.every(sample => sample.period === sample.details && sample.period === sample.indicators))
    const first = samples[0].layout
    for (const sample of samples) sample.layout.forEach((box, i) => box.forEach((value, j) =>
      assert.ok(Math.abs(value - first[i][j]) <= 1, `readout ${i} shifted on dimension ${j}`)))
  } finally { await browser.close() }
})
}

for (const [name, scenario] of [['reference', 0], ['current', 1]]) {
  test(`continuous playback holds a coherent pair at a delayed ${name} page boundary`, async () => {
    const browser = await chromium.launch({ headless: true })
    let state
    try {
      const page = await browser.newPage()
      state = await fixture(page, { blockedScenario: scenario })
      await page.goto(webUrl); await pause(page)
      await page.getByRole('slider', { name: 'Simulation step' }).fill('98')
      await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '98')
      await observe(page)
      await page.getByRole('button', { name: 'Play', exact: true }).click()
      await state.requestedPage
      await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) >= 99)
      // More than eight playback intervals: a pending page must keep the pair at 99.
      await page.waitForTimeout(500)
      assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '99')
      const held = await page.evaluate(() => window.stabilitySamples.filter(sample => sample.period >= 99))
      assert.ok(held.every(sample => sample.marker === 1 && sample.edge === 1 && sample.details === 99 && sample.indicators === 99))
      const first = held[0].layout
      for (const sample of held) sample.layout.forEach((box, i) => box.forEach((value, j) =>
        assert.ok(Math.abs(value - first[i][j]) <= 1, `pending ${name} page shifted readout ${i} on dimension ${j}`)))
      state.release()
      await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) >= 102)
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
      const resumed = await page.evaluate(() => window.stabilitySamples.filter(sample => sample.period >= 100))
      assert.ok(resumed.every(sample => sample.marker === 1 && sample.edge === 1 && sample.details === sample.period && sample.indicators === sample.period))
    } finally { state?.release(); await browser.close() }
  })
}
