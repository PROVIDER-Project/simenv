import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { readFile } from 'node:fs/promises'

await build({ entryPoints: ['src/playback/buffer.ts', 'src/playback/frame.ts', 'src/playback/reference.ts', 'src/playback/referenceLoader.ts', 'src/data/httpPlaybackSource.ts', 'src/data/staticPlaybackSource.ts', 'src/data/presentation.ts', 'src/data/gazetteer.ts'], outdir: '.test-build', bundle: true, platform: 'node', format: 'esm' })
const { createPlaybackBuffer } = await import('../.test-build/playback/buffer.js')
const { projectFrame } = await import('../.test-build/playback/frame.js')
const { parseFramePage, createHttpPlaybackSource } = await import('../.test-build/data/httpPlaybackSource.js')
const { createStaticPlaybackSource } = await import('../.test-build/data/staticPlaybackSource.js')
const { referenceCompatibility } = await import('../.test-build/playback/reference.js')
const { createReferenceLoader } = await import('../.test-build/playback/referenceLoader.js')
const { presentScene, entityDisplayName } = await import('../.test-build/data/presentation.js')
const { resolveScene } = await import('../.test-build/data/gazetteer.js')

test('buffer deduplicates, aligns seeks, evicts and rejects stale loads', async () => {
  const requests = []
  const source = { async getFrames(run, scenario, start, limit) {
    requests.push(start)
    return { run_id: run, scenario_id: scenario, start, next_start: start + limit,
      frames: Array.from({ length: limit }, (_, i) => ({ period: start + i, agents: [] })) }
  } }
  const buffer = createPlaybackBuffer(source, 'run', 1)
  await Promise.all([buffer.load(15), buffer.load(18)])
  assert.deepEqual(requests, [0])
  assert.equal(buffer.peek(15).period, 15)
  assert.equal(buffer.peek(200), null)
  assert.deepEqual(requests, [0], 'peek never initiates a request')
  assert.equal((await buffer.load(299)).period, 299)
  await buffer.load(100); await buffer.load(300); await buffer.load(400)
  await buffer.load(0)
  assert.deepEqual(requests, [0, 200, 100, 300, 400, 0])
  let resolve
  const slow = createPlaybackBuffer({ getFrames: () => new Promise(r => { resolve = r }) }, 'old', 0)
  const pending = slow.load(0)
  slow.dispose()
  assert.equal(slow.peek(0), null)
  resolve({ run_id: 'old', scenario_id: 0, start: 0, next_start: null, frames: [{ period: 0, agents: [] }] })
  await assert.rejects(pending)
})

test('projection never changes measurements and ignores page-dependent ranges', () => {
  const baseline = { period: 0, agents: [{ entity_id: 'farm', agent_id: 0, role: 'producer', values: { unit_price: 10, quantity_available: 100, active: 1 } }] }
  const frame = { period: 1, agents: [{ entity_id: 'farm', agent_id: 0, role: 'producer', values: { unit_price: 15.123456789012345, quantity_available: 100, active: 1 } }] }
  const original = structuredClone(frame)
  const result = projectFrame({ edges: [] }, frame, baseline)
  assert.equal(result.markerIntensity.farm, 1)
  assert.deepEqual(frame, original)
})

const agent = (values, agent_id = 0, role = 'producer', entity_id = 'farm') => ({ entity_id, agent_id, role, values })
const projection = (current, reference, scene = { edges: [] }) => projectFrame(scene,
  { period: 10, agents: current }, reference === null ? null : { period: 0, agents: reference })
const normal = { unit_price: 100, quantity_available: 100, active: 1 }

test('all metrics drive status, with fixed thresholds and recovery', () => {
  for (const [price, expected] of [[100, 0], [105, 0], [120, .5], [150, 1], [200, 1], [90, 0]]) {
    assert.equal(projection([agent({ ...normal, unit_price: price })], [agent(normal)]).nodes.farm.score, expected)
  }
  const result = projection([agent({ ...normal, unit_price: 90, quantity_available: 50 })], [agent(normal)])
  assert.equal(result.nodes.farm.score, 1)
  assert.equal(result.nodes.farm.winner.metric.key, 'quantity_available')
  assert.equal(projection([agent(normal)], [agent(normal)]).nodes.farm.score, 0)
})

