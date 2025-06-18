from time import sleep
from qbittorrentapi import Client, LoginFailed, exceptions, TorrentInfoList, TorrentDictionary
from logging import basicConfig, getLogger, ERROR, INFO
from sys import argv
from pyarr import SonarrAPI
from pyarr import RadarrAPI
from os import path, link, walk, makedirs, stat, scandir
from shutil import copy2
from json import dump,load
from PTN import parse
from time import time
from rapidfuzz import fuzz
from fnmatch import fnmatch


# set up logging
logging_level = INFO
if len(argv) > 1:
    input_level = argv[1].upper()
    logging_level = INFO if input_level == "INFO" else ERROR
basicConfig(level=logging_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = getLogger()

class ArchifskaQBitClient:
    """
    a class to interact with the qBittorrent Web API, given the host, port, and auth details
    """
    def __init__(self, host: str, port: str, username: str, password: str):
        with open(".env", "r") as env_file:
            self.creds = dict(line.split("=", 1) for line in env_file.read().splitlines())
        self.host = self.creds["QBIT_HOST"] if host is None else host
        self.port = self.creds["QBIT_PORT"] if port is None else port
        self.username = self.creds["QBIT_USERNAME"] if username is None else username
        self.password = self.creds["QBIT_PASSWORD"] if password is None else password

        # create a qbittorrentapi.Client instance
        self.client = Client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={'timeout': (360, 360)},
        )

    def connect(self) -> bool:
        # connect to the web api
        try:
            self.client.auth_log_in()
            logger.info("Connected to the qBittorrent Web API")
        except LoginFailed as login_exception:
            logger.error(f"Login failed: {login_exception}")
            return False
        return True

    def close(self):
        # close the connection to the web api
        logger.info("closing connection to the qBittorrent Web API")
        self.client.auth_log_out()

    def get_hash(self, file_name: str) -> str | None:
        # get the hash of a torrent (by name)
        torrents = self.client.torrents_info()
        for torrent in torrents:
            if file_name in torrent.name:
                return torrent.hash
        logger.error(f"torrent {file_name} not found")
        return None

    def multi_torrent_consumer(self, torrent_hashes: list[str]) -> tuple[list[TorrentDictionary], list[str]]:
        torrents = []
        qbit_paths = []

        if torrent_hashes is not None:
            # try to get the torrent path
            try:
                for torrent_hash in torrent_hashes:
                    if not self.client.torrents_info(None, None, None, None, None, None, torrent_hash):
                        raise ValueError(f"torrent {torrent_hash} not found")

                    torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                    qbit_path = torrent["content_path"]

                    torrents.append(torrent)
                    qbit_paths.append(qbit_path)

                    is_single_episode = True if torrent["category"] == "tv" and path.isfile(
                        torrent["content_path"]) else False
            except Exception as e:
                raise ValueError(f"failed to get torrent info for {torrent_hashes}: {e}")

        logger.info(f"qbit_paths are {qbit_paths}, torrents are {torrents}")
        return (torrents, qbit_paths)

    def qbit_path_inoder(self, qbit_path: str) -> dict:
        if path.isfile(qbit_path):
            return {qbit_path: stat(qbit_path).st_ino}

        with scandir(qbit_path) as entries:
            qbit_structure = {}
            for entry in entries:
                if entry.is_file():
                    qbit_structure[entry.path] = entry.inode()
        return qbit_structure

    def rar_lock_check(self, files: list) -> bool:
        logger.info(f"rarlock check for {files}")
        return True if any(file.endswith(".rar") for file in files) and len([file for file in files if fnmatch(file, "*.r[0-9][0-9]")]) > 3 else False

    def save_structure(self, original_location: str, save_file: str, torrent_hashes: list[str] = None):
        # save the structure of a directory to a json file and check every file for a respective qbittorrent file
        structure = {}
        qbit_structure = {}
        original_location = path.abspath(original_location)
        is_single_episode = False

        torrents, qbit_paths = self.multi_torrent_consumer(torrent_hashes)

        all_files = []

        for qbit_path in qbit_paths:
            if not path.exists(qbit_path):
                raise FileNotFoundError(f"qbit_path `{qbit_path}` does not exist")

            sub_files = [
                path.join(root, f)
                for root, dirs, files in walk(qbit_path)
                for f in files
            ]

            all_files.extend(sub_files)

            qbit_structure.update(self.qbit_path_inoder(qbit_path))

        rar_lock = self.rar_lock_check(all_files)
        logger.info(f"rar_lock is set to {rar_lock} !")

        logger.info(f"qbit_structure is {qbit_structure}")

        for root, dirs, files in walk(original_location):
            basename = path.basename(root)
            structure[root] = {"basename": basename, "dirs": dirs, "files": {}}
            # every directory gets its own "entry"

            for f in files:
                respective_qbit_file = None
                full_path = path.join(root, f)
                try:
                    file_info = stat(full_path)
                    inode = file_info.st_ino

                    if rar_lock == True and f.endswith((".mkv", ".mk3d", ".mp4", ".avi", ".m4v", ".mov", ".qt", ".wmv", ".asf",
                                                ".flv", ".webm", ".m4a", ".mp3", ".aac", ".ogg", ".opus", ".m2ts",
                                                ".mts", ".m2v", ".m4v", ".3gp")):
                        logger.info(f"rarlock is engaged! {f} in {root} is not part of the torrent")
                        respective_qbit_file = None
                        structure[root]["files"][f] = {
                            "path": full_path,
                            "inode": inode,
                            "qbit_file": respective_qbit_file,
                        }
                        continue

                    if inode in qbit_structure.values():
                        logger.debug(f"found inode {inode} in qbit_structure")
                        # if the inode is in the qbit_structure, then we can find the respective file
                        respective_qbit_file = next((key for key, value in qbit_structure.items() if value == inode), None)
                        logger.debug(f"respective_qbit_file is {respective_qbit_file}")

                except FileNotFoundError:
                    logger.error(f"file not found: {full_path}, probably a symlink")
                    inode = "missing/symlink"

                structure[root]["files"][f] = {
                    "path": full_path,
                    "inode": inode,
                    "qbit_file": respective_qbit_file,
                }

        with open(save_file, "w", encoding="utf-8") as outf:
            logger.info(f"saving {structure}")
            dump(structure, outf, indent=4)
        logger.info(f"saved to `{save_file}`")

    def recreate_structure(self, original_location: str, new_location: str, save_file: str, torrent_hashes: list[str] = None):
        if not path.exists(save_file):
            raise FileNotFoundError(f"`{save_file}` not found")

        with open(save_file, "r") as inf:
            stored_structure = load(inf)

        torrents, qbit_paths = self.multi_torrent_consumer(torrent_hashes)

        qbit_structure = {}

        for qbit_path in qbit_paths:
            qbit_structure.update(self.qbit_path_inoder(qbit_path))

        weirdoes = []
        for root, content in stored_structure.items():
            actual_path = path.relpath(root, original_location)
            target_root = path.join(new_location, actual_path)
            # for example: /new/media/movies + show_name/season

            makedirs(target_root, exist_ok=True)
            for file_name, info in content["files"].items():
                entire_path = info["path"]
                qbit_file = info["qbit_file"]
                inode = info["inode"]

                if qbit_file is None or qbit_file == "null":
                    logger.info(f"Copying {entire_path} to {target_root}/{file_name}")
                    copy2(entire_path, path.join(target_root, file_name))
                    continue

                og_qbit_basenames = [path.basename(qbit_file) for qbit_file in qbit_structure.keys()]

                logger.info(f"checking {path.basename(qbit_file)} with inode {inode} in {og_qbit_basenames}")

                if path.basename(qbit_file) in og_qbit_basenames:
                    logger.debug(f"found file {qbit_file} in qbit_structure")
                    # if the inode is in the qbit_structure, then we can find the respective file
                    respective_qbit_file = next((key for key, value in qbit_structure.items() if path.basename(key) == path.basename(qbit_file)), None)
                    logger.debug(f"respective_qbit_file is {respective_qbit_file}")
                    try:
                        logger.info(f"Linking {respective_qbit_file} to {target_root}/{file_name}")
                        link(respective_qbit_file, path.join(target_root, file_name))
                    except Exception as e:
                        logger.error(f"failed to link {respective_qbit_file} to {target_root}/{file_name} because: {e}, copying.")
                        copy2(respective_qbit_file, path.join(target_root, file_name))
                        weirdoes.append((file_name, entire_path, target_root, respective_qbit_file))
                else:
                    weirdoes.append((file_name, entire_path, target_root, inode))

        with open("RECHECK_THESE", "a") as recheck_file:
            recheck_file.write(str(weirdoes)) if weirdoes else None

    def list_torrents(self, category: str = None) -> TorrentInfoList:
        # list all torrents
        torrents = self.client.torrents_info("all", category, "completion_on")
        for torrent in torrents:
            logger.info(f"Torrent: {torrent.name}, Age: {torrent.completion_on}, content_path: {torrent.content_path}, Hash: {torrent.hash}, State: {torrent.state}")
        return torrents

    def check_for_other_seasons(self, torrent_list: list) -> list[TorrentDictionary]:
        # check if there are other seasons of the same show in the torrent list

        if torrent_list[0].category != "tv":
            logger.info("not a tv show, skipping season check")
            return torrent_list[:1]

        seasons = []
        for torrent in torrent_list:
            logger.debug(f"checking {torrent.name} against {torrent_list[0].name}")
            if fuzz.ratio(torrent_list[0].name, torrent.name) > 85:
                seasons.append(torrent)
        logger.info(f"found {len(seasons)} seasons for {torrent_list[0].name}: {seasons}")

        id = self.extract_id_and_path(torrent_list[0].name, category="tv")[0]

        sonarr_seasons = StarrUpdater(host=self.creds["SONARR_HOST"], port=self.creds["SONARR_PORT"],
                                    api_key=self.creds["SONARR_API_KEY"], service="sonarr").get_seasons(id)

        logger.info(f"sonarr seasons for ID {id} are: {sonarr_seasons}")

        monitored_seasons = [season for season in sonarr_seasons if season["monitored"] == True]

        if len(monitored_seasons) == len(seasons):
            logger.info(f"amount of seasons in sonarr ({len(monitored_seasons)}) matches amount of seasons in torrent list ({len(seasons)})")
            return seasons
        else:
            logger.error(f"amount of seasons in sonarr ({len(monitored_seasons)}) does not match amount of seasons in torrent list ({len(seasons)})")
            raise ValueError(f"amount of seasons in sonarr ({len(monitored_seasons)}) does not match amount of seasons in torrent list ({len(seasons)})")

    def get_candidates(self, category: str = None) -> list[TorrentDictionary]:
        # TODO: handle single-file tv torrents
        if category is None: # shouldn't prolly hardcode the following, gotta acommodate other services too?
            movies = [
                torrent for torrent in self.client.torrents_info("all", "movies", "completion_on")
                if "megafarm" not in torrent.content_path and (float(time())-float(torrent.completion_on))/(60*60*24) > 90
            ]
            tv = [
                torrent for torrent in self.client.torrents_info("all", "tv", "completion_on")
                if "megafarm" not in torrent.content_path and (float(time())-float(torrent.completion_on))/(60*60*24) > 90
            ]
            torrents = movies + tv

        else:
            torrents = [
                torrent for torrent in self.client.torrents_info("all", category, "completion_on")
                if "megafarm" not in torrent.content_path and (float(time())-float(torrent.completion_on))/(60*60*24) > 90
            ]

        torrents.sort(key=lambda x: x.completion_on)

        logger.info(f"found {len(torrents)} candidates in total, prime candidate is {torrents[0].name} with path {torrents[0].content_path} and age {torrents[0].completion_on}")
        logger.debug(f"all candidates: {[torrent.name for torrent in torrents]}")

        torrents = self.check_for_other_seasons(torrents) if torrents[0].category == "tv" else None
        logger.info(f"after season check, {len(torrents)} candidates left: {[torrent.name for torrent in torrents]}")

        return torrents

    def extract_id_and_path(self, filename: str, category: str = None) -> tuple[int, str]:
        movie_title = parse(filename)["title"]
        if category is None:
            radarr_runner = StarrUpdater(host=self.creds["RADARR_HOST"], port=self.creds["RADARR_PORT"],
                                         api_key=self.creds["RADARR_API_KEY"], service="radarr")
            sonarr_runner = StarrUpdater(host=self.creds["SONARR_HOST"], port=self.creds["SONARR_PORT"],
                                         api_key=self.creds["SONARR_API_KEY"], service="sonarr")
            radarr_id = radarr_runner.find_id_by_title(movie_title, ignore_errors=True)
            sonarr_id = sonarr_runner.find_id_by_title(movie_title, ignore_errors=True)
            if radarr_id and sonarr_id:
                raise ValueError(f"both Radarr and Sonarr found the same title: {movie_title}")
            else:
                if radarr_id:
                    return radarr_id, radarr_runner.get_path(radarr_id)
                else:
                    return sonarr_id, sonarr_runner.get_path(sonarr_id)
        else:
            if category == "movies":
                service = "radarr"
            elif category == "tv":
                service = "sonarr"
            else:
                raise ValueError(f"unknown category: {category}")
            runner = StarrUpdater(host=self.creds[f"{service.upper()}_HOST"],
                                  port=self.creds[f"{service.upper()}_PORT"],
                                  api_key=self.creds[f"{service.upper()}_API_KEY"], service=service)
            media_id = runner.find_id_by_title(movie_title)
            if media_id is None:
                raise ValueError(f"media not found in {service}: {movie_title}")
            else:
                return media_id, runner.get_path(media_id)

    def move_torrent(self, torrent_hashes: list[str], new_location: str):
        # move a torrent (by hash) to a new location, could do multiple at a time, but not sure if it would be wise
        for torrent_hash in torrent_hashes:
            try:
                self.client.torrents_set_location(new_location, torrent_hash)

                wait_lock = True

                while wait_lock:
                    sleep(15)
                    torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                    if torrent.state == "moving":
                        logger.info(f"still moving {torrent_hash} aka {torrent.name} to {new_location}")
                    else:
                        logger.info(f"torrent {torrent_hash} aka {torrent.name} is moved")
                        wait_lock = False
                logger.info(f"moved torrent {torrent_hash} to {new_location}, running recheck")

                wait_lock = True

                self.client.torrents_recheck(torrent_hash)
                while wait_lock:
                    sleep(15)
                    torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                    if torrent.state == "checkingDL" or torrent.state == "checkingUP":
                        logger.info(f"still checking {torrent_hash} aka {torrent.name}")
                    else:
                        logger.info(f"torrent {torrent_hash} aka {torrent.name} is checked")
                        wait_lock = False
            except exceptions.APIError as move_exception:
                logger.error(f"failed to move torrent {torrent_hash} because: {move_exception}")

    def let_starr_know(self, category: str, media_id: int, new_location: str):
        # let starr know about the new location
        try:
            if category == "movies":
                service = "radarr"
            elif category == "tv":
                service = "sonarr"
            else:
                raise ValueError(f"unknown category: {category}")
            runner = StarrUpdater(host=self.creds[f"{service.upper()}_HOST"], port=self.creds[f"{service.upper()}_PORT"], api_key=self.creds[f"{service.upper()}_API_KEY"], service=service)
            runner.update_path(media_id, new_location)
        except Exception as e:
            logger.error(f"failed to let {service} know about the new location because: {e}")

