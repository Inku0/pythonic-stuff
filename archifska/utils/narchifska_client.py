from __future__ import annotations

from utils.filesystem_service import FilesystemService
from utils.qbittorrent_service import QBittorrentService
from utils.starr_updater import StarrUpdater


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
        self.qbit_service: QBittorrentService = QBittorrentService()
        self.fs_service: FilesystemService = FilesystemService(
            qbit_service=self.qbit_service
        )
        self.starr_updater: StarrUpdater = StarrUpdater()
