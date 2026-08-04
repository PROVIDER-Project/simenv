import type { EnvState } from '../data/types'
import './timeline.css'

interface TimelineProps {
  period: number
  minPeriod: number
  maxPeriod: number
  playing: boolean
  env: EnvState | null
  onSeek: (period: number) => void
  onTogglePlay: () => void
}

const numberFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** Bottom-centre transport bar: play/pause, a scrubber, and a live env readout. */
export default function Timeline({
  period,
  minPeriod,
  maxPeriod,
  playing,
  env,
  onSeek,
  onTogglePlay,
}: TimelineProps) {
  const shock = env ? Math.round(env.shockScale * 100) : 0
  return (
    <div className="sim-timeline" role="group" aria-label="Playback">
      <button
        type="button"
        className="sim-timeline-play"
        onClick={onTogglePlay}
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {playing ? '❚❚' : '▶'}
      </button>

      <div className="sim-timeline-track">
        <input
          type="range"
          min={minPeriod}
          max={maxPeriod}
          value={period}
          step={1}
          onChange={(event) => onSeek(Number(event.target.value))}
          aria-label="Simulation step"
        />
        <div className="sim-timeline-readout">
          <span>
            step <b>{period}</b> / {maxPeriod}
          </span>
          {env && (
            <>
              <span className="sim-timeline-sep" aria-hidden="true" />
              <span>
                soy <b>{numberFmt.format(env.sojaPrice)}</b>
              </span>
              <span className="sim-timeline-sep" aria-hidden="true" />
              <span className={shock > 0 ? 'sim-timeline-shock sim-timeline-shock--on' : 'sim-timeline-shock'}>
                shock <b>{shock}%</b>
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
