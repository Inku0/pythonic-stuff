from qbittorrentapi import Client, LoginFailed, exceptions
from logging import basicConfig, getLogger, ERROR, INFO
from sys import argv
from pyarr import SonarrAPI
from pyarr import RadarrAPI
from os import path, link, mkdir, walk
import os
import shutil
import json


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
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        # create a qbittorrentapi.Client instance
        self.client = Client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
        )
    def connect(self):
        try:
            self.client.auth_log_in()
            logger.info("Connected to qBittorrent Web API")
        except LoginFailed as login_exception:
            logger.error(f"Login failed: {login_exception}")
            return False
        return True
    def close(self):
        logger.info("closing connection to qBittorrent Web API")
        self.client.auth_log_out()

    def get_hash(self, file_name: str):
        # get the hash of a torrent (by name)
        torrents = self.client.torrents_info()
        for torrent in torrents:
            if file_name in torrent.name:
                return torrent.hash
        logger.error(f"torrent {file_name} not found")
        return None

    def save_structure(self, original_location: str, save_file: str, torrent_hash=None):
        structure = {}
        original_location = os.path.abspath(original_location)
        for root, dirs, files in os.walk(original_location):
            basename = os.path.basename(root)
            structure[root] = {"basename": basename, "dirs": dirs, "files": {}}
            for f in files:
                full_path = os.path.join(root, f)
                try:
                    inode = os.stat(full_path).st_ino
                    try:
                        qbit_path = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]["content_path"]
                        for qbit_root, qbit_dirs, qbit_files in os.walk(qbit_path):
                            for qbit_file in qbit_files:
                                if os.stat(os.path.join(qbit_root, qbit_file)).st_ino == inode:
                                    qbit_inode = os.stat(os.path.join(qbit_root, qbit_file)).st_ino
                                    respective_qbit_file = os.path.join(qbit_root, qbit_file)
                    except FileNotFoundError:
                        logger.error(f"qbit_file not found, probably a symlink")
                        respective_qbit_file = ""
                except FileNotFoundError:
                    logger.error(f"File not found: {full_path}, probably a symlink")
                    inode = "missing/symlink"
                structure[root]["files"][f] = {
                    "path": full_path,
                    "inode": inode,
                    "qbit_file": respective_qbit_file,
                }

        with open(save_file, "w") as outf:
            json.dump(structure, outf, indent=4)
        print(f"Saved to `{save_file}`")

    def recreate_structure(new_location, original_location: str, save_file: str):
        if not os.path.exists(save_file):
            raise FileNotFoundError(f"`{save_file}` not found")

        with open(save_file, "r") as inf:
            stored_structure = json.load(inf)

        inode_map = {}
        for root, content in stored_structure.items():
            actual_path = os.path.relpath(root, original_location)
            target_root = os.path.join(new_location, actual_path)
            os.makedirs(target_root, exist_ok=True)
            for file_name, info in content["files"].items():
                entire_path = info["path"]
                inode = info["inode"]
                target_path = os.path.join(target_root, file_name)
                if inode in inode_map:
                    os.link(inode_map[inode], target_path)
                else:
                    shutil.copy2(orig_path, target_path)
                    inode_map[inode] = target_path

    def list_torrents(self, category: str):
        # list all torrents
        torrents = self.client.torrents_info("all", category)
        for torrent in torrents:
            logger.info(f"Torrent: {torrent.name}, Age: {torrent.completion_on}, content_path: {torrent.content_path}, Hash: {torrent.hash}, State: {torrent.state}")
        return torrents

    def move_torrent(self, torrent_hash: str, new_location: str, link_path: str ):
        # move a torrent (by hash) to a new location
        try:
            self.client.torrents_set_location(torrent_hash, new_location)
            wait_lock = True
            while wait_lock:
                torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                if torrent.state == "moving":
                    logger.debug(f"still moving {torrent_hash} aka {torrent.name} to {new_location}")
                else:
                    logger.info(f"torrent {torrent_hash} aka {torrent.name} is moved")
                    wait_lock = False
            logger.info(f"Moved torrent {torrent_hash} to {new_location}, running recheck")

            wait_lock = True
            self.client.torrents_recheck(torrent_hash)
            while wait_lock:
                torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                if torrent.state == "checkingDL" or torrent.state == "checkingUP":
                    logger.debug(f"still checking {torrent_hash} aka {torrent.name}")
                else:
                    logger.info(f"torrent {torrent_hash} aka {torrent.name} is checked")
                    wait_lock = False

            logger.info(f"linking {torrent_hash} to media")
            try:
                
                # create a hard link to the torrent in the new location
                torrent = self.client.torrents_info(None, None, None, None, None, None, torrent_hash)[0]
                if not path.exists(link_path):
                    mkdir(link_path)
                

                logger.info(f"linked {torrent_hash} to {new_location}")
            except:
                pass
        except exceptions.APIError as move_exception:
            logger.error(f"Failed to move torrent {torrent_hash}: {move_exception}")
class StarrUpdater:
    """
    a class to interact with sonarr, radarr, and others
    """
    def __init__(self, host: str, port: int, api_key: str, service: str):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.service = service.lower()
        self.host_url = f"{self.host}:{self.port}"
    def find_id_by_path(self, path: str):
        # find the id of the media (by path)
        match self.service:
            case "sonarr":
                sonarr = SonarrAPI(
                    self.host_url, self.api_key,
                )
                series = sonarr.get_series()
                for series in series:
                    if path in series["path"]:
                        return series["id"]
                logger.error(f"media {path} not found in sonarr")
                return None
            case "radarr":
                radarr = RadarrAPI(
                    self.host_url, self.api_key,
                )
                movies = radarr.get_movie()
                for movie in movies:
                    if path in movie["path"]:
                        return movie["id"]
                logger.error(f"media {path} not found in radarr")
                return None
            case _:
                logger.error(f"unknown service: {self.service}")
                return None
    def get_path(self, media_id: int):
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
                    logger.info(f"archifsking {media_id}")
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
