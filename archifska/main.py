import utils


with open(".env", "r") as env_file:
    creds = dict(line.split("=", 1) for line in env_file.read().splitlines())

if __name__ == "__main__":
    def all_in_one():
        qbit = utils.ArchifskaQBitClient(creds["QBIT_HOST"], creds["QBIT_PORT"], creds["QBIT_USERNAME"], creds["QBIT_PASSWORD"])
        qbit.connect()
        candidate = qbit.get_candidate("movies")[0]
        print(candidate.name)
        torrent_hash = candidate.infohash_v1
        torrent_category = candidate.category
        id_and_location_tuple = qbit.extract_id_and_path(candidate.name, torrent_category)
        original_location = id_and_location_tuple[1]
        qbit.save_structure(original_location=original_location, save_file="struc.json", torrent_hash=torrent_hash)

        # this stuff below is fragile, new_location shouldn't be hardcoded
        qbit.move_torrent(torrent_hash=torrent_hash, new_location=f"/megafarm/torrents/{torrent_category}")
        general_original_location = f"/data/media/{torrent_category}"
        qbit.recreate_structure(original_location=general_original_location, new_location=f"/megafarm/media/{torrent_category}", save_file="struc.json", torrent_hash=torrent_hash)
        qbit.let_starr_know(category=torrent_category, media_id=id_and_location_tuple[0], new_location=f"/megafarm/media/{torrent_category}")
        qbit.close()
    all_in_one()
