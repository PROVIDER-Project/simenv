import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'

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

test('Brazil ocean connections infer nearest upstream evidence without inventing port measurements', () => {
  const scene = { nodes: [component('brazil_wholesaler', 'wholesaler'), ...['santos_port', 'paranagua_port', 'rotterdam_port', 'hamburg_port'].map(id => component(id, 'land_transport', false))],
    edges: [connection('brazil_wholesaler', 'santos_port'), connection('brazil_wholesaler', 'paranagua_port'), connection('santos_port', 'rotterdam_port'), connection('paranagua_port', 'hamburg_port')] }
  const reference = [agent({ ...normal, storage_utilization: .2 }, 7, 'wholesaler', 'brazil_wholesaler')]
  const current = [agent({ ...normal, quantity_available: 50, storage_utilization: .2 }, 7, 'wholesaler', 'brazil_wholesaler')]
  const original = structuredClone({ scene, current, reference })
  const result = projection(current, reference, scene)
  for (const id of ['santos_port', 'paranagua_port']) {
    const evidence = result.edges[`${id}->${id === 'santos_port' ? 'rotterdam_port' : 'hamburg_port'}`]
    assert.equal(evidence.score, 1)
    assert.equal(evidence.kind, 'inferred')
    assert.deepEqual(evidence.sources.map(source => [source.nodeId, source.path]), [['brazil_wholesaler', ['brazil_wholesaler', id]]])
    assert.equal(evidence.winner.nodeId, 'brazil_wholesaler')
    assert.equal(evidence.winner.metric.key, 'quantity_available')
    assert.equal(evidence.winner.agent.agent_id, 7)
    assert.equal(result.nodes[id].score, null)
    assert.deepEqual(result.nodes[id].agents, [])
    assert.equal(result.markerIntensity[id], null)
  }
  assert.equal(result.edgeIntensity['santos_port->rotterdam_port'], 1)
  assert.deepEqual({ scene, current, reference }, original)
  assert.equal(projection(reference, reference, scene).edges['santos_port->rotterdam_port'].score, 0, 'recovery follows the measured upstream component')
})

test('only explicitly unrecorded transport roles are transparent, including legacy ports', () => {
  for (const [role, recorded, expected] of [['land_transport', false, 1], ['sea_transport', false, 1], ['port', false, 1], ['processor', false, null], ['land_transport', true, null], ['unknown', false, null]]) {
    const scene = { nodes: [component('farm'), component('middle', role, recorded), component('target')], edges: [connection('farm', 'middle'), connection('middle', 'target')] }
    assert.equal(projection([agent({ ...normal, quantity_available: 50 })], [agent(normal)], scene).edges['middle->target'].score, expected, `${role}, recorded=${recorded}`)
  }
})

test('inference crosses multiple transports but stops at missing nearest recorded evidence', () => {
  const scene = { nodes: [component('farm'), component('trader', 'feed_trader'), component('port', 'land_transport', false), component('sea', 'sea_transport', false), component('target')],
    edges: [connection('farm', 'trader'), connection('trader', 'port'), connection('port', 'sea'), connection('sea', 'target')] }
  const farm = agent({ ...normal, quantity_available: 50 })
  const missing = projection([farm], [agent(normal)], scene).edges['sea->target']
  assert.equal(missing.score, null)
  assert.equal(missing.kind, 'inferred')
  assert.deepEqual(missing.sources.map(source => [source.nodeId, source.path]), [['trader', ['trader', 'port', 'sea']]])
  const trader = agent(normal, 0, 'feed_trader', 'trader')
  const known = projection([farm, trader], [agent(normal), trader], scene).edges['sea->target']
  assert.equal(known.score, 0, 'a healthy nearer recorded component blocks a severe ancestor')
  const noReference = projection([farm, trader], [agent(normal)], scene).edges['sea->target']
  assert.equal(noReference.score, null, 'missing reference is not bypassed')
})

