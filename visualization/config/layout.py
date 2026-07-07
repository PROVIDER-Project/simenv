"""Geographic map layout — real-world lat/long positions, projected to canvas.

Nodes sit at their approximate real locations (BRA farms over Brazil, Santos on
the Brazilian coast, Rotterdam/Hamburg in NW Europe, etc.). This is NOT GIS:
positions are hand-chosen approximations and the coastlines are coarse. The map
view paints GEO_NOTE on-screen so nobody mistakes it for an accurate map.

Source of truth is geographic (lat, lon). At import we project everything to
canvas pixels via an undistorted equirectangular projection (a single uniform
scale, centered), so downstream view code keeps consuming GROUP_ANCHORS / PORTS
/ ROUTES in pixels exactly as before — only their values are now geographic.

Pure config/geometry: no Qt, no pandas, no DataSource import.
Convention: lat north-positive, lon east-positive; canvas x right, y down.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# Logical scene size; the view scales this to the widget.
CANVAS_W = 1000
CANVAS_H = 620

GEO_NOTE = "Approximate geographic positions — not GIS accurate"

# Atlantic-centered geographic window: Americas (west) to Europe/Africa (east).
LON_MIN, LON_MAX = -105.0, 25.0
LAT_MIN, LAT_MAX = -56.0, 62.0


def project(lat: float, lon: float) -> tuple[float, float]:
    """Equirectangular projection, uniform scale, centered (no distortion)."""
    span_lon = LON_MAX - LON_MIN
    span_lat = LAT_MAX - LAT_MIN
    scale = min(CANVAS_W / span_lon, CANVAS_H / span_lat)
    off_x = (CANVAS_W - span_lon * scale) / 2.0
    off_y = (CANVAS_H - span_lat * scale) / 2.0
    x = off_x + (lon - LON_MIN) * scale
    y = off_y + (LAT_MAX - lat) * scale   # north is up
    return (x, y)


# --- Geographic source of truth (lat, lon) -------------------------------

# Group cluster centers at approximate real regions. Source farms at their
# growing regions; EU processing-side nodes have NO location in the sim data,
# so these are plausible NW-Europe placements (labeled approximate in NOTES).
_GROUP_GEO: dict[str, tuple[float, float]] = {
    "UsaFarmers": (42.0, -93.0),    # US Midwest (Iowa)
    "BraFarmers": (-13.0, -56.0),   # Mato Grosso (center-west soy belt)
    "ArgFarmers": (-34.0, -62.0),   # Pampas
    "Wholesalers": (-23.0, -47.0),  # São Paulo region (SA market/collection hub)
    # EU processing-side nodes have NO location in the sim data; spread across
    # NW/Central Europe purely for legibility (illustrative).
    "Processors": (52.0, 4.5),          # Netherlands (near Rotterdam)
    "FeedManufacturers": (52.5, 13.0),  # NE Germany
    "FeedTraders": (47.5, 16.0),        # Austria region
    "EuFarmers": (46.5, 2.5),           # central France (EU livestock)
}

# Ports as (lat, lon, role). Waypoints on the corridors, not data nodes.
_PORTS_GEO: dict[str, tuple[float, float, str]] = {
    "USA-Gulf": (30.0, -90.0, "export"),    # New Orleans
    "Santos": (-24.0, -46.3, "export"),     # santos_share of BRA flow (approx)
    "Paranagua": (-25.5, -48.5, "export"),  # 1 - santos_share (approx)
    "ARG": (-34.0, -58.4, "export"),        # Rosario / Buenos Aires
    "Rotterdam": (51.95, 4.14, "import"),
    "Hamburg": (53.55, 9.99, "import"),
}

# Ship corridors as (lat, lon) waypoints, port-to-port and routed through OPEN
# OCEAN ONLY — they start at the export port, arc across the Atlantic well west
# of Africa, and approach the EU north-about (around Scotland into the North
# Sea), so ships never cross land. These drive the animated ships; no route line
# is drawn. The Santos/Paranagua split is an approximation (no per-port data).
_ROUTES_GEO: dict[str, list[tuple[float, float]]] = {
    "BRA": [(-24.0, -46.3), (-32.0, -38.0), (-12.0, -26.0), (12.0, -28.0),
            (38.0, -28.0), (52.0, -22.0), (58.0, -14.0), (60.0, -5.0),
            (60.0, 3.0), (56.0, 4.0), (53.0, 4.0), (51.95, 4.14)],
    "ARG": [(-34.0, -58.4), (-42.0, -48.0), (-18.0, -30.0), (8.0, -28.0),
            (34.0, -28.0), (52.0, -22.0), (58.0, -14.0), (60.0, -5.0),
            (60.0, 3.0), (56.0, 4.0), (53.0, 4.0), (51.95, 4.14)],
    "USA": [(30.0, -90.0), (27.0, -86.0), (24.5, -80.0), (27.0, -70.0),
            (40.0, -48.0), (52.0, -26.0), (59.0, -10.0), (62.0, -2.0),
            (61.0, 4.0), (57.0, 5.0), (54.5, 8.2)],
}

# Real country outlines come from a bundled Natural Earth 50m GeoJSON (public
# domain), trimmed to the Atlantic region. Loaded and projected at import.
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_COUNTRIES_FILE = _ASSETS_DIR / "world_countries.geojson"


def _iter_rings(geometry: dict) -> list[list[list[float]]]:
    """Return every ring (outer + holes) of a Polygon/MultiPolygon geometry.

    Each ring is a list of [lon, lat] pairs (GeoJSON order).
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        return list(coords)
    if gtype == "MultiPolygon":
        return [ring for poly in coords for ring in poly]
    return []


