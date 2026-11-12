import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'
import { origin, webUrl, run, scene, page as frames } from './playback-fixtures.mjs'

async function workshop(page, { referenceFailure = false } = {}) {
  await dismissInitialTutorial(page)
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
  const show = page.getByRole('button', { name: 'Show indicators', exact: true })
  if (await show.isVisible()) await show.click()
}

// Inspect the real mounted renderer inputs, like globe-layout's ref inspection;
// no application test hooks or replacement globe are needed.
async function oceanRendererState(page) {
  return page.evaluate(() => {
    const root = document.querySelector('#root')
    const fiber = root[Object.keys(root).find(key => key.startsWith('__reactContainer'))]
    function find(node) {
      if (!node) return null
      const props = node.memoizedProps
      if (Array.isArray(props?.arcsData) && Array.isArray(props?.pointsData) && typeof props.arcColor === 'function') return props
      return find(node.child) || find(node.sibling)
    }
    const props = find(fiber.stateNode?.current ?? fiber)
    if (!props) throw new Error('Mounted globe renderer props not found')
    const ocean = props.arcsData.filter(datum => ['ocean', 'santos_port->rotterdam_port'].includes(datum.edgeId))
    const port = props.pointsData.find(datum => datum.nodeId === 'rotterdam_port')
    return { ocean: ocean.map(datum => ({ layer: datum.layer, intensity: datum.intensity, color: props.arcColor(datum) })),
      port: { intensity: port.intensity, color: props.pointColor(port) },
      exportPorts: props.pointsData.filter(datum => ['santos_port', 'paranagua_port'].includes(datum.nodeId)).length,
      exportPortStates: props.pointsData.filter(datum => ['santos_port', 'paranagua_port'].includes(datum.nodeId))
        .map(datum => ({ id: datum.nodeId, intensity: datum.intensity, color: props.pointColor(datum) })),
      oceanLabel: props.htmlElementsData.find(anchor => anchor.id === `edge:${ocean[0]?.edgeId}`)?.text,
      markerCount: props.pointsData.length, edgeCount: new Set(props.arcsData.map(datum => datum.edgeId)).size,
      endpoints: ocean.length ? [ocean[0].startLat, ocean[0].startLng, ocean[0].endLat, ocean[0].endLng] : [],
      period: document.querySelector('[aria-label="Component status"]').dataset.period,
      indicatorPeriod: document.querySelector('[aria-label="Network indicators"]').dataset.period }
  })
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
    assert.equal(await page.getByRole('region', { name: 'Component status' }).count(), 0, 'automatic mode waits rather than showing a start-relative comparison')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('shock')
    const details = page.getByRole('region', { name: 'Component status' })
    assert.match(await details.innerText(), /Unavailable/)
    assert.match(await details.innerText(), /active/)
    await details.locator('.sim-metric').filter({ hasText: 'unit_price' }).getByText('Change: Unavailable', { exact: true }).waitFor()
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

test('View results retries the exact submission beyond page one and labels later edits', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await workshop(page)
    const target = 'submitted-workshop'
    let available = false
    await page.route('**/api/simulations', route => route.fulfill({ status: 202, json: {
      id: target, status: 'completed', label: 'Workshop', error: null,
      progress: { scenario_id: 1, step: 365, scenario_total_steps: 365, completed_steps: 365, total_steps: 365, percent_complete: 100 },
    } }))
    await page.route(`${origin}/runs?*`, route => {
      const offset = Number(new URL(route.request().url()).searchParams.get('offset'))
      return route.fulfill({ json: { items: offset ? available ? [run(target)] : [] : Array.from({ length: 50 }, (_, i) => run(`newer-${i}`)), total: 51 } })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
    await page.getByText('Results saved by the API.', { exact: false }).waitFor()
    await page.getByRole('textbox', { name: 'Scenario name' }).fill('Next workshop edits')
    await page.getByText('Unsubmitted edits for the next run.', { exact: false }).waitFor()
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'not in the configured playback database' }).waitFor()
    assert.notEqual(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), target)
    available = true
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.waitForFunction(id => document.querySelector('[aria-label="Recorded run"]')?.value === id, target)
    assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
    assert.match(await page.locator('.sim-frame-meta').innerText(), /submitted-workshop/)
  } finally { await browser.close() }
})

