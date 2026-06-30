import logging


LOG_FORMAT = "[ %(asctime)s ] %(lineno)d %(name)s - %(levelname)s - %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure console logging when an entrypoint wants logging output."""

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(format=LOG_FORMAT, level=level)