class StarrUpdater:
    """
    a class to interact with sonarr, radarr, and others
    """
    def __init__(self, host: str, port: str, api_key: str, service: str):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.service = service.lower()
        self.host_url = f"{self.host}:{self.port}"

    def get_seasons(self, media_id: int) -> list[int] | None:
        # get the seasons of the media (by id)
        sonarr = SonarrAPI(
            self.host_url, self.api_key,
        )
        series = sonarr.get_series(media_id)
        return series["seasons"]

    def find_id_by_title(self, title: str, ignore_errors: bool = False) -> int | None:
        # find the id of the media (by path)
        match self.service:
            case "sonarr":
                sonarr = SonarrAPI(
                    self.host_url, self.api_key,
                )
                series = sonarr.get_series()
                for show in series:
                    if fuzz.ratio(title, show["title"]) > 65:
                        logger.info(f"found {title} in sonarr: {show['title']}")
                        return show["id"]
                    else:
                        for alt_title in show["alternateTitles"]:
                            if fuzz.ratio(title, alt_title["title"]) > 65:
                                logger.info(f"found {title} in sonarr: {show['title']}")
                                return show["id"]
                if not ignore_errors:
                    logger.error(f"media {title} not found in sonarr")
                return None
            case "radarr":
                radarr = RadarrAPI(
                    self.host_url, self.api_key,
                )
                movies = radarr.get_movie()
                for movie in movies:
                    if fuzz.ratio(title, movie["originalTitle"]) > 65 or fuzz.ratio(title, movie["title"]) > 65:
                        logger.info(f"found {title} in radarr: {movie['originalTitle']}")
                        return movie["id"]
                    else:
                        for alt_title in movie["alternateTitles"]:
                            if fuzz.ratio(title, alt_title["title"]) > 65:
                                logger.info(f"found {title} in radarr: {movie['originalTitle']}")
                                return movie["id"]
                if not ignore_errors:
                    logger.error(f"media {title} not found in radarr")
                return None
            case _:
                logger.error(f"unknown service: {self.service}")
                return None
    def get_path(self, media_id: int) -> str | None:
        # get the path of the media (by id)
        match self.service:
            case "sonarr":
                sonarr = SonarrAPI(
                    self.host_url, self.api_key,
                )
                media = sonarr.get_series(media_id)
                return media["path"]
            case "radarr":
                radarr = RadarrAPI(
                    self.host_url, self.api_key,
                )
                media = radarr.get_movie(media_id)
                return media["path"]
            case _:
                logger.error(f"unknown service: {self.service}")
                return None
    def update_path(self, media_id: int, new_location: str):

        # check that the media isn't already archifskad (HARDCODED ATM)
        def is_archifskad(media_path: str):
            return True if "megafarm" in media_path else False

        match self.service:
            case "sonarr":
                sonarr = SonarrAPI(
                    self.host_url, self.api_key,
                )
                media = sonarr.get_series(media_id)
                if is_archifskad(media["path"]):
                    logger.error(f"media {media_id} is already archifskad")
                    return
                else:
                    logger.info(f"archifsking {media_id}, new path is {new_location + "/" + path.basename(media["path"])}")
                    media["path"] = new_location + f"/{path.basename(media["path"])}"
                    sonarr.upd_series(media)

            case "radarr":
                radarr = RadarrAPI(
                    self.host_url, self.api_key,
                )
                media = radarr.get_movie(media_id)
                if is_archifskad(media["path"]):
                    logger.error(f"media {media_id} is already archifskad")
                    return
                else:
                    logger.info(f"archifsking {media_id} ")
                    media["path"] = new_location + f"/{path.basename(media["path"])}"
                    radarr.upd_movie(media)
            case _:
                logger.error(f"unknown service: {self.service}")
                return
