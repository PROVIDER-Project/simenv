import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { readFile } from 'node:fs/promises'

await build({ entryPoints: ['src/playback/buffer.ts', 'src/playback/frame.ts', 'src/playback/reference.ts', 'src/playback/referenceLoader.ts', 'src/data/httpPlaybackSource.ts', 'src/data/presentation.ts', 'src/data/gazetteer.ts'], outdir: '.test-build', bundle: true, platform: 'node', format: 'esm' })
const { createPlaybackBuffer } = await import('../.test-build/playback/buffer.js')
const { projectFrame } = await import('../.test-build/playback/frame.js')
const { parseFramePage } = await import('../.test-build/data/httpPlaybackSource.js')
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

test('shipped bundle displays Brazilian originator routes like Argentina and US without changing raw data', async () => {
  const bundle = JSON.parse(await readFile(new URL('../public/bundle.json', import.meta.url), 'utf8'))
  const raw = { run_id: 'demo', scenario_id: 1, nodes: bundle.nodes, edges: bundle.edges }
  const original = structuredClone(raw)
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value) } }
  freeze(raw)
  const display = presentScene(raw)
  assert.equal(raw.nodes.length, 16)
  assert.equal(raw.edges.length, 16)
  assert.equal(display.nodes.length, 14)
  assert.equal(display.edges.length, 14)
  assert.deepEqual(raw, original)
  assert.deepEqual(display.nodes.filter(node => !original.nodes.some(old => old.id === node.id)), [])
  assert.deepEqual(original.nodes.filter(node => !display.nodes.some(retained => retained.id === node.id)).map(node => node.id).sort(), ['paranagua_port', 'santos_port'])
  assert.deepEqual(display.edges.filter(edge => edge.isSeaCrossing).map(edge => [edge.source, edge.target]).sort(), [
    ['argentina_wholesaler', 'rotterdam_port'], ['brazil_wholesaler', 'hamburg_port'], ['brazil_wholesaler', 'rotterdam_port'], ['us_wholesaler', 'rotterdam_port'],
  ])
  const placed = resolveScene(display.nodes, display.edges)
  assert.equal(placed.markers.length, 14)
  assert.equal(placed.edges.length, 14)
  assert.equal(display.nodes.find(node => node.id === 'rotterdam_port').hasRecordedData, false)
  assert.deepEqual(presentScene(display), display, 'display projection is idempotent')
  assert.equal(referenceCompatibility(raw, { ...original, scenario_id: 0 }), null, 'reference checks still use original topology')
})

test('display collapse forms all originator/destination routes and prefers an existing direct sea edge', () => {
  const raw = displayFixture()
  raw.nodes.push(component('b', 'wholesaler'), component('y', 'land_transport', false), component('parallel', 'port', false))
  raw.edges.push(connection('b', 'port'), seaConnection('port', 'y'), connection('a', 'parallel'), seaConnection('parallel', 'x'), seaConnection('a', 'x', 'existing-sea'), connection('a', 'x'))
  const display = presentScene(raw)
  assert.deepEqual(display.nodes.map(node => node.id).sort(), ['a', 'b', 'x', 'y'])
  assert.deepEqual(display.edges.map(edge => [edge.source, edge.target, edge.isSeaCrossing]).sort(), [
    ['a', 'x', false], ['a', 'x', true], ['a', 'y', true], ['b', 'x', true], ['b', 'y', true],
  ])
  assert.equal(display.edges.find(edge => edge.source === 'a' && edge.target === 'x' && edge.isSeaCrossing).id, 'existing-sea')
  assert.equal(display.edges.find(edge => edge.source === 'a' && edge.target === 'x' && !edge.isSeaCrossing).id, 'a->x')
  assert.ok(display.edges.every(edge => display.nodes.some(node => node.id === edge.source) && display.nodes.some(node => node.id === edge.target)))
  assert.deepEqual(presentScene(display), display)
})

