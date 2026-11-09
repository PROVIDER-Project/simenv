import { useCallback, useEffect, useId, useState } from 'react'
import { useTutorialPanel } from '../tutorial/context'
import type { EnvState } from '../data/types'
import type { MetricStatus } from './status'
import { formatValue, statusColor, statusLabel } from '../design/status'
import './timeline.css'

interface TimelineProps {
  period: number
  minPeriod: number
  maxPeriod: number
  playing: boolean
  env: EnvState | null
  indicators?: MetricStatus[]
  indicatorsPreference: boolean | null
  onIndicatorsPreference: (expanded: boolean) => void
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
  indicators = [],
  indicatorsPreference,
  onIndicatorsPreference,
  onSeek,
  onTogglePlay,
}: TimelineProps) {
  const [compact, setCompact] = useState(() => matchMedia('(max-width: 1500px), (max-height: 800px)').matches)
  useEffect(() => {
    const query = matchMedia('(max-width: 1500px), (max-height: 800px)')
    const update = () => setCompact(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  const [tutorialExpanded, setTutorialExpanded] = useState<boolean | null>(null)
  const revealIndicators = useCallback(() => {
    setTutorialExpanded(true)
    return () => setTutorialExpanded(null)
  }, [])
  useTutorialPanel('indicators', revealIndicators)
  const expanded = tutorialExpanded ?? indicatorsPreference ?? !compact
  const indicatorsId = useId()
  const shock = env && Number.isFinite(env.shockScale) ? Math.round(env.shockScale * 100) : null
  return (
    <div data-tutorial="timeline" className="sim-timeline" role="group" aria-label="Playback">
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
                soy <b>{Number.isFinite(env.soyPrice) ? numberFmt.format(env.soyPrice) : 'Unavailable'}</b>
              </span>
              <span className="sim-timeline-sep" aria-hidden="true" />
              <span className={shock !== null && shock > 0 ? 'sim-timeline-shock sim-timeline-shock--on' : 'sim-timeline-shock'}>
                shock <b>{shock === null ? 'Unavailable' : `${shock}%`}</b>
              </span>
            </>
          )}
        </div>
        <button className="sim-indicators-toggle" type="button" aria-expanded={expanded} aria-controls={indicatorsId} onClick={() => {
          if (tutorialExpanded !== null) setTutorialExpanded(!expanded)
          else onIndicatorsPreference(!expanded)
        }}>{expanded ? 'Hide indicators' : 'Show indicators'}</button>
        <div id={indicatorsId} hidden={!expanded} data-tutorial="indicators" className="sim-network-indicators" role="group" aria-label="Network indicators" data-period={period}>
          {indicators.map(metric => <span key={metric.key} data-metric={metric.key} style={{ borderColor: statusColor(metric.score) }}
            tabIndex={0} title={metric.reason} aria-label={`${metric.label}: ${formatValue(metric.current, metric.direction === 'capacity')}. ${statusLabel(metric.score)}. ${metric.reason}`}>
            <span className="sim-network-label">{metric.label}</span><b>{formatValue(metric.current, metric.direction === 'capacity')}</b>
            <small>{statusLabel(metric.score)} · {metric.reason}</small>
          </span>)}
        </div>
      </div>
    </div>
  )
}