test('branch inference retains adverse partial evidence and deterministic metric provenance', () => {
  const scene = { nodes: [component('a'), component('b'), component('port', 'port', false), component('target')],
    edges: [connection('b', 'port'), connection('a', 'port'), connection('port', 'target')] }
  const state = (id, quantity = 50) => agent({ ...normal, quantity_available: quantity }, 0, 'producer', id)
  const reference = [state('a', 100), state('b', 100)]
  const severe = projection([state('b'), state('a')], reference, scene).edges['port->target']
  assert.equal(severe.score, 1)
  assert.equal(severe.coverage, 'complete')
  assert.equal(severe.winner.nodeId, 'a')
  assert.deepEqual(severe.sources.map(source => source.nodeId), ['a', 'b'])
  const reordered = { nodes: [...scene.nodes].reverse(), edges: [...scene.edges].reverse() }
  assert.deepEqual(projection([state('a'), state('b')], reference, reordered).edges['port->target'], severe)
  const partial = projection([state('a')], reference, scene).edges['port->target']
  assert.equal(partial.score, 1)
  assert.equal(partial.coverage, 'partial')
  const insufficient = projection([state('a', 100)], reference, scene).edges['port->target']
  assert.equal(insufficient.score, null)
  assert.equal(insufficient.coverage, 'partial')
})

test('unresolved transport branches cannot become healthy or borrow target or network status', () => {
  const farm = agent(normal)
  const target = agent({ ...normal, quantity_available: 50 }, 0, 'producer', 'target')
  const environment = agent({ transport_utilisation: 1 }, 0, 'environment', 'environment')
  for (const extra of [[], [connection('missing', 'port')], [connection('loop', 'port'), connection('port', 'loop')]]) {
    const scene = { nodes: [component('farm'), component('port', 'port', false), component('loop', 'sea_transport', false), component('target')], edges: [...extra, connection('port', 'target')] }
    const result = projection([farm, target, environment], [farm, agent(normal, 0, 'producer', 'target')], scene)
    const unknown = result.edges['port->target']
    assert.equal(unknown.score, null)
    assert.ok(unknown.unresolved.length)
    assert.equal(unknown.winner, null)
    assert.equal(result.nodes.target.score, 1)
    scene.edges.push(connection('farm', 'port'))
    const mixed = projection([farm, target], [farm, target], scene).edges['port->target']
    assert.equal(mixed.score, extra.length ? null : 0)
    assert.equal(mixed.coverage, extra.length ? 'partial' : 'complete')
    const adverse = projection([agent({ ...normal, quantity_available: 50 }), target], [farm, target], scene).edges['port->target']
    // With no broken branch, adding the farm resolves the previously empty port.
    assert.equal(adverse.score, 1)
    assert.equal(adverse.coverage, extra.length ? 'partial' : 'complete')
  }
})

test('inferred edges exclude their own recorded destination without sharing another target result', () => {
  const scene = { nodes: [component('farm'), component('port', 'land_transport', false), component('other')],
    edges: [connection('farm', 'port'), connection('port', 'other'), connection('port', 'farm'), connection('farm', 'farm')] }
  for (const quantity of [100, 50]) {
    const result = projection([agent({ ...normal, quantity_available: quantity })], [agent(normal)], scene)
    const cycle = result.edges['port->farm']
    assert.equal(cycle.score, null, 'a recorded target cannot become its own inferred source')
    assert.deepEqual(cycle.sources, [])
    assert.equal(cycle.winner, null)
    assert.deepEqual(cycle.unresolved.map(item => item.path), [['farm', 'port']])
    assert.match(cycle.unresolved[0].reason, /destination/i)
    assert.equal(result.edges['port->other'].score, quantity === 100 ? 0 : 1, 'another target retains valid upstream evidence')
    assert.equal(result.edges['farm->port'].score, quantity === 100 ? 0 : 1, 'direct recorded sources are unchanged')
    assert.equal(result.edges['farm->farm'].score, quantity === 100 ? 0 : 1, 'destination exclusion applies only to inference')
    assert.equal(result.nodes.port.score, null)
  }
})

test('destination exclusion through multiple transports retains only independent branch evidence', () => {
  const scene = { nodes: [component('farm'), component('b'), component('port', 'port', false), component('sea', 'sea_transport', false)],
    edges: [connection('farm', 'port'), connection('b', 'port'), connection('port', 'sea'), connection('sea', 'farm')] }
  const state = (id, quantity) => agent({ ...normal, quantity_available: quantity }, 0, 'producer', id)
  const reference = [state('farm', 100), state('b', 100)]
  const healthy = projection(reference, reference, scene).edges['sea->farm']
  assert.equal(healthy.score, null)
  assert.equal(healthy.coverage, 'partial')
  assert.deepEqual(healthy.sources.map(source => source.nodeId), ['b'])
  assert.deepEqual(healthy.unresolved.map(item => item.path), [['farm', 'port', 'sea']])
  const adverse = projection([state('farm', 100), state('b', 50)], reference, scene).edges['sea->farm']
  assert.equal(adverse.score, 1)
  assert.equal(adverse.coverage, 'partial')
  assert.equal(adverse.winner.nodeId, 'b')
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
