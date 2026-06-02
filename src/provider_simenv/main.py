"""
v.0.5.1 notes:
- Melodie writes CSVs (data_output_type default)
- csv_to_sqlite() post-processes all Result_Simulator_*.csv files into a single SQLite database
- This avoids the SQAlchemy 2.0 missing-commit but in Melodie's built-in sqlite mode,
  while still providing a SQLite file for visualize_sql.py
"""
import glob
import os
import sqlite3
import shutil
import argparse

import pandas as pd

from Melodie import Config, Simulator
from scipy.constants import value

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.pdl_loader import PDLLoader

_PDL_TIMING_COLUMNS = {
      "farm_capacity_bra":       ("shock_onset_farm_bra",       "shock_end_farm_bra"),
      "farm_capacity_arg":       ("shock_onset_farm_arg",       "shock_end_farm_arg"),
      "port_capacity_santos":    ("shock_onset_port_santos",    "shock_end_port_santos"),
      "port_capacity_paranagua": ("shock_onset_port_paranagua", "shock_end_port_paranagua"),
      "port_capacity_rotterdam": ("shock_onset_port_rotterdam", "shock_end_port_rotterdam"),
      "port_capacity_hamburg":   ("shock_onset_port_hamburg",   "shock_end_port_hamburg"),
      "fertilizer_price_factor": ("shock_onset_fertilizer",     "shock_end_fertilizer"),
      "energy_price_factor":     ("shock_onset_energy",         "shock_end_energy"),
      "oil_mill_capacity":       ("shock_onset_oil_mill",       "shock_end_oil_mill"),
      "feed_mill_capacity":      ("shock_onset_feed_mill",      "shock_end_feed_mill"),
}
# --------------------
# Helpers
# --------------------

def csv_to_sqlite(output_dir: str, db_name: str = "provider-simenv.sqlite") -> None:
    """
    Read every Result_Simulator_*.csv file in output_dir, convert it to SQLite database
    Uses sqlite3 + pandas directly - no SQAlchemy
    The database is recreated from scratch on every run (replace mode)
    """
    db_path = os.path.join(output_dir, db_name)
    pattern = os.path.join(output_dir, "Result_Simulator_*.csv")
    csv_files = glob.glob(pattern)

    if not csv_files:
        print("[csv_to_sqlite] WARNING: no Result_Simulator_*.csv files found in:")
        print("                " + output_dir)
        return

    conn = sqlite3.connect(db_path)
    try:
        for csv_path in csv_files:
            table_name = os.path.splitext(os.path.basename(csv_path))[0]
            df = pd.read_csv(csv_path)
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            print(f"[csv_to_sqlite] {table_name} -> {len(df)} rows")
        conn.commit()
    finally:
        conn.close()

    print(f"[csv_to_sqlite] SQLite database written to:")
    print("                 " + db_path)



# --------------------
# Main
# --------------------

if __name__ == "__main__":

    # CLI arguments
    parser = argparse.ArgumentParser(description="PROVIDER supply chain simulation")
    parser.add_argument(
        "--pdl",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Path to a PDL YAML scenario file (e.g. scenarios/s1-soja.pdl.yaml)."
            "When given, shock parameters in SimulatorScenarios.csv are replaced "
            "with values derived from the PDL before the simulation runs."
        ),
    )
    parser.add_argument(
        "--postgres-url",
        type=str,
        default=None,
        metavar="URL",
        help=(
            "Optional PostgreSQL SQLAlchemy connection string for tick writes, "
            "e.g. postgresql+psycopg2://user:pass@host:5432/dbname"
            ),
        )
    parser.add_argument(
        "--cascade",
        type=str,
        default=None,
        metavar="ID",
        help=(
            "PDL cascade id to use for timing. Defaults to the first cascade in the PDL file."
        ),
    )

    args = parser.parse_args()

    if args.postgres_url:
        os.environ["PROVIDER_SIMENV_POSTGRES_URL"] = args.postgres_url
        print("[main] Using PostgreSQL connection string from --postgres-url")

    # Folder paths (both needed for PDL injection and Config)
    here = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(here, "data", "input")
    output_folder = os.path.join(here, "data", "output")
    csv_path = os.path.join(input_folder, "SimulatorScenarios.csv")
    template_path = os.path.join(input_folder, "SimulatorScenarios_template.csv")

    # Always restore the working CSV from the template before every run.
    # This prevents previous PDL runs from contaminating the baseline values.
    if os.path.exists(template_path):
        shutil.copy2(template_path, csv_path)

    # PDL Injection: update shock columns in SimulatorScenarios.csv
    if args.pdl:
        loader = PDLLoader(args.pdl)
        schedule = loader.to_cascade_schedule(args.cascade)
        all_overrides = loader.to_scenario_overrides()
        overrides = {
            param: value
            for param, value in all_overrides.items()
            if param in schedule
        }

        print(f"\n[pdl_loader] Scenario : {loader.label}")
        print(f"[pdl_loader] Source : {args.pdl}")
        print(f"[pdl_loader] Cascade: {args.cascade or 'first cascade in file'}")
        print("[pdl_loader] Overrides applied to SimulatorScenarios.csv (id > 0):")
        for col, val in overrides.items():
            print(f"{col} = {val}")

        df = pd.read_csv(csv_path)

        # keep only the baseline row (id=0)
        baseline = df[df["id"] == 0].copy()

        # build exactly one PDL scenario row from the baseline
        pdl_row = baseline.iloc[0].copy()
        pdl_row["id"] = 1

        # apply shock value override
        for col, val in overrides.items():
            if col in df.columns:
                pdl_row[col] = val
            else:
                print(f"[pdl_loader] WARNING: column {col} not found, skipping")

        # apply cascade timing
        print("[pdl_loader] Cascade timing applied to PDL scenario row (id=1):")
        for param, timing in schedule.items():
            fields = _PDL_TIMING_COLUMNS.get(param)
            if fields is None:
                continue
            onset_col, end_col = fields
            pdl_row[onset_col] = timing["onset"]
            pdl_row[end_col] = timing["end"]
            print(
                f"    {param}: "
                f"{onset_col}={timing['onset']}, {end_col}={timing['end']}"
            )

        df = pd.concat([baseline, pdl_row.to_frame().T], ignore_index=True)
        for col in baseline.select_dtypes(include="int64").columns:
            df[col] = df[col].astype(int)
        df.to_csv(csv_path, index=False)
        print(f"[pdl_loader] CSV updated (baseline + 1 PDL scenario). \n")


    config = Config(
        project_name= "provider-simenv",
        project_root= here,
        input_folder= input_folder,
        output_folder= output_folder,
    )

    simulator = Simulator(
        config=config,
        scenario_cls=SupplyChainScenario,
        model_cls=SupplyChainModel,
    )
    simulator.run()

    # post-process: merge CSVs -> SQLite for visualize_sql.py
    print("\n[main] Converting CSVs to SQLite...")
    csv_to_sqlite(output_folder)
