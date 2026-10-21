import type { RunSummary } from '../data/playback'

interface Props {
  runs: RunSummary[]
  selected: string
  scenario: number
  hasMore: boolean
  loading: boolean
  error: string | null
  onRun: (id: string) => void
  onScenario: (id: number) => void
  onRefresh: () => void
  onMore: () => void
}

export default function RunSelector(props: Props) {
  const selected = props.runs.find(run => run.id === props.selected)
  return <section className="sim-run-selector" aria-label="Recorded playback">
    <label>Recorded run
      <select aria-label="Recorded run" value={props.selected} onChange={e => props.onRun(e.target.value)}>
        <option value="" disabled>Select a recorded run</option>
        {props.runs.map(run => <option key={run.id} value={run.id} disabled={!run.playable}>
          {run.label || run.id} · {new Date(run.started_at).toLocaleString()} · {run.id}
          {!run.playable ? ` — ${run.unavailable_reason}` : ''}
        </option>)}
      </select>
    </label>
    <label>Recorded scenario
      <select aria-label="Recorded scenario" value={props.scenario} disabled={!selected}
        onChange={e => props.onScenario(Number(e.target.value))}>
        {(selected?.scenario_ids ?? [1]).map(id => <option key={id} value={id}>{id === 0 ? 'Baseline (0)' : `Scenario ${id}`}</option>)}
      </select>
    </label>
    <button type="button" onClick={props.onRefresh} disabled={props.loading}>Refresh runs</button>
    {props.hasMore && <button type="button" onClick={props.onMore} disabled={props.loading}>More runs</button>}
    {props.loading && <span role="status">Loading recorded runs…</span>}
    {props.error && <p role="alert">{props.error}</p>}
    {!props.loading && !props.runs.length && !props.error && <p>No recorded runs yet.</p>}
  </section>
}
