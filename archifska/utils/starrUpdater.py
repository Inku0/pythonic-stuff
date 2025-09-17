from __future__ import annotations

from logging import Logger
from os import path
from typing import Any
from urllib.parse import urlparse

from pyarr import RadarrAPI, SonarrAPI
from rapidfuzz import fuzz

from utils.loggingSetup import logging_setup

FUZZ_THRESHOLD = 65


def _build_base_url(host: str, port: str | None) -> str:
    host = host.strip().rstrip("/")
    parsed = urlparse(host)
    if parsed.scheme:  # already a full URL
        base = host
    else:
        base = f"http://{host}"
    if port and f":{port}" not in base.split("://", 1)[-1]:
        base = f"{base}:{port}"
    return base


class StarrUpdater:
    """
    Interact with Sonarr/Radarr to discover media and update library paths.
    """

    def __init__(self, host: str, port: str | None, api_key: str, service: str):
        self.logger: Logger = logging_setup()
        self.host = host
        self.port = port or ""
        self.api_key = api_key
        self.service = service.lower().strip()
        self.host_url = _build_base_url(self.host, self.port)

        if self.service not in {"sonarr", "radarr"}:
            raise ValueError(f"Unsupported service: {self.service}")

    # --------
    # Sonarr
    # --------
    def get_seasons(self, media_id: int) -> list[dict[str, Any]]:
        if self.service != "sonarr":
            raise ValueError("get_seasons is only available for Sonarr")
        sonarr = SonarrAPI(self.host_url, self.api_key)
        series = sonarr.get_series(media_id)
        seasons = series.get("seasons") or []
        if not isinstance(seasons, list):
            return []
        return seasons

    # ---------------
    # Common helpers
    # ---------------
    def find_id_by_title(self, title: str, ignore_errors: bool = False) -> int | None:
        match self.service:
            case "sonarr":
                return self._find_sonarr_id_by_title(title, ignore_errors)
            case "radarr":
                return self._find_radarr_id_by_title(title, ignore_errors)
            case _:
                if not ignore_errors:
                    self.logger.error(f"unknown service: {self.service}")
                return None

    def get_path(self, media_id: int) -> str | None:
        match self.service:
            case "sonarr":
                sonarr = SonarrAPI(self.host_url, self.api_key)
                media = sonarr.get_series(media_id)
                return media.get("path")
            case "radarr":
                radarr = RadarrAPI(self.host_url, self.api_key)
                media = radarr.get_movie(media_id)
                return media.get("path")
            case _:
                self.logger.error(f"unknown service: {self.service}")
                return None

    @staticmethod
    def is_archifskad(media_path: str) -> bool:
        return "megafarm" in (media_path or "")

    def update_path(self, media_id: int, new_location: str) -> None:
        runner = self._get_runner()
        media = self._get_media(runner, media_id)

        current_path = media.get("path")
        if not current_path:
            self.logger.error(f"media {media_id} has no path set")
            return

        if self.is_archifskad(current_path):
            self.logger.warning(
                f"media {media_id} appears to be already archifskad: {current_path}"
            )
            return

        new_full_path = path.join(new_location, path.basename(current_path))
        self.logger.info(f"updating path for media {media_id} to {new_full_path}")
        media["path"] = new_full_path

        try:
            if self.service == "sonarr":
                runner.upd_series(media)
            else:
                runner.upd_movie(media)
        except Exception as e:
            self.logger.error(f"failed to update {self.service} media {media_id}: {e}")

    # ---------------
    # Private helpers
    # ---------------
    def _get_runner(self):
        if self.service == "sonarr":
            return SonarrAPI(self.host_url, self.api_key)
        else:
            return RadarrAPI(self.host_url, self.api_key)

    def _get_media(self, runner, media_id: int) -> dict[str, Any]:
        if self.service == "sonarr":
            return runner.get_series(media_id)
        else:
            return runner.get_movie(media_id)

    def _find_sonarr_id_by_title(self, title: str, ignore_errors: bool) -> int | None:
        sonarr = SonarrAPI(self.host_url, self.api_key)
        try:
            series_list = sonarr.get_series()
        except Exception as e:
            if not ignore_errors:
                self.logger.error(f"failed to query Sonarr: {e}")
            return None

        best_id = None
        best_score = -1

        for show in series_list or []:
            score = max(
                fuzz.ratio(title, show.get("title", "")),
                max(
                    (
                        fuzz.ratio(title, t.get("title", ""))
                        for t in show.get("alternateTitles", [])
                    ),
                    default=0,
                ),
            )
            if score > best_score and score >= FUZZ_THRESHOLD:
                best_score = score
                best_id = show.get("id")

        if best_id is None and not ignore_errors:
            self.logger.error(f"media {title} not found in sonarr")
        else:
            self.logger.debug(
                f"best Sonarr match for '{title}': id={best_id}, score={best_score}"
            )
        return best_id

    def _find_radarr_id_by_title(self, title: str, ignore_errors: bool) -> int | None:
        radarr = RadarrAPI(self.host_url, self.api_key)
        try:
            movies = radarr.get_movie()
        except Exception as e:
            if not ignore_errors:
                self.logger.error(f"failed to query Radarr: {e}")
            return None

        best_id = None
        best_score = -1

        for movie in movies or []:
            score = max(
                fuzz.ratio(title, movie.get("originalTitle", "")),
                fuzz.ratio(title, movie.get("title", "")),
                max(
                    (
                        fuzz.ratio(title, t.get("title", ""))
                        for t in movie.get("alternateTitles", [])
                    ),
                    default=0,
                ),
            )
            if score > best_score and score >= FUZZ_THRESHOLD:
                best_score = score
                best_id = movie.get("id")

        if best_id is None and not ignore_errors:
            self.logger.error(f"media {title} not found in radarr")
        else:
            self.logger.debug(
                f"best Radarr match for '{title}': id={best_id}, score={best_score}"
            )
        return best_id