test('zero quotes/references and missing coverage cannot become healthy', () => {
  assert.equal(projection([agent({ ...normal, unit_price: 0, quantity_available: 0 })], [agent(normal)]).nodes.farm.score, 1)
  assert.equal(projection([agent(normal)], [agent({ ...normal, quantity_available: 0 })]).nodes.farm.score, null)
  assert.equal(projection([agent(normal)], null).nodes.farm.score, null)
  assert.equal(projection([agent(normal)], null).nodes.farm.coverage, 'partial')
  const inactive = projection([agent({ ...normal, active: 0 })], null).nodes.farm
  assert.equal(inactive.score, 1)
  assert.equal(inactive.coverage, 'partial')
  assert.equal(projection([agent({ ...normal, unit_price: 0 })], [agent(normal)]).nodes.farm.score, null)
})

test('disappearing environment keeps all four unavailable indicators and reference values', () => {
  const env = agent({ soy_price: 10, feed_price: 20, total_soy_supply: 100, transport_utilisation: .5 }, 0, 'environment', 'environment')
  const result = projection([], [env])
  assert.equal(result.indicators.length, 4)
  assert.deepEqual(result.indicators.map(item => item.score), [null, null, null, null])
  assert.deepEqual(result.indicators.map(item => item.reference), [10, 20, 100, .5])
})

test('reference compatibility ignores geography but rejects topology and period mismatches', () => {
  const scene = { scenario_id: 1, min_period: 0, max_period: 299,
    nodes: [{ id: 'farm', label: 'Farm', role: 'producer', entityIds: ['a', 'b'], hasRecordedData: true, placements: [] }], edges: [] }
  const base = { ...scene, scenario_id: 0 }
  assert.equal(referenceCompatibility(scene, { ...base, nodes: [{ ...scene.nodes[0], label: 'Other', entityIds: ['b', 'a'] }] }), null)
  assert.match(referenceCompatibility(scene, { ...base, max_period: 100 }), /period/)
  assert.match(referenceCompatibility(scene, { ...base, nodes: [] }), /structure/)
  assert.match(referenceCompatibility(scene, scene), /scenario 0/)
})

test('capacity is absolute, processing inputs optional and unused input diagnostic only', () => {
  for (const [storage_utilization, expected] of [[.79, 0], [.8, .5], [.95, 1], [1.1, 1]]) {
    const state = agent({ ...normal, storage_utilization }, 0, 'wholesaler')
    assert.equal(projection([state], [state]).nodes.farm.score, expected)
  }
  const base = agent(normal, 0, 'processor')
  assert.equal(projection([base], [base]).nodes.farm.coverage, 'complete')
  assert.equal(projection([agent({ ...normal, input_processed: 20 }, 0, 'processor')], [agent({ ...normal, input_processed: 100 }, 0, 'processor')]).nodes.farm.score, 1)
  assert.equal(projection([agent({ ...normal, unused_input: 100 }, 0, 'processor')], [base]).nodes.farm.score, 0)
  assert.equal(projection([agent({ ...normal, input_received: 100 }, 0, 'processor')], [base]).nodes.farm.score, null)
})

test('worst individual agent wins deterministically, with exact reference identities', () => {
  const first = agent({ ...normal, quantity_available: 50 }, 1)
  const second = agent({ ...normal, quantity_available: 50 }, 2)
  const refs = [agent(normal, 1), agent(normal, 2)]
  const a = projection([second, first], refs).nodes.farm
  const b = projection([first, second], refs).nodes.farm
  assert.deepEqual(a, b)
  assert.equal(a.winner.agent.agent_id, 1)
  assert.equal(a.agents.length, 2)
  assert.equal(projection([agent(normal)], [agent(normal, 0, 'consumer')]).nodes.farm.score, null)
  assert.equal(projection([agent(normal)], [agent(normal, 0, 'producer', 'other')]).nodes.farm.score, null)
})

