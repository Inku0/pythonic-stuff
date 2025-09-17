import argparse

from qbittorrentapi import TorrentDictionary

import utils.archiskaClient as archifska

# Base locations (adjust as needed)
BASE_TORRENTS = "/megafarm/torrents"
BASE_SOURCE = "/data/media"
BASE_DEST = "/megafarm/media"


def _torrent_hash(t: TorrentDictionary) -> str:
    return getattr(t, "infohash_v1", getattr(t, "hash"))


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
    qbit = archifska.ArchifskaQBitClient()
    qbit.connect()

    try:
        candidates = qbit.get_candidates()
        if len(candidates) == 0:
            raise ValueError("No candidates found.")

        # Ensure all candidates share the same category
        categories = {t.category for t in candidates}
        if len(categories) != 1:
            raise ValueError(
                f"All candidates must share the same category: {categories}"
            )
        torrent_category = categories.pop()

        # Resolve media id and library path from the first candidate, then validate all
        media_id, media_path = qbit.extract_id_and_path(
            candidates[0].name, category=torrent_category
        )

        for t in candidates[1:]:
            check_id, check_path = qbit.extract_id_and_path(
                t.name, category=torrent_category
            )
            if check_id != media_id or check_path != media_path:
                raise ValueError(
                    "All candidates must resolve to the same media. "
                    f"Expected ({media_id}, {media_path}), got ({check_id}, {check_path}) for {t.name}"
                )

        torrent_hashes = [_torrent_hash(t) for t in candidates]

        general_original_location = f"{BASE_SOURCE}/{torrent_category}"
        destination_root = f"{BASE_DEST}/{torrent_category}"
        torrents_target = f"{BASE_TORRENTS}/{torrent_category}"

        # Snapshot the exact media folder structure
        qbit.save_structure(
            original_location=media_path,
            save_file=save_file,
            torrent_hashes=torrent_hashes,
        )

        if dry_run:
            qbit.logger.info(
                "----- DRY RUN: Planning actions (no changes will be made) -----"
            )
            qbit.logger.info(f"Candidates: {[t.name for t in candidates]}")
            qbit.logger.info(f"Category: {torrent_category}")
            qbit.logger.info(f"Media resolved: id={media_id}, path={media_path}")
            qbit.logger.info(f"Torrent hashes: {torrent_hashes}")
            qbit.logger.info(f"Saved structure from: {media_path} -> {save_file}")
            qbit.logger.info(f"Would move torrents to: {torrents_target}")
            qbit.logger.info(
                f"Would restore structure: {general_original_location} -> {destination_root} using {save_file}"
            )
            qbit.logger.info(
                f"Would notify *arr to update path: media_id={media_id} -> {destination_root}"
            )
            qbit.logger.info("----- DRY RUN COMPLETE -----")
            return

        # Move torrents to the new torrents location for the category
        qbit.move_torrent(torrent_hashes=torrent_hashes, new_location=torrents_target)

        # Restore (link/copy) structure from the general category root into destination root
        qbit.restore_structure(
            original_location=general_original_location,
            new_location=destination_root,
            save_file=save_file,
            torrent_hashes=torrent_hashes,
        )

        # Update the path in the respective *arr service
        qbit.let_starr_know(
            category=torrent_category, media_id=media_id, new_location=destination_root
        )
    finally:
        qbit.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archifska main orchestrator")
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Plan and log actions without making changes",
    )
    parser.add_argument(
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
