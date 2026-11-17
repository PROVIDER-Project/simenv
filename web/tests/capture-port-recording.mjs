// Issue84 review evidence: controlled API fixtures, NOT empirical simulation results.
// Run from web/: node tests/capture-port-recording.mjs
// Both Vite servers need VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001.
// Defaults: clean 113f3b8 at :15886, Issue84 worktree at :15884.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, readdir, readlink, realpath } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { mockPlayback, origin, scene, page as frames } from './playback-fixtures.mjs'

const root = fileURLToPath(new URL('../../', import.meta.url))
const output = new URL('../../docs/screenshots/issue84/', import.meta.url)
const versions = [
  { label: 'Before113f3b8', url: process.env.SIMENV_BASELINE_WEB_URL || 'http://127.0.0.1:15886',
    source: process.env.SIMENV_BASELINE_SOURCE || resolve(root, '../84-port-data-before'), recorded: false },
  { label: 'AfterIssue84', url: process.env.SIMENV_WEB_URL || 'http://127.0.0.1:15884', source: root, recorded: true },
]
const ports = [
  ['santos_port', 'Port of Santos', -23.96, -46.33],
  ['paranagua_port', 'Port of Paranaguá', -25.52, -48.51],
  ['rotterdam_port', 'Port of Rotterdam', 51.95, 4.14],
  ['hamburg_port', 'Port of Hamburg', 53.55, 9.99],
]
const edges = [
  ['farm-originator', 'brazil_farms', 'brazil_wholesaler', false],
  ['originator-santos', 'brazil_wholesaler', 'santos_port', false],
  ['originator-paranagua', 'brazil_wholesaler', 'paranagua_port', false],
  ['santos-rotterdam', 'santos_port', 'rotterdam_port', true],
  ['paranagua-hamburg', 'paranagua_port', 'hamburg_port', true],
].map(([id, source, target, isSeaCrossing]) => ({ id, source, target, isSeaCrossing }))

// Fail before capture if a URL points at another worktree or stale Vite source.
async function verifyServer(version) {
  const web = await realpath(resolve(version.source, 'web'))
  const port = new URL(version.url).port
  const processes = await Promise.all((await readdir('/proc')).filter(id => /^\d+$/.test(id)).map(async id => {
    try {
      const args = (await readFile(`/proc/${id}/cmdline`, 'utf8')).split('\0')
      return args.some(arg => arg.endsWith('/vite')) && args.includes(port)
        ? { pid: id, cwd: await readlink(`/proc/${id}/cwd`) } : null
    } catch { return null }
  }))
  assert.ok(processes.some(process => process?.cwd === web), `${version.url} must serve ${web}`)
  if (!version.recorded) {
    const git = args => execFileSync('git', args, { cwd: version.source, encoding: 'utf8' }).trim()
    assert.equal(git(['status', '--porcelain']), '', 'before worktree must be clean')
    assert.ok(git(['rev-parse', 'HEAD']).startsWith('113f3b8'))
  }
  const response = await fetch(`${version.url}/src/playback/status.ts`)
  assert.equal(response.status, 200)
  const served = await response.text()
  const map = JSON.parse(Buffer.from(served.split('sourceMappingURL=data:application/json;base64,')[1].trim(), 'base64'))
  assert.equal(map.sourcesContent[0], await readFile(resolve(web, 'src/playback/status.ts'), 'utf8'))
  assert.equal(served.includes('Effective transport capacity'), version.recorded)
  console.log(`Verified ${version.label}: ${version.url} -> ${web}`)
}

async function fixture(page, recorded) {
  await mockPlayback(page)
  await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
    const parts = new URL(route.request().url()).pathname.split('/')
    const result = scene(parts[2], Number(parts[4]))
    result.nodes.push({ id: 'brazil_wholesaler', label: 'Brazil grain originator', role: 'wholesaler',
      entityIds: ['brazil_wholesaler'], hasRecordedData: true,
      placements: [{ entityId: 'brazil_wholesaler', label: 'Brazil grain originator', lat: -23, lng: -47, illustrative: true }] })
    for (const [id, label, lat, lng] of ports) result.nodes.push({ id, label, role: 'land_transport',
      entityIds: [id], hasRecordedData: recorded && id === 'santos_port',
      placements: [{ entityId: id, label, lat, lng, illustrative: false }] })
    result.edges = edges
    return route.fulfill({ json: result })
  })
  await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
    const url = new URL(route.request().url()), parts = url.pathname.split('/')
    const scenario = Number(parts[4])
    const result = frames(parts[2], scenario, Number(url.searchParams.get('start')))
    for (const frame of result.frames) {
      frame.agents[0].values = { unit_price: 100, quantity_available: 100, active: 1 }
      frame.agents.push({ entity_id: 'brazil_wholesaler', agent_id: 7, role: 'wholesaler',
        values: { unit_price: 100, quantity_available: 100, storage_utilization: .2 } })
      // Historical backend did not record port rows; scene flag was false too.
      // New recording exposes capacity loss without inventing an output decline.
      if (recorded) {
        const loss = scenario === 1 && frame.period >= 50 && frame.period < 200
        frame.agents.push({ entity_id: 'santos_port', agent_id: 3, role: 'land_transport', values: {
          capacity: 500, effective_capacity: loss ? 100 : 500, quantity_available: 70,
          unit_price: 100, utilisation: loss ? .7 : .14, active: 1,
        } })
      }
    }
    return route.fulfill({ json: result })
  })
}