test('scenario-start reference remains pinned after first-page eviction and backward seeking', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.route(`${origin}/runs/shock/scenarios/1/scene`, route => route.fulfill({ json: { ...scene('shock', 1), max_period: 599 } }))
    await page.route(`${origin}/runs/shock/scenarios/1/frames*`, route => {
      const start = Number(new URL(route.request().url()).searchParams.get('start'))
      const result = frames('shock', 1, start % 300)
      result.start = start; result.next_start = start + 100 < 600 ? start + 100 : null
      for (const frame of result.frames) {
        frame.period += Math.floor(start / 300) * 300
        frame.agents[0].values = { unit_price: 100, quantity_available: frame.period < 100 ? 100 : 50, active: 1 }
      }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    const slider = page.getByRole('slider', { name: 'Simulation step' })
    for (const step of [150, 250, 350, 450, 550, 150]) {
      await slider.fill(String(step))
      await page.waitForFunction(period => document.querySelector('[aria-label="Component status"]')?.dataset.period === String(period), step)
      assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /Supply availability down 50%/)
    }
    await slider.fill('0')
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability up 0%', { exact: true }).waitFor()
  } finally { await browser.close() }
})

test('delayed reference page holds the last matched display pair until the seek is ready', async () => {
  const browser = await chromium.launch({ headless: true })
  let release
  try {
    const page = await browser.newPage()
    const state = await workshop(page)
    await page.goto(webUrl); await pause(page)
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    const previous = await page.getByRole('slider', { name: 'Simulation step' }).inputValue()
    state.delay = new Promise(resolve => { release = resolve })
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.getByRole('region', { name: 'Reference comparison' }).getByText(/Waiting for matching measurements/).waitFor()
    const details = page.getByRole('region', { name: 'Component status' })
    assert.equal(await details.getAttribute('data-period'), previous)
    assert.equal(await page.getByRole('group', { name: 'Network indicators' }).getAttribute('data-period'), previous)
    assert.match(await details.innerText(), /Supply availability down 50%/)
    assert.match(await page.locator('[data-metric="soy_price"]').innerText(), /Soy price up 50%/)
    assert.match(await page.locator('[data-metric="transport_utilisation"]').innerText(), /Severe/)
    release(); state.delay = null
    await details.getByText('Supply availability up 0%', { exact: true }).waitFor()
  } finally { release?.(); await browser.close() }
})

test('unplaced components remain keyboard-inspectable with unavailable measured status', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      result.nodes.push({ id: 'unplaced', label: 'Unplaced port', role: 'port', entityIds: ['unplaced'], placements: [], hasRecordedData: false })
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    const selector = page.getByRole('combobox', { name: 'Inspect component' })
    await selector.focus(); await page.keyboard.press('End'); await page.keyboard.press('Enter')
    assert.equal(await selector.inputValue(), 'unplaced')
    const details = page.getByRole('region', { name: 'Component status' })
    assert.match(await details.innerText(), /No measurements recorded for this component/)
    assert.match(await details.innerText(), /Unavailable/)
  } finally { await browser.close() }
})