test('connections inherit source only; day-zero baseline and raw measurements stay independent', () => {
  const scene = { edges: [{ id: 'link', source: 'unknown', target: 'farm' }] }
  const current = Object.freeze([Object.freeze(agent(Object.freeze({ ...normal, quantity_available: 50 })))])
  const reference = Object.freeze([Object.freeze(agent(Object.freeze(normal)))])
  const result = projection(current, reference, scene)
  assert.equal(result.edges.link.score, null)
  assert.equal(result.nodes.farm.score, 1)
  assert.equal(projection(current, current).nodes.farm.score, 0)
  assert.equal(current[0].values.quantity_available, 50)
  assert.equal(reference[0].values.quantity_available, 100)
})

const component = (id, role = 'producer', hasRecordedData = true) => ({ id, label: id, role, hasRecordedData, entityIds: [id], placements: [] })
const connection = (source, target) => ({ id: `${source}->${target}`, source, target, isSeaCrossing: false })

const seaConnection = (source, target, id = `${source}->${target}`) => ({ ...connection(source, target), id, isSeaCrossing: true })
const displayFixture = () => ({ nodes: [component('a', 'wholesaler'), component('port', 'land_transport', false), component('x', 'land_transport', false)],
  edges: [connection('a', 'port'), seaConnection('port', 'x')] })

test('shipped presentation preserves all ports, edges, labels and marker geometry', async () => {
  const bundle = JSON.parse(await readFile(new URL('../public/bundle.json', import.meta.url), 'utf8'))
  const raw = { run_id: 'demo', scenario_id: 1, nodes: bundle.nodes, edges: bundle.edges }
  const original = structuredClone(raw)
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value) } }
  freeze(raw)
  const display = presentScene(raw)
  assert.equal(raw.nodes.length, 16)
  assert.equal(raw.edges.length, 16)
  assert.equal(display.nodes.length, 16)
  assert.equal(display.edges.length, 16)
  assert.deepEqual(raw, original)
  assert.deepEqual(display.nodes.map(node => node.id), raw.nodes.map(node => node.id))
  assert.deepEqual(display.edges, raw.edges)
  const placed = resolveScene(display.nodes, display.edges)
  assert.equal(placed.markers.length, 16)
  assert.equal(placed.edges.length, 16)
  for (const id of ['santos_port', 'paranagua_port', 'rotterdam_port', 'hamburg_port']) assert.equal(display.nodes.find(node => node.id === id).hasRecordedData, false)
  const ocean = placed.edges.find(edge => edge.id === 'santos_port->rotterdam_port')
  assert.equal(ocean.label, 'Port of Santos → Port of Rotterdam')
  assert.deepEqual([ocean.startLat, ocean.startLng, ocean.endLat, ocean.endLng], [-24, -46.3, 51.95, 4.14])
  assert.deepEqual(presentScene(display), display)
  assert.equal(referenceCompatibility(raw, { ...display, scenario_id: 0 }), null)
})

const transportNormal = { effective_capacity: 1000, quantity_available: 70, unit_price: 100, utilisation: .7, active: 1, capacity: 1000 }
const transport = (values = transportNormal, role = 'land_transport', id = 'port', agentId = 3) => agent(values, agentId, role, id)

test('transport capacity loss colors the local port and outgoing arc independently of its wholesaler', () => {
  const scene = displayFixture()
  scene.nodes[1].hasRecordedData = true
  const origin = agent({ ...normal, storage_utilization: .2 }, 7, 'wholesaler', 'a')
  const reference = [origin, transport()]
  for (const [effective_capacity, score] of [[200, 1], [0, 1], [800, .5], [1000, 0]]) {
    const current = [origin, transport({ ...transportNormal, effective_capacity })]
    const original = structuredClone({ scene, current, reference })
    const result = projection(current, reference, scene)
    assert.equal(result.markerIntensity.port, score)
    assert.equal(result.edgeIntensity['port->x'], score)
    assert.equal(result.edges['port->x'], result.nodes.port)
    assert.equal(result.markerIntensity.a, 0)
    assert.equal(result.markerIntensity.x, null, 'source evidence does not fabricate downstream harm')
    assert.equal(result.nodes.port.coverage, 'complete')
    assert.equal(result.nodes.port.winner.metric.key, 'effective_capacity')
    assert.equal(result.nodes.port.winner.agent.agent_id, 3)
    assert.deepEqual({ scene, current, reference }, original)
  }
  const result = projection([agent({ ...origin.values, quantity_available: 50 }, 7, 'wholesaler', 'a'), transport()], reference, scene)
  assert.equal(result.markerIntensity.a, 1)
  assert.equal(result.edgeIntensity['a->port'], 1)
  assert.equal(result.markerIntensity.port, 0)
  assert.equal(result.edgeIntensity['port->x'], 0)
})

