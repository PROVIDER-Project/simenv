import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'

await build({ entryPoints: ['src/playback/buffer.ts', 'src/playback/frame.ts', 'src/playback/reference.ts', 'src/data/httpPlaybackSource.ts'], outdir: '.test-build', bundle: true, platform: 'node', format: 'esm' })
const { createPlaybackBuffer } = await import('../.test-build/playback/buffer.js')
const { projectFrame } = await import('../.test-build/playback/frame.js')
const { parseFramePage } = await import('../.test-build/data/httpPlaybackSource.js')
const { referenceCompatibility } = await import('../.test-build/playback/reference.js')

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
  assert.equal((await buffer.load(299)).period, 299)
  await buffer.load(100); await buffer.load(300); await buffer.load(400)
  await buffer.load(0)
  assert.deepEqual(requests, [0, 200, 100, 300, 400, 0])
  let resolve
  const slow = createPlaybackBuffer({ getFrames: () => new Promise(r => { resolve = r }) }, 'old', 0)
  const pending = slow.load(0)
  slow.dispose()
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
