from collections.abc import Mapping

from dotenv import dotenv_values

config = dotenv_values(".env")


def read_env() -> Mapping[str, str | None]:
    if config is None:
        raise ValueError("No .env file found or it is empty.")
    return config