test('both transport roles score output, price, utilization and participation with nominal capacity diagnostic only', () => {
  for (const role of ['land_transport', 'sea_transport']) {
    for (const [changes, score, key] of [
      [{ quantity_available: 35 }, 1, 'quantity_available'],
      [{ unit_price: 120 }, .5, 'unit_price'],
      [{ utilisation: .79 }, 0, 'effective_capacity'],
      [{ utilisation: .8 }, .5, 'utilisation'],
      [{ utilisation: .95 }, 1, 'utilisation'],
      [{ active: 0 }, 1, 'active'],
      [{ capacity: 0 }, 0, 'effective_capacity'],
    ]) {
      const result = projection([transport({ ...transportNormal, ...changes }, role)], [transport(transportNormal, role)]).nodes.port
      assert.equal(result.score, score, `${role}: ${JSON.stringify(changes)}`)
      assert.equal(result.winner.metric.key, key)
      const metrics = result.agents[0].metrics
      assert.equal(metrics.find(metric => metric.key === 'quantity_available').label, 'Transport output available')
      assert.equal(metrics.find(metric => metric.key === 'unit_price').label, 'Transport output asking price')
      assert.equal(metrics.find(metric => metric.key === 'capacity').score, null)
    }
  }
})

test('transport missing and zero comparisons preserve adverse partial evidence without inventing healthy status', () => {
  for (const [values, reference, score, coverage] of [
    [{ ...transportNormal, effective_capacity: 0 }, transportNormal, 1, 'complete'],
    [transportNormal, { ...transportNormal, effective_capacity: 0 }, null, 'partial'],
    [{ ...transportNormal, effective_capacity: 0 }, { ...transportNormal, effective_capacity: 0 }, null, 'partial'],
    [{ ...transportNormal, unit_price: 0 }, transportNormal, null, 'partial'],
    [{ effective_capacity: 200 }, transportNormal, 1, 'partial'],
    [{ quantity_available: 70 }, transportNormal, null, 'partial'],
    [transportNormal, null, null, 'partial'],
    [{ utilisation: .95 }, null, 1, 'partial'],
    [{ active: 0 }, null, 1, 'partial'],
    [{}, transportNormal, null, 'unavailable'],
  ]) {
    const result = projection([transport(values)], reference ? [transport(reference)] : null).nodes.port
    assert.equal(result.score, score, JSON.stringify({ values, reference }))
    assert.equal(result.coverage, coverage)
  }
  for (const reference of [transport(transportNormal, 'sea_transport'), transport(transportNormal, 'land_transport', 'port', 4)]) {
    assert.equal(projection([transport()], [reference]).nodes.port.score, null, 'reference identity must match exactly')
  }
})

test('historical ports and missing local agents never borrow wholesaler, target, hidden sea or network status', () => {
  const scene = displayFixture()
  const origin = agent({ ...normal, quantity_available: 50, storage_utilization: .2 }, 7, 'wholesaler', 'a')
  const others = [origin, transport({ ...transportNormal, effective_capacity: 0 }, 'sea_transport', 'sea_transport_port__x'),
    transport({ ...transportNormal, utilisation: 1 }, 'land_transport', 'x'),
    agent({ transport_utilisation: 1 }, 0, 'environment', 'environment')]
  for (const recorded of [false, true]) {
    scene.nodes[1].hasRecordedData = recorded
    const current = recorded ? others : [...others, transport()]
    const result = projection(current, [agent({ ...normal, storage_utilization: .2 }, 7, 'wholesaler', 'a'), ...others.slice(1), transport()], scene)
    assert.equal(result.nodes.a.score, 1)
    assert.equal(result.markerIntensity.port, null)
    assert.equal(result.edgeIntensity['port->x'], null)
    assert.equal(result.edges['port->x'], result.nodes.port)
    if (!recorded) assert.deepEqual(result.nodes.port.agents, [], 'historical metadata is not bypassed')
  }
  const currentScene = { ...scene, scenario_id: 1, min_period: 0, max_period: 10 }
  const historical = structuredClone({ ...currentScene, scenario_id: 0 })
  historical.nodes[1].hasRecordedData = false
  assert.match(referenceCompatibility(currentScene, historical), /structure/)
})

