import type { PlaybackSource, RecordedFrame } from './playback'
import { staticJsonSource } from './staticJsonSource'

/** Explicit standalone demo. The bundle already contains legacy exported values. */
export function createStaticPlaybackSource(): PlaybackSource {
  let promise: ReturnType<typeof staticJsonSource.getBundle> | undefined
  const bundle = () => promise ??= staticJsonSource.getBundle().catch(error => { promise = undefined; throw error })
  const frames = async () => {
    const b = await bundle()
    return b.env.map((env): RecordedFrame => ({ period: env.period, agents: [
      ...b.ticks.filter(tick => tick.period === env.period).map(tick => ({
        entity_id: tick.nodeId, agent_id: 0, role: b.nodes.find(n => n.id === tick.nodeId)?.role ?? 'demo',
        values: Object.fromEntries(Object.entries(tick.values).filter(([, v]) => v !== null).map(([k, v]) => [k, Number(v)])),
      })),
      { entity_id: 'environment', agent_id: 0, role: 'environment', values: {
        soy_price: env.soyPrice, feed_price: env.feedPrice, shock_scale: env.shockScale,
        drought_severity: env.droughtSeverity, total_soy_supply: env.totalSoySupply,
        transport_utilisation: env.transportUtilisation, current_step: env.currentStep,
      } },
    ] }))
  }
  let all: ReturnType<typeof frames> | undefined
  return {
    name: 'Static demo (exported values)',
    async listRuns(limit, offset) {
      const b = await bundle()
      return { total: 1, items: offset || !limit ? [] : [{ id: 'demo', label: 'Static demo', started_at: b.meta.generatedAt,
        finished_at: b.meta.generatedAt, status: 'completed', scenario_ids: [1], period_num: b.meta.ticks,
        playable: true, unavailable_reason: null }] }
    },
    async getScene() {
      const b = await bundle()
      return { run_id: 'demo', scenario_id: 1, min_period: 0, max_period: b.meta.ticks - 1,
        pdl: b.meta.pdl, honesty_note: b.meta.honestyNote, nodes: b.nodes, edges: b.edges }
    },
    async getFrames(run, scenario, start, limit) {
      const series = await (all ??= frames())
      const end = Math.min(start + limit, series.length)
      return { run_id: run, scenario_id: scenario, start, next_start: end < series.length ? end : null,
        frames: series.slice(start, end) }
    },
  }
}
