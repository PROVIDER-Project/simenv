/**
 * Visual system for the Issue #23 globe.
 *
 * The two Batch-4 references establish a night-side cartographic object: deep
 * ink oceans, cyan edge light, restrained white city sparkle, hairline routes,
 * and a technical frame. Keeping the values here makes later chrome reuse the
 * same language without shipping that out-of-scope chrome in this batch.
 */

export const color = {
  base: '#02050C',
  surface: '#08111E',
  surfaceRaised: '#0B1727',
  border: 'rgba(151, 201, 239, 0.16)',

  accent: '#43B7FF',
  accentBright: '#B9E9FF',
  positive: '#51E3A5',
  warning: '#F6C55B',
  muted: '#60758E',

  text: '#F2F8FF',
  textMuted: '#8298B1',
  textFaint: '#536980',
} as const

export const typography = {
  display: 'Bahnschrift, "Avenir Next Condensed", "Segoe UI Variable Display", sans-serif',
  body: 'Aptos, "Segoe UI Variable Text", "Segoe UI", sans-serif',
  mono: '"Cascadia Code", "SFMono-Regular", Consolas, monospace',
  eyebrowTracking: '0.18em',
} as const

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const

export const radius = {
  sm: 6,
  md: 12,
  lg: 18,
  pill: 999,
} as const

export const shadow = {
  ambient: '0 18px 60px rgba(0, 0, 0, 0.36)',
  cyanGlow: '0 0 26px rgba(67, 183, 255, 0.22)',
} as const

export const globe = {
  background: color.base,
  ocean: '#020D1B',
  land: '#071A2B',
  landCap: 'rgba(9, 29, 49, 0.16)',
  landSide: 'rgba(64, 143, 194, 0.2)',
  landStroke: 'rgba(111, 195, 241, 0.1)',
  coast: '#2E739D',
  cityLight: '#E8F6FF',
  cityWarm: '#FFD9A1',
  atmosphere: '#62C7FF',
  atmosphereAltitude: 0.135,
  landAltitude: 0.006,
  cameraDesktop: 1.78,
  cameraMobile: 4.4,
  autoRotateSpeed: 0.06,
} as const

export const arc = {
  sea: '#64B9E8',
  land: '#3D789F',
  altitude: 0.16,
  stroke: 0.2,
  dashLength: 0.74,
  dashGap: 0.18,
  dashAnimateMs: 6200,
} as const

export const marker = {
  altitude: 0.014,
  radius: 0.34,
  selectedRadius: 0.52,
  haloRadius: 4.2,
  haloSpeed: 0.55,
  haloRepeatMs: 1800,
} as const

/** CSS custom properties consumed by the frame and annotation stylesheets. */
export const designVars = {
  '--sim-color-base': color.base,
  '--sim-color-surface': color.surface,
  '--sim-color-surface-raised': color.surfaceRaised,
  '--sim-color-border': color.border,
  '--sim-color-accent': color.accent,
  '--sim-color-accent-bright': color.accentBright,
  '--sim-color-positive': color.positive,
  '--sim-color-warning': color.warning,
  '--sim-color-muted': color.muted,
  '--sim-color-text': color.text,
  '--sim-color-text-muted': color.textMuted,
  '--sim-color-text-faint': color.textFaint,
  '--sim-font-display': typography.display,
  '--sim-font-body': typography.body,
  '--sim-font-mono': typography.mono,
  '--sim-radius-sm': `${radius.sm}px`,
  '--sim-radius-md': `${radius.md}px`,
  '--sim-radius-lg': `${radius.lg}px`,
  '--sim-shadow-ambient': shadow.ambient,
  '--sim-shadow-cyan': shadow.cyanGlow,
} as const