test('temporary ocean colors follow the originator while port geometry, labels and inspection stay unchanged', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await workshop(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      const ports = [
        ['santos_port', 'Workshop export port'], ['paranagua_port', 'Workshop secondary port'],
        ['rotterdam_port', 'Workshop import port'], ['hamburg_port', 'Workshop secondary import'],
      ].map(([id, label]) => ({ id, label, role: 'land_transport', entityIds: [id], placements: [], hasRecordedData: false }))
      // Ports remain in the original scene order, including initial selection.
      result.nodes = [...ports.slice(0, 2), ...result.nodes, {
        id: 'brazil_wholesaler', label: 'Brazil grain originator', role: 'wholesaler', entityIds: ['brazil_wholesaler'], hasRecordedData: true,
        placements: [{ entityId: 'brazil_wholesaler', label: 'Brazil grain originator', lat: -23, lng: -47, illustrative: true }],
      }, ...ports.slice(2)]
      result.edges = [
        { id: 'farm-originator', source: 'brazil_farms', target: 'brazil_wholesaler', isSeaCrossing: false },
        { id: 'originator-port', source: 'brazil_wholesaler', target: 'santos_port', isSeaCrossing: false },
        { id: 'originator-secondary', source: 'brazil_wholesaler', target: 'paranagua_port', isSeaCrossing: false },
        { id: 'ocean', source: 'santos_port', target: 'rotterdam_port', isSeaCrossing: true },
        { id: 'secondary-ocean', source: 'paranagua_port', target: 'hamburg_port', isSeaCrossing: true },
      ]
      return route.fulfill({ json: result })
    })
    await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
      const url = new URL(route.request().url()), parts = url.pathname.split('/')
      const scenario = Number(parts[4]), start = Number(url.searchParams.get('start'))
      const result = frames(parts[2], scenario, start)
      for (const frame of result.frames) {
        frame.agents[0].values = scenario === 1 && frame.period >= 280 ? {}
          : { unit_price: 100, quantity_available: scenario === 1 && frame.period < 200 ? 50 : 100, active: 1 }
        frame.agents[1].values.transport_utilisation = 1
        frame.agents.push({ entity_id: 'brazil_wholesaler', agent_id: 7, role: 'wholesaler', values: { ...frame.agents[0].values, storage_utilization: .2 } })
      }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    const selector = page.getByRole('combobox', { name: 'Inspect component' })
    assert.equal(await selector.inputValue(), 'santos_port', 'the original first port remains selectable')
    assert.equal(await selector.locator('option[value="santos_port"], option[value="paranagua_port"]').count(), 2)
    const details = page.getByRole('region', { name: 'Component status' })
    assert.equal(await details.locator('.sim-status-heading strong').innerText(), 'Unavailable')
    assert.match(await details.innerText(), /No measurements recorded for this component/)
    assert.match(await details.innerText(), /across 0 recorded agents/)
    await selector.selectOption('brazil_wholesaler')
    await details.getByText('Severe', { exact: true }).waitFor()
    assert.match(await details.locator('.sim-status-responsible').innerText(), /Supply availability · agent 7 \(wholesaler\)/)
    assert.match(await details.locator('.sim-metric').filter({ hasText: 'quantity_available' }).innerText(), /Current: 50.*Reference: 100/s)
    assert.equal(await details.getByRole('region', { name: 'Connection inference' }).count(), 0)
    for (const [period, score, label, rgb] of [
      [0, 1, 'Severe', '255,96,80'],
      [250, 0, 'Near reference / low pressure', '81,227,165'],
      [290, null, 'Unavailable', '135,147,163'],
      [250, 0, 'Near reference / low pressure', '81,227,165'],
    ]) {
      await page.getByRole('slider', { name: 'Simulation step' }).fill(String(period))
      await page.waitForFunction(step => document.querySelector('[aria-label="Component status"]')?.dataset.period === String(step), period)
      assert.equal(await details.locator('.sim-status-heading strong').innerText(), label)
      const rendered = await oceanRendererState(page)
      assert.equal(rendered.period, String(period))
      assert.equal(rendered.indicatorPeriod, String(period))
      assert.deepEqual(rendered.port, { intensity: null, color: '#8793A3' })
      assert.equal(rendered.exportPorts, 2)
      assert.deepEqual(rendered.exportPortStates, [
        { id: 'santos_port', intensity: null, color: '#8793A3' },
        { id: 'paranagua_port', intensity: null, color: '#8793A3' },
      ])
      assert.deepEqual(rendered.endpoints, [-24, -46.3, 51.95, 4.14], 'ocean geometry still begins at Santos, not the originator')
      assert.equal(rendered.oceanLabel, 'Workshop export port → Workshop import port')
      assert.deepEqual(rendered.ocean, [
        { layer: 'halo', intensity: score, color: `rgba(${rgb},0.16)` },
        { layer: 'glow', intensity: score, color: `rgba(${rgb},0.34)` },
        { layer: 'core', intensity: score, color: `rgba(${rgb},0.92)` },
      ], 'the temporary color override follows the one-hop originator without changing the ocean arc')
    }
    for (const port of ['santos_port', 'paranagua_port', 'rotterdam_port', 'hamburg_port']) {
      await selector.selectOption(port)
      assert.equal(await details.locator('.sim-status-heading strong').innerText(), 'Unavailable')
      assert.match(await details.innerText(), /No measurements recorded for this component/)
    }
  } finally { await browser.close() }
})

