from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from json import dump, load
from logging import Logger
from os import link, walk
from pathlib import Path
from shutil import copy2
from typing import Any, TypedDict

from qbittorrentapi import TorrentDictionary

from utils.logging_setup import logging_setup
from utils.media_extensions import MEDIA_EXTENSIONS
from utils.narchifska_errors import (
    RestoreError,
    SnapshotError,
)
from utils.qbittorrent_service import QBittorrentService


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


class FilesystemService:
    """
    Snapshot and restore filesystem structures, linking to qBittorrent-managed files.
    """

    def __init__(self, qbit_service: QBittorrentService) -> None:
        self.logger: Logger = logging_setup()
        # get the qbit_service from up-high
        self.qbit_service: QBittorrentService = qbit_service

    # ----------------------
    # Static file methods
    # ----------------------
    @staticmethod
    def _rar_lock_check(files: list[str]) -> bool:
        """
        Check if files represent a multipart rar archive that won't need linking.

        A RAR lock is engaged if:
        1. At least one file ends with .rar
        2. At least 3 files match the pattern *.r[0-9][0-9] (part files)

        When a RAR lock is engaged, media files are excluded from linking and
        will be treated as non-qbit files.

        Args:
            files: List of filenames to check

        Returns:
            bool: True if the files appear to be a RAR archive set
        """
        has_rar = any(f.endswith(".rar") for f in files)
        has_rar_parts = sum(1 for f in files if fnmatch(f, "*.r[0-9][0-9]")) >= 3
        return has_rar and has_rar_parts

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
            result = copy2(src, dst)
            logger.debug(f"Copied {src} -> {result}")
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
            # should Path.link() be used here?
            link(src, dst)
            logger.debug(f"Linked {src} -> {dst}")
        except OSError as e:
            logger.warning(f"Hardlink failed ({e}), fallback copy: {src} -> {dst}")
            FilesystemService._logged_copy(src, dst, logger)
        except Exception as e:
            logger.warning(
                f"Unexpected error during linking ({e}), fallback copy: {src} -> {dst}"
            )
            FilesystemService._logged_copy(src, dst, logger)

    @staticmethod
    def _link_or_copy(src: Path, dst: Path, logger: Logger) -> None:
        """
        Create a hard link between files, falling back to copy if linking fails.

        Args:
            src: Source path
            dst: Destination path
            logger: Logger to record the operation
        """
        FilesystemService._logged_link(src, dst, logger)

    # ----------------------
    # Snapshot
    # ----------------------
    def save_structure(
        self,
        original_location: Path,
        save_file: Path,
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

        torrent_hash_dict = self.qbit_service.get_paths_torrents_by_hash_list(
            torrent_hashes
        )

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
                self.qbit_service.qbit_path_inode_map(
                    qbit_path=t_path, rar_lock=rar_lock
                )
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
        original_location: Path,
        new_location: Path,
        save_file: Path,
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
        weird_cases = []
        if not torrent_hashes:
            raise RestoreError("torrent_hashes must be provided")

        original_path = Path(original_location).resolve()
        new_path = Path(new_location).resolve()
        save_file_path = Path(save_file).resolve()

        if not save_file_path.exists():
            raise RestoreError("snapshot file not found", save_file=str(save_file_path))

        with save_file_path.open("r", encoding="utf-8") as fh:
            stored_structure: dict[str, dict[str, Any]] = load(fh)

        torrent_hash_dict = self.qbit_service.get_paths_torrents_by_hash_list(
            torrent_hashes
        )

        basename_index: dict[str, str] = {}
        for info in torrent_hash_dict.values():
            inode_map = self.qbit_service.qbit_path_inode_map(
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
                        try:
                            self._link_or_copy(
                                qbit_candidate, target_file_path, self.logger
                            )
                            continue
                        except Exception as e:
                            self.logger.error(
                                f"Failed to link/copy {qbit_candidate} -> {target_file_path}: {e}"
                            )
                            weird_cases.append(
                                (
                                    fname,
                                    str(original_file_path),
                                    str(target_root),
                                    "link_failed",
                                )
                            )
                    else:
                        self.logger.warning(
                            f"Stored qbit file missing and not relinked: {qbit_candidate}"
                        )
                        weird_cases.append(
                            (
                                fname,
                                str(original_file_path),
                                str(target_root),
                                "qbit_file_missing",
                            )
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
                    try:
                        self._logged_copy(
                            original_file_path, target_file_path, self.logger
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to copy {original_file_path} -> {target_file_path}: {e}"
                        )
                        weird_cases.append(
                            (
                                fname,
                                str(original_file_path),
                                str(target_root),
                                "copy_failed",
                            )
                        )
                else:
                    self.logger.error(
                        f"Original file missing; cannot restore {target_file_path}"
                    )
                    weird_cases.append(
                        (
                            fname,
                            str(original_file_path),
                            str(target_root),
                            "original_missing",
                        )
                    )

        self.logger.info(f"Restore completed: {new_path}")

        if weird_cases:
            weird_log_path = Path(new_path) / "RECHECK_THESE.txt"
            with weird_log_path.open("a", encoding="utf-8") as recheck_file:
                for item in weird_cases:
                    recheck_file.write(f"{item}\n")
            self.logger.warning(
                f"Some files had issues during restore. See {weird_log_path}"
            )
