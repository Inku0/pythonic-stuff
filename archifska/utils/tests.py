import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure 'archifska' root is on sys.path to allow 'utils.*' imports as a namespace package
THIS_FILE = Path(__file__).resolve()
ARCHIFSKA_ROOT = THIS_FILE.parents[1]  # .../archifska
if str(ARCHIFSKA_ROOT) not in sys.path:
    sys.path.insert(0, str(ARCHIFSKA_ROOT))

# Import modules under test after adjusting sys.path
from utils import archiskaClient as ac_mod  # module for monkeypatching
from utils import starrUpdater as su_mod  # module for monkeypatching
from utils.archiskaClient import ArchifskaQBitClient
from utils.starrUpdater import StarrUpdater, _build_base_url


# -----------------------
# StarrUpdater test suite
# -----------------------
def test_build_base_url():
    assert _build_base_url("http://localhost", "8989") == "http://localhost:8989"
    assert _build_base_url("http://localhost:8989", "8989") == "http://localhost:8989"
    assert _build_base_url("localhost", "7878") == "http://localhost:7878"
    assert _build_base_url("https://sonarr.local", None) == "https://sonarr.local"


def test_sonarr_get_seasons(monkeypatch: pytest.MonkeyPatch):
    class FakeSonarr:
        def __init__(self, host_url: str, api_key: str) -> None:
            self.host_url = host_url
            self.api_key = api_key

        def get_series(self, media_id: int) -> dict[str, Any]:
            assert media_id == 42
            return {
                "id": media_id,
                "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}],
            }

    # Monkeypatch the pyarr SonarrAPI used in module namespace
    monkeypatch.setattr(su_mod, "SonarrAPI", FakeSonarr)

    updater = StarrUpdater(
        host="http://sonarr", port="8989", api_key="xyz", service="sonarr"
    )
    seasons = updater.get_seasons(42)
    assert isinstance(seasons, list)
    assert len(seasons) == 2
    assert seasons[0]["seasonNumber"] == 1


def test_find_id_by_title_sonarr_best_match(monkeypatch: pytest.MonkeyPatch):
    class FakeSonarr:
        def __init__(self, host_url: str, api_key: str) -> None:
            pass

        def get_series(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": 1,
                    "title": "Some Other Show",
                    "alternateTitles": [{"title": "SOS"}],
                },
                {"id": 2, "title": "My Exact Title", "alternateTitles": []},
                {
                    "id": 3,
                    "title": "Close Enough",
                    "alternateTitles": [{"title": "My Exact Ttl"}],
                },
            ]

    monkeypatch.setattr(su_mod, "SonarrAPI", FakeSonarr)
    updater = StarrUpdater(
        host="http://sonarr", port="8989", api_key="xyz", service="sonarr"
    )
    # Should pick the exact title (id=2) as best match
    mid = updater.find_id_by_title("My Exact Title")
    assert mid == 2


def test_get_path_radarr(monkeypatch: pytest.MonkeyPatch):
    class FakeRadarr:
        def __init__(self, host_url: str, api_key: str) -> None:
            pass

        def get_movie(self, media_id: int) -> dict[str, Any]:
            return {"id": media_id, "path": "/movies/Title (2024)"}

    monkeypatch.setattr(su_mod, "RadarrAPI", FakeRadarr)
    updater = StarrUpdater(
        host="http://radarr", port="7878", api_key="abc", service="radarr"
    )
    p = updater.get_path(111)
    assert p == "/movies/Title (2024)"


def test_update_path_radarr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeRadarr:
        def __init__(self) -> None:
            self.updates: list[dict[str, Any]] = []

        def get_movie(self, media_id: int) -> dict[str, Any]:
            return {"id": media_id, "path": "/media/Movies/Title (2021)"}

        def upd_movie(self, media: dict[str, Any]) -> None:
            self.updates.append(dict(media))

    fake = FakeRadarr()

    updater = StarrUpdater(
        host="http://radarr", port="7878", api_key="abc", service="radarr"
    )

    # Use instance-level monkeypatch for simple control
    monkeypatch.setattr(updater, "_get_runner", lambda: fake)

    new_base = "/mnt/megafarm/Movies"
    updater.update_path(media_id=1, new_location=new_base)

    assert len(fake.updates) == 1
    assert fake.updates[0]["path"] == f"{new_base}/Title (2021)"


def test_update_path_skips_when_already_archifskad(monkeypatch: pytest.MonkeyPatch):
    class FakeRadarr:
        def __init__(self) -> None:
            self.updates: list[dict[str, Any]] = []

        def get_movie(self, media_id: int) -> dict[str, Any]:
            return {"id": media_id, "path": "/mnt/megafarm/Movies/Title (2020)"}

        def upd_movie(self, media: dict[str, Any]) -> None:
            self.updates.append(dict(media))

    fake = FakeRadarr()
    updater = StarrUpdater(
        host="http://radarr", port="7878", api_key="abc", service="radarr"
    )
    monkeypatch.setattr(updater, "_get_runner", lambda: fake)

    updater.update_path(media_id=2, new_location="/some/new/base")

    # No update should be performed
    assert len(fake.updates) == 0


