(N)Archifska is a utility for finding old torrents that should be moved to another mountpoint for archival.

It does this by 
  1. filtering by age in qBittorrent
  2. if the prime candidate for archival is a tv-series, it will also locate other seasons via fuzzy matching and Sonarr
  3. copying the Radarr/Sonarr media directory structure of the candidate into a JSON format
  4. moving the torrent
  5. rechecking the torrent
  6. restoring the structure (hardlinks where possible)
  7. notifying Radarr/Sonarr about the new location

Configuration is done in a `.env` file. The file must include the following:
```.env
SONARR_API_KEY
SONARR_HOST
SONARR_PORT
RADARR_API_KEY
RADARR_HOST
RADARR_PORT
QBIT_USERNAME
QBIT_PASSWORD
QBIT_HOST
QBIT_PORT
LOGGING_LEVEL
```

TODO:
  1. remove hardcoded paths
  2. optimize
  3. improve season finding

