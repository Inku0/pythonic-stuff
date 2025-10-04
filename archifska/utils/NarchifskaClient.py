from __future__ import annotations

import contextlib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from json import dump, load
from logging import Logger
from os import link, walk
from pathlib import Path
from shutil import copy2
from typing import Any, TypedDict

from PTN import parse
from qbittorrentapi import Client, TorrentDictionary, TorrentInfoList
from qbittorrentapi import exceptions as qb_exceptions
from qbittorrentapi.exceptions import Forbidden403Error, LoginFailed
from rapidfuzz import fuzz

from utils.ErrorCodes import ErrorCode
from utils.logging_setup import logging_setup
from utils.mediaExtensions import MEDIA_EXTENSIONS
from utils.NarchifskaErrors import (
    FileMatchNotFoundError,
    NarchifskaError,
    RestoreError,
    SnapshotError,
    TorrentAmbiguityError,
    TorrentNotFoundError,
)
from utils.read_env import read_env
from utils.StarrUpdater import StarrUpdater


class TorrentPathInfo(TypedDict, total=True):
    path: Path
    torrent: TorrentDictionary
    rar_lock: bool


@dataclass(frozen=True)
class FileEntry:
    """
    Represents a file in a snapshot.

    Attributes:
        path: Absolute path to original file at snapshot time
        inode: Inode number (or 'missing' sentinel) at snapshot time
        qbit_file: Absolute path to linked qBittorrent-managed file (if resolved)
    """

    path: str
    inode: int
    qbit_file: str | None


