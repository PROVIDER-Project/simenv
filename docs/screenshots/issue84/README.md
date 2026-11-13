# Issue84 — controlled-fixture UI evidence

**These screenshots use controlled API fixtures, not actual empirical simulation
results.** The fixtures exercise the real before/after UI and renderer. They do
not establish throughput loss, downstream harm, or an economic simulation result.

## Screens

| Image | State and expected difference |
| --- | --- |
| [Before113f3b8](santos-capacity-loss-Before113f3b8.png) | Day 100, Santos selected. Historical recording contract: no port agent rows, `hasRecordedData: false`. Port status and marker are unavailable/gray; the temporary wholesaler-based ocean coloring is green because the wholesaler is healthy. |
| [AfterIssue84](santos-capacity-loss-AfterIssue84.png) | Matched day 100, Santos selected. Port rows and `hasRecordedData: true` expose an 80% effective-capacity loss. The responsible metric is effective transport capacity; the Santos marker and Santos → Rotterdam ocean arc are red even though the wholesaler remains healthy. |
| [AfterIssue84 recovery](santos-recovered-AfterIssue84.png) | Day 250, Santos selected. Effective capacity has recovered to 500; the port and its outgoing ocean arc are green. Output remains 70. |

Both versions use the same six nodes, geographic coordinates, five routes,
endpoint identities, connection labels, Atlantic camera, and 1600 × 1100 viewport.
The graph retains the original farm → wholesaler → export-port → import-port
structure; no marker or route is collapsed or replaced. The configurator is
collapsed because its unsubmitted edits do not describe the controlled history.
The existing inspector is scrolled to expose status and, after the fix, metrics.

## Controlled measurements

The selected run is `first`, scenario 1, paused at day/step 100. The explicit
reference is run `first`, unshocked scenario 0, at the corresponding recorded
period. Capacity loss is present on days 50–199; recovery is shown at day 250.

| Santos measurement | Reference | During capacity loss | Recovery |
| --- | ---: | ---: | ---: |
| Nominal capacity, diagnostic only | 500 | 500 | 500 |
| Effective capacity | 500 | 100 | 500 |
| Transport output available | 70 | 70 | 70 |
| Output asking price | 100 | 100 | 100 |
| Utilisation | 0.14 | 0.70 | 0.14 |
| Active | 1 | 1 | 1 |

The before fixture deliberately omits these port measurements, matching the old
backend's missing recording rather than sending new port rows to old UI code.
The healthy wholesaler has asking price 100, quantity available 100, and
storage/handling utilisation 0.20 in both scenarios and both versions. Other
ports remain unrecorded; after the fix their outgoing arcs remain gray.

## Reproduce

Prerequisites: existing `web/node_modules` with Playwright and its Chromium
browser, plus two running Vite servers. Start each command in the specified
directory in a separate terminal:

```bash
# .worktrees/84-port-data-before/web (clean origin/main at 113f3b8)
VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 15886 --strictPort

# .worktrees/84-port-data-congestion/web (Issue84 working tree)
VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 15884 --strictPort
```

Run from `.worktrees/84-port-data-congestion/web`:

```bash
SIMENV_BASELINE_WEB_URL=http://127.0.0.1:15886 \
SIMENV_WEB_URL=http://127.0.0.1:15884 \
SIMENV_TEST_PLAYBACK_ORIGIN=http://127.0.0.1:8001 \
node tests/capture-port-recording.mjs
```

These URLs are also the script defaults. The API origin is intercepted by the
existing `mockPlayback` pattern; no database or running API is required. The
script assumes local Linux Vite processes so it can verify their `/proc` working
directories before capturing. `SIMENV_BASELINE_SOURCE` can override the sibling
before worktree path.

## Verification

The command above passed. Before capture, the script confirmed:

- `15886` serves `.worktrees/84-port-data-before/web`, with clean Git state and
  HEAD pinned to `113f3b8` (the `origin/main` revision at capture time).
- `15884` serves `.worktrees/84-port-data-congestion/web`.
- Each served status module's Vite source-map content exactly matches its source
  file; only the after module contains the effective transport capacity registry.

Capture assertions passed for selected day/reference, before/after status,
responsible metric and agent, unchanged output and price, utilisation,
participation, nominal capacity, healthy wholesaler, source-port marker colors,
all three ocean arc layers, both ocean routes' geographic endpoints, and exact
before/after marker/route/label preservation. Recovery status and renderer color
assertions passed too. State readiness uses UI/period waits; the sole fixed delay
is a 700 ms rendering settle before each screenshot.

The screenshots were visually reviewed for fixture labels, readable inspector
measurements, and visible ocean color differences. Repository-wide verification
is handled by the main Issue84 task; this evidence capture does not claim those
checks. Documentation for the evidence and capture command is contained here.
