import type { RunSummary } from '../data/playback'

export default function ReferenceSelector({ runs, choice, onChange, explanation, loading, error, onRetry }: {
  runs: RunSummary[]; choice: string; onChange: (value: string) => void; explanation: string
  loading: boolean; error: string | null; onRetry: () => void
}) {
  return <section aria-label="Reference comparison" className="sim-reference">
    <label>Reference condition<select value={choice} onChange={event => onChange(event.target.value)}>
      <option value="start">Relative to scenario start</option>
      {choice !== 'start' && !runs.some(run => run.id === choice && run.playable && run.scenario_ids.includes(0)) &&
        <option value={choice}>{choice} · scenario 0 (outside loaded catalogue)</option>}
      {runs.filter(run => run.playable && run.scenario_ids.includes(0)).map(run =>
        <option key={run.id} value={run.id}>{run.label || run.id} · scenario 0</option>)}
    </select></label>
    <p>{explanation}</p>
    {loading && <p role="status">Loading reference; relative assessments unavailable…</p>}
    {error && <><p role="status">Reference unavailable: {error}</p><button type="button" onClick={onRetry}>Retry reference</button></>}
  </section>
}
