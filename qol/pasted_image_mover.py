from os import scandir
from pathlib import Path
from re import search
from shutil import copy2
from sys import argv
from urllib.parse import unquote


def main():
    screenshot_path = Path("/home/hringhorni/synced/")
    dest_path = Path("/home/hringhorni/git/opsys/")
    images_to_be_moved: list[str] = []
    given_file: Path = Path(argv[1])
    print(f"given file for reading: {given_file.name}")
    with open(given_file, "r") as f:
        for line in f:
            if "Pasted%20image" in line:
                # regex to remove "![somename or nothing]()" from the string
                match = search(r"!\[.*?\]\((Pasted%20image[^)]+)\)", line.strip())
                if match:
                    formatted_name = match.group(1)
                    decoded_formatted_name = unquote(formatted_name)
                    images_to_be_moved.append(decoded_formatted_name)
    with scandir(screenshot_path) as dir:
        for entry in dir:
            if entry.name in images_to_be_moved:
                _ = copy2(
                    entry.path,
                    dest_path,
                )


if __name__ == "__main__":
    main()
