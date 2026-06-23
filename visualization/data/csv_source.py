"""CsvDataSource — the pandas-backed DataSource (temporary CSV fallback).

This is the ONLY module in the visualization package that imports pandas or
knows the CSV layout. Everything pandas-shaped stays behind the DataSource
Protocol; callers receive only the frozen value objects from `models`.

Reads Result_Simulator_*.csv from the simulation's output directory (default:
src/provider_simenv/data/output/). Files are loaded lazily on first access and
cached for the life of the instance; call reload() after a fresh sim run.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import EnvState, NodeThroughput, OriginFlows

# Default location of the sim's CSV output, relative to the repo root. The repo
# root is three parents up from this file: visualization/data/csv_source.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "src" / "provider_simenv" / "data" / "output"

# Entity groups whose CSV carries an `active` column (farmers gray-out on False).
_FARMER_GROUPS = ("BraFarmers", "ArgFarmers", "UsaFarmers", "EuFarmers")
# Entity groups with quantity_available + unit_price but no `active` column.
# Wholesalers also carry bra/arg/usa volume columns (used by origin_flows).
_OTHER_GROUPS = ("Wholesalers", "Processors", "FeedManufacturers", "FeedTraders")
ALL_GROUPS = _FARMER_GROUPS + _OTHER_GROUPS

# Declared field-to-column mapping for NodeThroughput, per group:
#   group -> (quantity_column, price_column_or_None)
# Most groups expose soja quantity_available + unit_price. EuFarmers are
# livestock consumers: their throughput is livestock_output and they have no
# price (mapped to None). Declared explicitly rather than inferred by name.
_GROUP_COLUMNS: dict[str, tuple[str, str | None]] = {
    "BraFarmers": ("quantity_available", "unit_price"),
    "ArgFarmers": ("quantity_available", "unit_price"),
    "UsaFarmers": ("quantity_available", "unit_price"),
    "EuFarmers": ("livestock_output", None),
    "Wholesalers": ("quantity_available", "unit_price"),
    "Processors": ("quantity_available", "unit_price"),
    "FeedManufacturers": ("quantity_available", "unit_price"),
    "FeedTraders": ("quantity_available", "unit_price"),
}


class MissingOutputError(FileNotFoundError):
    """Raised when the expected CSV output is not present on disk."""


class CsvDataSource:
    """DataSource implementation reading Result_Simulator_*.csv via pandas."""

    def __init__(self, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = Path(output_dir)
        self._cache: dict[str, pd.DataFrame] = {}

    # -- loading -----------------------------------------------------------

    def _path(self, group: str) -> Path:
        return self._output_dir / f"Result_Simulator_{group}.csv"

    def _frame(self, group: str) -> pd.DataFrame:
        """Return the cached DataFrame for one group's CSV, loading on demand."""
        if group not in self._cache:
            path = self._path(group)
            if not path.exists():
                raise MissingOutputError(f"Expected output file not found: {path}")
            self._cache[group] = pd.read_csv(path)
        return self._cache[group]

    def reload(self) -> None:
        """Drop all cached frames so the next read re-reads from disk.

        Called by the view after a 'Run simulation' / 'Reload output' action.
        """
        self._cache.clear()

    def is_available(self) -> bool:
        """True if the Environment CSV exists (cheap missing-output guard)."""
        return self._path("Environment").exists()

    # -- DataSource Protocol ----------------------------------------------

    def scenarios(self) -> list[int]:
        env = self._frame("Environment")
        return sorted(int(s) for s in env["id_scenario"].unique())

    def periods(self, scenario: int) -> list[int]:
        env = self._frame("Environment")
        rows = env[env["id_scenario"] == scenario]
        return sorted(int(p) for p in rows["period"].unique())

    def environment_at(self, scenario: int, period: int) -> EnvState:
        env = self._frame("Environment")
        row = env[(env["id_scenario"] == scenario) & (env["period"] == period)]
        if row.empty:
            raise KeyError(f"No Environment row for scenario={scenario} period={period}")
        r = row.iloc[0]
        return EnvState(
            scenario=scenario,
            period=period,
            soja_price=float(r["soja_price"]),
            feed_price=float(r["feed_price"]),
            shock_scale=float(r["shock_scale"]),
            drought_severity=float(r["drought_severity"]),
            total_soja_supply=float(r["total_soja_supply"]),
            transport_utilisation=float(r["transport_utilisation"]),
            current_step=int(r["current_step"]),
        )

    def node_throughput(self, scenario: int, period: int) -> list[NodeThroughput]:
        out: list[NodeThroughput] = []
        for group in ALL_GROUPS:
            df = self._frame(group)
            rows = df[(df["id_scenario"] == scenario) & (df["period"] == period)]
            qty_col, price_col = _GROUP_COLUMNS[group]
            has_active = "active" in df.columns
            for _, r in rows.iterrows():
                out.append(
                    NodeThroughput(
                        group=group,
                        id=int(r["id"]),
                        quantity=float(r[qty_col]),
                        unit_price=float(r[price_col]) if price_col else None,
                        active=bool(r["active"]) if has_active else True,
                    )
                )
        return out

    def origin_flows(self, scenario: int, period: int) -> OriginFlows:
        w = self._frame("Wholesalers")
        rows = w[(w["id_scenario"] == scenario) & (w["period"] == period)]
        return OriginFlows(
            scenario=scenario,
            period=period,
            bra_volume=float(rows["bra_volume"].sum()),
            arg_volume=float(rows["arg_volume"].sum()),
            usa_volume=float(rows["usa_volume"].sum()),
        )
