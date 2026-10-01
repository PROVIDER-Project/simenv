/**
 * Visual system for the Issue #23 globe.
 *
 * The globe is a realistic blue-marble Earth (NASA texture + topology bump on a
 * night-sky field), matching the reference explorer's renderer treatment: a
 * light-blue atmosphere rim, a slow spin, and teal supply corridors drawn as a
 * layered glow. Keeping the values here lets later chrome reuse the same
 * language without shipping that out-of-scope chrome in this batch.
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

/** Static texture assets (bundled offline in web/public/textures). */
export const texture = {
  earth: '/textures/earth-blue-marble.jpg',
  bump: '/textures/earth-topology.png',
  nightSky: '/textures/night-sky.png',
} as const

export const globe = {
  background: color.base,
  atmosphere: '#7ec8ff',
  atmosphereAltitude: 0.18,
  cameraDesktop: 1.78,
  cameraMobile: 4.4,
  autoRotateSpeed: 0.35,
} as const

/**
 * Supply corridors, drawn as three stacked arcs per edge (a soft wide halo, a
 * mid glow, and a bright core) so each reads as one glowing line. The core is
 * dash-animated so flow reads as moving from source to target. Altitude scales
 * with arc length (`altitudeAutoScale`, like the reference) so long crossings
 * lift clear of the globe instead of sinking through it. Teal to sit with the
 * cyan atmosphere rather than the reference's shock-red.
 */
export const arc = {
  /** Matches the globe's `arcAltitudeAutoScale` and `arcApex` geometry. */
  altitudeAutoScale: 0.45,
  /** Low lift for short physical land connectors. */
  overlandAltitude: 0.006,
  overlandStrokeScale: 0.45,
  /** Surface path z-budget: above the globe, below markers at 0.014. */
  pathAltitude: 0.008,
  /** Path-specific hierarchy: moving glow/core dominate a restrained solid halo. */
  pathStrokeScale: { halo: 1, glow: 1.8, core: 2.4 },
  pathAlphaScale: { halo: 0.35, glow: 1, core: 1 },
  /** Commercial relationships are optional context, not geographic routes. */
  commercialAlphaScale: 0.24,
  commercialStrokeScale: 0.45,
  commercialDashLength: 0.16,
  commercialDashGap: 0.1,
  commercialDashAnimateMs: 3600,
  /** Disruption colour: corridors lerp teal → this as tick intensity rises. */
  hot: [255, 96, 80] as [number, number, number],
  halo: { stroke: 2.8, alpha: 0.16, teal: [[57, 208, 200], [126, 224, 230]] },
  glow: { stroke: 1.5, alpha: 0.34, teal: [[57, 208, 200], [126, 224, 230]] },
  core: { stroke: 0.7, alpha: 0.92, teal: [[214, 255, 250], [57, 208, 200]] },
  coreDashLength: 0.4,
  coreDashGap: 0.22,
  coreDashAnimateMs: 1400,
  pathCoreDashLength: 0.1,
  pathCoreDashGap: 0.065,
  pathCoreDashAnimateMs: 1800,
  /** Slight phase offset broadens the moving pulse without filling its visible gap. */
  pathGlowDashInitialGap: 0.025,
} as const

export const marker = {
  altitude: 0.014,
  radius: 0.34,
  selectedRadius: 0.52,
  haloRadius: 4.2,
  haloSpeed: 0.55,
  haloRepeatMs: 1800,
  portAltitude: 0.009,
  portLabelSize: 0.45,
  portDotRadius: 0.4,
  portOriginColor: 'rgba(246, 197, 91, 0.95)',
  portDestinationColor: 'rgba(185, 233, 255, 0.85)',
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