test('HTTP and static consumers retain transport measurements through local-source projection', async t => {
  const localScene = { ...displayFixture(), run_id: 'r', scenario_id: 1, min_period: 0, max_period: 1, pdl: 'fixture.pdl.yaml', honesty_note: 'Fixture' }
  localScene.nodes[1].hasRecordedData = true
  const reference = { period: 0, agents: [transport()] }
  const current = { period: 1, agents: [transport({ ...transportNormal, effective_capacity: 200, unit_price: 100.123456789012345 })] }
  const page = { run_id: 'r', scenario_id: 1, start: 0, next_start: null, frames: [reference, current] }
  const bundle = { nodes: localScene.nodes, edges: localScene.edges,
    meta: { pdl: 'fixture.pdl.yaml', scenario: 'fixture', ticks: 2, generatedAt: 'recorded', honestyNote: 'Fixture' },
    ticks: page.frames.map(frame => ({ period: frame.period, nodeId: 'port', values: frame.agents[0].values })),
    env: page.frames.map(frame => ({ period: frame.period, soyPrice: 10, feedPrice: 20, shockScale: 1, droughtSeverity: 0, totalSoySupply: 100, transportUtilisation: .7, currentStep: frame.period })) }
  const original = structuredClone({ localScene, page, bundle })
  t.mock.method(globalThis, 'fetch', async url => new Response(JSON.stringify(url === '/bundle.json' ? bundle : url.endsWith('/scene') ? localScene : page)))
  for (const [source, runId] of [[createHttpPlaybackSource('http://fixture'), 'r'], [createStaticPlaybackSource(), 'demo']]) {
    const parsedScene = await source.getScene(runId, 1)
    const parsedPage = await source.getFrames(runId, 1, 0, 2)
    const result = projectFrame(parsedScene, parsedPage.frames[1], parsedPage.frames[0])
    assert.equal(result.markerIntensity.port, 1)
    assert.equal(result.edgeIntensity['port->x'], 1)
    assert.equal(result.nodes.port.agents[0].metrics.find(metric => metric.key === 'unit_price').current, 100.123456789012345)
    assert.equal(result.nodes.port.winner.metric.key, 'effective_capacity')
    assert.deepEqual(parsedScene.edges, localScene.edges)
  }
  assert.deepEqual({ localScene, page, bundle }, original)
})

test('wire validation preserves precision and rejects nonfinite and duplicate agent states', () => {
  const page = { run_id: 'r', scenario_id: 0, start: 0, next_start: null,
    frames: [{ period: 0, agents: [{ entity_id: 'farm', agent_id: 1, role: 'producer', values: { unit_price: 1.123456789012345 } }] }] }
  assert.deepEqual(parseFramePage(page), page)
  const invalid = structuredClone(page)
  invalid.frames[0].agents[0].values.unit_price = NaN
  assert.throws(() => parseFramePage(invalid))
  page.frames[0].agents.push(page.frames[0].agents[0])
  assert.throws(() => parseFramePage(page))
})

test('reference failures settle without retrying each step and a new generation can retry', async () => {
  const calls = []
  let fail = true
  const source = { async getScene() { return scene }, async getFrames(run_id, scenario_id, start) {
    calls.push(start)
    if (start === 200 && fail) throw new Error('Reference offline')
    return { run_id, scenario_id, start, next_start: null, frames: Array.from({ length: 100 }, (_, i) => ({ period: start + i, agents: [agent(normal)] })) }
  } }
  const scene = { run_id: 'r', scenario_id: 0, min_period: 0, max_period: 299, nodes: [], edges: [] }
  const baseline = { period: 0, agents: [agent(normal)] }
  const loader = createReferenceLoader(source, scene, baseline, 'r')
  assert.equal(loader.peek(baseline), null)
  assert.equal((await loader.load(baseline)).frame.period, 0)
  assert.equal(loader.peek({ ...baseline, period: 50 }).frame.period, 50)
  assert.equal((await loader.load({ ...baseline, period: 250 })).error, 'Reference offline')
  assert.equal((await loader.load({ ...baseline, period: 251 })).error, 'Reference offline')
  assert.deepEqual(calls, [0, 200])
  loader.dispose()
  assert.equal(loader.peek(baseline), null)
  await assert.rejects(loader.load(baseline), /Reference changed/)
  fail = false
  const retry = createReferenceLoader(source, scene, baseline, 'r')
  assert.equal((await retry.load({ ...baseline, period: 250 })).frame.period, 250)
  retry.dispose()
})

