# Database playback

![Recorded playback with the expanded left panel at step 150 (static demo)](playback-preview.png)

[View or download the full-size screenshot](playback-preview.png).

## Start the complete stack

```bash
docker compose -f compose.playback.yml up --build -d
```

The Python-service builds install `provider-agents` from the latest public
**main** branch, separately from hash-verified third-party requirements. No
GitHub token or build secret is needed. Compose disables caching for those
builds so each rebuild fetches current agent main. For direct image builds,
use `docker build --no-cache -f Dockerfile.api ...` or
`docker build --no-cache -f Dockerfile.playback ...`.

Open **http://localhost:8080**. An empty database is supported: use the scenario
configurator's **Run simulation** button to record the first run. On completion
the catalogue refreshes. Use **View results** to select that exact run's scenario
1, or select a run/scenario manually, then play, pause, or seek. The
newest playable run is selected initially. Refresh and More runs browse records.
The globe does not rotate automatically. Drag to rotate it manually and scroll
to zoom; simulation playback is independent of camera movement.

Run and scenario selection are stacked in **Recorded playback**, with
**Disturbance impact directly below it** in one narrow left sidebar. Both panels
start expanded and have independent **Hide**/**Show** buttons; run, scenario,
reference, inspected component and current playback are retained. Desktop panels
share a single bounded scroll area, so collapsing run selection moves impact up
naturally without adding an overlay across the globe. On smaller screens the
sidebar becomes full-width page flow with no nested scrolling. Globe connections
remain visible in all status states, including gray for unknown upstream status.
The desktop grid keeps the timeline in the center column between both sidebars;
the sidebars start 24px from the application top and span the header, globe and
timeline rows. The title and **Restart tutorial** occupy a normal-flow center
header. Narrow or very short application space uses page flow to keep
all controls reachable; see the exact thresholds below.

Interface examples (using the bundled static demo):
[collapsed panel](playback-selector-collapsed.png) and
[mobile layout](playback-selector-mobile.png).

| Service | Default address | Purpose |
| --- | --- | --- |
| Frontend | http://localhost:8080 | Globe, run selection, scenario submission |
| Simulation API | http://localhost:8000/docs | Submission, status, progress, logs; also usable by external services |
| Playback API | http://localhost:8001/docs | Read-only discovery, scene metadata, frame ranges |
| PostgreSQL | Compose network only | Shared persistent database |

PostgreSQL and simulation job files have separate named volumes. `docker compose
-f compose.playback.yml down` keeps both volumes.

### Responsive playback layout

The desktop grid keeps a **300px left sidebar** and a flexible center with a
**360px minimum**. The configurator is **320px** wide when the named `sim-shell`
container is **1160–1500 CSS pixels inclusive**, and **420px above 1500px**.
With two 16px gaps and 48px outer padding, the medium layout's width budget is
**1060px**, versus 1160px with the wider configurator. The page-flow threshold
remains conservatively at **1160px**, not the medium layout's exact minimum.
At 1275px of application width, the center is **575px** wide: the narrower
configurator gives it 100px more room without changing the left column or center
minimum. Below 1160px of available application
width, or at available height **≤540px**, controls use full-width scrollable page
flow, with the header and restart button before the controls. A docked tutorial
reduces the available application area, so these layout
thresholds can apply even when the browser viewport itself is larger. On desktop,
both sidebars scroll independently; oversized center content makes the application
scroll rather than covering adjacent controls or being permanently clipped.

The four **network indicator cards** start collapsed when viewport width is
**≤1500px OR height ≤800px**. They start expanded only when both dimensions exceed
those thresholds. **Show indicators / Hide indicators** toggles the cards, leaving
play/pause, the step slider and basic step/soy/shock readout available. This changes
visible globe space, not globe scale or playback time. Recorded playback and
Disturbance impact still start expanded and retain their separate Hide/Show buttons.

Before an explicit indicator choice, resizing updates the responsive default.
Either explicit choice then survives resizing and run/scenario changes for the
current page session; reload resets it. The tutorial's final step temporarily
reveals the cards and restores the underlying explicit choice or current responsive
default when you leave the step, finish or dismiss the tour. Hiding cards during
that step changes only the temporary reveal; revisiting reveals them again.

#### Matched responsive review evidence

All five images use **1275 × 605 CSS pixels**, Chromium device scale factor 1
(1275 × 605 image pixels). The reported physical screenshot was approximately
1912 × 907 pixels, consistent with 150% scaling; physical pixels are not the CSS
layout viewport, so using those physical dimensions as the viewport would test a
different layout.

| State | Capture |
| --- | --- |
| Before: clean issue #79 HEAD `6add5ef`, timeline overlaps configurator | [Before medium](responsive-before-medium.png) |
| After: 320px configurator, top-aligned side panels, center header, default collapsed cards | [After medium](responsive-after-medium.png) |
| After: Show indicators, four-card grid at the viewport's lower edge | [Expanded medium](responsive-expanded-medium.png) |
| Last tutorial step: temporary reveal, English | [English](responsive-tutorial-en-medium.png) |
| Last tutorial step: temporary reveal, Deutsch | [Deutsch](responsive-tutorial-de-medium.png) |

The before capture is served from a clean detached worktree at **`6add5ef`**, not
the older issue #75 server used for the historical tutorial screenshots below.
The four refreshed after captures use the **uncommitted narrower-configurator
working tree beyond `8254dab`** on `79-interactive-tutorial`, served on port 5179:
a 320px configurator, 575px center, side panels at 24px from the application top,
and a normal-flow center title/restart header. They supersede the earlier
top-alignment captures made beyond `94c2ff6`; neither commit alone reproduces
these refreshed images. The original before PNG is preserved byte-for-byte. Both use
the same **controlled recorded-response fixtures** from `playback-fixtures.mjs`:
run `first`, scenario 1, paused step 100, component `brazil_farms`, scenario-start
reference, expanded configurator. These are interface fixtures, not empirical
simulation results; no simulation is submitted. Tutorial completion is seeded
only for the three comparison captures; the last two navigate a fresh tour.

To reproduce, create a detached baseline outside the working tree and start its
recorded-mode Vite server (the existing issue #79 recorded server stays on 5179):

```bash
# From the repository root; run once for this baseline location.
git worktree add --detach /tmp/opencode/simenv79-responsive-baseline 6add5ef
# From /tmp/opencode/simenv79-responsive-baseline/web:
npm ci
VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8079 npm run dev -- --host 127.0.0.1 --port 5181 --strictPort
# From the followup worktree's web/ directory, in another terminal:
SIMENV_BASELINE_WEB_URL=http://127.0.0.1:5181 \
SIMENV_WEB_URL=http://127.0.0.1:5179 \
SIMENV_TEST_PLAYBACK_ORIGIN=http://127.0.0.1:8079 \
  node tests/capture-responsive-playback.mjs
# Preserve the existing before image after the script regenerates the matched set:
git -C .. restore -- docs/responsive-before-medium.png
```

The capture script reuses playback fixtures and their browser-setup completion
seed, checks the expected baseline/default toggle state, and logs panel geometry.
Visual review confirms top-aligned after side panels, the center title/restart
header and separated columns, plus readable configurator labels, buttons, inputs
and range controls within 320px. The expanded cards and EN/DE final-step guidance
remain readable. At this short viewport the expanded grid reaches the
lower image edge; scroll for its remaining content. Tutorial navigation can scroll
the sidebar contents while the panel containers still start at 24px.
The older tutorial/status screenshots remain historical evidence of their stated
source revisions; they have not been regenerated with the responsive followup.

## Interactive tutorial

A first visit automatically starts a nine-step tour: scenario name, disruption
settings, execution/monitoring, completed results, recorded selection, timeline,
reference/legend, component evidence and network indicators. The popup highlights
the relevant controls and opens their panel on step entry. **Back/Next** remain
available even if a target has not loaded or a run has not completed; you can
continue and return later. The tour never edits inputs, submits a simulation,
switches the selected run or moves the playback time. Automatic disruption-free
reference preparation remains normal playback behavior, not a tutorial action.

**Close for session** or Escape dismisses the tour for this page session. Reload
starts an unfinished tour again at step 1. **Finish** on the last step stores
completion locally in this browser for this site, suppressing automatic start on
later visits. The **Restart tutorial** button near the top clears completion and
starts at step 1, keeping your language. Select **English** or **Deutsch** inside
the popup to change tutorial text and actions; the choice is remembered locally.
This does not translate the rest of the interface. Completion and language are
not account settings or shared between browsers/origins. If `localStorage` is
blocked, the tutorial degrades gracefully to current-page-session behavior:
navigation, dismissal and language switching work, but completion and language
cannot be remembered after reload.

The popup is a labeled, non-modal region. Step entry focuses its heading;
Tab/Shift+Tab reach both tutorial buttons and application controls, and
Enter/Space activate buttons. Escape closes and returns focus to the opener or
**Restart tutorial**. Use native keyboard controls for sliders/selects and
**Inspect component** as an alternative to globe interaction. Narrow/short
screens allow scrolling the popup and may dock it above the application with
space reserved for the highlighted controls.

The tour works in both playback modes, but does not create missing services or
results. In static mode its selection step explains that the exported demo is
separate from submitted runs. Executing your inputs needs the simulation API and
PostgreSQL; viewing the completed job requires recorded playback, both APIs
sharing the database, and **View results** to open that exact job's scenario 1.
Existing recordings can be explored without submitting a new job.

### Tutorial review evidence

| State | Desktop (1440 × 1000) | Mobile (390 × 844) |
| --- | --- | --- |
| Before: configurator, no tutorial | [Before desktop](tutorial-before-desktop.png) | [Before mobile](tutorial-before-mobile.png) |
| After: first-visit English popup and scenario-name highlight | [After desktop](tutorial-after-desktop.png) | [After mobile](tutorial-after-mobile.png) |

Impact guidance at step 8, with the same selected component and playback step:
[English](tutorial-impact-en.png) / [Deutsch](tutorial-impact-de.png). Only the
tutorial changes language; the surrounding English controls remain visible.

The four static screenshots use the same committed `bundle.json`, paused at
step 100. Before is the unmodified issue #75 source at commit
`4b35fce12db40774984fa437144d0b9f13dd4ccc`, served by the existing static server
on port 5176; after is the issue #79 working tree on port 5180. Mobile captures
are scrolled to center the scenario-name input, rather than showing page top.
The capture script asserts byte equality of the two bundles; the captured
SHA-256 was `0efafdb2224af97984ee0caf86131c0c6493a0c10ebc078855721daaa72713f0`.
The two impact screenshots use **controlled recorded-response fixtures**, not
empirical simulation results: run `first`, scenario 1, step 100, component
`brazil_farms`, explicitly selected scenario-start reference. No simulation is
submitted by the capture script.

Reproduce from `web/`, with before/after static servers and the issue #79
recorded-mode server running (see the [tutorial browser setup](../web/README.md#tutorial-browser-check)):

```bash
SIMENV_BASELINE_WEB_URL=http://127.0.0.1:5176 \
SIMENV_STATIC_WEB_URL=http://127.0.0.1:5180 \
SIMENV_WEB_URL=http://127.0.0.1:5179 \
SIMENV_TEST_PLAYBACK_ORIGIN=http://127.0.0.1:8079 \
  node tests/capture-tutorial.mjs
```

`SIMENV_TEST_PLAYBACK_ORIGIN` must match the recorded frontend's build/dev API
origin. Its default is `http://127.0.0.1:8001`; port 8079 requires the override
above. Playwright Chromium captures these six PNGs at device scale factor 1.

## Configuration

Compose variables: `SIMENV_BROWSER_HOST` (default `localhost`), `SIMENV_WEB_PORT`
(`8080`), `SIMENV_API_PORT` (`8000`), `SIMENV_PLAYBACK_PORT` (`8001`), and
`SIMENV_API_JOB_TIMEOUT` (`300`). Use the configured browser hostname exactly:
`localhost` and `127.0.0.1` are distinct CORS origins. For remote browsers use the
server's browser-reachable hostname, not a Compose service name. API URLs are
build-time frontend settings; rebuild after changing hostnames or ports.

Outside Compose, set both services' `PROVIDER_SIMENV_POSTGRES_URL` to the same
database. Start the simulation API first with that variable set: it initializes
the additive schema before any submission. Then start playback:

```bash
python -m uvicorn provider_simenv.playback.app:app --port 8001
```

Set `SIMENV_PLAYBACK_ALLOWED_ORIGINS` and `SIMENV_API_ALLOWED_ORIGINS` to
comma-separated frontend origins, e.g. `http://localhost:5173`. Configure Vite
with `VITE_PLAYBACK_API_BASE_URL=http://localhost:8001` and
`VITE_SIMENV_API_BASE_URL=http://localhost:8000` for independent direct API access.
Omitting the playback URL explicitly selects **Static demo (exported values)**;
API failures never switch database playback to demo data.

## API and fidelity

```text
GET /runs?limit=50&offset=0
GET /runs/{run_id}/scenarios/{scenario_id}/scene
GET /runs/{run_id}/scenarios/{scenario_id}/frames?start=200&limit=100
GET /health
```

Runs are ordered newest first. Catalogue limits are 1–100; frame limits are
1–500, default 100. Ranges are start-inclusive, end-exclusive and clipped to the
run. Beyond-end requests return empty terminal pages; `next_start` is null at
the end. The browser caches three 100-period pages and prefetches the next page
while playing. It holds its last frame when buffering.

Frames contain `period` and `agents`. Each agent contains `entity_id`, `agent_id`,
`role`, and numeric `values` keyed by metric name. Environment is entity
`environment`, agent 0. Values come from `sim_tick_readable`: no summing,
averaging, rounding, downsampling, or interpolation. Flags remain numeric 0/1.
JSON numbers retain the database's double precision and agents stay distinct.

Globe colours are display-only assessments using the fixed workshop rules below.
They never mutate or replace measurements, and do not depend on page-cache contents
or full-run minimum/maximum values.

Only completed runs with available scenes are playable. New runs store versioned
topology snapshots in PostgreSQL and remain playable if inputs change or
disappear. Legacy runs can use shipped scenarios only when PDL and roster hashes
match; otherwise their unavailability is explained in the selector.

Errors: unknown run/scenario 404; unavailable/incomplete run 409; invalid range
422; database outage 503; corrupt/incomplete committed measurements 500. No
missing values are invented and database credentials are not returned.

## Workshop status and references

**Disturbance impact** combines a compact legend, reference selection and component
inspection. Select a marker or use the keyboard-accessible **Inspect component**
list, including nodes without geographic placement. Details show step, status,
responsible metric/agent, current/reference values, changes and missing evidence.
Pooled geographic markers share their roster node's assessment. Multi-agent nodes
retain the strongest individual metric status, not an average; ties follow stable
agent identity and metric-registry order.

Clicking an icon or its component label opens **Disturbance impact** and updates
the dropdown in place. Clicking an already selected component also reopens
collapsed details, without automatically scrolling or moving focus. Node labels
are native buttons supporting pointer input and Enter/Space; connection labels
remain informational. Decorative connection layers remain visible but do
not intercept marker clicks. Map and dropdown selection use the same owning node
ID, including pooled components, and preserve playback, reference and run selection.

Selection retains both the sidebar's desktop scroll position and the responsive
page position. Scroll anchoring is disabled in these containers, and the inspector
retains its tallest visible content height at the current width so shorter details
cannot clamp a bottom-scrolled position. Hidden/collapsed measurements do not erase
that reservation. It resets on an actual width change or new run/scenario.

A shared English presentation scene supplies node/placement/connection labels,
dropdown options, headings and pooled member names. Exact built-in German names
are normalized using represented entity IDs, including historical roster aliases.
Custom English names are retained. Original recordings, metric values, coordinates
and reference compatibility checks are unaffected.

### Fixed illustrative workshop policy

| Indicator | Adverse evidence | Green | Amber | Red |
| --- | --- | --- | --- | --- |
| Prices | Relative increase | through 5% | 20% | 50% and above |
| Availability / output | Relative decrease | through 5% | 20% | 50% and above |
| Capacity pressure | Absolute recorded fraction | below 80% | 80% | 95% and above |
| Participation | Recorded `active` | active | — | inactive |

Relative colors interpolate green–amber from 5–20% and amber–red from 20–50%.
Capacity is green below 80%, then interpolates amber–red from 80–95%. Improvements
return toward green. These are initial workshop defaults pending domain review,
centrally configured in `web/src/playback/status.ts`; shared palette/interpolation
live in `web/src/design/`. Selection rings and illustrative placement labels do
not change status fill.

Evaluate all role-applicable measurements: asking price and quantity for producers,
wholesalers, processors, feed manufacturers/traders; feed received and livestock
output for consumers; participation where recorded; storage/handling pressure for
wholesalers. Optional processor/manufacturer `input_received` means **input
offered**, while `input_processed` means transformed input. Their relative
decreases contribute to status when supported; `unused_input` is diagnostic only.
Historical optional diagnostics absent on both sides do not imply incomplete data.
One-sided missing diagnostics do. These values cannot establish production-capacity
utilization without a recorded capacity denominator. Storage pressure is not
production utilization or persistent inventory, and low quantity alone does not
establish unmet demand.

Gray means missing measurements, unusable references, incompatible identities,
or insufficient evidence. Relative references must be positive: zero-to-zero is
unknown, not healthy. Zero current availability against a positive reference is
a severe decline. Zero price is **no quote / no contributing volume**, not recovery.
Inactivity and absolute capacity remain evaluable even if references fail.
Known adverse evidence with missing comparisons retains its color and is labeled
**Incomplete evidence**; green-only evidence with missing comparisons is gray.
Expected-agent checks use the first-frame census; the API has no independent
manifest to detect agents absent from every frame.

### Choosing normal

1. Recorded playback defaults to **Disruption-free reference (automatic)**.
   Discovery exhausts catalogue pages and prefers a compatible same-run scenario
   0, then external scenario 0, comparing corresponding periods and exact
   `(entity_id, agent_id, role)` identities. Incompatible candidates are skipped.
2. Workshop API jobs contain **scenario 1 only**. The frontend reads preserved
   inputs through `GET /simulations/{id}/inputs` and searches for a verified
   empty-events scenario 1 with the same canonical non-event PDL, roster and
   engine parameters. A matching queued/running API job is monitored instead of
   being submitted again. Completed history without recorded playback is not
   considered an existing database reference.
3. If no eligible recording or active job exists, the **frontend calls the
   simulation API** to submit a separate job with `events: []` and a declared
   `unshocked_reference` cascade containing `timeline: []`. Non-event declarations,
   economics, roster absence, duration and seed are preserved/checked. The API
   still executes just the single submitted scenario. Comparison waits for both
   completion and playable database results; 100% progress alone is not completion.
   Progress/errors appear in the reference area, with no transient start-relative
   comparison. Accepted parameters are checked again to detect changed defaults.
4. **Relative to scenario start** remains an explicit option in recorded mode.
   This pins the first recorded **end-of-step** frame outside the evictable cache.
   It cannot reveal disturbances already present at the first step. The static
   exported demo uses this mode and retains its legacy exporter aggregation.

External scenario 0 is a **structurally compatible recorded baseline**; its
economic equivalence is not certified. Automatically selected scenario 1 must
have verified empty event definitions/timeline and matching preserved model,
roster and engine settings. Labels are never baseline evidence. Neither path
certifies equal runtime/agent versions. Missing historical inputs or incompatible
current API defaults explain why automatic reproduction is unavailable; today's
defaults are never silently substituted. Static mode never creates a job.

**Retry reference** resumes discovery/monitoring of an accepted job without
resubmitting it. Confirmed failed jobs need explicit retry before replacement;
ambiguous POST outcomes are latched and retries only rediscover possible accepted
work. Discovery outages or incomplete pagination never mean “no baseline exists.”
Source-scoped coordination survives selection changes and StrictMode effects;
deduplication is local to the page/coordinator, not globally exactly-once across
independent clients. Missing data never silently switches comparison mode.
Initial agent censuses must match for a recorded baseline selection. If an agent
later disappears, its assessment is unavailable but exact matches for surviving
agents and unaffected network indicators retain their comparison evidence.
Current and reference frames are published together. During a same-reference seek
or page load, playback holds the last complete pair at its existing displayed step
until both measurements for the requested step are ready; the playback clock waits
too. Cached periods do not insert loading states or gray flashes. Both streams
prefetch their next page. A user pause while waiting remains paused after loading.
Changing source/run/scenario/reference (or retrying a reference) immediately
invalidates old reference evidence. A genuine reference failure settles to explicit
unavailable comparison until **Retry reference**; it does not trigger a new request
at every step. Current-page failures retain the display and stop playback. Details,
markers, connections and all four network indicators always share the displayed
pair, and late responses cannot replace a newer selection or seek.

The bottom indicators use fixed grid cells and tabular numbers. Loading messages
have reserved space, and detail values use separate current/reference/change rows,
so changing text and digit counts do not move the readouts while playing. Long
indicator explanations retain their full accessible text, focus label and tooltip.

### Connections and workshop results

The workshop **Active cascade** control is fixed to **Soy crisis cascade** for
now; its magnitude/timing/mitigation controls remain editable. API/CLI multi-cascade
support and playback of historical energy runs remain supported.

Connections show **inferred upstream status**: inherit only their source node's
assessment. Unknown source means gray, without target fallback or recursive
propagation through unrecorded ports. The four synchronized timeline indicators
are soy price, feed price, total soy supply and average transport utilization.
The last is network-wide; individual route/port utilization is not recorded.

After completion, **View results** searches catalogue pages for the submitted ID
and opens its scenario 1. It never substitutes the newest run. Errors retain the
displayed selection and allow retry. In static mode, configure
`VITE_PLAYBACK_API_BASE_URL` to view database results. The caption identifies
displayed recorded results; later configurator changes are **Unsubmitted edits
for the next run**, separate from the submitted input snapshot.

### Review screenshots

- [Automatic reference preparing](automatic-reference-preparing.png) — the
  frontend's separate job can still be running at 100%; no comparison is shown.
- [Automatic reference ready, soy cascade locked](automatic-reference-ready.png)
  and [day-0 detail comparison](automatic-reference-details.png). These use
  explicitly controlled API/playback fixtures; real-service acceptance separately
  verifies empty-event job creation/reuse. Reproduce from `web/` with
  `SIMENV_WEB_URL=http://127.0.0.1:5175 SIMENV_CAPTURE_BASELINE=1 node --test tests/automatic-reference-browser.test.mjs`.

- [Before: previous static demo interface, step 150](status-before.png) — main
  checkout `9dee6b0`, before issue #75. Different data from the controlled states.
- [Healthy: step 0](status-healthy.png).
- [Disturbed: step 100](status-disturbed.png) — quantity down 50%, price increases,
  and near-full network transport utilization.
- [Recovered: step 250](status-recovered.png) — availability/prices return to reference.
- [Unavailable: step 290](status-unavailable.png) — missing measurements stay gray.
- [Metric breakdown: disturbed step 100](status-details.png) — current/reference
  values and percentage changes in the scrollable inspector.
- [Mobile inspection layout](status-mobile.png).
- [Collapsed impact sidebar](status-sidebar-collapsed.png).
- [Static-demo network with restored connections](status-static-network.png) and
  [the same network with impact collapsed](status-static-network-collapsed.png).
- [Map-label selection with synchronized English details/dropdown](status-map-selection.png).
  Compare the [reader's position immediately before selection](status-label-selection-before.png).

The after screenshots use explicitly **controlled recorded-response fixtures**,
not empirical simulation results. Reproduce from `web/` with Vite configured for
`VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001`:
`SIMENV_WEB_URL=http://127.0.0.1:5175 SIMENV_STATIC_WEB_URL=http://127.0.0.1:5176 node tests/capture-status.mjs`.
The static-network images use the committed demo bundle rather than intercepted
responses. For comparison, the
[previous overlapping layout](https://github.com/PROVIDER-Project/simenv/blob/f216590f2da88b106c2441af1189bff96f1cc00d/docs/status-disturbed.png)
documents the interface before the sidebar correction.
Real-service workshop coverage separately submits and opens two edited soy
configurations and verifies reference creation/reuse.

## Verification

Install `.[dev]` and run against an isolated database:

```bash
SIMENV_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost/test_db \
  python -m pytest tests
```

Most fixtures create private schemas and remove only those schemas; the schema
test also initializes the configured database's default schema. Use a disposable
test database. The integration test submits a real 105-period run, deletes its
private inputs, fetches scenario 1 across pages, and compares every identity/value
to PostgreSQL. Set `PROVIDER_SIMENV_POSTGRES_URL` as well to enable live tick-writer
checks. CSV parity is separately opt-in via `PROVIDER_SIMENV_PARITY_RUN`.

Run `npm run test:tutorial` from `web/` using the
[two-server setup and fixture-origin configuration](../web/README.md#tutorial-browser-check).
It covers first-visit/completion/restart, remembered EN/DE, session dismissal,
keyboard focus, blocked storage, non-submitting navigation, selected-run/time
preservation and responsive target reachability. The static case is skipped
unless `SIMENV_STATIC_WEB_URL` is supplied. These fixtures do not replace
real-service simulation acceptance.

Run `npm run test:responsive-playback` from `web/` with `SIMENV_WEB_URL` and
`SIMENV_TEST_PLAYBACK_ORIGIN` set as in the tutorial setup. This separate
controlled-fixture suite checks responsive column geometry, control reachability,
width/height boundary defaults, explicit choices across resizing and selection
remounts, and temporary EN/DE tutorial indicator reveal/restoration. It needs
Chromium and a recorded-mode Vite server, not a live database or API.

From `web/`, run `npm run test:playback`. For browser tests, start Vite with
`VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001` and run
`npm run test:playback-browser`; these browser checks intercept API responses,
as does the separate tutorial suite.
`npm run test:simulation` uses real APIs: set `SIMENV_WEB_URL` to the running
stack. It submits two edited soy configurations, verifies catalogue refresh, opens each exact
completed run via **View results**, and seeks into a later database page. Status
browser regressions cover day-0 comparison, recovery, missing/reference failures,
keyboard inspection, reference switching/refresh, delayed responses, cache eviction
and exact-ID pagination/retry. Edge-bearing globe regressions inspect finite
THREE curve geometry and RGBA buffers, geographic endpoints, and visible canvas
pixels through healthy/disturbed/recovered/unknown states and run/scenario changes.
Sidebar regressions cover independent collapse, continuous playback and resizing.
Continuous commit/animation-frame observation checks no transient unknown status,
stable desktop/mobile readout bounds, and coherent holding at delayed current and
reference page boundaries. Loader regressions cover sticky failures, explicit retry,
cache inspection/disposal and superseded-request failures.
Static-demo verification requires a Vite server
without `VITE_PLAYBACK_API_BASE_URL`; no database fallback is implicit.
Set `SIMENV_STATIC_WEB_URL` to that second server when running
`npm run test:playback-browser` to include its static-demo acceptance case;
without this setting that case is explicitly skipped.

### Frontend-versus-API performance

Build a production frontend with playback URL `http://127.0.0.1:8001`, serve
with `npm run preview`, then run
`SIMENV_WEB_URL=http://127.0.0.1:4173 npm run test:playback-performance`.
The Playwright test records browser/hardware configuration, warm-up and three
trials, p50/p95 durations, input-to-paint latency and main-thread long tasks.
Transport/body transfer, decoding, validation, cache insertion, frame calculation
and commit-to-next-paint are measured separately. Commit-to-paint is a scheduling
proxy, not a GPU timer; development builds additionally report React CPU time.

Fixtures contain 45 agents and 1,000 agents × 13 metrics × 300 periods, preserving
identities/precision in 100-period responses. The 16.7 ms calculation budget and
100 ms interaction target are investigation thresholds, not CI timing assertions.

Initial production results: Chromium 153, Intel Xeon w7-3455, 48 logical CPUs,
no CPU throttling, headless software rendering:

| p95 (ms) | 45 agents | 1,000 agents |
| --- | ---: | ---: |
| Frame calculation | 0.6 | 8.0 |
| JSON decoding (also includes small metadata responses) | 15.8 | 228.2 |
| Validation | 4.9 | 149.7 |
| Commit to next paint | 24.5 | 14.8 |
| Input to paint | 173.8 | 97.1 |

**Placement decision:** keep visual arithmetic in the browser: measured cost
is below the frame budget. Large-payload parsing/validation and software globe
rendering are the bottlenecks. Moving arithmetic to the API would not eliminate
them and would increase response size if raw measurements remain. Larger
deployments should investigate worker decoding or smaller windows first. The
representative interaction target was exceeded on this headless renderer; this
is reported rather than labelled a performance pass. Repeat on target hardware.

A real stack run's 100-period query used existing run-agent/tick indexes and
returned 4,000 metric rows in 14.9 ms (`EXPLAIN (ANALYZE, BUFFERS)`). No new index
was justified.

The performance test also supports `SIMENV_REAL_WEB_URL` pointing to a stack
with a completed run. This trial uses its persisted topology and real API
responses (no intercepted data). A recorded 16-node, 16-edge run measured p95
projection 0.6 ms, decoding 0.9 ms, validation 6.8 ms, commit-to-paint 70.2 ms,
and input-to-paint 186.3 ms in the same headless environment. This confirms
rendering/scheduling, rather than frame arithmetic, dominates that run; the
interaction target is not met there either. Reproduce both synthetic and real
trials with:

```bash
SIMENV_WEB_URL=http://127.0.0.1:4173 \
SIMENV_REAL_WEB_URL=http://localhost:8080 npm run test:playback-performance
```
