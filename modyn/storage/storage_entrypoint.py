"""Entrypoint for the storage service."""

import argparse
import logging
import multiprocessing as mp
import os
import pathlib

import yaml
from modyn.storage.storage import Storage

logging.basicConfig(
    level=logging.NOTSET,
    format="[%(asctime)s]  [%(filename)15s:%(lineno)4d] %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
)
logger = logging.getLogger(__name__)

# We need to do this at the top because other dependencies otherwise set fork.
try:
    mp.set_start_method("spawn")
except RuntimeError as error:
    if mp.get_start_method() != "spawn" and "PYTEST_CURRENT_TEST" not in os.environ:
        logger.error("Start method is already set to {}", mp.get_start_method())
        raise error


def setup_argparser() -> argparse.ArgumentParser:
    """Set up the argument parser.

    Returns:
        argparse.ArgumentParser: Argument parser
    """
    parser_ = argparse.ArgumentParser(description="Modyn Storage")
    parser_.add_argument("config", type=pathlib.Path, action="store", help="Modyn infrastructure configuration file")

    return parser_


def main() -> None:
    """Entrypoint for the storage service."""
    parser = setup_argparser()
    args = parser.parse_args()

    assert args.config.is_file(), f"File does not exist: {args.config}"

    with open(args.config, "r", encoding="utf-8") as config_file:
        modyn_config = yaml.safe_load(config_file)

    logger.info("Initializing storage.")
    storage = Storage(modyn_config)
    logger.info("Starting storage.")
    storage.run()

    logger.info("Storage returned, exiting.")


if __name__ == "__main__":
    main()
