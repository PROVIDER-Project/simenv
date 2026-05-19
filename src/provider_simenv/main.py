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

from .model import SupplyChainModel
from .scenario import SupplyChainScenario
from .pdl_loader import PDLLoader

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
    args = parser.parse_args()

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
        overrides = loader.to_scenario_overrides()

        print(f"\n[pdl_loader] Scenario : {loader.label}")
        print(f"[pdl_loader] Source : {args.pdl}")
        print("[pdl_loader] Overrides applied to SimulatorScenarios.csv (id > 0):")
        for col, val in overrides.items():
            print(f"{col} = {val}")

        df = pd.read_csv(csv_path)
        shocked = df["id"] > 0
        for col, val in overrides.items():
            if col in df.columns:
                df.loc[shocked, col] = val
            else:
                print(f"[pdl_loader] WARNING: column '{col}' not found in CSV - skipped")
        df.to_csv(csv_path, index=False)
        print(f"[pdl_loader] CSV updated. \n")


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
