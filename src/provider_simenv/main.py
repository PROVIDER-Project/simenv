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

import pandas as pd

from Melodie import Config, Simulator

from model import SupplyChainModel
from scenario import SupplyChainScenario

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
    output_folder = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "output"
    )

    config = Config(
        project_name= "provider-simenv",
        project_root= os.path.dirname(os.path.abspath(__file__)),
        input_folder= os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "input"),
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
