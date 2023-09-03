#!/usr/bin/env python3
from sys import argv

from aiohttp import ClientSession
from asyncio import run, gather, Semaphore
import bazarr_syncer


async def main():
    try:
        api_key, base_url, dir_path = argv[1:4]
        headers = {"X-API-KEY": api_key, "accept": "application/json"}

        async with ClientSession() as session:
            list_of_movies = await bazarr_syncer.get_list_of_movies(session, base_url, dir_path, headers)
            ids_of_movies = await bazarr_syncer.get_ids_of_movies(session, base_url, headers)
            semaphore = Semaphore(3)
            tasks = [bazarr_syncer.subtitle_action(
                session,
                movie,
                "translate",
                base_url,
                headers,
                semaphore,
                ids_of_movies,
                "fr",
                "movie"
            ) for movie in list_of_movies]
            await gather(*tasks)
    except IndexError:
        print("Error... Supply three arguments: api key, base_url and the directory.")


if __name__ == "__main__":
    run(main())
