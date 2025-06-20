import utils


with open(".env", "r") as env_file:
    creds = dict(line.split("=", 1) for line in env_file.read().splitlines())

if __name__ == "__main__":
    def all_in_one():
        qbit = utils.ArchifskaQBitClient(creds["QBIT_HOST"], creds["QBIT_PORT"], creds["QBIT_USERNAME"], creds["QBIT_PASSWORD"])
        qbit.connect()
        candidates = qbit.get_candidates()

        if len(candidates) == 0:
            raise ValueError("No candidates found.")
        elif len(candidates) > 1:
            torrent_category = candidates[0].category if candidates[0].category == candidates[1].category else None
            id_and_location_tuple = qbit.extract_id_and_path(candidates[0].name, torrent_category) if (
                qbit.extract_id_and_path(candidates[0].name, torrent_category)[0] ==
                qbit.extract_id_and_path(candidates[1].name, torrent_category)[0]
            ) else None
        else:
            torrent_category = candidates[0].category
            id_and_location_tuple = qbit.extract_id_and_path(candidates[0].name, torrent_category)

        original_location = None
        torrent_hashes = []

        for candidate in candidates:
            torrent_hash = candidate.infohash_v1

            torrent_hashes.append(torrent_hash)

            if original_location is None:
                original_location = id_and_location_tuple[1]
            elif original_location != id_and_location_tuple[1]:
                raise ValueError(f"All candidates must have the same original location, original_location is {original_location} but candidate {id_and_location_tuple[0]} has {id_and_location_tuple[1]}")

        qbit.save_structure(original_location=original_location, save_file="struc.json", torrent_hashes=torrent_hashes)

        # this stuff below is fragile, new_location shouldn't be hardcoded
        qbit.move_torrent(torrent_hashes=torrent_hashes, new_location=f"/megafarm/torrents/{torrent_category}")
        general_original_location = f"/data/media/{torrent_category}"
        qbit.recreate_structure(original_location=general_original_location, new_location=f"/megafarm/media/{torrent_category}", save_file="struc.json", torrent_hashes=torrent_hashes)
        qbit.let_starr_know(category=torrent_category, media_id=id_and_location_tuple[0], new_location=f"/megafarm/media/{torrent_category}")
        qbit.close()
    all_in_one()
