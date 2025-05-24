#!/usr/bin/env python3
import os
import ffmpeg
from sys import argv


def get_absolute_path(path: str):
    absolute_path = [os.path.join(path, file) for file in os.listdir(path)]
    return absolute_path


def main():
    corrupt = []
    movies_path = argv[1]
    sub_movies_path = get_absolute_path(movies_path)

    for folder in sub_movies_path:
        for file in get_absolute_path(folder):
            if file.endswith(".mkv"):
                try:
                    ffmpeg.probe(file)
                except Exception:
                    corrupt.append(file)

    with open("corrupt", "w") as fail:
        fail.write(str(corrupt))


if __name__ == "__main__":
    main()