test('generated display route IDs avoid original IDs and remain deterministic across input ordering', () => {
  const raw = displayFixture()
  raw.nodes.push(component('b', 'wholesaler'), component('y', 'land_transport', false))
  raw.edges.push(connection('b', 'port'), seaConnection('port', 'y'), { ...connection('b', 'y'), id: 'display:["a","x",true]' }, { ...connection('a', 'y'), id: 'display:["a","x",true]:1' })
  const display = presentScene(raw)
  assert.equal(display.edges.find(edge => edge.source === 'a' && edge.target === 'x').id, 'display:["a","x",true]:2')
  assert.equal(new Set(display.edges.map(edge => edge.id)).size, display.edges.length)
  const reversed = presentScene({ ...raw, nodes: [...raw.nodes].reverse(), edges: [...raw.edges].reverse() })
  const routes = value => value.edges.map(edge => [edge.source, edge.target, edge.isSeaCrossing, edge.id]).sort()
  assert.deepEqual(routes(reversed), routes(display))
})

test('unsupported branches preserve the entire waypoint and its original connections', () => {
  const unsupported = [
    scene => { scene.nodes[1].hasRecordedData = true },
    scene => { delete scene.nodes[1].hasRecordedData },
    scene => { scene.nodes[1].role = 'processor' },
    scene => { scene.nodes[0].role = 'producer' },
    scene => { scene.nodes[0].hasRecordedData = false },
    scene => { scene.edges[0].isSeaCrossing = true },
    scene => { scene.edges[1].isSeaCrossing = false },
    scene => { scene.edges.push(connection('missing', 'port')) },
    scene => { scene.edges.push(seaConnection('port', 'missing')) },
    scene => { scene.edges.push(seaConnection('port', 'a')) },
    scene => { scene.edges.push(connection('port', 'port')) },
    scene => { scene.edges.shift() },
    scene => { scene.edges.pop() },
    scene => { scene.nodes.push(component('branch')); scene.edges.push(connection('port', 'branch')) },
    scene => { scene.nodes.push(component('branch')); scene.edges.push(connection('branch', 'port')) },
  ]
  for (const change of unsupported) {
    const raw = displayFixture()
    change(raw)
    assert.deepEqual(presentScene(raw), raw, change.toString())
  }
  const raw = displayFixture()
  raw.nodes.push(component('second', 'port', false), component('end'))
  raw.edges.push(seaConnection('x', 'second'), seaConnection('second', 'end'))
  const display = presentScene(raw)
  assert.deepEqual(display.nodes.map(node => node.id), ['a', 'x', 'second', 'end'], 'only original candidates are collapsed; sea-fed transports stay visible')
  assert.ok(display.edges.some(edge => edge.source === 'x' && edge.target === 'second'))
  assert.deepEqual(presentScene(display), display)
})

test('display sea edges use only the immediate originator assessment and retain its metric details', () => {
  const raw = displayFixture()
  const display = presentScene(raw)
  const reference = [agent({ ...normal, storage_utilization: .2 }, 7, 'wholesaler', 'a')]
  const edge = display.edges.find(edge => edge.source === 'a' && edge.target === 'x')
  for (const [values, expected] of [[{ ...normal, storage_utilization: .2 }, 0], [{ ...normal, quantity_available: 50, storage_utilization: .2 }, 1], [{}, null]]) {
    const current = [agent(values, 7, 'wholesaler', 'a')]
    const result = projection(current, reference, display)
    assert.equal(result.edgeIntensity[edge.id], expected)
    assert.equal(result.edges[edge.id], result.nodes.a)
    assert.equal(result.markerIntensity.x, null)
    if (expected === 1) {
      assert.equal(result.nodes.a.winner.metric.key, 'quantity_available')
      assert.equal(result.nodes.a.winner.agent.agent_id, 7)
    }
  }
  const uncollapsed = projection([agent({ ...normal, quantity_available: 50, storage_utilization: .2 }, 7, 'wholesaler', 'a')], reference, raw)
  assert.equal(uncollapsed.edges['port->x'].score, null, 'ordinary unrecorded sources do not recursively inherit')
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
