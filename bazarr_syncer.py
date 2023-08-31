#!/usr/bin/env python3
from sys import argv

from aiohttp import ClientSession
from aiofiles import open
from asyncio import run, create_task, gather, Semaphore
from os import walk, path


async def get_list_of_movies(session: ClientSession, base_url: str, dir_path: str, headers: dict) -> list:
    url = f"{base_url}/api/files?path={dir_path}"
    async with session.get(url, headers=headers) as response:
        return await response.json()


async def get_ids_of_movies(session: ClientSession, base_url: str, headers: dict) -> list:
    url = f"{base_url}/api/movies"
    async with session.get(url, headers=headers) as response:
        return await response.json()


async def subtitle_action(session: ClientSession, movie: list, action: str, base_url: str, headers: dict, semaphore: Semaphore, ids_of_movies: dict):
    # may god have mercy upon this function...
    async with semaphore:
        print(f"Syncing subs for movie: {movie['name']}")
        tasks = []
        for true_path, _, file in walk(movie["path"]):
            subtitle_path = None
            radarrId = None
            final_path = None
            for filename in file:
                if "sample" not in filename and filename.endswith(".mkv") or filename.endswith(".mp4"):
                    movie_path = path.join(movie["path"], filename)
                    for test in ids_of_movies["data"]:
                        if movie_path == test["path"]:
                            radarrId = test["radarrId"]

                if filename.endswith("en.srt"):
                    subtitle_path = path.join(movie["path"], filename)

                if subtitle_path is None or radarrId is None:
                    continue
                final_path = f"{base_url}/api/subtitles?action={action}&language=en&path={subtitle_path}&type=movie&id={radarrId}"
            if final_path is not None:
                print(final_path)
                task = create_task(send_patch(session, final_path, headers))
                tasks.append(task)
                await gather(*tasks)
                print(f"Finished syncing subs for movie: {movie['name']}")


async def is_synced(url):
    async with open("synced", "r") as sync_file:
        contents = await sync_file.read()
        lines = contents.split("\n")
        return url in lines


async def append_to_synced_file(url):
    async with open("synced", "a") as sync_file:
        await sync_file.write(url + "\n")


async def send_patch(session, url, headers):
    async with session.patch(url, headers=headers) as patch:
        print(url)
        print(patch.status)
        if patch.status == 204 and not await is_synced(url):
            completed_syncs.add(url)
            await append_to_synced_file(url)
        else:
            print(f"Failed for {url}")


async def main():
    global completed_syncs
    completed_syncs = set()
    try:
        api_key, base_url, dir_path = argv[1:4]
        headers = {"X-API-KEY": api_key, "accept": "application/json"}

        async with ClientSession() as session:
            list_of_movies = await get_list_of_movies(session, base_url, dir_path, headers)
            ids_of_movies = await get_ids_of_movies(session, base_url, headers)
            semaphore = Semaphore(1)
            tasks = [subtitle_action(session, movie, "sync", base_url, headers, semaphore, ids_of_movies) for movie in list_of_movies]
            await gather(*tasks)
    except IndexError:
        print("Error... Supply three arguments: api key, base_url and the directory.")


if __name__ == "__main__":
    run(main())
