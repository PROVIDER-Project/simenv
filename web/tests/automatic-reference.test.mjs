import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'

await build({ entryPoints: ['src/playback/automaticReference.ts', 'src/configurator/simulationApi.ts'],
  outdir: '.test-build/automatic', bundle: true, splitting: true, platform: 'node', format: 'esm' })
const { createAutomaticReferenceCoordinator, referenceRecipe, hasEmptyEvents } = await import('../.test-build/automatic/playback/automaticReference.js')
const { SimulationApiError } = await import('../.test-build/automatic/configurator/simulationApi.js')

function fixture() {
  const inputs = { pdl: { scenario: { name: 'Workshop' }, entities: [{ id: 'farm' }], events: [{ id: 'shock' }],
    cascades: [{ id: 'soy', timeline: [{ event: 'shock', at: 0 }] }] }, roster: { economics: { capacity: 10 } }, cascade: 'soy',
    parameters: { period_num: 300, farm_size_seed: 42 }, current_parameters: { period_num: 300, farm_size_seed: 42 }, evidence: 'execution-hashes' }
  const run = id => ({ id, playable: true, scenario_ids: [1], label: id, period_num: 300 })
  const job = (id, status = 'completed') => ({ id, status, error: null, label: id,
    progress: { percent_complete: status === 'completed' ? 100 : 0 } })
  const data = new Map([['shock', inputs], ['other', { ...inputs, pdl: { ...inputs.pdl, scenario: { name: 'Other workshop' } } }]])
  const state = { inputs, data, run, job, runs: [run('shock')], jobs: [job('shock')], submissions: [], reads: [],
    source: null, api: null }
  state.source = { mode: 'recorded', async listRuns(limit, offset) { return { items: state.runs.slice(offset, offset + limit), total: state.runs.length } },
    async getScene(run_id, scenario_id) { return { run_id, scenario_id, min_period: 0, max_period: 299, nodes: [], edges: [] } },
    async getFrames(run_id, scenario_id, start) { return { run_id, scenario_id, start, frames: [{ period: start,
      agents: [{ entity_id: 'farm', agent_id: 0, role: 'producer', values: { quantity_available: 100 } }] }] } } }
  state.api = { async inputs(id) { state.reads.push(id); if (!data.has(id)) throw new SimulationApiError('Missing inputs', 404, 'GET'); return structuredClone(data.get(id)) },
    async list(limit, offset) { return { items: state.jobs.slice(offset, offset + limit), total: state.jobs.length } },
    async submit(submission) {
      state.submissions.push(submission)
      const id = `reference-${state.submissions.length}`
      data.set(id, { ...inputs, pdl: JSON.parse(submission.pdl), roster: submission.roster === null ? null : JSON.parse(submission.roster), cascade: submission.cascade, evidence: 'preserved' })
      state.jobs.push(job(id, 'queued')); return job(id, 'queued')
    }, async inspect(id) {
      data.get(id).evidence = 'execution-hashes'
      if (!state.runs.some(run => run.id === id)) state.runs.push(run(id))
      return job(id)
    } }
  return state
}

function settled(entry) {
  if (['ready', 'error'].includes(entry.getSnapshot().phase)) return Promise.resolve(entry.getSnapshot())
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { unsubscribe(); reject(new Error('Coordinator did not settle')) }, 3000)
    const unsubscribe = entry.subscribe(() => {
      const state = entry.getSnapshot()
      if (['ready', 'error'].includes(state.phase)) { clearTimeout(timer); unsubscribe(); resolve(state) }
    })
  })
}
const coordinator = state => createAutomaticReferenceCoordinator(state.source, state.api, { wait: async () => {}, maxPolls: 4 })

test('recipe removes every event, preserves economics and canonicalizes mapping order and names', () => {
  const f = fixture(), original = structuredClone(f.inputs)
  const a = referenceRecipe(f.inputs)
  assert.deepEqual(JSON.parse(a.submission.pdl).events, [])
  assert.deepEqual(JSON.parse(a.submission.pdl).cascades, [{ id: 'unshocked_reference', timeline: [] }])
  assert.deepEqual(JSON.parse(a.submission.roster), original.roster)
  assert.deepEqual(f.inputs, original)
  assert.equal(a.key, referenceRecipe({ ...f.inputs, pdl: { ...f.inputs.pdl, scenario: { name: 'Different label' } },
    parameters: { farm_size_seed: 42, period_num: 300 } }).key)
  assert.equal(referenceRecipe({ ...f.inputs, roster: null }).submission.roster, null)
  assert.equal(hasEmptyEvents(f.inputs), false)
})

