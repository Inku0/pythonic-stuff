from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from logging import Logger
from os import walk
from pathlib import Path
from time import sleep
from typing import TypedDict

from PTN import parse
from qbittorrentapi import Client, TorrentDictionary, TorrentInfoList
from qbittorrentapi import exceptions as qb_exceptions
from qbittorrentapi.exceptions import Forbidden403Error, LoginFailed
from rapidfuzz import fuzz

from utils.error_codes import ErrorCode
from utils.logging_setup import logging_setup
from utils.narchifska_errors import (
    FileMatchNotFoundError,
    NarchifskaError,
    TorrentAmbiguityError,
    TorrentNotFoundError,
)
from utils.read_env import read_env


class TorrentPathInfo(TypedDict, total=True):
    path: Path
    torrent: TorrentDictionary
    rar_lock: bool


class QBittorrentService:
    """
    Service class for interacting with qBittorrent Web API and related operations.
    """

    def __init__(self) -> None:
        """Initialize the NarchifskaClient with configuration from environment."""
        creds: Mapping[str, str | None] = read_env()
        self.logger: Logger = logging_setup()

        # Load configuration
        try:
            self.host: str = creds["QBIT_HOST"]
            self.port: str = creds["QBIT_PORT"]
            self.username: str = creds["QBIT_USERNAME"]
            self.password: str = creds["QBIT_PASSWORD"]
        except KeyError as e:
            raise NarchifskaError(
                f".env is missing required key: {e}",
                code=ErrorCode.ENV_MISSING,
                context={"missing_key": str(e)},
                cause=e,
            ) from e

        # Initialize client
        try:
            self.client: Client = Client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={"timeout": (360, 360)},
            )
        except qb_exceptions.APIConnectionError as e:
            raise NarchifskaError(
                f"Failed to construct qBittorrent client: {e}",
                code=ErrorCode.CONNECTION,
                cause=e,
            ) from e

        self.all_torrents: list[TorrentDictionary] = []
        self.filtered_torrents: list[TorrentDictionary] = []

    # ----------------------
    # Connection Management
    # ----------------------
    def connect(self) -> None:
        """
        Connect to the qBittorrent Web API.

        Raises:
            NarchifskaError: If connection fails due to permission or network issues
        """
        try:
            self.client.auth_log_in()
            self.logger.info("Connected to qBittorrent Web API")
        except Forbidden403Error as e:
            raise NarchifskaError(
                "Forbidden: not logged in / banned / restricted API.",
                code=ErrorCode.FORBIDDEN,
                context={"host": self.host, "port": self.port},
                cause=e,
            ) from e
        except LoginFailed as e:
            raise NarchifskaError(
                f"Login failed: {e}",
                code=ErrorCode.LOGIN_FAILED,
                context={"host": self.host, "username": self.username},
                cause=e,
            ) from e
        except qb_exceptions.APIConnectionError as e:
            raise NarchifskaError(
                f"Connection error: {e}",
                code=ErrorCode.CONNECTION,
                context={"host": self.host, "port": self.port},
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Disconnect from the qBittorrent Web API."""
        try:
            self.client.auth_log_out()
            self.logger.info("Logged out of qBittorrent Web API")
        except qb_exceptions.APIError as e:
            self.logger.warning(f"API error during logout: {e}")
        except Exception as e:
            self.logger.warning(f"Unexpected error during logout: {e}")

    @contextlib.contextmanager
    def connection_context(self) -> Iterator[None]:
        """
        Context manager for qBittorrent connection.

        Usage:
            with client.connection_context():
                client.some_operation()
        """
        try:
            self.connect()
            yield
        finally:
            self.disconnect()

    # ----------------------
    # Torrent File Helpers
    # ----------------------
    def get_path_by_filename_and_hash_list(
        self, file_name: str, torrent_hashes: Sequence[str]
    ) -> str:
        """
        Search each torrent (by hash) for a file whose basename matches `file_name`.
        Returns the absolute full path of the first match.

        Args:
            file_name: The filename to search for
            torrent_hashes: List of torrent hashes to search within

        Returns:
            str: Absolute path to the matched file

        Raises:
            ValueError: If torrent_hashes is empty
            TorrentAmbiguityError: If a hash resolves to multiple torrents
            FileMatchNotFoundError: If no matching file is found in any torrent
        """
        if not torrent_hashes:
            raise ValueError("torrent_hashes must be provided")

        target_name = Path(file_name).name
        self.logger.debug(
            f"Searching for file '{target_name}' in {len(torrent_hashes)} torrents"
        )

        for torrent_hash in torrent_hashes:
            try:
                results: TorrentInfoList = self.client.torrents_info(
                    None, None, None, None, None, None, torrent_hash
                )
            except qb_exceptions.APIError as e:
                self.logger.error(f"API error fetching torrent {torrent_hash}: {e}")
                continue

            if not results:
                self.logger.warning(f"Hash {torrent_hash} not found; skipping")
                continue
            if len(results) != 1:
                raise TorrentAmbiguityError(torrent_hash, len(results))

            torrent: TorrentDictionary = results[0]
            content_path = Path(str(torrent["content_path"]))

            # handle single-file torrent case
            if content_path.is_file():
                # is this extra check necessary (or even useful)?
                if content_path.name == target_name:
                    resolved = str(content_path.resolve())
                    self.logger.debug(
                        f"Matched {target_name} in single-file torrent {torrent.name}: {resolved}"
                    )
                    return resolved
                continue

            # handle multi-file torrent case
            if not content_path.exists():
                self.logger.warning(
                    f"Content path {content_path} for {torrent_hash} missing; skipping"
                )
                continue

            for root, _, files in walk(content_path):
                if target_name in files:
                    full_path = str((Path(root) / target_name).resolve())
                    self.logger.debug(
                        f"Matched {target_name} in multi-file torrent {torrent.name}: {full_path}"
                    )
                    return full_path

        raise FileMatchNotFoundError(file_name, torrent_hashes)

    def get_paths_torrents_by_hash_list(
        self, torrent_hashes: Sequence[str]
    ) -> dict[str, TorrentPathInfo]:
        """
        Get path and torrent information for a list of torrent hashes.

        Args:
            torrent_hashes: List of torrent hashes to retrieve

        Returns:
            dict: Mapping of torrent hash (str) to its path information (TorrentPathInfo)

        Raises:
            TorrentNotFoundError: If a hash doesn't match any torrent
            TorrentAmbiguityError: If a hash resolves to multiple torrents
        """
        hash_dict: dict[str, TorrentPathInfo] = {}
        self.logger.debug(f"Resolving torrent hashes: {torrent_hashes}")

        def fetch_torrent_info(
            torrent_hash: str,
        ) -> tuple[str, TorrentPathInfo]:
            try:
                results: TorrentInfoList = self.client.torrents_info(
                    None, None, None, None, None, None, torrent_hash
                )
            except qb_exceptions.APIError as e:
                raise TorrentNotFoundError(torrent_hash) from e

            if not results:
                raise TorrentNotFoundError(torrent_hash)
            if len(results) != 1:
                raise TorrentAmbiguityError(torrent_hash, len(results))

            torrent: TorrentDictionary = results[0]
            qbit_path: Path = Path(str(torrent["content_path"]))
            info: TorrentPathInfo = {
                "path": qbit_path,
                "torrent": torrent,
                "rar_lock": False,
            }
            self.logger.debug(
                f"{torrent_hash}: path={qbit_path}, name={torrent.name}, category={torrent.category}"
            )
            return torrent_hash, info

        # for small lists, process sequentially; for larger lists, use thread pool
        if len(torrent_hashes) <= 5:
            for torrent_hash in torrent_hashes:
                fetched_torrent_hash, info = fetch_torrent_info(torrent_hash)
                hash_dict[fetched_torrent_hash] = info
        else:
            with ThreadPoolExecutor(
                max_workers=min(10, len(torrent_hashes))
            ) as executor:
                results = executor.map(fetch_torrent_info, torrent_hashes)
                for torrent_hash, info in results:
                    hash_dict[torrent_hash] = info

        return hash_dict

    def qbit_path_inode_map(
        self, qbit_path: Path, rar_lock: bool = False
    ) -> dict[str, int]:
        """
        Build an inode map for a qBittorrent content path.

        Args:
            qbit_path: Path to the qBittorrent content
            rar_lock: If True, only record a sentinel (-1) for the base path

        Returns:
            dict: Mapping of absolute file paths to their inode numbers
        """
        qbit_structure: dict[str, int] = {}

        if rar_lock:
            qbit_structure[str(qbit_path.resolve())] = -1
            return qbit_structure

        def update(file_path: Path) -> None:
            try:
                qbit_structure[str(file_path.resolve())] = file_path.stat().st_ino
            except FileNotFoundError:
                self.logger.debug(f"Skipping missing during inode scan: {file_path}")
            except PermissionError:
                self.logger.warning(f"Permission denied during inode scan: {file_path}")

        if qbit_path.is_file():
            update(qbit_path)
            return qbit_structure

        # Process directory contents
        try:
            for root, _, filenames in walk(qbit_path):
                rpath = Path(root)
                for fname in filenames:
                    update(rpath / fname)
        except PermissionError as e:
            self.logger.error(f"Permission denied walking directory {qbit_path}: {e}")

        return qbit_structure

    # ----------------------
    # general torrent methods
    # ----------------------
    def move_torrent(self, torrent_hashes: list[str], new_location: Path) -> None:
        """
        Move torrents to a new location and recheck them.

        Args:
            torrent_hashes: List of torrent hashes to move
            new_location: New location path
        """

        with self.connection_context():
            for torrent_hash in torrent_hashes:
                try:
                    self.client.torrents_set_location(new_location, torrent_hash)

                    # periodic poll for move completion
                    while True:
                        sleep(15)
                        torrent = self.client.torrents_info(
                            None, None, None, None, None, None, torrent_hash
                        )[0]
                        if torrent.state not in {"moving", "checkingDL", "checkingUP"}:
                            break

                    self.logger.info(f"Moved torrent {torrent_hash} aka {torrent.name}")

                    # Recheck after move
                    self.client.torrents_recheck(torrent_hash)

                    # wait for recheck to complete
                    while True:
                        sleep(15)
                        torrent = self.client.torrents_info(
                            None, None, None, None, None, None, torrent_hash
                        )[0]
                        if torrent.state not in {"moving", "checkingDL", "checkingUP"}:
                            break

                    self.logger.info(
                        f"Rechecked torrent {torrent_hash} aka {torrent.name}"
                    )

                except Exception as move_exception:
                    self.logger.error(
                        f"Failed to move/recheck torrent {torrent_hash}: {move_exception}"
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
            + f"with path {prime_candidate.content_path} and age {prime_candidate.completion_on}"
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

    def get_inodes_from_hash(self, torrent_hash: str) -> dict[str, int]:
        results = self.client.torrents_info(
            None, None, None, None, None, None, torrent_hash
        )
        if not results:
            raise TorrentNotFoundError(torrent_hash)
        torrent: TorrentDictionary = results[0]
        return self.qbit_path_inode_map(Path(str(torrent["content_path"])))

    def list_torrents(self, category: str | None = None) -> None:
        self.all_torrents = self.client.torrents_info("all", None, "completion_on")  # pyright: ignore[reportAttributeAccessIssue]
        if category is None:
            movies = [t for t in self.all_torrents if t.category == "movies"]
            tv = [t for t in self.all_torrents if t.category == "tv"]
            self.filtered_torrents = movies + tv
        else:
            self.filtered_torrents = [
                t for t in self.all_torrents if t.category == category
            ]
        try:
            self.filtered_torrents.sort(key=lambda x: getattr(x, "completion_on", 0))
        except Exception:
            pass

    def season_counter(self, seasons: Sequence[TorrentDictionary]) -> int:
        seen: set[int] = set()
        for s in seasons:
            try:
                season_val = parse(s.name).get("season")
            except Exception:
                season_val = None
            if isinstance(season_val, int):
                seen.add(season_val)
        return len(seen)

    def check_similarity(
        self, given_torrent: TorrentDictionary, other_torrent: TorrentDictionary
    ) -> bool:
        # should this instead get media file paths from *arr, then find the corresponding torrents?
        ratio = fuzz.ratio(given_torrent.name, other_torrent.name)
        try:
            given_title = parse(given_torrent.name).get("title")
            other_title = parse(other_torrent.name).get("title")
        except Exception:
            return False
        if ratio < 50:
            double_check_ratio: int = fuzz.ratio(given_title, other_title)
            return double_check_ratio > 90 and given_title == other_title
        return ratio > 45 and given_title == other_title

    def get_hash_by_file_and_title(self, file: Path, title: str) -> str:
        """
        Find a torrent hash by fuzzy matching names and files.

        Args:
            file: filename to match against torrent content
            title: title to be fuzzy matched against torrent titles

        Returns:
            str: The hash of the matched torrent

        Raises:
            TorrentNotFoundError: If no torrent matches found
        """
        torrents: TorrentInfoList = self.client.torrents_info()
        for torrent in torrents:
            if fuzz.ratio(title, torrent.name) > 50:
                for root, _, files in walk(torrent.content_path):
                    if file.name in files:
                        self.logger.debug(
                            f"Fuzzy matched {file.name} to {torrent.name} with ratio {fuzz.ratio(file.name, torrent.name)}"
                        )
                return torrent.hash

        raise TorrentNotFoundError(f"torrent containing '{file.name}' not found")

    def check_for_other_seasons(
        self, given_torrent: TorrentDictionary
    ) -> list[TorrentDictionary]:
        """
        Check for other seasons of the same TV show.

        Args:
            given_torrent: The torrent to check for other seasons

        Returns:
            list[TorrentDictionary]: List of torrents that appear to be seasons of the same show
        """
        if given_torrent.category != "tv":
            self.logger.info("Not a TV show, skipping season check")
            return [given_torrent]

        seasons: list[TorrentDictionary] = []
        from concurrent.futures import ThreadPoolExecutor, as_completed

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
            f"Found {actual_seasons_amount} seasons for {given_torrent.name}: {seasons}"
        )

        return seasons
