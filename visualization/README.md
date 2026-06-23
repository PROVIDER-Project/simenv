# Supply Chain HQ Map — visualization (GitHub issue #21)

A self-contained Qt visualization of the PROVIDER supply-chain simulation: a
geographic "headquarters" map where nodes are simulation components and animated
flows are transports along the BRA / ARG / USA → EU corridors, with a timeline
you can play to watch the run evolve.

This is the **QT-suitability proof of concept** for issue #21 (try Qt; fall back
to web if Qt can't do it cleanly). See [NOTES.md](NOTES.md) for the verdict.

It **reads** the simulation's CSV output through a data-access layer and may
**run** the sim via subprocess. It never imports or modifies `provider_simenv`.

## Install

From the repo root, using the project venv:

```
.\.venv\Scripts\python.exe -m pip install -r visualization\requirements.txt
```

(`matplotlib` is only needed for the price side-chart.)

## Run

```
.\.venv\Scripts\python.exe -m visualization.app.main
```

If there is no simulation output yet, use **Run simulation** in the app (or run
`python -m provider_simenv.main` yourself), then the map populates.

## Controls

- **Scenario** — pick `id_scenario` (0 baseline / 1 PDL shock).
- **Timeline** — play / pause, step ‹ ›, seek slider, speed (0.5–4×).
- **Run simulation / Reload output** — runs `python -m provider_simenv.main
  [--pdl <file>]` via QProcess, streams the log, reloads the map on finish.
- **Price chart** — soja/feed price over the whole scenario with a playhead.

## Architecture

```
visualization/
  config/layout.py     # geographic projection, node/route geometry, country load
  data/
    models.py          # frozen value objects crossing the seam
    source.py          # DataSource Protocol  <- the seam the views depend on
    csv_source.py      # CsvDataSource (pandas) — the only CSV/pandas code
  app/
    main.py            # window, controls, entrypoint
    map_view.py        # QGraphicsScene/View: countries, nodes, routes, HUD, ships
    nodes.py  hud.py  ships.py  timeline.py  chart.py  runner.py
  assets/
    world_countries.geojson   # Natural Earth 50m (public domain), Atlantic region
```

**The seam:** every view widget depends only on `data.source.DataSource` and the
frozen models — never on pandas/CSV. `CsvDataSource` is today's implementation;
a future `PostgresDataSource` (reading per-tick rows from `tick_writer.py`) is a
drop-in swap with zero view changes. See [NOTES.md](NOTES.md).
