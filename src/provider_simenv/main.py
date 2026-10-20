"""Command-line entry point for the PROVIDER supply-chain simulation."""

import argparse
import logging

from provider_simenv.execution import execute_cli


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="PROVIDER supply chain simulation"
    )
    parser.add_argument(
        "--pdl", metavar="PATH", help="PDL YAML scenario file"
    )
    parser.add_argument(
        "--postgres-url",
        metavar="URL",
        help="Optional PostgreSQL SQLAlchemy connection URL",
    )
    parser.add_argument(
        "--cascade",
        metavar="ID",
        help="Cascade ID; defaults to the first cascade",
    )
    parser.add_argument("--label", help="Optional label stored with the run")
    parser.add_argument(
        "--no-postgres",
        action="store_true",
        help=(
            "Run without writing to PostgreSQL. Without this flag an unreachable "
            "database fails the run rather than being skipped silently."
        ),
    )
    execute_cli(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