test('a disappearing agent retains surviving adverse evidence and unaffected network comparisons', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
      const url = new URL(route.request().url())
      const parts = url.pathname.split('/')
      const scenario = Number(parts[4]), start = Number(url.searchParams.get('start'))
      const result = frames(parts[2], scenario, start)
      for (const frame of result.frames) {
        const current = scenario === 1
        frame.agents[0].values = { unit_price: 100, quantity_available: current ? 50 : 100, active: 1 }
        frame.agents[1].values.soy_price = current ? 150 : 100
        if (!current || frame.period < 200) frame.agents.push({ ...frame.agents[0], agent_id: 1 })
      }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    const details = page.getByRole('region', { name: 'Component status' })
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"]')?.dataset.period === '250')
    await details.getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.match(await details.innerText(), /Severe/)
    assert.match(await details.innerText(), /Incomplete evidence/)
    assert.match(await page.locator('[data-metric="soy_price"]').innerText(), /Soy price up 50%/)
  } finally { await browser.close() }
})

test('missing measurements have unavailable text without NaN or healthy color attribution', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.route(`${origin}/runs/shock/scenarios/1/frames*`, route => {
      const start = Number(new URL(route.request().url()).searchParams.get('start'))
      const result = frames('shock', 1, start)
      for (const frame of result.frames) { frame.agents[0].values = { active: 1 }; frame.agents[1].values = {} }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    const details = page.getByRole('region', { name: 'Component status' })
    await details.getByText(/Insufficient evidence/).waitFor()
    assert.doesNotMatch(await page.getByRole('group', { name: 'Playback', exact: true }).innerText(), /NaN/)
    assert.doesNotMatch(await details.innerText(), /Responsible metric: Market participation/)
  } finally { await browser.close() }
})

test('an external baseline with incompatible initial identities stays unavailable', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    await workshop(page)
    await page.route(`${origin}/runs/baseline/scenarios/0/frames*`, route => {
      const start = Number(new URL(route.request().url()).searchParams.get('start'))
      const result = frames('baseline', 0, start)
      for (const frame of result.frames) frame.agents[0].agent_id = 99
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl); await pause(page)
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('baseline')
    await page.getByRole('region', { name: 'Reference comparison' }).getByText(/identities are incompatible/).waitFor()
    assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /Unavailable/)
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'baseline')
  } finally { await browser.close() }
})

test('static demo keeps its start-mode limitation and explains submitted-result configuration', { skip: !process.env.SIMENV_STATIC_WEB_URL }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await page.route('**/api/simulations', route => route.fulfill({ status: 202, json: {
      id: 'external-job', status: 'completed', label: 'Workshop', error: null,
      progress: { scenario_id: 1, step: 365, scenario_total_steps: 365, completed_steps: 365, total_steps: 365, percent_complete: 100 },
    } }))
    await dismissInitialTutorial(page)
    await page.goto(process.env.SIMENV_STATIC_WEB_URL); await pause(page)
    const components = page.getByRole('combobox', { name: 'Inspect component' })
    assert.equal(await components.locator('option').count(), 16)
    assert.equal(await components.locator('option[value="santos_port"], option[value="paranagua_port"]').count(), 2)
    const displayed = await oceanRendererState(page)
    assert.equal(displayed.markerCount, 16)
    assert.equal(displayed.edgeCount, 16)
    assert.equal(displayed.exportPorts, 2)
    assert.deepEqual(displayed.endpoints, [-24, -46.3, 51.95, 4.14])
    assert.equal(displayed.oceanLabel, 'Port of Santos → Port of Rotterdam')
    assert.deepEqual(displayed.port, { intensity: null, color: '#8793A3' })
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'start')
    assert.match(await page.getByRole('region', { name: 'Reference comparison' }).innerText(), /cannot reveal disturbances already present/)
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'requires recorded playback' }).waitFor()
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'demo')
  } finally { await browser.close() }
})
