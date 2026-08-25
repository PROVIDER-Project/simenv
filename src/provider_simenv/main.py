"""Command-line entry point for the PROVIDER supply-chain simulation."""
import logging
import os
import shutil
import argparse

import pandas as pd

from Melodie import Config, Simulator

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.pdl_loader import PDLLoader

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

    args = parser.parse_args()

    if args.postgres_url:
        os.environ["PROVIDER_SIMENV_POSTGRES_URL"] = args.postgres_url
        logger.info("Using PostgreSQL connection string from --postgres-url")

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

    simulator.run()

    if hasattr(SupplyChainModel, "_event_registry"):
        del SupplyChainModel._event_registry
    if hasattr(SupplyChainModel, "_pdl_path"):
        del SupplyChainModel._pdl_path
