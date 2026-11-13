import type { Scene } from '../data/playback'
import type { projectFrame } from './frame'
import { formatValue, statusColor, statusLabel } from '../design/status'
import { entityDisplayName } from '../data/presentation'

export function StatusLegend() {
  return <section className="sim-status-legend" aria-label="Status legend">
    <div className="sim-status-scale">{[0, .5, 1, null].map(score => <span key={String(score)}><i style={{ background: statusColor(score) }} />{score === 0 ? 'Green: near reference' : score === .5 ? 'Amber: elevated' : score === 1 ? 'Red: severe' : 'Gray: unavailable'}</span>)}</div>
    <details><summary>Thresholds &amp; metric rules</summary>
    <p>Relative adverse change: green through 5%, amber at 20%, red at 50%, interpolated between anchors. Capacity utilization: green below 80%, amber at 80%, red at 95%. Illustrative workshop thresholds, pending domain calibration.</p>
    <p>Overview = strongest applicable metric of the strongest individual agent. Incomplete evidence is labeled; healthy evidence plus missing comparisons is gray.</p>
    <p>Connections inherit their immediate source component’s status. An ocean arc leaving a port therefore uses that port’s recorded evidence, not its grain originator or a separate sea-transport agent. Geometry and labels stay unchanged; historical unrecorded ports and their outgoing connections remain unavailable.</p>
    <p>Transport status compares effective capacity, output available and output asking price against the reference, and evaluates recorded utilization and participation directly. Nominal capacity is diagnostic only. Capacity loss can be severe while output is unchanged and utilization is low; it does not establish downstream harm. The target is never used, and network-average transport utilization does not measure individual ports or routes.</p>
    <p>Lower availability alone does not prove unmet demand. Storage/handling pressure is not production utilization or persistent warehouse inventory. Geographic placement annotations and selection rings are separate from status.</p>
    </details>
  </section>
}

export default function StatusPanel({ scene, projected, period, selected, onSelect, reference }: {
  scene: Scene; projected: ReturnType<typeof projectFrame>; period: number
  selected: string; onSelect: (id: string) => void; reference: string
}) {
  const node = scene.nodes.find(item => item.id === selected)
  const status = projected.nodes[selected]
  return <section aria-label="Component status" className="sim-component-status" data-period={period}>
    <label data-tutorial="component">Inspect component<select value={selected} onChange={event => onSelect(event.target.value)}>
      {scene.nodes.map(item => <option key={item.id} value={item.id}>{item.label} · {statusLabel(projected.nodes[item.id]?.score ?? null)}</option>)}
    </select></label>
    {node && status && <>
      <h3>{node.label} · step {period}</h3>
      <p className="sim-status-heading" style={{ borderColor: statusColor(status.score) }}><strong>{statusLabel(status.score)}</strong>{status.coverage === 'partial' && ' · Incomplete evidence'}</p>
      <p className="sim-status-reason" title={status.reason}>{status.reason}</p>
      <p className="sim-status-responsible">{status.winner && status.score !== null
        ? `Responsible metric: ${status.winner.metric.label} · agent ${status.winner.agent.agent_id} (${status.winner.agent.role}).`
        : 'Responsible metric: unavailable comparison evidence.'}</p>
      <p>Aggregation: strongest individual status across {status.agents.length} recorded agents; values below remain separate.</p>
      {node.entityIds.length > 1 && <p>Pooled component: {node.entityIds.map(id => entityDisplayName(node, id)).join(', ')}. Its geographic markers share this assessment.</p>}
      {node.placements.some(item => item.illustrative) && <p>Illustrative geographic placement (not a simulation-status indicator).</p>}
      <p className="sim-reference-note">{reference}</p>
      {status.agents.map(agent => <details key={JSON.stringify(agent.agent)} open={status.agents.length === 1}>
        <summary>Agent {agent.agent.agent_id} · {agent.agent.role} · {statusLabel(agent.score)}{agent.coverage === 'partial' ? ' · incomplete' : ''}</summary>
        {!agent.metrics.length && <p>{agent.reason}</p>}
        <dl>{agent.metrics.map(metric => <div key={metric.key} className="sim-metric" style={{ borderColor: statusColor(metric.score) }}>
          <dt>{metric.label} <code>{metric.key}</code></dt>
          <dd className="sim-metric-values"><span>Current: {formatValue(metric.current, metric.direction === 'capacity')}</span>
            <span>Reference: {formatValue(metric.reference, metric.direction === 'capacity')}</span>
            <span>Change: {metric.change === null
              ? metric.direction === 'increase' || metric.direction === 'decrease' ? 'Unavailable' : 'Not a relative comparison'
              : `${metric.change >= 0 ? '+' : ''}${(metric.change * 100).toFixed(1)}%`}</span></dd>
          <dd>{metric.reason}</dd>
        </div>)}</dl>
      </details>)}
    </>}
  </section>
}
