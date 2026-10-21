export const origin = 'http://127.0.0.1:8001'
export const webUrl = process.env.SIMENV_WEB_URL || 'http://127.0.0.1:5173'
export function run(id, playable = true) {
  return { id, label: id, started_at: '2026-10-21T12:00:00Z', finished_at: '2026-10-21T12:01:00Z',
    status: playable ? 'completed' : 'failed', scenario_ids: [0, 1], period_num: 300,
    playable, unavailable_reason: playable ? null : 'Only completed runs can be played' }
}
export function scene(id = 'first', scenario = 1) {
  return { run_id: id, scenario_id: scenario, min_period: 0, max_period: 299,
    pdl: 'test.yaml', honesty_note: 'Approximate positions', nodes: [{
      id: 'brazil_farms', label: 'Brazil farms', role: 'producer', entityIds: ['brazil_farms'],
      placements: [{ entityId: 'brazil_farms', label: 'Brazil farms', lat: -15, lng: -50, illustrative: true }], hasRecordedData: true,
    }], edges: [] }
}
export function page(id, scenario, start, count = 1, metrics = 1) {
  return { run_id: id, scenario_id: scenario, start, next_start: start + 100 < 300 ? start + 100 : null,
    frames: Array.from({ length: Math.min(100, 300 - start) }, (_, i) => ({ period: start + i, agents: [
      ...Array.from({ length: count }, (_, agent_id) => ({ entity_id: 'brazil_farms', agent_id, role: 'producer',
        values: { unit_price: 10.123456789012345 + start + i,
          ...Object.fromEntries(Array.from({ length: metrics - 1 }, (_, m) => [`metric_${m}`, 1.123456789012345 + agent_id])) } })),
      { entity_id: 'environment', agent_id: 0, role: 'environment', values: {
        soy_price: 10, feed_price: 20, shock_scale: 0, drought_severity: 0,
        total_soy_supply: 100, transport_utilisation: 0.5, current_step: start + i,
      } },
    ] })) }
}
export async function mockPlayback(browserPage, { count = 1, metrics = 1, beyondFirst = false } = {}) {
  const requests = []
  await browserPage.route(`${origin}/**`, async route => {
    const url = new URL(route.request().url())
    let body
    if (url.pathname === '/runs') {
      const offset = Number(url.searchParams.get('offset'))
      body = beyondFirst && !offset ? { items: Array.from({ length: 50 }, (_, i) => run(`failed-${i}`, false)), total: 52 }
        : { items: [run('first'), run('second')], total: beyondFirst ? 52 : 2 }
    } else {
      const [, , id, , scenarioId, kind] = url.pathname.split('/')
      if (kind === 'scene') body = scene(id, Number(scenarioId))
      else {
        requests.push({ id, scenario: Number(scenarioId), start: Number(url.searchParams.get('start')), limit: Number(url.searchParams.get('limit')) })
        body = page(id, Number(scenarioId), Number(url.searchParams.get('start')), count, metrics)
      }
    }
    await route.fulfill({ json: body, headers: { 'access-control-allow-origin': '*' } })
  })
  return requests
}
