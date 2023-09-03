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


async def subtitle_action(
        session: ClientSession,
        movie: list,
        action: str,
        base_url: str,
        headers: dict,
        semaphore: Semaphore,
        ids_of_movies: dict,
        language: str,
        typeof: str
):
    # may god have mercy upon this function...
    async with semaphore:
        tasks = []
        for true_path, _, file in walk(movie["path"]):
            subtitle_path = None
            radarrId = None
            final_path = None
            language_not_found = True
            for filename in file:
                if "sample" not in filename and filename.endswith(".mkv") or filename.endswith(".mp4"):
                    movie_path = path.join(movie["path"], filename)
                    for test in ids_of_movies["data"]:
                        if movie_path == test["path"]:
                            radarrId = test["radarrId"]
                            if action == "translate":
                                for subtitle in test["subtitles"]:
                                    if language in subtitle["code2"]:
                                        language_not_found = False
                                        break

                if filename.endswith("en.srt"):
                    subtitle_path = path.join(movie["path"], filename)

                if subtitle_path is None or radarrId is None:
                    continue
                final_path = f"{base_url}/api/subtitles?action={action}&language={language}&path={subtitle_path}&type={typeof}&id={radarrId}"

        if final_path is not None:
            if action == "translate" and language_not_found:
                print(f"{language} for {movie['name']} NOT found")
                print(final_path)
                task = create_task(send_patch(session, final_path, headers, action))
                tasks.append(task)
            elif action == "sync":
                print(f"{action} for movie: {movie['name']}")
                print(final_path)
                task = create_task(send_patch(session, final_path, headers, action))
                tasks.append(task)
                print(f"Finished {action} for movie: {movie['name']}")

        await gather(*tasks)


async def is_synced(url, filename):
    async with open(filename, "r") as sync_file:
        contents = await sync_file.read()
        lines = contents.split("\n")
        return url in lines


async def append_to_synced_file(url, filename):
    async with open(filename, "a+") as sync_file:
        await sync_file.write(url + "\n")


async def send_patch(session, url, headers, filename):
    async with session.patch(url, headers=headers) as patch:
        if patch.status == 204 and not await is_synced(url, filename):
            await append_to_synced_file(url, filename)
        else:
            print(f"Failed for {url}")


async def main():
    try:
        api_key, base_url, dir_path = argv[1:4]
        headers = {"X-API-KEY": api_key, "accept": "application/json"}

        async with ClientSession() as session:
            list_of_movies = await get_list_of_movies(session, base_url, dir_path, headers)
            ids_of_movies = await get_ids_of_movies(session, base_url, headers)
            semaphore = Semaphore(1)
            tasks = [subtitle_action(
                session,
                movie,
                "sync",
                base_url,
                headers,
                semaphore,
                ids_of_movies,
                "en",
                "movie"
            ) for movie in list_of_movies]
            await gather(*tasks)
    except IndexError:
        print("Error... Supply three arguments: api key, base_url and the directory.")


if __name__ == "__main__":
    run(main())
