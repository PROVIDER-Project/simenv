import type { RunSummary } from '../data/playback'

export default function ReferenceSelector({ runs, choice, onChange, explanation, loading, error, onRetry, preparation, automaticAvailable = true }: {
  runs: RunSummary[]; choice: string; onChange: (value: string) => void; explanation: string
  loading: boolean; error: string | null; onRetry: () => void
  preparation?: string
  automaticAvailable?: boolean
}) {
  return <section aria-label="Reference comparison" className="sim-reference">
    <label>Reference condition<select value={choice} onChange={event => onChange(event.target.value)}>
      {automaticAvailable && <option value="auto">Disruption-free reference (automatic)</option>}
      <option value="start">Relative to scenario start</option>
      {choice !== 'start' && choice !== 'auto' && !runs.some(run => run.id === choice && run.playable && run.scenario_ids.includes(0)) &&
        <option value={choice}>{choice} · scenario 0 (outside loaded catalogue)</option>}
      {runs.filter(run => run.playable && run.scenario_ids.includes(0)).map(run =>
        <option key={run.id} value={run.id}>{run.label || run.id} · scenario 0</option>)}
    </select></label>
    <p>{explanation}</p>
    <p className="sim-reference-status" role={loading || error ? 'status' : undefined}>
      {error ? `Reference unavailable: ${error}` : preparation || (loading ? 'Waiting for matching measurements…' : '')}
    </p>
    {error && <button type="button" onClick={onRetry}>Retry reference</button>}
  </section>
}
