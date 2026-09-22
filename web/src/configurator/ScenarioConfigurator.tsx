import { useEffect, useMemo, useState } from 'react'
import type { BundleMeta } from '../data/types'
import {
  buildPdl,
  cascadeLabel,
  cascadeSummary,
  defaultScenarioConfig,
  suggestedFileName,
  type CascadeId,
  type ScenarioConfig,
} from './pdlTemplate'
import './configurator.css'

interface ScenarioConfiguratorProps {
  meta: BundleMeta
}

interface RangeFieldProps {
  label: string
  min: number
  max: number
  step?: number
  value: number
  suffix: string
  onChange: (value: number) => void
}

interface ToggleFieldProps {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}

function RangeField({ label, min, max, step = 1, value, suffix, onChange }: RangeFieldProps) {
  return (
    <label className="sim-configurator-field">
      <span className="sim-configurator-field-row">
        <span>{label}</span>
        <b>
          {value}
          {suffix}
        </b>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function ToggleField({ label, checked, onChange }: ToggleFieldProps) {
  return (
    <label className="sim-configurator-toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  )
}

export default function ScenarioConfigurator({ meta }: ScenarioConfiguratorProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [notice, setNotice] = useState<string>('')
  const [config, setConfig] = useState<ScenarioConfig>(() => ({
    ...defaultScenarioConfig,
    scenarioName: meta.scenario && meta.scenario !== 'scenario-1' ? meta.scenario : defaultScenarioConfig.scenarioName,
  }))

  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth <= 900) setCollapsed(true)
  }, [])

  const pdl = useMemo(() => buildPdl(config), [config])
  const summary = useMemo(() => cascadeSummary(config), [config])
  const fileName = useMemo(() => suggestedFileName(config), [config])

  const setCascade = (cascadeId: CascadeId) => setConfig((current) => ({ ...current, cascadeId }))

  const download = () => {
    const blob = new Blob([pdl], { type: 'application/yaml;charset=utf-8' })
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = fileName
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(href), 0)
    setNotice(`Downloaded ${fileName}`)
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(pdl)
      setNotice(`Copied ${fileName} to the clipboard`)
    } catch {
      setNotice('Clipboard export failed in this browser context. Use Download PDL instead.')
    }
  }

  return (
    <aside className={`sim-configurator${collapsed ? ' sim-configurator--collapsed' : ''}`}>
      <div className="sim-configurator-header">
        <div>
          <p className="sim-configurator-eyebrow">Issue #22 · scenario builder</p>
          <h2>PDL configurator</h2>
        </div>
        <button type="button" className="sim-configurator-collapse" onClick={() => setCollapsed((value) => !value)}>
          {collapsed ? 'Open' : 'Hide'}
        </button>
      </div>

      {!collapsed && (
        <>
          <p className="sim-configurator-copy">
            Tune a first-pass disruption scenario inside the globe view and export a runnable PDL document.
          </p>

          <label className="sim-configurator-text-field">
            <span>Scenario name</span>
            <input
              type="text"
              value={config.scenarioName}
              onChange={(event) => setConfig((current) => ({ ...current, scenarioName: event.target.value }))}
            />
          </label>

          <label className="sim-configurator-text-field">
            <span>Active cascade</span>
            <select
              value={config.cascadeId}
              onChange={(event) => setCascade(event.target.value as CascadeId)}
            >
              <option value="soy_crisis_cascade">{cascadeLabel('soy_crisis_cascade')}</option>
              <option value="energy_food_cascade">{cascadeLabel('energy_food_cascade')}</option>
            </select>
          </label>

          <div className="sim-configurator-summary" aria-label="Selected parameter summary">
            {summary.map((entry) => (
              <span key={entry}>{entry}</span>
            ))}
          </div>

          {config.cascadeId === 'soy_crisis_cascade' ? (
            <>
              <section className="sim-configurator-section">
                <h3>Origin shock</h3>
                <RangeField
                  label="Brazil drought loss"
                  min={5}
                  max={90}
                  value={config.soy.droughtLossPct}
                  suffix="%"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, droughtLossPct: value } }))}
                />
                <RangeField
                  label="Drought duration"
                  min={15}
                  max={365}
                  value={config.soy.droughtDurationDays}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, droughtDurationDays: value } }))}
                />
                <RangeField
                  label="Drought start day"
                  min={0}
                  max={180}
                  value={config.soy.droughtDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, droughtDay: value } }))}
                />
              </section>

              <section className="sim-configurator-section">
                <h3>Flow responses</h3>
                <ToggleField
                  label="Santos port congestion"
                  checked={config.soy.portCongestionEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, portCongestionEnabled: value } }))}
                />
                <RangeField
                  label="Congestion loss"
                  min={5}
                  max={80}
                  value={config.soy.portCongestionLossPct}
                  suffix="%"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, portCongestionLossPct: value } }))}
                />
                <RangeField
                  label="Congestion duration"
                  min={7}
                  max={180}
                  value={config.soy.portCongestionDurationDays}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, portCongestionDurationDays: value } }))}
                />
                <RangeField
                  label="Congestion start day"
                  min={0}
                  max={180}
                  value={config.soy.portCongestionDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, portCongestionDay: value } }))}
                />
              </section>

              <section className="sim-configurator-section">
                <h3>Mitigations</h3>
                <ToggleField
                  label="Argentina supply response"
                  checked={config.soy.argentinaSupplyEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, argentinaSupplyEnabled: value } }))}
                />
                <RangeField
                  label="Argentina response day"
                  min={0}
                  max={180}
                  value={config.soy.argentinaSupplyDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, argentinaSupplyDay: value } }))}
                />
                <ToggleField
                  label="US emergency supply"
                  checked={config.soy.usEmergencyEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, usEmergencyEnabled: value } }))}
                />
                <RangeField
                  label="US response day"
                  min={0}
                  max={180}
                  value={config.soy.usEmergencyDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, usEmergencyDay: value } }))}
                />
                <ToggleField
                  label="Strategic reserve release"
                  checked={config.soy.reserveReleaseEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, reserveReleaseEnabled: value } }))}
                />
                <RangeField
                  label="Reserve release day"
                  min={0}
                  max={180}
                  value={config.soy.reserveReleaseDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, reserveReleaseDay: value } }))}
                />
                <ToggleField
                  label="Alternative protein activation"
                  checked={config.soy.alternativeProteinEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, alternativeProteinEnabled: value } }))}
                />
                <RangeField
                  label="Alternative protein day"
                  min={0}
                  max={180}
                  value={config.soy.alternativeProteinDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, soy: { ...current.soy, alternativeProteinDay: value } }))}
                />
              </section>
            </>
          ) : (
            <>
              <section className="sim-configurator-section">
                <h3>Origin shock</h3>
                <RangeField
                  label="Gas price increase"
                  min={25}
                  max={400}
                  value={config.energy.gasPriceIncreasePct}
                  suffix="%"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, gasPriceIncreasePct: value } }))}
                />
                <RangeField
                  label="Price shock duration"
                  min={15}
                  max={365}
                  value={config.energy.gasPriceDurationDays}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, gasPriceDurationDays: value } }))}
                />
                <RangeField
                  label="Price shock start day"
                  min={0}
                  max={180}
                  value={config.energy.gasPriceDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, gasPriceDay: value } }))}
                />
              </section>

              <section className="sim-configurator-section">
                <h3>Industrial disruptions</h3>
                <ToggleField
                  label="Ammonia production halt"
                  checked={config.energy.ammoniaHaltEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, ammoniaHaltEnabled: value } }))}
                />
                <RangeField
                  label="Ammonia supply loss"
                  min={10}
                  max={95}
                  value={config.energy.ammoniaHaltLossPct}
                  suffix="%"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, ammoniaHaltLossPct: value } }))}
                />
                <RangeField
                  label="Ammonia halt duration"
                  min={7}
                  max={180}
                  value={config.energy.ammoniaHaltDurationDays}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, ammoniaHaltDurationDays: value } }))}
                />
                <RangeField
                  label="Ammonia halt day"
                  min={0}
                  max={180}
                  value={config.energy.ammoniaHaltDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, ammoniaHaltDay: value } }))}
                />
                <ToggleField
                  label="Oil mill slowdown"
                  checked={config.energy.oilMillSlowdownEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, oilMillSlowdownEnabled: value } }))}
                />
                <RangeField
                  label="Oil mill loss"
                  min={5}
                  max={90}
                  value={config.energy.oilMillSlowdownLossPct}
                  suffix="%"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, oilMillSlowdownLossPct: value } }))}
                />
                <RangeField
                  label="Oil mill duration"
                  min={7}
                  max={180}
                  value={config.energy.oilMillSlowdownDurationDays}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, oilMillSlowdownDurationDays: value } }))}
                />
                <RangeField
                  label="Oil mill day"
                  min={0}
                  max={180}
                  value={config.energy.oilMillSlowdownDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, oilMillSlowdownDay: value } }))}
                />
              </section>

              <section className="sim-configurator-section">
                <h3>Mitigations</h3>
                <ToggleField
                  label="Strategic reserve release"
                  checked={config.energy.reserveReleaseEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, reserveReleaseEnabled: value } }))}
                />
                <RangeField
                  label="Reserve release day"
                  min={0}
                  max={180}
                  value={config.energy.reserveReleaseDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, reserveReleaseDay: value } }))}
                />
                <ToggleField
                  label="Alternative protein activation"
                  checked={config.energy.alternativeProteinEnabled}
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, alternativeProteinEnabled: value } }))}
                />
                <RangeField
                  label="Alternative protein day"
                  min={0}
                  max={180}
                  value={config.energy.alternativeProteinDay}
                  suffix="d"
                  onChange={(value) => setConfig((current) => ({ ...current, energy: { ...current.energy, alternativeProteinDay: value } }))}
                />
              </section>
            </>
          )}

          <div className="sim-configurator-actions">
            <button type="button" onClick={() => void copy()}>
              Copy PDL
            </button>
            <button type="button" onClick={download}>
              Download PDL
            </button>
          </div>

          <div className="sim-configurator-meta">
            <span>Based on {meta.pdl}</span>
            <span>{fileName}</span>
          </div>

          <label className="sim-configurator-preview">
            <span>Generated PDL</span>
            <textarea readOnly value={pdl} spellCheck={false} />
          </label>

          <p className="sim-configurator-notice" aria-live="polite">
            {notice || 'Export the document and run provider_simenv.main --pdl <file> later.'}
          </p>
        </>
      )}
    </aside>
  )
}
