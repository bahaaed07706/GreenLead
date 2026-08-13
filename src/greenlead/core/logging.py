import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    # Clear existing handlers to prevent duplicate logs
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Example setup for Uvicorn logger overrides if needed later
    # logging.getLogger("uvicorn.access").handlers = []
