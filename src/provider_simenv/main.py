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

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.pdl_loader import PDLLoader

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

    # PDL Injection: a PDL run adds one shock scenario row (id=1) to SimulatorScenario.csv
    # Shock values and timing are derived at runtime by the EventTracker from the PDL itself
    if args.pdl:
        loader = PDLLoader(args.pdl)

        print(f"\n[pdl_loader] Scenario: {loader.label}")
        print(f"\n[pdl_loader] Source: {args.pdl}")
        print(f"\n[pdl_loader] Cascade: {args.cascade or 'first cascade in file'}")

        df = pd.read_csv(csv_path)

        # keep only the baseline row (id=0)
        baseline = df[df["id"] == 0].copy()

        # build exactly one PDL scenario row from the baseline (shocks injected at runtime)
        pdl_row = baseline.iloc[0].copy()
        pdl_row["id"] = 1

        df = pd.concat([baseline, pdl_row.to_frame().T], ignore_index=True)
        for col in baseline.select_dtypes(include="int64").columns:
            df[col] = df[col].astype(int)
        df.to_csv(csv_path, index=False)
        print(f"[pdl_loader] CSV updated (baseline + 1 PDL scenario row). \n")

        # build event registry for conditional runtime evaluation
        event_registry = loader.to_event_registry(args.cascade)
        n_total = len(event_registry["events"])
        n_shocking = sum(1 for e in event_registry["events"] if e["impacts"])
        n_conditional = sum(1 for e in event_registry["events"] if e["condition"])
        print(f"[event_tracker] Registry: {n_total} events "
              f"{n_shocking} with shocks, {n_conditional} conditional)")



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

    # attach event registry to model class so setup can inject the tracker into the env
    if args.pdl:
        SupplyChainModel._event_registry = event_registry

    simulator.run()

    if hasattr(SupplyChainModel, "_event_registry"):
        del SupplyChainModel._event_registry

    # post-process: merge CSVs -> SQLite for visualize_sql.py
    print("\n[main] Converting CSVs to SQLite...")
    csv_to_sqlite(output_folder)
