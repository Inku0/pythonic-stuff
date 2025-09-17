from logging import ERROR, basicConfig, getLogger


def logging_setup():
    try:
        logging_level = read_env()["LOGGING_LEVEL"]
    except KeyError:
        print("LOGGING_LEVEL wasn't found in .env")
        logging_level = ERROR
    finally:
        basicConfig(
            level=logging_level, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        return getLogger(name="logging")