test('concurrent selections and remounts share one accepted reference per recipe', async () => {
  const f = fixture(), service = coordinator(f)
  const first = service.ensure('shock', 1)
  const detach = first.subscribe(() => {}); detach()
  assert.equal(service.ensure('shock', 1), first)
  const second = service.ensure('other', 1)
  const [a, b] = await Promise.all([settled(first), settled(second)])
  assert.equal(a.phase, 'ready'); assert.equal(b.phase, 'ready')
  assert.equal(a.reference.runId, b.reference.runId)
  assert.equal(a.reference.scenarioId, 1)
  assert.equal(f.submissions.length, 1)
})

test('later-page scenario zero discovery skips wrong identities and avoids any POST', async () => {
  const f = fixture()
  f.source.listRuns = async (limit, offset) => ({ items: offset ? [
    { ...f.run('wrong'), scenario_ids: [0] }, { ...f.run('valid'), scenario_ids: [0] },
  ] : Array.from({ length: 50 }, (_, i) => ({ ...f.run(`failed-${i}`), playable: false })), total: 52 })
  const frames = f.source.getFrames
  f.source.getFrames = async (...args) => {
    const page = await frames(...args)
    if (args[0] === 'wrong') page.frames[0].agents[0].agent_id = 99
    return page
  }
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.deepEqual(state.reference, { runId: 'valid', scenarioId: 0, evidence: 'scenario-zero' })
  assert.equal(f.submissions.length, 0)
})

test('verified completed scenario one is reused; a baseline label does not establish eligibility', async () => {
  const f = fixture()
  f.runs.push({ ...f.run('fake'), label: 'Automatic disruption-free reference' })
  f.data.set('fake', f.inputs)
  const submission = referenceRecipe(f.inputs).submission
  await f.api.submit(submission); await f.api.inspect('reference-1')
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.reference.runId, 'reference-1')
  assert.equal(f.submissions.length, 1, 'discovery made no additional submission')
})

test('matching queued job on a later history page is monitored rather than resubmitted', async () => {
  const f = fixture()
  await f.api.submit(referenceRecipe(f.inputs).submission)
  f.api.list = async (limit, offset) => ({ items: offset ? [f.job('reference-1', 'queued')]
    : Array.from({ length: 50 }, (_, i) => f.job(`other-${i}`)), total: 51 })
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'ready'); assert.equal(f.submissions.length, 1)
})

test('a discovery outage never permits creation', async () => {
  const f = fixture()
  f.api.list = async () => { throw new SimulationApiError('History unavailable', 503, 'GET') }
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'error'); assert.equal(f.submissions.length, 0)
})

test('monitoring retry retains its accepted ID and does not submit again', async () => {
  const f = fixture(), inspect = f.api.inspect
  f.api.inspect = async () => { throw new Error('Offline') }
  const entry = coordinator(f).ensure('shock', 1)
  const failed = await settled(entry)
  assert.equal(failed.failure, 'monitoring'); assert.equal(failed.jobId, 'reference-1')
  f.api.inspect = inspect; entry.retry()
  assert.equal((await settled(entry)).phase, 'ready')
  assert.equal(f.submissions.length, 1)
})

test('unknown submission outcome is latched across retry without another POST', async () => {
  const f = fixture()
  f.api.submit = async input => { f.submissions.push(input); throw new SimulationApiError('Response lost', null, 'POST') }
  const entry = coordinator(f).ensure('shock', 1)
  assert.equal((await settled(entry)).failure, 'unknown-submission')
  await new Promise(resolve => setImmediate(resolve)); entry.retry()
  assert.equal((await settled(entry)).failure, 'unknown-submission')
  assert.equal(f.submissions.length, 1)
})

