from collections.abc import Sequence
from typing import Any

from utils.error_codes import ErrorCode


class NarchifskaError(Exception):
    """
    Base structured exception with an error code and contextual metadata.
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.GENERIC,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context or {}
        self.__cause__ = cause

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if self.context:
            return f"{base} | context={self.context}"
        return base


class TorrentNotFoundError(NarchifskaError):
    def __init__(self, torrent_hash: str):
        super().__init__(
            f"torrent with hash {torrent_hash} not found",
            code=ErrorCode.TORRENT_NOT_FOUND,
            context={"hash": torrent_hash},
        )


class TorrentAmbiguityError(NarchifskaError):
    def __init__(self, torrent_hash: str, count: int):
        super().__init__(
            f"expected exactly one torrent for hash {torrent_hash}, found {count}",
            code=ErrorCode.TORRENT_AMBIGUOUS,
            context={"hash": torrent_hash, "count": count},
        )


class FileMatchNotFoundError(NarchifskaError):
    def __init__(self, file_name: str, hashes: Sequence[str]):
        super().__init__(
            f"file '{file_name}' not found in provided torrent hashes",
            code=ErrorCode.FILE_MATCH_NOT_FOUND,
            context={"file_name": file_name, "hashes": list(hashes)},
        )


class SnapshotError(NarchifskaError):
    def __init__(self, message: str, **ctx: Any):
        super().__init__(message, code=ErrorCode.SNAPSHOT, context=ctx)


class RestoreError(NarchifskaError):
    def __init__(self, message: str, **ctx: Any):
        super().__init__(message, code=ErrorCode.RESTORE, context=ctx)
