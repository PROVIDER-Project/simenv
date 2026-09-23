# provider-simenv — web frontend (Issue #23)

World map / globe view for the PROVIDER simulation environment. Renders the geolocatable
projection of the soy supply chain — producers, ports, EU processing, livestock — and plays
back an exported simulation run on a 3D globe.

This directory is a standalone Vite application. It does **not** need the Python simulation
to run: a pre-exported `public/bundle.json` is committed, so `npm install && npm run dev` is
enough to see the view.

---

## Components

| Component | Required? | Purpose |
|---|---|---|
| **Node.js + npm** | yes | Builds and serves the frontend. |
| **`public/bundle.json`** | yes | The run data the view renders. A committed export is already in the repo. |
| **Python simulation** (`src/provider_simenv`) | only to regenerate data | Produces the CSVs that `export_bundle.py` turns into a new `bundle.json`. |
| **PostgreSQL** | no | Not used by the frontend. It is an output target of the simulation only. |

The globe now also includes an integrated **PDL configurator**. It adjusts a first-pass set of disruption parameters in the live visualization and emits a downloadable `*.pdl.yaml` document plus its matching `*.roster.yaml` sidecar for later execution through `provider_simenv.main --pdl ...`.

---

## Prerequisites

- **Node.js 20 LTS or newer** (Vite 5 requires `^18.0.0 || >=20.0.0`; Node 18 is end-of-life)
- **npm 10+** (ships with Node 20)

Check with:

```bash
node -v
npm -v
```

A WebGL-capable browser is required — the globe is rendered with three.js.

---

## Install

From this directory (`web/`):

```bash
npm install
```

`package-lock.json` is committed; use `npm ci` instead if you want an exact, reproducible
install.

---

## Start

```bash
# Development server with hot reload — http://localhost:5173
npm run dev

# Production build into web/dist/
npm run build

# Serve the production build locally
npm run preview
```

Quality gates, both used in review:

```bash
npm run typecheck   # tsc --noEmit against tsconfig.app.json
npm run lint        # eslint src
```

`npm run build` runs `tsc -b` first, so a type error fails the build.

### Scenario configurator

Inside the running app, open **PDL configurator** from the top-right panel to:

- switch between the soy-crisis and energy-food cascades
- tune a first set of event magnitudes, durations, and activation days with sliders
- toggle mitigation and contingency events with switches
- copy or download a runnable PDL document and the matching roster sidecar built from the current settings

The generated files keep the shipped scenario topology and narrow the document to the currently selected cascade. Save both files beside each other so simenv can resolve the sidecar automatically, then run:

```bash
python -m provider_simenv.main --pdl /path/to/generated-scenario.pdl.yaml
```

---

## Where the data comes from

The view never talks to the simulation directly. It reads a single JSON bundle through the
`DataSource` seam:

```
simulation run (Melodie)
  └─ src/provider_simenv/data/output/Result_Simulator_*.csv
       └─ python -m provider_simenv.export_bundle
            └─ web/public/bundle.json
                 └─ staticJsonSource  →  DataSource  →  views
```

- `src/data/source.ts` — the `DataSource` interface. Every view depends on this and never on
  a concrete source.
- `src/data/staticJsonSource.ts` — fetches `/bundle.json` and validates it structurally
  (`parseBundle`) before any view sees it.
- `src/main.tsx` — the composition root and the **only** place a concrete source is chosen.
  Swapping sources touches no view file.

Geography is deliberately *not* in the bundle. Coordinates live in the frontend gazetteer
(`src/data/gazetteer.ts`), keyed by PDL entity id. Entities the gazetteer does not know are
not rendered and a console warning is logged — a visible gap is preferred over a confident
wrong placement. Positions are approximate, not GIS accurate.

### Regenerating `bundle.json`

Only needed after a new simulation run. From the **repository root**, with the Python
environment installed (`pip install -e '.[dev]'`):

```bash
# 1. Run the simulation (writes Result_Simulator_*.csv to data/output/).
#    Run from the package directory — Melodie resolves data/ paths from the cwd.
cd src/provider_simenv
python main.py --pdl scenarios/s1-soja.pdl.yaml
cd ../..

# 2. Export the CSVs to the web bundle
python -m provider_simenv.export_bundle --scenario 1
```

This writes `web/public/bundle.json`. Options:

| Flag | Default | Meaning |
|---|---|---|
| `--scenario` | `1` | `id_scenario` to export. `0` = baseline, `1` = PDL shock. |
| `--input` | `src/provider_simenv/data/output` | Directory holding the `Result_Simulator_*.csv` files. |
| `--output` | `web/public/bundle.json` | Target path. |
| `--pdl` | `s1-soja.pdl.yaml` | PDL name recorded in the bundle metadata. |

On Windows, set `PYTHONIOENCODING=utf-8` before running either step — the scenario summary
prints box-drawing characters that raise `UnicodeEncodeError` on a cp1252 console.

---

## Layout

```
web/
├── index.html
├── package.json
├── vite.config.ts            three/globe.gl split into vendor chunks
├── public/
│   ├── bundle.json           exported run data (committed)
│   └── textures/             blue-marble, topology, night-sky
└── src/
    ├── main.tsx              composition root — picks the DataSource
    ├── App.tsx               loads the bundle, owns playback state
    ├── data/                 types, DataSource seam, sources, gazetteer
    ├── design/tokens.ts      colours, globe/atmosphere and arc settings
    ├── globe/                GlobeView + arc geometry helpers
    └── playback/             timeline scrubber + per-period intensity
```

`node_modules/` and `dist/` are gitignored.

---

## Troubleshooting

**"Failed to load the simulation bundle"** — `public/bundle.json` is missing or malformed.
Restore it from git or regenerate it (see above).

**Blank globe, no errors** — the browser has no WebGL. Check `chrome://gpu`, or run the dev
server in a normal browser window rather than an embedded IDE preview pane.

**Markers missing from the map** — the gazetteer has no entry for that PDL entity id. Open
the console; each drop is logged as `[gazetteer] not rendered — …`. Add the entity to
`src/data/gazetteer.ts` to place it.

**Large chunk warning on build** — expected and configured for. three.js and globe.gl exceed
Vite's 500 kB default and are split into their own long-cached vendor chunks
(`vite.config.ts`).
