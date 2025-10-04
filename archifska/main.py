import argparse
from pathlib import Path
from typing import Literal

# import utils.archiskaClient as archifska
from utils.narchifska_client import NarchifskaClient

# Base locations (adjust as needed)
BASE_TORRENTS = Path("/megafarm/torrents")
BASE_SOURCE = Path("/data/media")
BASE_DEST = Path("/megafarm/media")


def all_in_one(dry_run: bool = False, save_file: str = "struc.json") -> None:
    """
    End-to-end flow:
    1) Pick candidate torrent(s)
    2) Resolve media id and original library path via *arr
    3) Save file structure snapshot (non-destructive)
    4) Move torrents to new storage
    5) Restore (link/copy) structure into final destination
    6) Notify *arr about new path

    When dry_run=True, actions are planned and logged, but not executed.
    """
    narchifska = NarchifskaClient()
    narchifska.qbit_service.connect()

    try:
        candidates = narchifska.qbit_service.get_candidates()
        if len(candidates) == 0:
            raise ValueError("No candidates found.")

        # Ensure all candidates share the same category
        categories = {t.category for t in candidates}
        if len(categories) != 1:
            raise ValueError(
                f"All candidates must share the same category: {categories}"
            )

        torrent_category: Literal["movies", "tv"] = categories.pop()

        service = None

        if torrent_category == "movies":
            service = "radarr"
        elif torrent_category == "tv":
            service = "sonarr"
        else:
            raise ValueError(f"Unsupported category: {torrent_category}")

        # resolve media id and library path from the first candidate, then validate all
        media_id = narchifska.starr_updater.find_id_by_title(
            title=candidates[0].name, service=service
        )

        media_path = narchifska.starr_updater.get_path(
            media_id=media_id, service=service
        )

        for t in candidates[1:]:
            check_id = narchifska.starr_updater.find_id_by_title(
                title=t.name, service=service
            )

            check_path = narchifska.starr_updater.get_path(
                media_id=check_id, service=service
            )

            if check_id != media_id or check_path != media_path:
                raise ValueError(
                    "All candidates must resolve to the same media. "
                    + f"Expected ({media_id}, {media_path}), got ({check_id}, {check_path}) for {t.name}"
                )

        torrent_hashes = [t.hash for t in candidates]

        general_original_location: Path = BASE_SOURCE / torrent_category
        destination_root: Path = BASE_DEST / torrent_category
        torrents_target: Path = BASE_TORRENTS / torrent_category

        # Snapshot the exact media folder structure
        narchifska.fs_service.save_structure(
            original_location=Path(media_path),
            save_file=Path(save_file),
            torrent_hashes=torrent_hashes,
        )

        if dry_run:
            narchifska.qbit_service.logger.info(
                "----- DRY RUN: Planning actions (no changes will be made) -----"
            )
            narchifska.qbit_service.logger.info(
                f"Candidates: {[t.name for t in candidates]}"
            )
            narchifska.qbit_service.logger.info(f"Category: {torrent_category}")
            narchifska.qbit_service.logger.info(
                f"Media resolved: id={media_id}, path={media_path}"
            )
            narchifska.qbit_service.logger.info(f"Torrent hashes: {torrent_hashes}")
            narchifska.qbit_service.logger.info(
                f"Saved structure from: {media_path} -> {save_file}"
            )
            narchifska.qbit_service.logger.info(
                f"Would move torrents to: {torrents_target}"
            )
            narchifska.qbit_service.logger.info(
                f"Would restore structure: {general_original_location} -> {destination_root} using {save_file}"
            )
            narchifska.qbit_service.logger.info(
                f"Would notify *arr to update path: media_id={media_id} -> {destination_root}"
            )
            narchifska.qbit_service.logger.info("----- DRY RUN COMPLETE -----")
            narchifska.starr_updater.find_other_seasons_files(media_id)
            return

        # Move torrents to the new torrents location for the category
        narchifska.qbit_service.move_torrent(
            torrent_hashes=torrent_hashes, new_location=torrents_target
        )

        # Restore (link/copy) structure from the general category root into destination root
        narchifska.fs_service.restore_structure(
            original_location=general_original_location,
            new_location=destination_root,
            save_file=Path(save_file),
            torrent_hashes=torrent_hashes,
        )

        # Update the path in the respective *arr service
        result = narchifska.starr_updater.update_path(
            service=service, media_id=media_id, new_location=destination_root
        )
        if not result:
            narchifska.starr_updater.logger.error(
                f"Failed to update path in {torrent_category} for media_id={media_id}"
            )
    finally:
        narchifska.qbit_service.disconnect()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archifska main orchestrator")
    _ = parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Plan and log actions without making changes",
    )
    _ = parser.add_argument(
        "-o",
        "--output",
        dest="save_file",
        default="struc.json",
        help="Path to save the structure snapshot (default: struc.json)",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    all_in_one(dry_run=args.dry_run, save_file=args.save_file)
