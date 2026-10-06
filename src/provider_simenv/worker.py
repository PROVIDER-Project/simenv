"""Internal worker: execute a simulation-owned persisted run context."""

import argparse
import logging
from pathlib import Path

from .execution import execute_prepared_run, load_prepared_run


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path)
    args = parser.parse_args()
    execute_prepared_run(load_prepared_run(args.context))


if __name__ == "__main__":
    main()