async function rendererState(page) {
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
    if (!props) return null
    return {
      markers: props.pointsData.map(point => ({ id: point.nodeId, lat: point.lat, lng: point.lng })).sort((a, b) => a.id.localeCompare(b.id)),
      states: props.pointsData.map(point => ({ id: point.nodeId, intensity: point.intensity, color: props.pointColor(point) })),
      routes: props.arcsData.filter(arc => arc.layer === 'core').map(arc => ({ id: arc.edgeId,
        endpoints: [arc.startLat, arc.startLng, arc.endLat, arc.endLng] })),
      ocean: props.arcsData.filter(arc => arc.edgeId === 'santos-rotterdam')
        .map(arc => ({ layer: arc.layer, intensity: arc.intensity, color: props.arcColor(arc) })),
      labels: props.htmlElementsData.filter(anchor => anchor.kind === 'edge').map(anchor => ({ id: anchor.id, text: anchor.text })),
    }
  })
}

async function seek(page, step) {
  await page.getByRole('slider', { name: 'Simulation step' }).fill(String(step))
  await page.waitForFunction(period => document.querySelector('[aria-label="Component status"]')?.dataset.period === String(period)
    && !document.querySelector('[aria-label="Reference comparison"] [role="status"]'), step)
}

async function capture(page, name, label, step) {
  // Reposition the existing scrollable inspector; no application UI is replaced.
  await page.locator('.sim-playback-sidebar').evaluate(sidebar => {
    sidebar.scrollTop += sidebar.querySelector('[aria-label="Component status"]').getBoundingClientRect().top - sidebar.getBoundingClientRect().top - 12
  })
  await page.evaluate(({ label, step }) => {
    document.querySelector('#issue84-capture-label')?.remove()
    const badge = document.createElement('div')
    badge.id = 'issue84-capture-label'
    badge.textContent = `CONTROLLED API FIXTURE — NOT EMPIRICAL SIMULATION RESULTS | ${label} | paused day ${step} | reference first/scenario 0`
    badge.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:100;pointer-events:none;background:#071321f5;color:white;font:12px/1.5 monospace;padding:3px 5px;text-align:center'
    document.body.append(badge)
  }, { label, step })
  await page.evaluate(() => document.fonts.ready)
  // Rendering settle only: globe route entrance transitions need to complete.
  await page.waitForTimeout(700)
  const path = fileURLToPath(new URL(`${name}.png`, output))
  await page.screenshot({ path, animations: 'disabled' })
  console.log(`Screenshot: ${path}`)
}

function assertRenderer(state, score, oceanScore) {
  assert.equal(state.markers.length, 6)
  assert.deepEqual(state.markers.map(point => point.id), ['brazil_farms', 'brazil_wholesaler', 'hamburg_port', 'paranagua_port', 'rotterdam_port', 'santos_port'])
  assert.equal(state.routes.length, 5)
  assert.deepEqual(state.routes.find(route => route.id === 'santos-rotterdam').endpoints, [-23.96, -46.33, 51.95, 4.14])
  assert.deepEqual(state.routes.find(route => route.id === 'paranagua-hamburg').endpoints, [-25.52, -48.51, 53.55, 9.99])
  assert.deepEqual(state.states.find(point => point.id === 'santos_port'), {
    id: 'santos_port', intensity: score, color: score === null ? '#8793A3' : score === 1 ? '#ff6050' : '#51e3a5',
  })
  assert.equal(state.states.find(point => point.id === 'brazil_wholesaler').intensity, 0)
  const rgb = oceanScore === 1 ? '255,96,80' : '81,227,165'
  assert.deepEqual(state.ocean, [['halo', .16], ['glow', .34], ['core', .92]].map(([layer, opacity]) => ({
    layer, intensity: oceanScore, color: `rgba(${rgb},${opacity.toFixed(2)})`,
  })))
}

