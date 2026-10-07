import { useEffect, useRef, useState } from 'react'
import { inspectSimulation, submitSimulation, type SimulationJob, type SimulationSubmission } from './simulationApi'

interface SimulationRunnerProps {
  submission: SimulationSubmission
  hidden: boolean
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export default function SimulationRunner({ submission, hidden }: SimulationRunnerProps) {
  const [submitting, setSubmitting] = useState(false)
  const [job, setJob] = useState<SimulationJob | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [monitoringError, setMonitoringError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const submissionController = useRef<AbortController | null>(null)
  const active = job?.status === 'queued' || job?.status === 'running'
  const id = job?.id

  useEffect(() => () => submissionController.current?.abort(), [])

  useEffect(() => {
    if (!id || !active) return
    const controller = new AbortController()
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await inspectSimulation(id, controller.signal)
        if (controller.signal.aborted) return
        setJob(next)
        setMonitoringError(null)
        if (next.status === 'queued' || next.status === 'running') {
          timer = window.setTimeout(() => void poll(), 1000)
        }
      } catch (error) {
        if (!controller.signal.aborted) setMonitoringError(message(error))
      }
    }
    timer = window.setTimeout(() => void poll(), 1000)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [id, active, retry])

  const run = async () => {
    if (submissionController.current || active) return
    const controller = new AbortController()
    submissionController.current = controller
    setSubmitting(true)
    setSubmissionError(null)
    setMonitoringError(null)
    setJob(null)
    try {
      const next = await submitSimulation(submission, controller.signal)
      if (!controller.signal.aborted) setJob(next)
    } catch (error) {
      if (!controller.signal.aborted) setSubmissionError(message(error))
    } finally {
      submissionController.current = null
      if (!controller.signal.aborted) setSubmitting(false)
    }
  }

  return (
    <section className="sim-configurator-section sim-configurator-run" hidden={hidden} aria-label="Simulation execution">
      <h3>Execute this scenario</h3>
      <p className="sim-configurator-copy">
        Run the generated PDL and roster with the selected cascade. Edits after submission apply to the next run.
      </p>
      <div className="sim-configurator-actions">
        <button type="button" onClick={() => void run()} disabled={submitting || active}>
          {submitting ? 'Submitting…' : 'Run simulation'}
        </button>
      </div>
      {submissionError && (
        <p className="sim-configurator-run-error" role="alert">
          {submissionError} If the connection failed, check API job history before submitting again; the run may have been accepted.
        </p>
      )}
      {job && (
        <div className="sim-configurator-run-status" role="status" aria-live="polite">
          <p><strong>{job.label || 'Simulation'}</strong> · {job.status}</p>
          <p>Run ID: <code>{job.id}</code></p>
          <progress max={100} value={job.progress.percent_complete} aria-label="Overall simulation progress" />
          <p>{job.progress.percent_complete.toFixed(1)}% · {job.progress.completed_steps}/{job.progress.total_steps} total steps</p>
          {job.progress.scenario_id !== null && (
            <p>{job.progress.scenario_id === 0 ? 'Baseline' : 'PDL scenario'} · step {job.progress.step}/{job.progress.scenario_total_steps}</p>
          )}
          {job.status === 'completed' && <p>Results saved by the API. The globe still shows the loaded playback bundle.</p>}
        </div>
      )}
      {job?.error && <p className="sim-configurator-run-error" role="alert">{job.error}</p>}
      {monitoringError && (
        <>
          <p className="sim-configurator-run-error" role="alert">Monitoring paused: {monitoringError}. The simulation may still be running.</p>
          <div className="sim-configurator-actions">
            <button type="button" onClick={() => { setMonitoringError(null); setRetry(value => value + 1) }}>
              Retry monitoring
            </button>
          </div>
        </>
      )}
    </section>
  )
}
