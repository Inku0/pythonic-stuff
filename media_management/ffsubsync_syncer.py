#!/usr/bin/env python3
import concurrent.futures
from os import walk, path
from sys import argv
from mkv_finder_replacer import get_absolute_path
from subprocess import run as sub_run


def start_subprocess(final_command: str):
    sub_run(final_command, shell=True, check=True)


def is_synced(movie_path, synced_set):
    return movie_path in synced_set


def sync_subtitles(folder, synced_set):
    subtitle_path = None
    movie_path = None
    final_command = None
    for i, j, files in walk(folder):
        for filename in files:
            if "sample" not in filename and (filename.endswith(".mkv") or filename.endswith(".mp4") or filename.endswith(".avi")):
                movie_path = path.join(folder, filename)
            if filename.endswith("en.srt"):
                subtitle_path = path.join(folder, filename)
            if subtitle_path is not None and movie_path is not None:
                final_command = f"ffsubsync --overwrite-input \"{movie_path}\" -i \"{subtitle_path}\""

    if final_command is not None:
        if not is_synced(movie_path, synced_set):
            print(final_command)
            with open("ffsubsynced", "a") as file:
                file.write(movie_path + "\n")
            start_subprocess(final_command)
            print(f"Finished syncing subs for movie: {movie_path}")
            synced_set.add(movie_path)


def main():
    movies_path = argv[1]
    sub_movies_paths = get_absolute_path(movies_path)
    synced_set = set()

    # Create a ThreadPoolExecutor with as many workers as you want
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(sync_subtitles, folder, synced_set) for folder in sub_movies_paths]


if __name__ == "__main__":
    main()