for (const version of versions) await verifyServer(version)
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
let topology
try {
  for (const version of versions) {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 })
    page.setDefaultTimeout(20000)
    await fixture(page, version.recorded)
    await page.goto(version.url)
    const details = page.getByRole('region', { name: 'Component status' })
    await details.waitFor()
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'first')
    assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
    const pause = page.getByRole('button', { name: 'Pause', exact: true })
    if (await pause.count()) await pause.click()
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('first')
    await seek(page, 100)
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'first')
    assert.match(await details.locator('.sim-reference-note').innerText(), /first, scenario 0/)
    const hide = page.getByRole('button', { name: 'Hide indicators', exact: true })
    if (await hide.count()) await hide.click()
    // Builder values are unsubmitted edits, unrelated to the controlled history.
    const builderHide = page.locator('.sim-configurator').getByRole('button', { name: 'Hide', exact: true })
    if (await builderHide.count()) await builderHide.click()
    const inspector = page.getByRole('combobox', { name: 'Inspect component' })
    assert.equal(await inspector.locator('option').count(), 6)
    // Healthy originator independently checked before selecting Santos.
    await inspector.selectOption('brazil_wholesaler')
    await details.getByRole('heading', { name: 'Brazil grain originator · step 100' }).waitFor()
    assert.equal(await details.locator('.sim-status-heading strong').innerText(), 'Near reference / low pressure')
    await inspector.selectOption('santos_port')
    await details.getByRole('heading', { name: 'Port of Santos · step 100' }).waitFor()
    // Use the real GlobeMethods ref, as in globe-browser-utils.mjs. An identical
    // Atlantic camera keeps both ocean endpoints visible beside the inspector.
    await page.evaluate(async () => {
      const root = document.querySelector('#root')
      const fiber = root[Object.keys(root).find(key => key.startsWith('__reactContainer'))]
      function find(node) {
        if (!node) return null
        if (node.type?.name === 'GlobeView') return node
        return find(node.child) || find(node.sibling)
      }
      const component = find(fiber.stateNode?.current ?? fiber)
      let hook = component.memoizedState
      while (typeof hook?.memoizedState?.current?.scene !== 'function') hook = hook.next
      const globe = hook.memoizedState.current
      globe.controls().autoRotate = false
      globe.controls().enableDamping = false
      globe.pointOfView({ lat: 12, lng: -22, altitude: 2.6 }, 0)
      globe.controls().update()
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    })
    assert.equal(await details.locator('.sim-status-heading strong').innerText(), version.recorded ? 'Severe' : 'Unavailable')
    if (version.recorded) {
      assert.match(await details.locator('.sim-status-responsible').innerText(), /Effective transport capacity · agent 3 \(land_transport\)/)
      for (const [key, expression] of [
        ['effective_capacity', /Current: 100\s+Reference: 500\s+Change: -80.0%/],
        ['quantity_available', /Current: 70\s+Reference: 70\s+Change: \+0.0%/],
        ['unit_price', /Current: 100\s+Reference: 100\s+Change: \+0.0%/],
        ['utilisation', /Current: 70.0%\s+Reference: 14.0%/],
        ['active', /Current: 1\s+Reference: 1/],
        ['capacity', /Current: 500\s+Reference: 500/],
      ]) assert.match(await details.locator('.sim-metric').filter({ has: page.locator('code', { hasText: new RegExp(`^${key}$`) }) }).innerText(), expression)
    } else assert.match(await details.innerText(), /No measurements recorded for this component/)
    const state = await rendererState(page)
    assertRenderer(state, version.recorded ? 1 : null, version.recorded ? 1 : 0)
    const geometry = { markers: state.markers, routes: state.routes, labels: state.labels }
    if (topology) assert.deepEqual(geometry, topology, 'markers, coordinates, route endpoints and labels must match')
    else topology = geometry
    console.log(`${version.label} renderer: ${JSON.stringify(state)}`)
    await capture(page, `santos-capacity-loss-${version.label}`, `${version.label} · Santos 80% capacity loss · output unchanged · healthy wholesaler`, 100)
    if (version.recorded) {
      await seek(page, 250)
      assert.equal(await details.locator('.sim-status-heading strong').innerText(), 'Near reference / low pressure')
      assertRenderer(await rendererState(page), 0, 0)
      await capture(page, 'santos-recovered-AfterIssue84', 'AfterIssue84 · Santos recovered · effective capacity 500 · output still 70', 250)
    }
    await page.close()
  }
  console.log('PASS: source provenance, status/responsible metric, unchanged output/price, healthy wholesaler, marker/ocean colors, preserved topology and recovery')
} finally { await browser.close() }
