from logging import ERROR, DEBUG, INFO, basicConfig, getLogger
from utils.read_env import read_env


def logging_setup():
    try:
        str_logging_level = read_env()["LOGGING_LEVEL"]
        str_logging_level = str_logging_level.upper()
        if str_logging_level == "DEBUG":
            logging_level = DEBUG
        if str_logging_level == "INFO":
            logging_level = INFO
    except KeyError:
        print("LOGGING_LEVEL wasn't found in .env")
        logging_level = ERROR
    finally:
        basicConfig(
            level=logging_level, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        return getLogger(name="logging")
