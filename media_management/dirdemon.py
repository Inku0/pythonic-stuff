from concurrent.futures import ThreadPoolExecutor, as_completed
from os import scandir, DirEntry
from os.path import isdir
from shutil import rmtree


def check_dir_lacking(directory: str) -> bool:
    if isdir(directory):
        files = [entry.name for entry in scandir(directory) if entry.is_file()]
        ending_set = {file.split(".")[-1] for file in files}
        if len(files) == 2 and ending_set == {"opf", "jpg"}:
            return True
    return False


def is_empty_dir(directory_path: str) -> bool:
    with scandir(directory_path) as it:
        return next(it, None) is None


def check_dir_empty(directory: str) -> bool:
    if isdir(directory) and is_empty_dir(directory):
        return True
    return False

def list_subdirs(d):
    return [f.path for f in scandir(d) if f.is_dir()]

def fast_scandir(dirname: str):
    subfolders = []
    queue = [dirname]  # Start with the root directory in the queue

    with ThreadPoolExecutor() as executor:
        while queue:
            # Submit a scanning task for each directory currently in the queue
            futures = {
                executor.submit(list_subdirs, d): d
                for d in queue
            }
            queue = []  # Clear the queue to store next level of directories

            for future in as_completed(futures):
                try:
                    dirs = future.result()  # Get subdirectories found in this directory
                    subfolders.extend(dirs)  # Add them to the master list
                    queue.extend(dirs)       # Add them to the queue to scan next
                except Exception as e:
                    print(f"Error scanning {futures[future]}: {e}")

    return subfolders



def check_deletability(path: str | DirEntry[str]) -> bool:
    return True if check_dir_lacking(directory=path) or check_dir_empty(directory=path) else False


def run(directory: str, delete: bool = False) -> None:
    final_list = []
    entries = fast_scandir(directory)
    with ThreadPoolExecutor() as pool:
        futures = {pool.submit(check_deletability, entry): entry for entry in entries}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                if future.result():
                    final_list.append(entry)
            except Exception as e:
                print(f"Error checking {entry}: {e}")
    if delete:
        for directory in final_list:
            rmtree(directory)
    print(f'{"deleted" if delete else "want to delete"} {len(final_list)} directories: {final_list}')
