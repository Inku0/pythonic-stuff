import utils
from sys import argv


env_file_path = ".env"
path = argv[1] if len(argv) > 1 else "Wallander"

with open(env_file_path, "r") as env_file:
    creds = dict(line.split("=", 1) for line in env_file.read().splitlines())

if __name__ == "__main__":
    starr_updater = utils.StarrUpdater(
        host="http://192.168.1.33",
        port=8989,
        api_key=creds["SONARR_API_KEY"],
        service="sonarr"
    )

    # Example: Update media path
    #starr_updater.update_path(media_id=1, new_location="/new/media/path")
    #utils.save_structure("/data/media/tv/Wallander.COMPLETE.SWEDiSH.720p.BluRay.x264-NORDiSC", "struc.json")
    qbit = utils.ArchifskaQBitClient("http://192.168.1.33","5080", creds["QBIT_USERNAME"], creds["QBIT_PASSWORD"])
    qbit.connect()
    qbit.list_torrents("movies")
    qbit.close()