def load_country_shapes() -> dict[str, list[list[tuple[float, float]]]]:
    """Load the bundled world-countries GeoJSON, projected, keyed by name.

    Returns {country_name: [ring, ...]} where each ring is a list of (x, y).
    The map view draws all rings as filled land and recolors named regions for
    the drought heatmap. Offline only: reads the local asset; returns {} if it
    is missing so the app still renders (ocean only) without it.
    """
    if not _COUNTRIES_FILE.exists():
        return {}
    data = json.loads(_COUNTRIES_FILE.read_text(encoding="utf-8"))
    shapes: dict[str, list[list[tuple[float, float]]]] = {}
    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        name = feat.get("properties", {}).get("name", "")
        projected = [
            [project(lat, lon) for lon, lat in ring] for ring in _iter_rings(geom)
        ]
        shapes.setdefault(name, []).extend(projected)
    return shapes


# --- Projected to canvas pixels (what the view consumes) -----------------

GROUP_ANCHORS: dict[str, tuple[float, float]] = {
    g: project(lat, lon) for g, (lat, lon) in _GROUP_GEO.items()
}

PORTS: dict[str, tuple[float, float, str]] = {
    name: (*project(lat, lon), role) for name, (lat, lon, role) in _PORTS_GEO.items()
}

ROUTES: dict[str, list[tuple[float, float]]] = {
    origin: [project(lat, lon) for lat, lon in pts]
    for origin, pts in _ROUTES_GEO.items()
}

COUNTRY_SHAPES: dict[str, list[list[tuple[float, float]]]] = load_country_shapes()
COUNTRY_POLYGONS: list[list[tuple[float, float]]] = [
    ring for rings in COUNTRY_SHAPES.values() for ring in rings
]

# --- Country label layout (centroid, area tier) ---------------------------

_COUNTRY_SHORT: dict[str, str] = {
    "United States of America": "United States",
    "United Kingdom": "UK",
    "Dem. Rep. Congo": "DR Congo",
    "Central African Rep.": "CAR",
    "Dominican Rep.": "Dominican Rep.",
    "Eq. Guinea": "Eq. Guinea",
    "S. Geo. and the Is.": "S. Georgia",
    "St. Vin. and Gren.": "St Vincent",
    "St. Kitts and Nevis": "St Kitts",
    "Antigua and Barb.": "Antigua",
    "Turks and Caicos Is.": "Turks & Caicos",
    "British Virgin Is.": "British Virgin Is.",
    "U.S. Virgin Is.": "U.S. Virgin Is.",
    "St. Pierre and Miquelon": "St Pierre",
    "Bosnia and Herz.": "Bosnia",
    "North Macedonia": "N. Macedonia",
    "Côte d'Ivoire": "Côte d'Ivoire",
    "São Tomé and Principe": "São Tomé",
}