# --------------------------------------
# ArchifskaQBitClient structure snapshot
# --------------------------------------
def _fake_env() -> dict[str, str]:
    return {
        "QBIT_HOST": "http://localhost",
        "QBIT_PORT": "8080",
        "QBIT_USERNAME": "user",
        "QBIT_PASSWORD": "pass",
        "RADARR_HOST": "http://radarr",
        "RADARR_PORT": "7878",
        "RADARR_API_KEY": "abc",
        "SONARR_HOST": "http://sonarr",
        "SONARR_PORT": "8989",
        "SONARR_API_KEY": "xyz",
    }


def _basic_logger() -> logging.Logger:
    logger = logging.getLogger("archifska_test")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)
    return logger


def test_save_and_restore_links_with_inode_matching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Arrange environment and logging
    monkeypatch.setattr(ac_mod, "read_env", _fake_env)
    monkeypatch.setattr(ac_mod, "logging_setup", _basic_logger)

    client = ArchifskaQBitClient()

    qbit_dir = tmp_path / "qbit"
    orig_dir = tmp_path / "orig"
    new_dir = tmp_path / "new"
    qbit_dir.mkdir()
    orig_dir.mkdir()
    new_dir.mkdir()

    # Create qbit-managed file
    qbit_file = qbit_dir / "movie.mkv"
    qbit_file.write_bytes(b"video data")

    # Create original structure with a hardlink to qbit file (same inode)
    orig_movie = orig_dir / "movie.mkv"
    os.link(qbit_file, orig_movie)

    # Create a non-qbit file
    other_file = orig_dir / "note.txt"
    other_file.write_text("hello")

    # Make qbit path discoverable
    monkeypatch.setattr(
        client,
        "get_paths_torrents_by_hash",
        lambda torrent_hashes: ([], [str(qbit_dir)]),
    )

    snapshot_path = tmp_path / "snapshot.json"

    # Act: save structure
    client.save_structure(str(orig_dir), str(snapshot_path), torrent_hashes=["abc123"])

    # Assert snapshot content
    data = json.loads(snapshot_path.read_text())
    orig_dir_entry = data[str(orig_dir)]
    assert "files" in orig_dir_entry
    assert "movie.mkv" in orig_dir_entry["files"]
    assert "note.txt" in orig_dir_entry["files"]
    assert orig_dir_entry["files"]["movie.mkv"]["qbit_file"] is not None
    assert Path(orig_dir_entry["files"]["movie.mkv"]["qbit_file"]).name == "movie.mkv"
    assert orig_dir_entry["files"]["note.txt"]["qbit_file"] is None

    # Act: restore structure
    client.restore_structure(
        original_location=str(orig_dir),
        new_location=str(new_dir),
        save_file=str(snapshot_path),
        torrent_hashes=["abc123"],
    )

    # Assert restore results
    restored_movie = new_dir / "movie.mkv"
    restored_note = new_dir / "note.txt"

    assert restored_movie.exists()
    assert restored_note.exists()
    assert restored_note.read_text() == "hello"

    # movie should be a hardlink to qbit_file (same inode)
    assert restored_movie.stat().st_ino == qbit_file.stat().st_ino
    # note should be a copy (different inode than original)
    assert restored_note.stat().st_ino != other_file.stat().st_ino


def test_save_structure_rar_lock_excludes_media(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Arrange environment and logging
    monkeypatch.setattr(ac_mod, "read_env", _fake_env)
    monkeypatch.setattr(ac_mod, "logging_setup", _basic_logger)

    client = ArchifskaQBitClient()

    qbit_dir = tmp_path / "qbit"
    orig_dir = tmp_path / "orig"
    qbit_dir.mkdir()
    orig_dir.mkdir()

    # Set up RAR lock in qbit path
    (qbit_dir / "archive.part01.rar").write_bytes(b"rar")
    (qbit_dir / "archive.r00").write_bytes(b"part")
    (qbit_dir / "archive.r01").write_bytes(b"part")
    (qbit_dir / "archive.r02").write_bytes(b"part")

    # Media file inside qbit path
    qbit_media = qbit_dir / "episode.mkv"
    qbit_media.write_bytes(b"media")
    # Original path contains a hardlink to qbit media (would match by inode)
    orig_media = orig_dir / "episode.mkv"
    os.link(qbit_media, orig_media)

    # qbit path discovery stub
    monkeypatch.setattr(
        client,
        "get_paths_torrents_by_hash",
        lambda torrent_hashes: ([], [str(qbit_dir)]),
    )

    snapshot_path = tmp_path / "snapshot_rar.json"

    # Act: save structure with rar lock engaged
    client.save_structure(str(orig_dir), str(snapshot_path), torrent_hashes=["def456"])

    # Assert: media should be excluded from qbit linking
    data = json.loads(snapshot_path.read_text())
    entry = data[str(orig_dir)]["files"]["episode.mkv"]
    assert entry["qbit_file"] is None

    # On restore, it should copy from original (not link), producing a different inode than qbit_media
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    client.restore_structure(
        original_location=str(orig_dir),
        new_location=str(new_dir),
        save_file=str(snapshot_path),
        torrent_hashes=["def456"],
    )
    restored = new_dir / "episode.mkv"
    assert restored.exists()
    assert restored.stat().st_ino != qbit_media.stat().st_ino