for (const stage of ['before', 'accepted', 'completed']) {
  test(`parameter drift ${stage} creation cannot publish an incompatible reference`, async () => {
    const f = fixture()
    if (stage === 'before') f.inputs.current_parameters.farm_size_seed = 99
    if (stage === 'accepted') {
      const submit = f.api.submit
      f.api.submit = async input => { const job = await submit(input); f.data.get(job.id).parameters = { ...f.inputs.parameters, farm_size_seed: 99 }; return job }
    }
    if (stage === 'completed') {
      const inspect = f.api.inspect
      f.api.inspect = async id => { const job = await inspect(id); f.data.get(id).parameters = { ...f.inputs.parameters, farm_size_seed: 99 }; return job }
    }
    const state = await settled(coordinator(f).ensure('shock', 1))
    assert.equal(state.phase, 'error')
    assert.equal(f.submissions.length, stage === 'before' ? 0 : 1)
  })
}

test('a confirmed failed job needs explicit retry before a replacement submission', async () => {
  const f = fixture(), inspect = f.api.inspect
  f.api.inspect = async id => {
    if (id === 'reference-1') { f.jobs.find(job => job.id === id).status = 'failed'; return f.job(id, 'failed') }
    return inspect(id)
  }
  const entry = coordinator(f).ensure('shock', 1)
  assert.equal((await settled(entry)).failure, 'failed-job')
  assert.equal(f.submissions.length, 1)
  await new Promise(resolve => setImmediate(resolve)); entry.retry()
  assert.equal((await settled(entry)).phase, 'ready'); assert.equal(f.submissions.length, 2)
})

test('retry discovers a newly available scenario zero before submitting', async () => {
  const f = fixture(), history = f.api.list
  f.api.list = async () => { throw new SimulationApiError('Offline', 503, 'GET') }
  const entry = coordinator(f).ensure('shock', 1)
  assert.equal((await settled(entry)).phase, 'error')
  f.runs.push({ ...f.run('cli'), scenario_ids: [0] }); f.api.list = history
  entry.retry()
  assert.equal((await settled(entry)).reference.runId, 'cli')
  assert.equal(f.submissions.length, 0)
})

test('history skips a completed identity-mismatched candidate and attaches a later queued match', async () => {
  const f = fixture()
  await f.api.submit(referenceRecipe(f.inputs).submission)
  await f.api.inspect('reference-1')
  await f.api.submit(referenceRecipe(f.inputs).submission)
  const frames = f.source.getFrames
  f.source.getFrames = async (...args) => {
    const page = await frames(...args)
    if (args[0] === 'reference-1') page.frames[0].agents[0].agent_id = 99
    return page
  }
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'ready')
  assert.equal(state.reference.runId, 'reference-2')
  assert.equal(f.submissions.length, 2)
})

test('a repeated final history page fails discovery closed with zero POSTs', async () => {
  const f = fixture()
  f.api.list = async () => ({ items: Array.from({ length: 50 }, (_, i) => f.job(`repeat-${i}`)), total: 100 })
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'error')
  assert.equal(f.submissions.length, 0)
})

test('a historical completed API job missing from playback does not prevent creating a recorded reference', async () => {
  const f = fixture()
  await f.api.submit(referenceRecipe(f.inputs).submission)
  f.jobs.find(job => job.id === 'reference-1').status = 'completed'
  f.data.get('reference-1').evidence = 'execution-hashes'
  const inspect = f.api.inspect
  f.api.inspect = id => id === 'reference-1' ? Promise.resolve(f.job(id)) : inspect(id)
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'ready')
  assert.equal(state.reference.runId, 'reference-2')
  assert.equal(f.submissions.length, 2)
})

test('a reference completing during history discovery is reused without a duplicate POST', async () => {
  const f = fixture()
  await f.api.submit(referenceRecipe(f.inputs).submission)
  const list = f.api.list
  f.api.list = async (...args) => {
    f.jobs.find(job => job.id === 'reference-1').status = 'completed'
    f.data.get('reference-1').evidence = 'execution-hashes'
    if (!f.runs.some(run => run.id === 'reference-1')) f.runs.push(f.run('reference-1'))
    return list(...args)
  }
  const state = await settled(coordinator(f).ensure('shock', 1))
  assert.equal(state.phase, 'ready')
  assert.equal(state.reference.runId, 'reference-1')
  assert.equal(f.submissions.length, 1)
})