def _ring_area(ring: list[tuple[float, float]]) -> float:
    if len(ring) < 3:
        return 0.0
    area = 0.0
    for i, (x0, y0) in enumerate(ring):
        x1, y1 = ring[(i + 1) % len(ring)]
        area += x0 * y1 - x1 * y0
    return abs(area) * 0.5


def _ring_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    if len(ring) < 3:
        return ring[0] if ring else (0.0, 0.0)
    cx = cy = signed = 0.0
    for i, (x0, y0) in enumerate(ring):
        x1, y1 = ring[(i + 1) % len(ring)]
        cross = x0 * y1 - x1 * y0
        signed += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(signed) < 1e-6:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    signed *= 0.5
    return (cx / (6.0 * signed), cy / (6.0 * signed))


def _ring_intersects_canvas(ring: list[tuple[float, float]]) -> bool:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return not (max(xs) < 0 or min(xs) > CANVAS_W or max(ys) < 0 or min(ys) > CANVAS_H)


def country_display_name(name: str) -> str:
    return _COUNTRY_SHORT.get(name, name)


def build_country_labels() -> list[dict[str, float | int | str]]:
    """Centroids + area tiers for countries visible in the Atlantic viewport."""
    entries: list[tuple[str, float, float, float]] = []
    for name, rings in COUNTRY_SHAPES.items():
        visible_rings = [r for r in rings if len(r) >= 3 and _ring_intersects_canvas(r)]
        if not visible_rings:
            continue
        main_ring = max(visible_rings, key=_ring_area)
        area = _ring_area(main_ring)
        if area < 80.0:
            continue
        cx, cy = _ring_centroid(main_ring)
        if cx < 0 or cx > CANVAS_W or cy < 0 or cy > CANVAS_H:
            continue
        entries.append((name, cx, cy, area))
    entries.sort(key=lambda item: item[3], reverse=True)
    labels: list[dict[str, float | int | str]] = []
    for rank, (name, cx, cy, area) in enumerate(entries):
        if rank < 25:
            tier = 1
        elif rank < 75:
            tier = 2
        else:
            tier = 3
        labels.append({
            "name": name,
            "display": country_display_name(name),
            "x": cx,
            "y": cy,
            "tier": tier,
            "area": area,
        })
    return labels


COUNTRY_LABELS: list[dict[str, float | int | str]] = build_country_labels()

# Soja-source regions tinted by the drought heatmap. The data's drought_severity
# is GLOBAL (no per-region values), so all source regions are tinted by the same
# value — labeled approximate in NOTES.
DROUGHT_REGIONS = ("Brazil", "Argentina", "United States of America")

# Default scenario constant for the Santos/Paranagua visual split (see
# scenario.py santos_share = 0.7). Labeled "approx" wherever shown.
SANTOS_SHARE_APPROX = 0.7


def fan_out(
    anchor: tuple[float, float],
    n: int,
    *,
    per_row: int = 5,
    dx: float = 22.0,
    dy: float = 22.0,
) -> list[tuple[float, float]]:
    """Deterministically place n agents in a small grid centered on `anchor`.

    Positions depend only on n and the anchor (never on data), so nodes stay put
    across periods. Returns n (x, y) points in canvas pixels.
    """
    if n <= 0:
        return []
    ax, ay = anchor
    rows = math.ceil(n / per_row)
    points: list[tuple[float, float]] = []
    for i in range(n):
        row = i // per_row
        col = i % per_row
        in_row = min(per_row, n - row * per_row)
        x = ax + (col - (in_row - 1) / 2) * dx
        y = ay + (row - (rows - 1) / 2) * dy
        points.append((x, y))
    return points
