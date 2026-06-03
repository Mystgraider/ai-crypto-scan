import logging
import os


LOG_DIR = "logs"

os.makedirs(
    LOG_DIR,
    exist_ok=True
)


def get_logger():

    logger = logging.getLogger(
        "scanner"
    )

    if logger.handlers:
        return logger

    logger.setLevel(
        logging.INFO
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    scanner_handler = logging.FileHandler(
        f"{LOG_DIR}/scanner.log"
    )

    scanner_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        scanner_handler
    )

    return logger


logger = get_logger()
