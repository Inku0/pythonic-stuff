from __future__ import annotations

from logging import Logger
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pyarr import RadarrAPI, SonarrAPI
from rapidfuzz import fuzz

from utils.logging_setup import logging_setup

# Threshold for fuzzy matching media titles
FUZZ_THRESHOLD = 65

# Type definitions
ServiceType = Literal["sonarr", "radarr"]
MediaID = int


def _build_base_url(host: str, port: str | None) -> str:
    """
    Build a complete base URL from host and optional port parameters.

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

    def __init__(
        self,
        host: str,
        port: str | None,
        api_key: str,
        service: ServiceType,
    ) -> None:
        """
        Initialize the StarrUpdater with connection details.

        Args:
            host: Hostname or IP address of the Starr service
            port: Port number for the service
            api_key: API key for authentication
            service: Service type ("sonarr" or "radarr")

        Raises:
            ValueError: If service is not "sonarr" or "radarr"
        """
        self.logger: Logger = logging_setup()
        self.host: str = host
        self.port: str = port or ""
        self.api_key: str = api_key
        self.service: str = service.lower().strip()
        self.host_url: str = _build_base_url(self.host, self.port)

        if self.service not in {"sonarr", "radarr"}:
            raise NotImplementedError(f"Unsupported service: {self.service}")

        # Initialize API client (lazy)
        self._api_client: SonarrAPI | RadarrAPI | None = None

    @property
    def api(self) -> SonarrAPI | RadarrAPI:
        """Get (or initialize) the appropriate API client."""
        if self._api_client is None:
            if self.service == "sonarr":
                self._api_client = SonarrAPI(self.host_url, self.api_key)
            else:
                self._api_client = RadarrAPI(self.host_url, self.api_key)
        return self._api_client

    # --------
    # Sonarr
    # --------
    def get_seasons(self, media_id: MediaID) -> list[dict[str, Any]]:
        """
        Get seasons for a series from Sonarr.

        Args:
            media_id: Sonarr series ID

        Returns:
            List of season information dictionaries

        Raises:
            ValueError: If not using Sonarr
            ConnectionError: If API connection fails
        """
        if self.service != "sonarr":
            raise ValueError("get_seasons is only available for Sonarr")

        try:
            sonarr: SonarrAPI = self.api
            series = sonarr.get_series(media_id)
            seasons = series.get("seasons") or []

            if not isinstance(seasons, list):
                self.logger.warning(f"Invalid seasons data for media ID {media_id}")
                return []

            return seasons

        except Exception as e:
            self.logger.error(f"Failed to get seasons for media ID {media_id}: {e}")
            raise ConnectionError(f"Sonarr API error: {e}") from e

    # ---------------
    # Common helpers
    # ---------------
    def find_id_by_title(
        self, title: str, ignore_errors: bool = False
    ) -> MediaID | None:
        """
        Find media ID by title using fuzzy matching.

        Args:
            title: Media title to search for
            ignore_errors: If True, suppress error logging on failures

        Returns:
            Media ID if found, None otherwise
        """
        match self.service:
            case "sonarr":
                return self._find_sonarr_id_by_title(title, ignore_errors)
            case "radarr":
                return self._find_radarr_id_by_title(title, ignore_errors)
            case _:
                if not ignore_errors:
                    self.logger.error(f"Unknown service: {self.service}")
                return None

    def get_path(self, media_id: MediaID) -> str | None:
        """
        Get the filesystem path for media by ID.

        Args:
            media_id: ID of the media item

        Returns:
            Filesystem path as string, or None if not found
        """
        try:
            media = self._get_media(self.api, media_id)
            return media.get("path")
        except Exception as e:
            self.logger.error(f"Failed to get path for media ID {media_id}: {e}")
            return None

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

    def update_path(self, media_id: MediaID, new_location: str) -> bool:
        """
        Update the path for a media item.

        Args:
            media_id: ID of the media item
            new_location: New root location for the media

        Returns:
            True if update was successful, False otherwise
        """
        try:
            runner = self.api
            media = self._get_media(runner, media_id)

            current_path: str = media.get("path")
            if not current_path:
                self.logger.error(f"Media {media_id} has no path set")
                return False

            if self.is_archifskad(current_path):
                self.logger.warning(
                    f"Media {media_id} appears to be already archifskad: {current_path}"
                )
                return False

            # Create new path by joining the new location with current basename
            new_full_path = str(Path(new_location) / Path(current_path).name)
            self.logger.info(f"Updating path for media {media_id} to {new_full_path}")
            media["path"] = new_full_path

            # Update the media record
            if self.service == "sonarr":
                runner.upd_series(media)
            else:
                runner.upd_movie(media)

            return True

        except Exception as e:
            self.logger.error(f"Failed to update {self.service} media {media_id}: {e}")
            return False

    # ---------------
    # Private helpers
    # ---------------
    def _get_media(
        self, runner: SonarrAPI | RadarrAPI, media_id: MediaID
    ) -> dict[str, Any]:
        """
        Get media information by ID.

        Args:
            runner: API client instance
            media_id: ID of the media item

        Returns:
            Media information dictionary

        Raises:
            Exception: If API call fails
        """
        if self.service == "sonarr":
            return runner.get_series(media_id)  # type: ignore
        else:
            return runner.get_movie(media_id)  # type: ignore

    def _find_sonarr_id_by_title(
        self, title: str, ignore_errors: bool
    ) -> MediaID | None:
        """
        Find Sonarr series ID by title using fuzzy matching.

        Args:
            title: Series title to search for
            ignore_errors: If True, suppress error logging on failures

        Returns:
            Series ID if found, None otherwise
        """
        try:
            series_list = self.api.get_series()

            # Handle empty response
            if not series_list:
                if not ignore_errors:
                    self.logger.error("No series found in Sonarr library")
                return None

            best_id = None
            best_score = -1

            for show in series_list:
                # Get primary title score
                primary_score = fuzz.ratio(title, show.get("title"))

                # Get scores for alternate titles
                alt_scores = [
                    fuzz.ratio(title, t.get("title", ""))
                    for t in show.get("alternateTitles")
                ]

                # Use the highest score among primary and alternates
                max_alt_score = max(alt_scores, default=0)
                score = max(primary_score, max_alt_score)

                if score > best_score and score >= FUZZ_THRESHOLD:
                    best_score = score
                    best_id = show.get("id")

            if best_id is None and not ignore_errors:
                self.logger.error(f"Media '{title}' not found in Sonarr")
            else:
                self.logger.debug(
                    f"Best Sonarr match for '{title}': id={best_id}, score={best_score}"
                )

            return best_id

        except Exception as e:
            if not ignore_errors:
                self.logger.error(f"Failed to query Sonarr: {e}")
            return None

    def _find_radarr_id_by_title(
        self, title: str, ignore_errors: bool
    ) -> MediaID | None:
        """
        Find Radarr movie ID by title using fuzzy matching.

        Args:
            title: Movie title to search for
            ignore_errors: If True, suppress error logging on failures

        Returns:
            Movie ID if found, None otherwise
        """
        try:
            movies = self.api.get_movie()  # type: ignore

            # Handle empty response
            if not movies:
                if not ignore_errors:
                    self.logger.error("No movies found in Radarr library")
                return None

            best_id = None
            best_score = -1

            for movie in movies:
                # Check original title, current title, and alternate titles
                scores = [
                    fuzz.ratio(title, movie.get("originalTitle", "")),
                    fuzz.ratio(title, movie.get("title", "")),
                ]

                # Add scores for alternate titles
                alt_scores = [
                    fuzz.ratio(title, t.get("title", ""))
                    for t in movie.get("alternateTitles", [])
                ]

                # Find the best score among all title variants
                score = max([*scores, *alt_scores])

                if score > best_score and score >= FUZZ_THRESHOLD:
                    best_score = score
                    best_id = movie.get("id")

            if best_id is None and not ignore_errors:
                self.logger.error(f"Media '{title}' not found in Radarr")
            else:
                self.logger.debug(
                    f"Best Radarr match for '{title}': id={best_id}, score={best_score}"
                )

            return best_id

        except Exception as e:
            if not ignore_errors:
                self.logger.error(f"Failed to query Radarr: {e}")
            return None