test('a superseded reference failure cannot poison the active seek', async () => {
  let reject
  const scene = { run_id: 'r', scenario_id: 0, min_period: 0, max_period: 299, nodes: [], edges: [] }
  const baseline = { period: 0, agents: [agent(normal)] }
  const loader = createReferenceLoader({ async getScene() { return scene }, async getFrames(run_id, scenario_id, start) {
    if (start === 200) return new Promise((_, failure) => { reject = failure })
    return { run_id, scenario_id, start, next_start: null, frames: [baseline] }
  } }, scene, baseline, 'r')
  await loader.load(baseline)
  const controller = new AbortController()
  const old = loader.load({ ...baseline, period: 250 }, controller.signal)
  await new Promise(resolve => setImmediate(resolve))
  controller.abort()
  assert.equal((await loader.load(baseline)).error, null)
  reject(new Error('Late old-page failure'))
  await assert.rejects(old, /Reference changed/)
  assert.equal(loader.peek(baseline).frame.period, 0)
  loader.dispose()
})

test('English presentation covers legacy identities, placements and pooled labels without mutating recordings', () => {
  const node = (id, label, entityIds, placements = []) => ({ id, label, entityIds, placements, role: 'processor', hasRecordedData: true })
  const raw = { run_id: 'recorded', scenario_id: 1, min_period: 0, max_period: 299, pdl: 'original.yaml', honesty_note: 'Recorded metadata', nodes: [
    node('processors', 'EU Ölmühlen', ['eu_oil_mills'], [{ entityId: 'eu_oil_mills', label: 'EU Ölmühlen', lat: 52, lng: 4.5, illustrative: true }]),
    node('eu_farmers', 'Geflügelbetriebe / Schweinebetriebe / Milchwirtschaft', ['poultry_farms', 'pig_farms', 'dairy_farms']),
    node('brazil_farms', 'Workshop North Farm', ['brazil_farms']),
    node('custom', 'Workshop processor', ['custom'], [{ entityId: 'custom', label: 'Custom site', lat: 1, lng: 2, illustrative: false }]),
  ], edges: [{ id: 'flow', source: 'processors', target: 'eu_farmers', isSeaCrossing: false }] }
  const original = structuredClone(raw)
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value) } }
  freeze(raw)
  const display = presentScene(raw)
  assert.deepEqual(raw, original)
  assert.equal(display.nodes[0].label, 'EU oil mills')
  assert.equal(display.nodes[0].placements[0].label, 'EU oil mills')
  assert.equal(display.nodes[1].label, 'EU poultry farms / EU pig farms / EU dairy farms')
  assert.deepEqual(display.nodes[1].entityIds.map(id => entityDisplayName(display.nodes[1], id)), ['EU poultry farms', 'EU pig farms', 'EU dairy farms'])
  assert.equal(display.nodes[2].label, 'Workshop North Farm')
  assert.equal(resolveScene(display.nodes, display.edges).markers.find(marker => marker.nodeId === 'brazil_farms').label, 'Workshop North Farm')
  assert.equal(display.nodes[3].label, 'Workshop processor')
  assert.equal(display.nodes[3].placements[0].label, 'Custom site')
  assert.equal(resolveScene(display.nodes, display.edges).edges[0].label, 'EU oil mills → EU poultry farms / EU pig farms / EU dairy farms')
  assert.deepEqual(display.nodes.map(n => [n.id, n.entityIds, n.role, n.hasRecordedData]), original.nodes.map(n => [n.id, n.entityIds, n.role, n.hasRecordedData]))
  assert.equal(referenceCompatibility({ ...raw, scenario_id: 1 }, { ...display, scenario_id: 0 }), null)
})
