from __future__ import annotations

from collections.abc import Mapping
from logging import Logger
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pyarr import RadarrAPI, SonarrAPI
from rapidfuzz import fuzz

from utils.error_codes import ErrorCode
from utils.logging_setup import logging_setup
from utils.narchifska_errors import NarchifskaError
from utils.read_env import read_env

# Threshold for fuzzy matching media titles
FUZZ_THRESHOLD = 65

# Type definitions
ServiceType = Literal["sonarr", "radarr"]
MediaID = int


def _build_base_url(host: str, port: str | None) -> str:
    """
    build a complete base URL from host and optional port parameters.

    Args:
        host: The hostname or base URL
        port: Optional port number as string

    Returns:
        Complete base URL with scheme and port if needed
    """
    host = host.strip().rstrip("/")
    parsed = urlparse(host)

    # Add http:// if no scheme provided
    if parsed.scheme:
        base = host
    else:
        base = f"http://{host}"

    # Add port if not already in the URL
    if port and f":{port}" not in base.split("://", 1)[-1]:
        base = f"{base}:{port}"

    return base


class StarrUpdater:
    """
    Interact with Sonarr/Radarr APIs to discover media and update library paths.

    This class provides a unified interface to both Sonarr and Radarr APIs,
    offering methods to find media by title, retrieve paths, and update paths.
    """

    def __init__(self) -> None:
        creds: Mapping[str, str | None] = read_env()

        try:
            self.radarr_host: str = creds["RADARR_HOST"]
            self.radarr_port: str = creds["RADARR_PORT"]
            self.radarr_api_key: str = creds["RADARR_API_KEY"]
            self.sonarr_host: str = creds["SONARR_HOST"]
            self.sonarr_port: str = creds["SONARR_PORT"]
            self.sonarr_api_key: str = creds["SONARR_API_KEY"]

        except KeyError as e:
            raise NarchifskaError(
                f".env is missing required key: {e}",
                code=ErrorCode.ENV_MISSING,
                context={"missing_key": str(e)},
                cause=e,
            ) from e

        self.logger: Logger = logging_setup()
        self.radarr_host_url: str = _build_base_url(self.radarr_host, self.radarr_port)
        self.sonarr_host_url: str = _build_base_url(self.sonarr_host, self.sonarr_port)

        # initialize API clients
        self.radarr_api: RadarrAPI = RadarrAPI(
            host_url=self.radarr_host_url, api_key=self.sonarr_api_key
        )
        self.sonarr_api: SonarrAPI = SonarrAPI(
            host_url=self.sonarr_host_url, api_key=self.sonarr_api_key
        )

    # ---------------
    # Common helpers
    # ---------------
    def find_id_by_title(self, title: str, service: ServiceType) -> MediaID | None:
        """
        Find media ID by title using fuzzy matching.

        Args:
            title: Media title to search for

        Returns:
            Media ID if found, None otherwise
        """
        match service:
            case "sonarr":
                return self._find_sonarr_id_by_title(title)
            case "radarr":
                return self._find_radarr_id_by_title(title)
            case _:
                raise ValueError(f"Unknown service: {service}")

    def get_path(self, media_id: MediaID, service: ServiceType) -> str | None:
        """
        Get the filesystem path for media by ID.

        Args:
            media_id: ID of the media item

        Returns:
            Filesystem path as string, or None if not found
        """
        match service:
            case "sonarr":
                return self.sonarr_api.get_series(media_id)
            case "radarr":
                return self.radarr_api.get_movie(media_id)
            case _:
                raise ValueError(f"Unknown service: {service}")

    @staticmethod
    def is_archifskad(media_path: str) -> bool:
        """
        Check if media path appears to be already processed by Archifska.

        Args:
            media_path: Media path to check

        Returns:
            True if path appears to be already processed
        """
        return "megafarm" in (media_path)

    def update_path(
        self, media_id: MediaID, new_location: str, service: ServiceType
    ) -> bool:
        """
        Update the path for a media item.

        Args:
            media_id: ID of the media item
            new_location: New root location for the media

        Returns:
            True if update was successful, False otherwise
        """
        try:
            media = None

            match service:
                case "sonarr":
                    media = self.sonarr_api.get_series(media_id)
                case "radarr":
                    media = self.radarr_api.get_movie(media_id)

            current_path: str = media.get("path")

            if not current_path:
                self.logger.error(f"media {media_id} has no path set")
                return False

            if self.is_archifskad(current_path):
                self.logger.warning(
                    f"media {media_id} appears to be already archifskad: {current_path}"
                )
                return False

            # create the new path by joining the new location with current basename
            new_full_path = str(Path(new_location) / Path(current_path).name)
            self.logger.info(f"Updating path for media {media_id} to {new_full_path}")
            media["path"] = new_full_path

            # update the media record
            match service:
                case "sonarr":
                    self.sonarr_api.upd_series(media)
                case "radarr":
                    self.radarr_api.upd_movie(media)

            return True

        except Exception as e:
            self.logger.error(f"Failed to update {service} media {media_id}: {e}")
            return False

    # ---------------
    # Private helpers
    # ---------------

    def _find_sonarr_id_by_title(self, title: str) -> MediaID | None:
        """
        Find Sonarr series ID by title using fuzzy matching.

        Args:
            title: Series title to search for

        Returns:
            Series ID if found, None otherwise
        """
        series_list = self.sonarr_api.get_series()

        # Handle empty response
        if not series_list:
            raise ValueError("no series found in Sonarr library")

        best_id = None
        best_score = -1

        for show in series_list:
            # Get primary title score
            primary_score = fuzz.ratio(title, show.get("title"))

            # Get scores for alternate titles
            alt_scores = [
                fuzz.ratio(title, t.get("title")) for t in show.get("alternateTitles")
            ]

            # Use the highest score among primary and alternates
            max_alt_score = max(alt_scores, default=0)
            score = max(primary_score, max_alt_score)

            if score > best_score and score >= FUZZ_THRESHOLD:
                best_score = score
                best_id = show.get("id")

        if best_id is None:
            raise ValueError(f"series '{title}' not found in Sonarr")
        else:
            self.logger.debug(
                f"Best Sonarr match for '{title}': id={best_id}, score={best_score}"
            )

        return best_id

    def _find_radarr_id_by_title(self, title: str) -> MediaID | None:
        """
        Find Radarr movie ID by title using fuzzy matching.

        Args:
            title: Movie title to search for

        Returns:
            Movie ID if found, None otherwise
        """
        movies = self.radarr_api.get_movie()

        # Handle empty response
        if not movies:
            raise ValueError("no movies found in Radarr library")

        best_id = None
        best_score = -1

        for movie in movies:
            # Check original title, current title, and alternate titles
            scores = [
                fuzz.ratio(title, movie.get("originalTitle")),
                fuzz.ratio(title, movie.get("title")),
            ]

            # Add scores for alternate titles
            alt_scores = [
                fuzz.ratio(title, t.get("title")) for t in movie.get("alternateTitles")
            ]

            # Find the best score among all title variants
            score = max([*scores, *alt_scores])

            if score > best_score and score >= FUZZ_THRESHOLD:
                best_score = score
                best_id = movie.get("id")

        if best_id is None:
            raise ValueError(f"movie '{title}' not found in Radarr")
        else:
            self.logger.debug(
                f"Best Radarr match for '{title}': id={best_id}, score={best_score}"
            )

        return best_id
