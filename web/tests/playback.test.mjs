import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'

await build({ entryPoints: ['src/playback/buffer.ts', 'src/playback/frame.ts', 'src/data/httpPlaybackSource.ts'], outdir: '.test-build', bundle: true, platform: 'node', format: 'esm' })
const { createPlaybackBuffer } = await import('../.test-build/playback/buffer.js')
const { projectFrame } = await import('../.test-build/playback/frame.js')
const { parseFramePage } = await import('../.test-build/data/httpPlaybackSource.js')

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
  const baseline = { period: 0, agents: [{ entity_id: 'farm', agent_id: 0, values: { unit_price: 10 } }] }
  const frame = { period: 1, agents: [{ entity_id: 'farm', agent_id: 0, values: { unit_price: 15.123456789012345 } }] }
  const original = structuredClone(frame)
  const result = projectFrame({ edges: [] }, frame, baseline)
  assert.equal(result.markerIntensity.farm, (15.123456789012345 - 10) / 10)
  assert.deepEqual(frame, original)
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
