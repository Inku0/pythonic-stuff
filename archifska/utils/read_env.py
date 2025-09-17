from collections.abc import Mapping

from dotenv import dotenv_values

config = dotenv_values(".env")


def read_env() -> Mapping[str, str]:
    if type(config) is not Mapping[str, str]:
        raise ValueError("No .env file found or it is empty.")
    return config
