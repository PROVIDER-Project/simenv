"""Command-line entry point for the PROVIDER supply-chain simulation."""
import logging
import os
import shutil
import argparse
from datetime import datetime, timezone

import pandas as pd

from Melodie import Config, Simulator

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.db_config import PostgresDBConfig
from provider_simenv.tick_writer import TickWriter
from provider_simenv.run_registry import (
    finish_run,
    new_run_id,
    run_dir,
    run_record,
    start_run,
)

logger = logging.getLogger(__name__)

# --------------------
# Main
# --------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="Optional label stored with the run.",
    )
    parser.add_argument(
        "--no-postgres",
        action="store_true",
        help=(
            "Run without writing to PostgreSQL. Without this flag an unreachable "
            "database fails the run rather than being skipped silently."
        ),
    )

    args = parser.parse_args()

    if args.postgres_url:
        os.environ["PROVIDER_SIMENV_POSTGRES_URL"] = args.postgres_url
        logger.info("Using PostgreSQL connection string from --postgres-url")

    # Folder paths (both needed for PDL injection and Config)
    here = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(here, "data", "input")
    output_root = os.path.join(here, "data", "output")
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

        logger.info("Scenario: %s", loader.label)
        logger.info("Source: %s", args.pdl)
        logger.info("Cascade: %s", args.cascade or 'first cascade in file')

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
        logger.info("CSV updated (baseline + 1 PDL scenario row).")

        # build event registry for conditional runtime evaluation
        event_registry = loader.to_event_registry(args.cascade)
        n_total = len(event_registry["events"])
        n_shocking = sum(1 for e in event_registry["events"] if e["impacts"])
        n_conditional = sum(1 for e in event_registry["events"] if e["condition"])
        logger.info("Registry: %d events, %d with shocks, %d conditional", n_total, n_shocking, n_conditional)

    scenario_rows = pd.read_csv(csv_path)
    missing = {"id", "period_num"} - set(scenario_rows.columns)
    if missing:
        logger.error(
            "SimulatorScenarios.csv is missing required column(s): %s",
            ", ".join(sorted(missing)),
        )
        raise SystemExit(1)
    period_nums = scenario_rows["period_num"]
    if period_nums.isna().any() or period_nums.nunique() != 1:
        logger.error(
            "All scenarios in one run must have the same period_num; found %s",
            period_nums.drop_duplicates().tolist(),
        )
        raise SystemExit(1)

    scenario_ids = [int(value) for value in scenario_rows["id"]]
    period_num = int(period_nums.iloc[0])
    run_id = new_run_id()
    output_folder = run_dir(output_root, run_id)
    logger.info("Run id: %s", run_id)

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
        # also drive the agent roster from this PDL (not just the shocks), so a
        # swapped PDL with new entities/regions instantiates the matching lists.
        SupplyChainModel._pdl_path = args.pdl

    record = run_record(
        run_id,
        pdl=args.pdl,
        scenario_ids=scenario_ids,
        period_num=period_num,
        label=args.label,
        started_at=datetime.now(timezone.utc),
    )
    start_run(output_root, record)

    tick_writer = None
    try:
        if not args.no_postgres:
            tick_writer = TickWriter.from_config(PostgresDBConfig())
            tick_writer.open_run(record)
            SupplyChainModel._tick_writer = tick_writer
            SupplyChainModel._run_id = run_id
        simulator.run()
    except Exception:
        finish_run(output_root, run_id, status="failed")
        if tick_writer is not None:
            try:
                tick_writer.close_run(run_id, status="failed")
            except Exception as exc:
                logger.warning("could not record the failed run in sim_run: %s", exc)
        raise
    else:
        finish_run(output_root, run_id, status="completed")
        if tick_writer is not None:
            tick_writer.close_run(run_id, status="completed")
    finally:
        if hasattr(SupplyChainModel, "_event_registry"):
            del SupplyChainModel._event_registry
        if hasattr(SupplyChainModel, "_pdl_path"):
            del SupplyChainModel._pdl_path
        if hasattr(SupplyChainModel, "_tick_writer"):
            del SupplyChainModel._tick_writer
        if hasattr(SupplyChainModel, "_run_id"):
            del SupplyChainModel._run_id