class NarchifskaClient:
    """
    High-level orchestrator for:
      - qBittorrent inspection and movement
      - Radarr/Sonarr path synchronization
      - Filesystem snapshot & restore of media directories

    The client manages connections to qBittorrent WebUI API and Starr services,
    providing methods to snapshot and restore media directory structures while
    maintaining references to torrent-managed files.
    """

    def __init__(self) -> None:
        """Initialize the NarchifskaClient with configuration from environment."""
        creds: Mapping[str, str | None] = read_env()
        self.logger: Logger = logging_setup()

        # Load configuration
        try:
            self._load_config(creds)
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

    def _load_config(self, creds: dict[str, str]) -> None:
        """Load configuration from credentials dictionary."""
        self.host = creds["QBIT_HOST"]
        self.port = creds["QBIT_PORT"]
        self.username = creds["QBIT_USERNAME"]
        self.password = creds["QBIT_PASSWORD"]

        # Initialize Starr services
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

    @staticmethod
    def _rar_lock_check(files: Iterable[str]) -> bool:
        """
        Check if files represent a multipart rar archive that won't need linking

        Args:
            files: List of filenames to check

        Returns:
            bool: True if the files appear to be a RAR archive set
        """
        has_rar = any(f.endswith(".rar") for f in files)
        has_rar_parts = sum(1 for f in files if fnmatch(f, "*.r[0-9][0-9]")) >= 3
        return has_rar and has_rar_parts

    @staticmethod
    def _is_media_file(name: str) -> bool:
        """
        Check if a file is a recognized media file based on its extension.

        Args:
            name: Filename to check

        Returns:
            bool: True if the file has a recognized media extension
        """
        return Path(name).suffix.lower() in MEDIA_EXTENSIONS

    @staticmethod
    def _invert_inode_map(inode_map: dict[str, int]) -> dict[int, str]:
        """
        Invert an inode map from path->inode to inode->path.

        Args:
            inode_map: Mapping of file paths to inode numbers

        Returns:
            dict: Mapping of inode numbers to file paths
        """
        return {
            inode: file_path for file_path, inode in inode_map.items() if inode != -1
        }

    @staticmethod
    def _logged_copy(src: Path, dst: Path, logger: Logger) -> None:
        """
        Copy a file and log the operation.

        Args:
            src: Source path
            dst: Destination path
            logger: Logger to record the operation
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            copy2(src, dst)
            logger.debug(f"Copied {src} -> {dst}")
        except PermissionError as e:
            logger.error(f"Permission denied copying {src} -> {dst}: {e}")
            raise
        except FileNotFoundError as e:
            logger.error(f"File not found copying {src} -> {dst}: {e}")
            raise

    @staticmethod
    def _logged_link(src: Path, dst: Path, logger: Logger) -> None:
        """
        Create a hard link between files and log the operation.
        Falls back to copy if linking fails.

        Args:
            src: Source path
            dst: Destination path
            logger: Logger to record the operation
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            link(src, dst)
            logger.debug(f"Linked {src} -> {dst}")
        except OSError as e:
            logger.warning(f"Hardlink failed ({e}), fallback copy: {src} -> {dst}")
            NarchifskaClient._logged_copy(src, dst, logger)
        except Exception as e:
            logger.warning(
                f"Unexpected error during linking ({e}), fallback copy: {src} -> {dst}"
            )
            NarchifskaClient._logged_copy(src, dst, logger)

    @staticmethod
    def _link_or_copy(src: Path, dst: Path, logger: Logger) -> None:
        """
        Create a hard link between files, falling back to copy if linking fails.

        Args:
            src: Source path
            dst: Destination path
            logger: Logger to record the operation
        """
        NarchifskaClient._logged_link(src, dst, logger)

    # ----------------------
    # Snapshot
    # ----------------------
    def save_structure(
        self,
        original_location: str | Path,
        save_file: str | Path,
        torrent_hashes: Sequence[str],  # list of torrent hashes as strings
    ) -> None:
        """
        Snapshot directory structure for later restoration.
        Attempts to link files to qBittorrent-managed originals via inode match.
        """
        if not torrent_hashes:
            raise SnapshotError("torrent_hashes must be provided")

        original_path = Path(original_location).resolve()
        if not original_path.exists():
            raise SnapshotError(
                "original_location does not exist",
                original=str(original_path),
            )

        torrent_hash_dict = self.get_paths_torrents_by_hash_list(torrent_hashes)

        qbit_structure: dict[str, int] = {}
        for t_hash, info in torrent_hash_dict.items():
            t_path = info["path"]
            if not t_path.exists():
                raise SnapshotError(
                    "torrent content path missing",
                    torrent_hash=t_hash,
                    path=str(t_path),
                )
            all_files: list[str] = []
            for _, _, filenames in walk(t_path):
                all_files.extend(filenames)
            rar_lock = self._rar_lock_check(all_files)
            info["rar_lock"] = rar_lock
            qbit_structure.update(
                self.qbit_path_inode_map(qbit_path=t_path, rar_lock=rar_lock)
            )
            self.logger.debug(
                f"hash={t_hash} name={info['torrent'].name} rar_lock={rar_lock}"
            )

        inode_to_qbit_file = self._invert_inode_map(qbit_structure)
        self.logger.debug(f"Inode index size={len(inode_to_qbit_file)}")

        structure: dict[str, dict[str, Any]] = {}
        for root, dirs, filenames in walk(original_path):
            rpath = Path(root)
            structure[root] = {"basename": rpath.name, "dirs": dirs, "files": {}}
            for fname in filenames:
                fpath = rpath / fname
                qbit_file: str | None = None
                inode: int | None = None
                try:
                    inode = fpath.stat().st_ino
                    if inode in inode_to_qbit_file and inode != -1:
                        qbit_file = inode_to_qbit_file[inode]
                except FileNotFoundError:
                    inode = None
                    self.logger.debug(
                        f"File got raptured (rip) during snapshot: {fpath}"
                    )

                entry = FileEntry(
                    path=str(fpath.resolve()),
                    inode=inode if inode is not None else -1,
                    qbit_file=qbit_file,
                )
                structure[root]["files"][fname] = asdict(entry)

        save_path = Path(save_file)
        with save_path.open("w", encoding="utf-8") as fh:
            dump(structure, fh, indent=2)
        self.logger.info(f"Snapshot saved to {save_path}")

    # ----------------------
    # Restore
    # ----------------------
    def restore_structure(
        self,
        original_location: str | Path,
        new_location: str | Path,
        save_file: str | Path,
        torrent_hashes: list[str],
        *,
        verify_missing_media: bool = True,
        relink_if_missing: bool = True,
    ) -> None:
        """
        Restore a previously saved structure:
          - Hardlink qbit-managed files where possible.
          - Copy where linking fails.
          - Attempt relink if original qbit file vanished but basename exists in current torrents.
        """
        if not torrent_hashes:
            raise RestoreError("torrent_hashes must be provided")

        original_path = Path(original_location).resolve()
        new_path = Path(new_location).resolve()
        save_file_path = Path(save_file).resolve()

        if not save_file_path.exists():
            raise RestoreError("snapshot file not found", save_file=str(save_file_path))

        with save_file_path.open("r", encoding="utf-8") as fh:
            stored_structure: dict[str, dict[str, Any]] = load(fh)

        torrent_hash_dict = self.get_paths_torrents_by_hash_list(torrent_hashes)

        basename_index: dict[str, str] = {}
        for info in torrent_hash_dict.values():
            inode_map = self.qbit_path_inode_map(
                info["path"], rar_lock=info.get("rar_lock", False)
            )
            for absfile in inode_map:
                basename_index[Path(absfile).name] = absfile

        for base_root, content in stored_structure.items():
            files: dict[str, dict[str, Any]] = content.get("files", {})
            base_root_path = Path(base_root)

            try:
                rel_part = base_root_path.relative_to(original_path)
            except ValueError:
                # Fallback: treat as absolute mismatch
                rel_part = base_root_path.name

            target_root = new_path / rel_part
            target_root.mkdir(parents=True, exist_ok=True)

            for fname, finfo in files.items():
                original_file_path = Path(finfo["path"])
                qbit_file_saved: str | None = finfo.get("qbit_file")
                target_file_path = target_root / fname

                if qbit_file_saved:
                    qbit_candidate = Path(qbit_file_saved)
                    if not qbit_candidate.exists() and relink_if_missing:
                        remap = basename_index.get(qbit_candidate.name)
                        if remap:
                            self.logger.info(
                                f"Relinking {qbit_candidate.name} -> {remap}"
                            )
                            qbit_candidate = Path(remap)

                    if qbit_candidate.exists():
                        self._link_or_copy(
                            qbit_candidate, target_file_path, self.logger
                        )
                        continue
                    else:
                        self.logger.warning(
                            f"Stored qbit file missing and not relinked: {qbit_candidate}"
                        )

                # Handle unlinked media
                if self._is_media_file(fname) and verify_missing_media:
                    try:
                        response = (
                            input(
                                f"Missing linkage for media {fname}. Continue? (y/N): "
                            )
                            .strip()
                            .lower()
                        )
                    except EOFError:
                        response = "y"
                    if response not in {"y", "yes"}:
                        raise RestoreError(
                            "aborted due to missing media linkage", file=fname
                        )

                if original_file_path.exists():
                    self._logged_copy(original_file_path, target_file_path, self.logger)
                else:
                    self.logger.error(
                        f"Original file missing; cannot restore {target_file_path}"
                    )

        self.logger.info(f"Restore completed: {new_path}")

    # ----------------------
    # Torrent inspection
    # ----------------------
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
