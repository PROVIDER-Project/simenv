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
| **Python simulation** (`src/provider_simenv`) | for execution or regenerating data | Runs scenarios and produces CSVs for `export_bundle.py`. |
| **Simulation API** (PR #50) | for the Run simulation button | Accepts generated PDL/roster and reports job progress. |
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
- press **Run simulation** to execute those same generated documents through the simulation API

The generated files keep the shipped scenario topology and narrow the document to the currently selected cascade. Save both files beside each other so simenv can resolve the sidecar automatically, then run:

```bash
python -m provider_simenv.main --pdl /path/to/generated-scenario.pdl.yaml
```

### Execute from the dashboard (Issue #26)

Execution requires the API from [PR #50](https://github.com/PROVIDER-Project/simenv/pull/50).
Until it is merged, run the API from its `49-simulation-api` branch in a separate checkout.
The frontend can still display playback and export PDL without the API.

1. In the **API checkout**, install and start the real service (Python 3.10+):

   ```bash
   pip install -e '.[api]'
   SIMENV_API_DATA_DIR=./data/api \
     uvicorn provider_simenv.api.app:app --host 127.0.0.1 --port 8000 --workers 1
   ```

   Alternatively, run `docker compose -f compose.api.yml up --build -d` in that
   checkout. See PR #50's `docs/api.md` for API deployment details.

2. In this checkout's `web/`, run `npm ci` and `npm run dev`, then open
   <http://localhost:5173>. Vite proxies `/api/*` to `http://127.0.0.1:8000/*`,
   so the browser does not need cross-origin API access.
3. Open **PDL configurator**, select a cascade, name the scenario, and adjust
   sliders/switches. Click **Run simulation** in its **Execute this scenario**
   section. No file download is required: the request contains the current
   PDL preview, matching roster preview, selected cascade, and scenario name
   as the run label. Both soy-crisis and energy-food cascades are supported.
4. The panel displays the API-generated run ID and polls once per second
   through `queued` → `running` → `completed` or `failed`. Overall progress
   covers both the baseline and PDL scenario; 100% can precede completion
   while the worker saves results. The button is disabled during submission
   and while the tracked job is active.

Editing controls after submission changes the next run, not the submitted run.
Hiding/reopening the panel retains monitoring. Submission validation errors
and worker failures are shown in the panel. If polling fails, **Retry monitoring**
resumes inspection of the same run ID without submitting another simulation.
Requests time out after 15 seconds. If submission loses its connection, check
the API's `GET /simulations` job history before retrying: the server may have
accepted the run even though its response did not reach the browser.

Tracking lasts for the current page session. Reloading or leaving the page
stops browser monitoring, but does not cancel an accepted job. Use the displayed
run ID with `GET /simulations/{id}` and `GET /simulations/{id}/logs` to inspect it.

#### API routing configuration

| Setting | Default | Purpose |
|---|---|---|
| `SIMENV_API_TARGET` | `http://127.0.0.1:8000` | Upstream for Vite dev/preview's `/api` proxy. Set in the shell or `web/.env.local`; restart Vite after changes. |
| `VITE_SIMENV_API_BASE_URL` | `/api` | Browser-visible API prefix, set before development/build. No trailing slash required. |

For another API port, start Vite with:

```bash
SIMENV_API_TARGET=http://127.0.0.1:8080 npm run dev
```

For production, serve `web/dist/` and reverse-proxy `/api/` to the API, stripping
the `/api` prefix (for example `/api/simulations` → `/simulations`). Vite's proxy
is not bundled into the static build. If your deployment exposes the API at
another same-origin prefix, set `VITE_SIMENV_API_BASE_URL` during `npm run build`.
A direct cross-origin URL requires the API/deployment to allow the frontend
origin via CORS; PR #50's default service does not enable CORS.

#### Viewing the new results

Completion means the API saved the run; the globe continues playing its loaded
`bundle.json`. The API currently provides status/log endpoints, not a downloadable
playback bundle. To display a completed API run, export its CSVs and reload the page.
With a local API data directory, run from this repository root:

```bash
python -m provider_simenv.export_bundle \
  --input /absolute/path/to/api-data/jobs/<run-id>/output/<run-id> \
  --scenario 1 --output web/public/bundle.json
```

For Docker, first copy outputs using the API checkout's Compose file:

```bash
docker compose -f compose.api.yml cp api:/data/jobs/<run-id>/output ./api-output
```

Then pass `./api-output/<run-id>` to the exporter using `--input`. For production
or `npm run preview`, rebuild and redeploy after changing `web/public/bundle.json`,
or replace the deployed `bundle.json` directly; reloading alone does not update
the copy already in `web/dist/`.

#### Browser acceptance check

With the real API (preferably idle, with no queued jobs) and Vite dev server
running as above, from `web/`:

```bash
npx playwright install --with-deps chromium
npm run test:simulation
```

This creates two real jobs (one per cascade), verifies that slider/switch edits
reach the API as the exact displayed PDL/roster, checks the submission lock and
monitoring across panel hide/show, and waits for completed runs with 730 steps.
Set `SIMENV_WEB_URL` to test a frontend on another URL and `SIMENV_TEST_TIMEOUT_MS`
to increase the per-run completion wait (default 120000 ms) for a busy API or
slower hardware. The test assumes the
API's bundled 365-step-per-scenario template. No API mock is included in the
application or test sources.

---

## Where the data comes from

Globe playback reads a single JSON bundle through the `DataSource` seam.
The configurator separately submits simulations and monitors them via the API:

```
simulation run (Melodie)
  └─ src/provider_simenv/data/output/<run-id>/Result_Simulator_*.csv
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
# 1. Run the simulation (writes Result_Simulator_*.csv to data/output/<run-id>/).
#    Run from the package directory — Melodie resolves data/ paths from the cwd.
cd src/provider_simenv
python main.py --pdl scenarios/s1-soja.pdl.yaml
cd ../..

# 2. Export the CSVs to the web bundle (newest completed run)
python -m provider_simenv.export_bundle --scenario 1

# ...or export one recorded run by id
python -m provider_simenv.export_bundle --scenario 1 --run 20260913T113537Z-f2b03f8b
```

This writes `web/public/bundle.json`. Each simulation run writes into its own
`data/output/<run-id>/` directory, indexed in `data/output/runs.json`. Without `--run` or
`--input` the exporter reads the newest completed run. Options:

| Flag | Default | Meaning |
|---|---|---|
| `--scenario` | `1` | `id_scenario` to export. `0` = baseline, `1` = PDL shock. |
| `--run` | newest completed run | Run id to export, as listed in `data/output/runs.json`. |
| `--input` | — | Directory holding the `Result_Simulator_*.csv` files. Read directly, bypassing the run registry. |
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
    ├── configurator/         parameter controls, PDL/roster generation, API execution
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
