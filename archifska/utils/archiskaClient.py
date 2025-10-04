from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from json import dump, load
from logging import Logger
from os import link, makedirs, path, stat, walk
from pathlib import Path
from shutil import copy2
from time import sleep
from typing import Any

from PTN import parse
from qbittorrentapi import (
    Client,
    Forbidden403Error,
    LoginFailed,
    TorrentDictionary,
    TorrentInfoList,
    exceptions,
)
from rapidfuzz import fuzz

from utils.logging_setup import logging_setup
from utils.read_env import read_env
from utils.StarrUpdater import StarrUpdater

MEDIA_EXTENSIONS = {
    ".mkv",
    ".mk3d",
    ".mp4",
    ".avi",
    ".m4v",
    ".mov",
    ".qt",
    ".wmv",
    ".asf",
    ".flv",
    ".webm",
    ".m4a",
    ".mp3",
    ".aac",
    ".ogg",
    ".opus",
    ".m2ts",
    ".mts",
    ".m2v",
    ".3gp",
}


@dataclass(frozen=True)
class FileEntry:
    path: str
    inode: int | str | None
    qbit_file: str | None


@dataclass(frozen=True)
class ExtTorrDict:
    is_rarlocked: bool
    torrent: TorrentDictionary


class ArchifskaQBitClient:
    """
    Interact with the qBittorrent Web UI API and helper services (Radarr/Sonarr).
    Provides utilities to snapshot a directory's file structure in relation to
    qBittorrent-managed files and restore/link that structure elsewhere.
    """

    def __init__(self) -> None:
        creds: Mapping[str, str] = read_env()
        self.logger: Logger = logging_setup()
        try:
            self.host: str = creds["QBIT_HOST"]
            self.port: str = creds["QBIT_PORT"]
            self.username: str = creds["QBIT_USERNAME"]
            self.password: str = creds["QBIT_PASSWORD"]
            self.radarr_runner = StarrUpdater(
                host=creds["RADARR_HOST"],
                port=creds["RADARR_PORT"],
                api_key=creds["RADARR_API_KEY"],
                service="radarr",
            )
            self.sonarr_runner = StarrUpdater(
                host=creds["SONARR_HOST"],
                port=creds["SONARR_PORT"],
                api_key=creds["SONARR_API_KEY"],
                service="sonarr",
            )
        except KeyError as e:
            print(f".env is missing {e}")

        self.client: Client = Client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={"timeout": (360, 360)},
        )

        self.all_torrents: list[TorrentDictionary] = []
        self.filtered_torrents: list[TorrentDictionary] = []

    # ----------------------
    # qBittorrent connection
    # ----------------------
    def connect(self) -> bool:
        try:
            self.client.auth_log_in()
            self.logger.info("Connected to the qBittorrent Web API")
            return True
        except (LoginFailed, Forbidden403Error) as login_exception:
            raise ValueError(f"Login failed: {login_exception}") from login_exception

    def close(self) -> None:
        self.client.auth_log_out()
        self.logger.info("Closed the connection to the qBittorrent Web API")

    # ----------------------
    # Helpers
    # ----------------------
    def get_hash(self, file_name: str) -> str:
        torrents: TorrentInfoList = self.client.torrents_info()
        for torrent in torrents:
            if file_name in torrent.name:
                return torrent.hash
        raise ValueError(f"torrent {file_name} not found")

    def get_paths_torrents_by_hash(
        self, torrent_hashes: list[str]
    ) -> tuple[list[TorrentDictionary], list[str]]:
        torrents: list[TorrentDictionary] = []
        qbit_paths: list[str] = []

        try:
            for torrent_hash in torrent_hashes:
                results: TorrentInfoList = self.client.torrents_info(
                    None, None, None, None, None, None, torrent_hash
                )
                if len(results) == 0:
                    raise ValueError(f"torrent with hash {torrent_hash} not found")

                torrent: TorrentDictionary = results[0]
                qbit_path = torrent["content_path"]
                torrents.append(torrent)
                qbit_paths.append(qbit_path)
        except Exception as e:
            raise ValueError(
                f"failed to get torrent info for {torrent_hashes}: {e}"
            ) from e

        self.logger.debug(f"qbit_paths are {qbit_paths}, torrents are {torrents}")
        return (torrents, qbit_paths)

    def qbit_path_inoder(self, qbit_path: str) -> dict[str, int]:
        """
        Build an inode map for a qBittorrent content path. Recurses into directories.
        Returns a map of absolute file path -> inode.
        """
        if path.isfile(qbit_path):
            return {path.abspath(qbit_path): stat(qbit_path).st_ino}

        qbit_structure: dict[str, int] = {}
        for r, _, files in walk(qbit_path):
            for f in files:
                fp = path.join(r, f)
                try:
                    qbit_structure[path.abspath(fp)] = stat(fp).st_ino
                except FileNotFoundError:
                    # Skip transient/missing files
                    self.logger.debug(f"Skipping missing file during inode scan: {fp}")
        return qbit_structure

    @staticmethod
    def _rar_lock_check(files: list[str]) -> bool:
        # engaged if a .rar exists AND at least 3 files matching *.r[0-9][0-9]
        has_rar = any(f.endswith(".rar") for f in files)
        has_parts = len([f for f in files if fnmatch(f, "*.r[0-9][0-9]")]) >= 3
        return has_rar and has_parts

    @staticmethod
    def _is_media_file(name: str) -> bool:
        return Path(name).suffix.lower() in MEDIA_EXTENSIONS

    @staticmethod
    def _invert_inode_map(inode_map: dict[str, int]) -> dict[int, str]:
        # if duplicates exist, last one wins
        return {inode: file_path for file_path, inode in inode_map.items()}

    @staticmethod
    def _safe_copy(src: str, dst: str, logger: Logger) -> None:
        copy2(src, dst)
        logger.debug(f"Copied {src} -> {dst}")

    @staticmethod
    def _link_or_copy(src: str, dst: str, logger: Logger) -> None:
        try:
            link(src, dst)
            logger.debug(f"Linked {src} -> {dst}")
        except Exception as e:
            logger.warning(
                f"Hardlink failed ({e}), falling back to copy: {src} -> {dst}"
            )
            ArchifskaQBitClient._safe_copy(src, dst, logger)

    # ----------------------
    # Structure snapshot/restore
    # ----------------------
    def save_structure(
        self,
        original_location: str,
        save_file: str,
        torrent_hashes: list[str],
    ) -> None:
        """
        Snapshot the directory structure at original_location. For each file,
        attempt to find the corresponding qBittorrent-managed file using inode matching.
        If a RAR lock is detected, media files are excluded from linking and will be treated as non-qbit files.
        """
        if len(torrent_hashes) == 0:
            raise ValueError("torrent_hashes must be provided")

        original_location = path.abspath(original_location)
        if not path.exists(original_location):
            raise FileNotFoundError(
                f"original_location `{original_location}` does not exist"
            )

        _, qbit_paths = self.get_paths_torrents_by_hash(torrent_hashes)

        # TODO: add rar_lock tag per torrent

        all_qbit_files: list[str] = []
        qbit_structure: dict[str, int] = {}
        for qbit_path in qbit_paths:
            if not path.exists(qbit_path):
                raise FileNotFoundError(f"qbit_path `{qbit_path}` does not exist")
            # Gather all files for rar lock detection
            for r, _, files in walk(qbit_path):
                for f in files:
                    all_qbit_files.append(path.join(r, f))
            # Build inode map (recursive)
            qbit_structure.update(self.qbit_path_inoder(qbit_path))

        rar_lock = self._rar_lock_check(all_qbit_files)
        if rar_lock:
            self.logger.info("RAR lock engaged")
        else:
            self.logger.debug("RAR lock not engaged")

        inode_to_qbit_file = self._invert_inode_map(qbit_structure)
        self.logger.debug(f"qbit inode map size: {len(inode_to_qbit_file)}")

        structure: dict[str, dict[str, Any]] = {}

        for root, dirs, files in walk(original_location):
            structure[root] = {
                "basename": path.basename(root),
                "dirs": dirs,
                "files": {},
            }
            for fname in files:
                full_path = path.join(root, fname)
                qbit_file: str | None = None
                inode_value: int | str | None

                # If rar lock is engaged and the file looks like media, mark it as non-qbit
                # TODO: only set for the rar_locked torrent
                # do this by finding the torrent related to the file?
                if rar_lock and self._is_media_file(fname):
                    inode_value = self._safe_stat_inode(full_path)
                    structure[root]["files"][fname] = asdict(
                        FileEntry(path=full_path, inode=inode_value, qbit_file=None)
                    )
                    continue

                try:
                    inode = stat(full_path).st_ino
                    inode_value = inode
                    if inode in inode_to_qbit_file:
                        qbit_file = inode_to_qbit_file[inode]
                except FileNotFoundError:
                    self.logger.debug(
                        f"File not found during snapshot (likely a symlink): {full_path}"
                    )
                    inode_value = "missing/symlink"

                structure[root]["files"][fname] = asdict(
                    FileEntry(path=full_path, inode=inode_value, qbit_file=qbit_file)
                )

        with open(save_file, "w", encoding="utf-8") as outf:
            dump(structure, outf, indent=2)
        self.logger.info(f"Saved structure to `{save_file}`")

    def restore_structure(
        self,
        original_location: str,
        new_location: str,
        save_file: str,
        torrent_hashes: list[str] | None = None,
    ) -> None:
        """
        Recreate the directory hierarchy from the saved snapshot.
        - Files that were linked to a qBittorrent-managed file will be hardlinked if possible (fallback to copy).
        - Files without a qBittorrent match will be copied from their original path.
        """
        if not path.exists(save_file):
            raise FileNotFoundError(f"`{save_file}` not found")

        with open(save_file, "r", encoding="utf-8") as inf:
            stored_structure: dict[str, dict[str, Any]] = load(inf)

        if torrent_hashes is None or len(torrent_hashes) == 0:
            raise ValueError("torrent_hashes must be provided")

        _, qbit_paths = self.get_paths_torrents_by_hash(torrent_hashes)

        # Rebuild qbit inode structure and a basename -> fullpath index for linking
        qbit_structure: dict[str, int] = {}
        for qbit_path in qbit_paths:
            qbit_structure.update(self.qbit_path_inoder(qbit_path))

        basename_index: dict[str, str] = {}
        for fpath in qbit_structure.keys():
            basename_index[path.basename(fpath)] = fpath

        weird: list[tuple[str, str, str, Any]] = []

        original_location = path.abspath(original_location)
        new_location = path.abspath(new_location)

        for root, content in stored_structure.items():
            actual_rel = path.relpath(root, original_location)
            target_root = path.join(new_location, actual_rel)
            makedirs(target_root, exist_ok=True)

            for file_name, info in content["files"].items():
                original_file_path: str = info.get("path")
                qbit_file_saved: str | None = info.get("qbit_file")

                target_file_path = path.join(target_root, file_name)

                if not qbit_file_saved:
                    self.logger.info(
                        f"Copying non-qbit file: {original_file_path} -> {target_file_path}"
                    )
                    try:
                        self._safe_copy(
                            original_file_path, target_file_path, self.logger
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to copy {original_file_path} -> {target_file_path}: {e}"
                        )
                        weird.append(
                            (file_name, original_file_path, target_root, "copy_failed")
                        )
                    continue

                # Prefer matching by basename against the current qbit structure
                basename = path.basename(qbit_file_saved)
                current_qbit_match = basename_index.get(basename)

                if current_qbit_match:
                    try:
                        self.logger.info(
                            f"Linking qbit file: {current_qbit_match} -> {target_file_path}"
                        )
                        self._link_or_copy(
                            current_qbit_match, target_file_path, self.logger
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to link/copy {current_qbit_match} -> {target_file_path}: {e}"
                        )
                        weird.append(
                            (
                                file_name,
                                original_file_path,
                                target_root,
                                current_qbit_match,
                            )
                        )
                else:
                    self.logger.warning(
                        f"No current qbit match by basename for {basename}; copying original file"
                    )
                    try:
                        self._safe_copy(
                            original_file_path, target_file_path, self.logger
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to copy {original_file_path} -> {target_file_path}: {e}"
                        )
                        weird.append(
                            (
                                file_name,
                                original_file_path,
                                target_root,
                                "no_qbit_match",
                            )
                        )

        if weird:
            with open("RECHECK_THESE", "a", encoding="utf-8") as recheck_file:
                recheck_file.write(f"{weird}\n")

    # Backwards-compatible alias
    def recreate_structure(
        self,
        original_location: str,
        new_location: str,
        save_file: str,
        torrent_hashes: list[str] | None = None,
    ) -> None:
        self.restore_structure(
            original_location=original_location,
            new_location=new_location,
            save_file=save_file,
            torrent_hashes=torrent_hashes,
        )

    @staticmethod
    def _safe_stat_inode(fp: str) -> int | str | None:
        try:
            return stat(fp).st_ino
        except FileNotFoundError:
            return "missing/symlink"

    # ----------------------
    # Torrent listing and selection
    # ----------------------
    def list_torrents(self, category: str | None = None) -> None:
        self.all_torrents = self.client.torrents_info("all", None, "completion_on")

        if category is None:
            movies = [t for t in self.all_torrents if t.category == "movies"]
            tv = [t for t in self.all_torrents if t.category == "tv"]
            self.filtered_torrents = movies + tv
            self.filtered_torrents.sort(key=lambda x: x.completion_on)
        else:
            self.filtered_torrents = [
                t for t in self.all_torrents if t.category == category
            ]

    def season_counter(self, seasons: list[TorrentDictionary]) -> int:
        actual_seasons: list[int | None] = []
        for season in seasons:
            try:
                season_no = parse(season.name).get("season")
            except Exception:
                season_no = None
            if season_no not in actual_seasons:
                actual_seasons.append(season_no)
        return len([s for s in actual_seasons if s is not None])

    def check_similarity(
        self, given_torrent: TorrentDictionary, other_torrent: TorrentDictionary
    ) -> bool:
        ratio = fuzz.ratio(given_torrent.name, other_torrent.name)
        self.logger.debug(
            f"fuzz ratio for {given_torrent.name} and {other_torrent.name} is {ratio}"
        )
        try:
            given_title = parse(given_torrent.name)["title"]
            other_title = parse(other_torrent.name)["title"]
        except Exception:
            return False
        if ratio < 50:
            double_check_ratio = fuzz.ratio(given_title, other_title)
            return double_check_ratio > 90 and given_title == other_title
        return ratio > 45 and given_title == other_title

    def check_for_other_seasons(
        self, given_torrent: TorrentDictionary
    ) -> list[TorrentDictionary]:
        if given_torrent.category != "tv":
            self.logger.info("Not a TV show, skipping season check")
            return [given_torrent]

        seasons: list[TorrentDictionary] = []
        with ThreadPoolExecutor() as pool:
            futures = {
                pool.submit(self.check_similarity, given_torrent, torrent): torrent
                for torrent in self.filtered_torrents
            }
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    if future.result():
                        seasons.append(entry)
                except Exception as e:
                    self.logger.error(f"Error checking similarity for {entry}: {e}")

        actual_seasons_amount = self.season_counter(seasons)
        self.logger.debug(
            f"found {actual_seasons_amount} seasons for {given_torrent.name}: {seasons}"
        )

        media_id = self.extract_id_and_path(given_torrent.name, category="tv")[0]
        sonarr_seasons = self.sonarr_runner.get_seasons(media_id)
        self.logger.debug(f"Sonarr seasons for ID {media_id} are: {sonarr_seasons}")

        monitored_seasons = [
            s
            for s in sonarr_seasons
            if s.get("monitored")
            and s.get("statistics", {}).get("episodeFileCount", 0) > 0
        ]

        if len(monitored_seasons) == actual_seasons_amount:
            self.logger.info(
                f"Seasons in Sonarr ({len(monitored_seasons)}) match torrents list ({actual_seasons_amount})"
            )
            return seasons
        else:
            raise ValueError(
                f"Seasons in Sonarr ({len(monitored_seasons)}) do not match torrents list ({actual_seasons_amount})"
            )

    def get_candidates(self, category: str | None = None) -> list[TorrentDictionary]:
        if category is not None:
            self.logger.info(f"Getting candidates for category {category}")
            self.list_torrents(category=category)
        else:
            self.list_torrents()

        prime_candidate = next(
            torrent
            for torrent in self.filtered_torrents
            if "megafarm" not in torrent.content_path and "skip" not in torrent.tags
        )

        self.logger.info(
            f"Found {len(self.filtered_torrents)} candidates, prime candidate is {prime_candidate.name} "
            f"with path {prime_candidate.content_path} and age {prime_candidate.completion_on}"
        )
        self.logger.debug(
            f"All candidates: {[torrent.name for torrent in self.filtered_torrents]}"
        )

        torrents = (
            self.check_for_other_seasons(prime_candidate)
            if prime_candidate.category == "tv"
            else [prime_candidate]
        )
        self.logger.debug(
            f"After season check, {len(torrents)} candidates left: {[torrent.name for torrent in torrents]}"
        )

        return torrents

    def extract_id_and_path(
        self, filename: str, category: str | None = None
    ) -> tuple[int, str]:
        movie_title: str = parse(filename)["title"]
        if category is None:
            radarr_id = self.radarr_runner.find_id_by_title(
                movie_title, ignore_errors=True
            )
            sonarr_id = self.sonarr_runner.find_id_by_title(
                movie_title, ignore_errors=True
            )
            if radarr_id and sonarr_id:
                raise ValueError(
                    f"both Radarr and Sonarr found the same title: {movie_title}"
                )
            if radarr_id:
                return radarr_id, self.radarr_runner.get_path(radarr_id)
            if sonarr_id:
                return sonarr_id, self.sonarr_runner.get_path(sonarr_id)
            raise ValueError(f"media not found in Radarr/Sonarr: {movie_title}")

        if category == "movies":
            runner = self.radarr_runner
        elif category == "tv":
            runner = self.sonarr_runner
        else:
            raise ValueError("unknown category: must be 'movies' or 'tv'")

        media_id = runner.find_id_by_title(movie_title)
        if media_id is None:
            raise ValueError(f"media not found in {runner.service}: {movie_title}")
        return media_id, runner.get_path(media_id)

    # ----------------------
    # Torrent control
    # ----------------------
    def get_torrent_status(self, torrent_hash: str) -> bool:
        torrent = self.client.torrents_info(
            None, None, None, None, None, None, torrent_hash
        )[0]
        if torrent.state in {"moving", "checkingDL", "checkingUP"}:
            self.logger.debug(
                f"still moving/checking {torrent_hash} aka {torrent.name}"
            )
            return False
        else:
            self.logger.info(f"moved/checked torrent {torrent_hash} aka {torrent.name}")
            return True

    def move_torrent(self, torrent_hashes: list[str], new_location: str) -> None:
        for torrent_hash in torrent_hashes:
            try:
                self.client.torrents_set_location(new_location, torrent_hash)

                while True:
                    sleep(15)
                    if self.get_torrent_status(torrent_hash):
                        break

                self.client.torrents_recheck(torrent_hash)

                while True:
                    sleep(15)
                    if self.get_torrent_status(torrent_hash):
                        break

            except exceptions.APIError as move_exception:
                self.logger.error(
                    f"failed to move/recheck torrent {torrent_hash} because: {move_exception}"
                )

    def let_starr_know(self, category: str, media_id: int, new_location: str) -> None:
        if category == "movies":
            runner = self.radarr_runner
        elif category == "tv":
            runner = self.sonarr_runner
        else:
            raise ValueError(f"unknown category: {category}")

        try:
            runner.update_path(media_id, new_location)
        except Exception as e:
            self.logger.error(
                f"failed to let {runner.service} know about the new location because: {e}"
            )
