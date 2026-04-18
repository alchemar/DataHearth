#!/usr/bin/env python3
"""
Docker Compose Generator
Generates a combined docker-compose.yml from Gitea and Lexicon service templates,
with a dashboard container included.
"""

import os
import sys
import json
import textwrap

OUTPUT_DIR = "lexicon-deploy"

# ==============================================================================
# SERVICE DEFINITIONS
# ==============================================================================

# Services that support multiple named instances
MULTI_SERVICES = {
    "jellyfin": {
        "label": "Jellyfin (Video/Media Server)",
        "image": "jellyfin/jellyfin:latest",
        "port_base": 8100,
        "container_port": 8096,
        "icon": "🎬",
        "category": "Media",
        "description": "Video media server",
        "ram_mb": 1024,   # ~256 MB fresh, climbs to 1-2 GB with large library
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/jellyfin-{name}/config:/config",
            f"/mnt/disk0/lexicon/jellyfin-{name}/cache:/cache",
            f"/mnt/disk0/lexicon/jellyfin-{name}/media:/media",
        ],
        "environment": ["PUID=1000", "PGID=1000", "TZ=America/Chicago"],
    },
    "photoprism": {
        "label": "PhotoPrism (Photo Management)",
        "image": "photoprism/photoprism:latest",
        "port_base": 8200,
        "container_port": 2342,
        "icon": "📷",
        "category": "Media",
        "description": "AI-powered photo management",
        "ram_mb": 1536,   # ~500 MB idle, up to 1.5 GB during AI indexing
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/photoprism-{name}/storage:/photoprism/storage",
            f"/mnt/disk0/lexicon/photoprism-{name}/originals:/photoprism/originals",
        ],
        "environment_template": lambda ip, port: [
            "PHOTOPRISM_ADMIN_USER=alchemar",
            "PHOTOPRISM_ADMIN_PASSWORD=change_me",
            f"PHOTOPRISM_SITE_URL=http://{ip}:{port}",
            'PHOTOPRISM_DISABLE_TLS=true',
            "PHOTOPRISM_DATABASE_DRIVER=sqlite",
            "PHOTOPRISM_HTTP_PORT=2342",
        ],
        "security_opt": ["seccomp:unconfined", "apparmor:unconfined"],
    },
    "kavita": {
        "label": "Kavita (Manga/Comics/Books)",
        "image": "jvmilazz0/kavita:latest",
        "port_base": 8300,
        "container_port": 5000,
        "icon": "📚",
        "category": "Library",
        "description": "Digital library for manga/comics/books",
        "ram_mb": 256,   # .NET app, light; ~100-250 MB typical
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/kavita-{name}/config:/kavita/config",
            f"/mnt/disk0/lexicon/kavita-{name}/data:/data",
        ],
        "environment": ["TZ=America/Chicago"],
    },
    "navidrome": {
        "label": "Navidrome (Music Server)",
        "image": "deluan/navidrome:latest",
        "port_base": 8400,
        "container_port": 4533,
        "icon": "🎵",
        "category": "Media",
        "description": "Music server and streamer",
        "ram_mb": 200,   # Go app, very light; ~130-200 MB typical
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/navidrome-{name}/data:/data",
            f"/mnt/disk0/lexicon/navidrome-{name}/music:/music:ro",
        ],
        "environment": ["ND_SCANSCHEDULE=1h", "ND_LOGLEVEL=info", "ND_BASEURL=/"],
    },
    "manyfold": {
        "label": "Manyfold (3D Model Library)",
        "image": "ghcr.io/manyfold3d/manyfold:latest",
        "port_base": 8500,
        "container_port": 3214,
        "icon": "🖨️",
        "category": "Library",
        "description": "3D model library manager",
        "ram_mb": 512,   # app ~300 MB + postgres ~100 MB + redis ~30 MB
        "needs_db": True,
        "needs_redis": True,
        "db_port_base": 8550,
        "redis_pass_template": lambda name: f"manyfold_{name}_redis_password",
        "db_pass_template": lambda name: f"manyfold_{name}_password",
        "secret_template": lambda name: f"changeme_generate_secret_{name}",
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/manyfold-{name}/libraries:/libraries",
            f"/mnt/disk0/lexicon/manyfold-{name}/data:/config",
        ],
    },
    "webtop": {
        "label": "Webtop (Linux Desktop in Browser)",
        "image": "lscr.io/linuxserver/webtop:latest",
        "port_base": 8640,
        "container_port": 3000,
        "icon": "\U0001f5a5",
        "category": "Desktop",
        "description": "Full Linux desktop accessible via web browser",
        "ram_mb": 1024,   # full desktop env; 512 MB-2 GB depending on flavor/use
        "flavors": [
            "ubuntu-kde",
            "ubuntu-xfce",
            "ubuntu-mate",
            "ubuntu-i3",
            "alpine-xfce",
            "alpine-mate",
            "alpine-i3",
            "fedora-xfce",
            "arch-xfce",
        ],
        "volumes_template": lambda name: [
            f"/mnt/disk0/lexicon/webtop-{name}/config:/config",
        ],
    },
}

# Singleton services (0 or 1 instance, no name needed)
SINGLETON_SERVICES = {
    "gitea": {
        "label": "Gitea (Git Repository Service)",
        "icon": "🐙",
        "category": "Dev Tools",
        "description": "Self-hosted Git service",
        "ram_mb": 300,   # app ~150 MB + postgres ~100 MB
        "web_port": 8600,
        "needs_db": True,
        "db_port": 8602,
    },
    "opengrok": {
        "label": "OpenGrok (Source Code Search)",
        "icon": "🔍",
        "category": "Dev Tools",
        "description": "Source code search and cross-reference",
        "ram_mb": 768,   # Java app; ~512-768 MB typical
        "web_port": 8603,
    },
    "solr": {
        "label": "Solr + Tika (Search Platform)",
        "icon": "⚡",
        "category": "Infrastructure",
        "description": "Search platform and content extraction",
        "ram_mb": 3072,   # 2 GB heap as configured + 1 GB overhead + Tika ~512 MB
        "web_port": 8606,
    },
    "kiwix": {
        "label": "Kiwix (Offline Wikipedia)",
        "icon": "📖",
        "category": "Library",
        "description": "Offline Wikipedia and educational content",
        "ram_mb": 256,   # light C++ server; ~150-300 MB
        "web_port": 8610,
    },
    "nextcloud": {
        "label": "Nextcloud (File Sharing)",
        "icon": "☁️",
        "category": "Storage",
        "description": "File sharing and collaboration platform",
        "ram_mb": 512,   # PHP-FPM ~300 MB + postgres ~150 MB
        "web_port": 8612,
        "needs_db": True,
        "db_port": 8611,
    },
    "audiobookshelf": {
        "label": "Audiobookshelf (Audiobooks/Podcasts)",
        "icon": "🎧",
        "category": "Media",
        "description": "Audiobook and podcast server",
        "ram_mb": 350,   # Node.js; ~200-400 MB typical
        "web_port": 8620,
    },
    "tvheadend": {
        "label": "TVHeadend (Live TV/DVR)",
        "icon": "📺",
        "category": "Media",
        "description": "TV streaming and DVR server",
        "ram_mb": 256,   # ~150-300 MB
        "web_port": 8630,
    },
    "music_assistant": {
        "label": "Music Assistant",
        "icon": "🎼",
        "category": "Media",
        "description": "Multi-source music player and manager",
        "ram_mb": 256,   # Python; ~200-300 MB
        "web_port": None,  # host network
    },
    "snapserver": {
        "label": "Snapcast Server (Multi-room Audio)",
        "icon": "🔊",
        "category": "Media",
        "description": "Synchronous multi-room audio server",
        "ram_mb": 128,   # C++ server; ~64-128 MB
        "web_port": None,  # host network
    },
    "mopidy": {
        "label": "Mopidy (Music Player Daemon)",
        "icon": "🎛️",
        "category": "Media",
        "description": "Extensible music server (Subidy/MPD)",
        "ram_mb": 200,   # Python; ~150-250 MB
        "web_port": 8621,
    },
    "filebot": {
        "label": "FileBot CLI (Media Organizer)",
        "icon": "📁",
        "category": "Tools",
        "description": "Media file organizer (on-demand)",
        "ram_mb": 0,   # on-demand only, not persistent
        "web_port": None,
    },
    "romm": {
        "label": "RomM (Retro ROM Manager & Player)",
        "icon": "\U0001f579",
        "category": "Retro Gaming",
        "description": "Self-hosted ROM manager with EmulatorJS in-browser play, 400+ systems",
        "ram_mb": 512,   # app ~300 MB + MariaDB ~200 MB
        "web_port": 8710,
        "needs_db": True,
        "db_port": 8712,
        "redis_port": 8713,
    },
    "exodos": {
        "label": "eXoDOS Web Player",
        "icon": "\U0001f3ae",
        "category": "Retro Gaming",
        "description": "Browser-based DOS game library from eXoDOS collection",
        "ram_mb": 256,   # Flask/gunicorn; ~150-300 MB
        "web_port": 8700,
    },
    "headway": {
        "label": "Headway (Self-hosted Maps)",
        "icon": "\U0001f5fa",
        "category": "Utility",
        "description": "Full self-hosted maps stack: OSM tiles, geocoding, routing",
        "web_port": 8720,
        "ram_mb": 6144,  # ~6 GB runtime: Elasticsearch ~3.5 GB, Valhalla ~2 GB,
                         # tileserver ~300 MB, frontend ~50 MB
    },
}

# ==============================================================================
# COMPOSE FRAGMENT GENERATORS
# ==============================================================================

def indent(text, spaces=2):
    return textwrap.indent(text, " " * spaces)

def gen_gitea(ip, web_port=8600, ssh_port=8601, db_port=8602):
    return f"""
  # ============================================================================
  # GITEA - Git Repository Service
  # ============================================================================
  gitea-db:
    image: postgres:15-alpine
    container_name: gitea-db
    restart: unless-stopped
    networks:
      - app-network
    environment:
      POSTGRES_USER: gitea
      POSTGRES_PASSWORD: gitea_password
      POSTGRES_DB: gitea
    volumes:
      - /mnt/disk0/lexicon/gitea/postgres:/var/lib/postgresql/data
    ports:
      - "{db_port}:5432"

  gitea:
    image: gitea/gitea:latest
    container_name: gitea
    restart: unless-stopped
    networks:
      - app-network
    environment:
      USER_UID: 1000
      USER_GID: 1000
      GITEA__database__DB_TYPE: postgres
      GITEA__database__HOST: gitea-db:5432
      GITEA__database__NAME: gitea
      GITEA__database__USER: gitea
      GITEA__database__PASSWD: gitea_password
    volumes:
      - /mnt/disk0/lexicon/gitea/data:/data
      - /mnt/disk0/lexicon/gitea/custom/templates/custom:/data/gitea/custom/templates/custom
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "{web_port}:3000"
      - "{ssh_port}:22"
    depends_on:
      - gitea-db
"""

def gen_opengrok(ip, web_port=8603):
    return f"""
  # ============================================================================
  # OPENGROK - Source Code Search
  # ============================================================================
  opengrok:
    image: opengrok/docker:latest
    container_name: opengrok
    restart: unless-stopped
    networks:
      - app-network
    environment:
      OPENGROK_INDEXER_THREADS: 2
      INDEXER_OPT: -T 2
      NOMIRROR: "true"
      SYNC_PERIOD_MINUTES: 180
      AVOID_PROJECTS: "true"
    deploy:
      resources:
        limits:
          cpus: '1'
    volumes:
      - /mnt/disk0/lexicon/opengrok/src:/opengrok/src
      - /mnt/disk0/lexicon/opengrok/data:/opengrok/data
      - /mnt/disk0/lexicon/opengrok/etc:/opengrok/etc
    ports:
      - "{web_port}:8080"
"""

def gen_solr(ip, solr_port=8606, tika_port=8607, ui_port=8608, cores=None):
    cores = cores or []
    core_checks = ""
    for core in cores:
        core_checks += f"""
        if [ ! -d /var/solr/data/{core} ]; then
          precreate-core {core} /var/solr/data
        fi"""
    return f"""
  # ============================================================================
  # TIKA - Content Extraction
  # ============================================================================
  tika:
    image: apache/tika:latest
    container_name: tika
    restart: unless-stopped
    networks:
      - app-network
    deploy:
      resources:
        limits:
          cpus: '1'
    ports:
      - "{tika_port}:9998"

  # ============================================================================
  # SOLR - Search Platform
  # ============================================================================
  solr:
    image: solr:9-slim
    container_name: solr
    restart: unless-stopped
    networks:
      - app-network
    environment:
      SOLR_HEAP: 2g
      SOLR_JAVA_MEM: -Xms2g -Xmx2g
      SOLR_ULIMIT_CHECKS: "false"
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 3g
    volumes:
      - /mnt/disk0/lexicon/solr/data:/var/solr/data
    ports:
      - "{solr_port}:8983"
    entrypoint:
      - bash
      - -lc
      - |
        set -e
        mkdir -p /var/solr/data{core_checks}
        exec solr-foreground
"""

def gen_kiwix(ip, web_port=8610):
    return f"""
  # ============================================================================
  # KIWIX - Offline Wikipedia
  # ============================================================================
  kiwix:
    image: ghcr.io/kiwix/kiwix-serve:latest
    container_name: kiwix
    restart: unless-stopped
    networks:
      - app-network
    command: "*.zim"
    volumes:
      - /mnt/disk0/lexicon/kiwix/data:/data
    ports:
      - "{web_port}:8080"
"""

def gen_nextcloud(ip, web_port=8612, db_port=8611):
    return f"""
  # ============================================================================
  # NEXTCLOUD - File Sharing
  # ============================================================================
  nextcloud-db:
    image: postgres:15-alpine
    container_name: nextcloud-db
    restart: unless-stopped
    networks:
      - app-network
    environment:
      POSTGRES_DB: nextcloud
      POSTGRES_USER: nextcloud
      POSTGRES_PASSWORD: nextcloud_password
    volumes:
      - /mnt/disk0/lexicon/nextcloud/db:/var/lib/postgresql/data
    ports:
      - "{db_port}:5432"

  nextcloud:
    image: nextcloud:latest
    container_name: nextcloud
    restart: unless-stopped
    networks:
      - app-network
    environment:
      POSTGRES_HOST: nextcloud-db
      POSTGRES_DB: nextcloud
      POSTGRES_USER: nextcloud
      POSTGRES_PASSWORD: nextcloud_password
      NEXTCLOUD_ADMIN_USER: alchemar
      NEXTCLOUD_ADMIN_PASSWORD: change_me_1
      NEXTCLOUD_TRUSTED_DOMAINS: {ip}
    volumes:
      - /mnt/disk0/lexicon/nextcloud/data:/var/www/html
    ports:
      - "{web_port}:80"
    depends_on:
      - nextcloud-db
"""

def gen_audiobookshelf(ip, web_port=8620):
    return f"""
  # ============================================================================
  # AUDIOBOOKSHELF - Audiobooks & Podcasts
  # ============================================================================
  audiobookshelf:
    image: ghcr.io/advplyr/audiobookshelf:latest
    container_name: audiobookshelf
    restart: unless-stopped
    networks:
      - app-network
    environment:
      TZ: America/Chicago
    volumes:
      - /mnt/disk0/lexicon/audiobookshelf/config:/config
      - /mnt/disk0/lexicon/audiobookshelf/metadata:/metadata
      - /mnt/disk0/lexicon/audiobookshelf/audiobooks:/audiobooks
      - /mnt/disk0/lexicon/audiobookshelf/podcasts:/podcasts
    ports:
      - "{web_port}:80"
"""

def gen_tvheadend(ip, web_port=8630, htsp_port=8631):
    return f"""
  # ============================================================================
  # TVHEADEND - Live TV & DVR
  # ============================================================================
  tvheadend:
    image: lscr.io/linuxserver/tvheadend:latest
    container_name: tvheadend
    restart: unless-stopped
    networks:
      - app-network
    environment:
      PUID: 1000
      PGID: 1000
      TZ: America/Chicago
    volumes:
      - /mnt/disk0/lexicon/tvheadend/config:/config
      - /mnt/disk0/lexicon/tvheadend/recordings:/recordings
    ports:
      - "{web_port}:9981"
      - "{htsp_port}:9982"
    devices:
      - /dev/dri:/dev/dri
"""

def gen_snapserver():
    return f"""
  # ============================================================================
  # SNAPCAST - Multi-room Audio Server
  # ============================================================================
  snapserver:
    image: docker.io/sweisgerber/snapcast:latest
    container_name: snapserver
    restart: unless-stopped
    network_mode: host
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Chicago
      - START_SNAPCLIENT=false
      - START_AIRPLAY=false
    volumes:
      - /mnt/disk0/lexicon/snapserver/config/snapserver.conf:/config/snapserver.conf
      - /mnt/disk0/lexicon/snapserver/data:/data
      - /opt/snapcast/snapfifo:/tmp/snapfifo
      - /opt/snapcast/mopidy-snapfifo:/tmp/mopidy_snapfifo
      - /mnt/disk0/lexicon/snapserver/var/lib/snapserver:/var/lib/snapserver
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
"""

def gen_mopidy(ip, web_port=8621):
    return f"""
  # ============================================================================
  # MOPIDY - Music Player Daemon
  # ============================================================================
  mopidy:
    image: wernight/mopidy
    container_name: mopidy
    restart: unless-stopped
    networks:
      - app-network
    ports:
      - "{web_port}:6680"
    volumes:
      - /mnt/disk0/lexicon/mopidy:/config
      - /opt/snapcast/mopidy_snapfifo:/tmp/mopidy_snapfifo
    entrypoint: >
      sh -c "pip install Mopidy-Subidy && mopidy --config /config/mopidy.conf"
"""

def gen_music_assistant():
    return f"""
  # ============================================================================
  # MUSIC ASSISTANT
  # ============================================================================
  music-assistant:
    image: ghcr.io/music-assistant/server:latest
    container_name: music-assistant
    restart: unless-stopped
    network_mode: host
    volumes:
      - /mnt/disk0/lexicon/music-assistant/data:/data
      - /opt/snapcast/snapfifo:/tmp/snapfifo
    environment:
      - LOG_LEVEL=info
    cap_add:
      - SYS_ADMIN
      - DAC_READ_SEARCH
    security_opt:
      - apparmor:unconfined
"""

def gen_filebot():
    return f"""
  # ============================================================================
  # FILEBOT CLI - Media Organizer (on-demand)
  # ============================================================================
  filebot-cli:
    image: rednoah/filebot:latest
    container_name: filebot-cli
    restart: "no"
    networks:
      - app-network
    environment:
      TZ: America/Chicago
    volumes:
      - /mnt/disk0/lexicon/jellyfin/media:/media:rw
      - /mnt/disk0/lexicon/filebot-cli/data:/data:rw
    entrypoint: ["filebot"]
"""

def gen_jellyfin(name, ip, port):
    return f"""
  jellyfin-{name}:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin-{name}
    restart: unless-stopped
    networks:
      - app-network
    environment:
      PUID: 1000
      PGID: 1000
      TZ: America/Chicago
    volumes:
      - /mnt/disk0/lexicon/jellyfin-{name}/config:/config
      - /mnt/disk0/lexicon/jellyfin-{name}/cache:/cache
      - /mnt/disk0/lexicon/jellyfin-{name}/media:/media
    ports:
      - "{port}:8096"
"""

def gen_photoprism(name, ip, port):
    return f"""
  photoprism-{name}:
    image: photoprism/photoprism:latest
    container_name: photoprism-{name}
    restart: unless-stopped
    networks:
      - app-network
    security_opt:
      - seccomp:unconfined
      - apparmor:unconfined
    environment:
      PHOTOPRISM_ADMIN_USER: alchemar
      PHOTOPRISM_ADMIN_PASSWORD: change_me
      PHOTOPRISM_SITE_URL: "http://{ip}:{port}"
      PHOTOPRISM_DISABLE_TLS: "true"
      PHOTOPRISM_DATABASE_DRIVER: sqlite
      PHOTOPRISM_HTTP_PORT: 2342
    volumes:
      - /mnt/disk0/lexicon/photoprism-{name}/storage:/photoprism/storage
      - /mnt/disk0/lexicon/photoprism-{name}/originals:/photoprism/originals
    ports:
      - "{port}:2342"
"""

def gen_kavita(name, ip, port):
    return f"""
  kavita-{name}:
    image: jvmilazz0/kavita:latest
    container_name: kavita-{name}
    restart: unless-stopped
    networks:
      - app-network
    environment:
      TZ: America/Chicago
    volumes:
      - /mnt/disk0/lexicon/kavita-{name}/config:/kavita/config
      - /mnt/disk0/lexicon/kavita-{name}/data:/data
    ports:
      - "{port}:5000"
"""

def gen_navidrome(name, ip, port):
    return f"""
  navidrome-{name}:
    image: deluan/navidrome:latest
    container_name: navidrome-{name}
    restart: unless-stopped
    networks:
      - app-network
    environment:
      ND_SCANSCHEDULE: 1h
      ND_LOGLEVEL: info
      ND_BASEURL: /
    volumes:
      - /mnt/disk0/lexicon/navidrome-{name}/data:/data
      - /mnt/disk0/lexicon/navidrome-{name}/music:/music:ro
    ports:
      - "{port}:4533"
"""

def gen_manyfold(name, ip, port, db_port, solr_cores):
    db_pass = f"manyfold_{name}_password"
    redis_pass = f"manyfold_{name}_redis_password"
    secret = f"changeme_generate_secret_{name}"
    solr_cores.append(f"manyfold-{name}")
    return f"""
  manyfold-{name}-db:
    image: postgres:15-alpine
    container_name: manyfold-{name}-db
    restart: unless-stopped
    networks:
      - app-network
    environment:
      POSTGRES_USER: manyfold
      POSTGRES_PASSWORD: {db_pass}
      POSTGRES_DB: manyfold
    volumes:
      - /mnt/disk0/lexicon/manyfold-{name}/postgres:/var/lib/postgresql/data
    ports:
      - "{db_port}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U manyfold"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  manyfold-{name}-redis:
    image: redis:7-alpine
    container_name: manyfold-{name}-redis
    restart: unless-stopped
    networks:
      - app-network
    command: redis-server --requirepass {redis_pass}
    volumes:
      - /mnt/disk0/lexicon/manyfold-{name}/redis:/data

  manyfold-{name}:
    image: ghcr.io/manyfold3d/manyfold:latest
    container_name: manyfold-{name}
    restart: unless-stopped
    networks:
      - app-network
    environment:
      PUID: 1000
      PGID: 1000
      TZ: UTC
      DATABASE_ADAPTER: postgresql
      DATABASE_HOST: manyfold-{name}-db
      DATABASE_PORT: 5432
      DATABASE_NAME: manyfold
      DATABASE_USER: manyfold
      DATABASE_PASSWORD: {db_pass}
      REDIS_URL: "redis://:{redis_pass}@manyfold-{name}-redis:6379/0"
      SECRET_KEY_BASE: {secret}
      MIN_PASSWORD_SCORE: 0
    volumes:
      - /mnt/disk0/lexicon/manyfold-{name}/libraries:/libraries
      - /mnt/disk0/lexicon/manyfold-{name}/data:/config
    ports:
      - "{port}:3214"
    depends_on:
      manyfold-{name}-db:
        condition: service_healthy
      manyfold-{name}-redis:
        condition: service_started
"""


def gen_webtop(name, ip, port, flavor="ubuntu-kde", password=None):
    image = f"lscr.io/linuxserver/webtop:{flavor}"
    password_line = f"      PASSWORD: {password}" if password else "      # PASSWORD: optional_password"
    return f"""
  # ============================================================================
  # WEBTOP - {name} ({flavor})
  # All user data stored pre-downloaded on /mnt/disk0/lexicon/webtop-{name}/
  #
  #   config/    -> /config            (LinuxServer app config + desktop session)
  #   home/      -> /config/Desktop    (user home, persisted across restarts)
  #   downloads/ -> /config/Downloads  (browser/file downloads)
  #   shared/    -> /shared            (read-write share accessible from other
  #                                     containers, e.g. Jellyfin media drop)
  # ============================================================================
  webtop-{name}:
    image: {image}
    container_name: webtop-{name}
    restart: unless-stopped
    networks:
      - app-network
    security_opt:
      - seccomp:unconfined
    environment:
      PUID: 1000
      PGID: 1000
      TZ: America/Chicago
      TITLE: "Webtop — {name}"
{password_line}
    volumes:
      # Core config / session state — persisted on disk
      - /mnt/disk0/lexicon/webtop-{name}/config:/config
      # Explicit home-directory sub-mounts so they survive container rebuilds
      # and are accessible from the host without digging into /config/
      - /mnt/disk0/lexicon/webtop-{name}/home:/config/Desktop
      - /mnt/disk0/lexicon/webtop-{name}/downloads:/config/Downloads
      - /mnt/disk0/lexicon/webtop-{name}/documents:/config/Documents
      # Shared read-write folder — handy for dropping files in from other services
      - /mnt/disk0/lexicon/webtop-{name}/shared:/shared
      # Docker socket — lets you manage Docker from inside the desktop (optional)
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "{port}:3000"
      - "{port + 1}:3001"
    shm_size: "1gb"
"""


def gen_romm(ip, web_port=8710, db_port=8712, redis_port=8713):
    return f"""
  # ============================================================================
  # ROMM - Retro ROM Manager & In-Browser Player
  # Web-based ROM library with metadata from IGDB/Screenscraper/MobyGames,
  # in-browser play via EmulatorJS across 400+ systems, saves sync, and more.
  #
  # ROMs go in:  /mnt/disk0/lexicon/romm/library/<system>/
  # Systems use standard RetroPie/EmulationStation folder names, e.g.:
  #   nes/   snes/  n64/   gba/   gbc/   genesis/  psx/
  #   mame/  arcade/  atari2600/  ... (400+ supported)
  #
  # API keys (optional but recommended for metadata):
  #   IGDB:            https://api.igdb.com/  (free Twitch dev account)
  #   Screenscraper:   https://www.screenscraper.fr/
  #   SteamGridDB:     https://www.steamgriddb.com/profile/preferences/api
  # ============================================================================
  romm-db:
    image: mariadb:11
    container_name: romm-db
    restart: unless-stopped
    networks:
      - app-network
    environment:
      MARIADB_ROOT_PASSWORD: romm_root_password
      MARIADB_DATABASE: romm
      MARIADB_USER: romm-user
      MARIADB_PASSWORD: romm_password
    volumes:
      - /mnt/disk0/lexicon/romm/db:/var/lib/mysql
    ports:
      - "{db_port}:3306"
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  romm:
    image: rommapp/romm:latest
    container_name: romm
    restart: unless-stopped
    networks:
      - app-network
    depends_on:
      romm-db:
        condition: service_healthy
    environment:
      TZ: America/Chicago
      DB_HOST: romm-db
      DB_NAME: romm
      DB_USER: romm-user
      DB_PASSWD: romm_password
      ROMM_AUTH_SECRET_KEY: changeme_generate_with_openssl_rand_hex_32
      # Metadata API keys — fill these in for cover art and game info
      # IGDB_CLIENT_ID: your_igdb_client_id
      # IGDB_CLIENT_SECRET: your_igdb_client_secret
      # SCREENSCRAPER_USER: your_screenscraper_username
      # SCREENSCRAPER_PASSWORD: your_screenscraper_password
      # STEAMGRIDDB_API_KEY: your_steamgriddb_key
    volumes:
      # ROM library — organised by system folder name (RetroPie convention)
      - /mnt/disk0/lexicon/romm/library:/romm/library
      # Resources — downloaded cover art, metadata cache
      - /mnt/disk0/lexicon/romm/resources:/romm/resources
      # Assets — user-uploaded custom artwork
      - /mnt/disk0/lexicon/romm/assets:/romm/assets
      # Config — config.yml for advanced options
      - /mnt/disk0/lexicon/romm/config:/romm/config
      # Redis data — embedded, no separate container needed
      - /mnt/disk0/lexicon/romm/redis:/romm/redis-data
    ports:
      - "{web_port}:3000"
"""


def gen_headway(ip, web_port=8720):
    return f"""
  # ============================================================================
  # HEADWAY — Self-hosted Maps Stack (OpenStreetMap)
  #
  # Full map server: vector tiles (tileserver-gl), geocoding (Pelias /
  # Elasticsearch), routing (Valhalla), and a web frontend.
  #
  # SETUP REQUIRED before first start:
  #   1. Choose an area extract from https://download.geofabrik.de/
  #      or use a pre-built area slug from Headway's list of 200+ cities.
  #   2. Run the data build step (one-time, can take hours for large areas):
  #        docker run --rm -v /mnt/disk0/lexicon/headway/data:/data \\
  #          headwaymaps/headway build --area north-america
  #      Replace 'north-america' with your chosen area slug.
  #   3. Then start normally:  docker compose up -d headway
  #
  # RESOURCE USAGE (~6 GB RAM at runtime):
  #   Elasticsearch (geocoding):  ~3.5 GB
  #   Valhalla (routing):         ~2.0 GB
  #   tileserver-gl (tiles):      ~300 MB
  #   Frontend + placeholder:     ~250 MB
  #
  # Data updates: must be done manually by re-running the build step above.
  # Automated update support is not yet implemented in Headway.
  # ============================================================================
  headway:
    image: headwaymaps/headway:latest
    container_name: headway
    restart: unless-stopped
    networks:
      - app-network
    volumes:
      - /mnt/disk0/lexicon/headway/data:/data
    ports:
      - "{web_port}:8080"
    environment:
      - HOST=0.0.0.0
      - PORT=8080
"""


def gen_exodos(ip, web_port=8700):
    return f"""
  # ============================================================================
  # eXoDOS WEB PLAYER
  # Custom Flask+js-dos webapp that reads a fully pre-downloaded eXoDOS v6
  # collection from /mnt/disk0/lexicon/exodos/.
  #
  # Expected directory layout on the host (all pre-downloaded, nothing fetched
  # at runtime):
  #
  #   /mnt/disk0/lexicon/exodos/
  #     collection/                   <- eXoDOS root (mount as /exodos, ro)
  #       Data/Platforms/MS-DOS.xml   <- LaunchBox metadata XML
  #       eXo/eXoDOS/<GameFolder>/    <- per-game zip + bat files
  #       Images/MS-DOS/              <- box art, screenshots, banners
  #         Box - Front/
  #         Screenshot - Gameplay/
  #         Screenshot - Game Title/
  #         Banner/
  #         Clear Logo/
  #       Manuals/                    <- PDF manuals (optional)
  #       Videos/                     <- video snaps (optional)
  #     cache/                        <- app thumbnail/metadata cache (rw)
  #
  # Download the full eXoDOS v6 torrent from https://www.retro-exo.com/
  # and extract it into /mnt/disk0/lexicon/exodos/collection/
  # ============================================================================
  exodos:
    image: exodos-web:latest
    container_name: exodos
    build:
      context: ./exodos-web
      dockerfile: Dockerfile
    restart: unless-stopped
    networks:
      - app-network
    environment:
      EXODOS_ROOT: /exodos
      FLASK_ENV: production
      PYTHONUNBUFFERED: "1"
    volumes:
      # Full pre-downloaded eXoDOS collection — mounted read-only
      - /mnt/disk0/lexicon/exodos/collection:/exodos:ro
      # Writable cache dir for thumbnails and processed metadata
      - /mnt/disk0/lexicon/exodos/cache:/app/cache
    ports:
      - "{web_port}:5000"
"""

# ==============================================================================
# DASHBOARD HTML GENERATOR
# ==============================================================================

def gen_dashboard_html(ip, services_list):
    """Generate the dashboard HTML page."""
    
    # Group services by category
    categories = {}
    for svc in services_list:
        cat = svc.get("category", "Other")
        categories.setdefault(cat, []).append(svc)

    cards_html = ""
    for cat, svcs in sorted(categories.items()):
        cards_html += f'<div class="category"><h2 class="cat-title">{cat}</h2><div class="cards">\n'
        for svc in svcs:
            port = svc.get("port")
            url = f"http://{ip}:{port}" if port else "#"
            target = '_blank' if port else '_self'
            disabled = ' disabled' if not port else ''
            cards_html += f"""  <a href="{url}" target="{target}" class="card{disabled}">
    <span class="icon">{svc['icon']}</span>
    <span class="name">{svc['name']}</span>
    <span class="desc">{svc['description']}</span>
    {"<span class='port'>:" + str(port) + "</span>" if port else "<span class='port'>host network</span>"}
  </a>\n"""
        cards_html += "</div></div>\n"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lexicon — Service Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0c10;
    --surface: #111318;
    --border: #1e2330;
    --accent: #4af;
    --accent2: #f84;
    --text: #d0d8e8;
    --muted: #5a6580;
    --card-hover: #161c28;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    padding: 2rem;
  }}
  header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 1.5rem;
    margin-bottom: 2.5rem;
    display: flex;
    align-items: baseline;
    gap: 1rem;
  }}
  header h1 {{
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #fff;
  }}
  header h1 span {{ color: var(--accent); }}
  .host-badge {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--muted);
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 0.25rem 0.6rem;
    border-radius: 4px;
  }}
  .category {{ margin-bottom: 2.5rem; }}
  .cat-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--muted);
    margin-bottom: 1rem;
    padding-left: 0.25rem;
  }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.2rem 1rem;
    text-decoration: none;
    color: var(--text);
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    transition: background 0.15s, border-color 0.15s, transform 0.15s;
    position: relative;
    overflow: hidden;
  }}
  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    opacity: 0;
    transition: opacity 0.15s;
  }}
  .card:hover {{
    background: var(--card-hover);
    border-color: #2a3350;
    transform: translateY(-2px);
  }}
  .card:hover::before {{ opacity: 1; }}
  .card.disabled {{
    opacity: 0.45;
    cursor: default;
    pointer-events: none;
  }}
  .icon {{ font-size: 1.6rem; }}
  .name {{
    font-weight: 700;
    font-size: 0.95rem;
    color: #fff;
  }}
  .desc {{
    font-size: 0.75rem;
    color: var(--muted);
    line-height: 1.4;
  }}
  .port {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--accent);
    margin-top: auto;
  }}
  footer {{
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--muted);
    text-align: center;
  }}
</style>
</head>
<body>
<header>
  <h1>LEXI<span>CON</span></h1>
  <span class="host-badge">{ip}</span>
</header>
{cards_html}
<footer>Generated by compose-gen &nbsp;·&nbsp; {ip}:8080</footer>
</body>
</html>
"""

def gen_dashboard_service(ip):
    return f"""
  # ============================================================================
  # DASHBOARD - Service Index Page
  # ============================================================================
  dashboard:
    image: nginx:alpine
    container_name: dashboard
    restart: unless-stopped
    networks:
      - app-network
    ports:
      - "8080:80"
    volumes:
      - /mnt/disk0/lexicon/dashboard:/usr/share/nginx/html:ro
"""

# ==============================================================================
# TERMINAL UI HELPERS
# ==============================================================================

def clear():
    os.system('clear' if os.name == 'posix' else 'cls')

def header():
    print("\033[1;36m" + "=" * 60)
    print("       DOCKER COMPOSE GENERATOR — LEXICON SERVER")
    print("=" * 60 + "\033[0m")
    print()

def section(title):
    print(f"\n\033[1;33m── {title} \033[0m" + "─" * (55 - len(title)))

def success(msg):
    print(f"\033[1;32m✓ {msg}\033[0m")

def error(msg):
    print(f"\033[1;31m✗ {msg}\033[0m")

def info(msg):
    print(f"\033[0;36m  {msg}\033[0m")

def prompt(msg, default=None):
    default_hint = f" [{default}]" if default is not None else ""
    try:
        val = input(f"\033[0;37m  {msg}{default_hint}: \033[0m").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default

def prompt_int(msg, min_val=0, max_val=5, default=0):
    while True:
        raw = prompt(msg, default)
        try:
            v = int(raw)
            if min_val <= v <= max_val:
                return v
            error(f"Enter a number between {min_val} and {max_val}")
        except (ValueError, TypeError):
            error("Invalid number")

def pick_menu(title, options, multi=False):
    """
    Display a numbered menu. Returns index (single) or list of indices (multi).
    options: list of strings
    """
    print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        print(f"    \033[0;33m{i}\033[0m. {opt}")
    if multi:
        raw = prompt("Enter numbers separated by commas (or blank to skip)", "")
        if not raw:
            return []
        indices = []
        for part in raw.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < len(options):
                    indices.append(idx)
            except ValueError:
                pass
        return indices
    else:
        while True:
            raw = prompt("Enter number", 1)
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return idx
            except (ValueError, TypeError):
                pass
            error("Invalid choice")

# ==============================================================================
# CONFIG STATE
# ==============================================================================

class Config:
    def __init__(self):
        self.ip = "10.50.0.13"
        self.multi_instances = {}   # service_key -> list of name strings
        self.singleton_enabled = {} # service_key -> bool
        self.port_map = {}          # (service_key, name_or_None) -> port
        self.webtop_flavors = {}    # name -> flavor string
        self.webtop_passwords = {}  # name -> password or None

# ==============================================================================
# PORT ALLOCATION
# ==============================================================================

PORT_RANGES = {
    "jellyfin":      (8100, 8),
    "photoprism":    (8120, 8),
    "kavita":        (8140, 8),
    "navidrome":     (8160, 8),
    "manyfold":      (8180, 20),  # needs db + redis ports too
    "gitea":         (8200, 5),
    "opengrok":      (8210, 3),
    "solr":          (8220, 5),
    "kiwix":         (8230, 3),
    "nextcloud":     (8240, 5),
    "audiobookshelf":(8250, 3),
    "tvheadend":     (8260, 5),
    "mopidy":        (8270, 3),
    "webtop":        (8640, 20),  # 2 ports per instance
}

def allocate_ports(config):
    """Assign host ports to all enabled services."""
    used = {8080}  # dashboard always at 8080
    port_map = {}

    def next_free(start):
        p = start
        while p in used:
            p += 1
        used.add(p)
        return p

    # Multi-instance services
    for key, names in config.multi_instances.items():
        base = PORT_RANGES.get(key, (9000, 10))[0]
        for name in names:
            p = next_free(base)
            port_map[(key, name)] = p
            if key == "manyfold":
                port_map[(key + "_db", name)] = next_free(base + 50)
            elif key == "webtop":
                # Reserve the +1 port for KasmVNC HTTPS (3001)
                used.add(p + 1)

    # Singleton services
    singleton_ports = {
        "gitea":          (8200, 8201, 8202),
        "opengrok":       (8210,),
        "solr":           (8220, 8221, 8222),
        "kiwix":          (8230,),
        "nextcloud":      (8240, 8241),
        "audiobookshelf": (8250,),
        "tvheadend":      (8260, 8261),
        "mopidy":         (8270,),
        "exodos":         (8700,),
        "romm":           (8710, 8711, 8712),  # web, unused, db
        "headway":        (8720,),
    }
    for key, enabled in config.singleton_enabled.items():
        if enabled and key in singleton_ports:
            ports = [next_free(p) for p in singleton_ports[key]]
            port_map[key] = ports

    config.port_map = port_map
    return port_map

# ==============================================================================
# MAIN MENU FLOW
# ==============================================================================

def configure_ip(config):
    clear()
    header()
    section("Server IP Address")
    info("This IP is used for service URLs in the dashboard and PhotoPrism.")
    print()
    val = prompt("Enter server IP address", config.ip)
    config.ip = val
    success(f"IP set to {config.ip}")

def configure_multi_service(config, key):
    svc = MULTI_SERVICES[key]
    clear()
    header()
    section(f"Configure: {svc['label']}")
    info(f"Icon: {svc['icon']}  |  Category: {svc['category']}")
    info(svc['description'])
    print()

    count = prompt_int(f"How many {svc['label']} instances? (0–5)", 0, 5, 0)
    names = []
    for i in range(count):
        default_name = ["codex", "vault", "archive", "prime", "zero"][i]
        name = prompt(f"  Name for instance #{i+1}", default_name)
        # Sanitize: lowercase, replace spaces
        name = name.lower().replace(" ", "-").replace("_", "-")
        names.append(name)

    # For webtop: ask flavor and optional password per instance
    webtop_flavors = {}
    webtop_passwords = {}
    if key == "webtop" and names:
        flavors = MULTI_SERVICES["webtop"]["flavors"]
        print()
        info("Available desktop flavors:")
        for fi, fl in enumerate(flavors, 1):
            print(f"    \033[0;33m{fi}\033[0m. {fl}")
        print()
        for name in names:
            fi = prompt_int(f"  Flavor for webtop-{name}", 1, len(flavors), 1)
            webtop_flavors[name] = flavors[fi - 1]
            pw = prompt(f"  Password for webtop-{name} (blank = none)", "")
            webtop_passwords[name] = pw if pw else None
        config.webtop_flavors = getattr(config, "webtop_flavors", {})
        config.webtop_passwords = getattr(config, "webtop_passwords", {})
        config.webtop_flavors.update(webtop_flavors)
        config.webtop_passwords.update(webtop_passwords)

    config.multi_instances[key] = names
    if names:
        success(f"{count} instance(s): {', '.join(names)}")
    else:
        info("0 instances — skipped")

def configure_singleton(config, key):
    svc = SINGLETON_SERVICES[key]
    clear()
    header()
    section(f"Configure: {svc['label']}")
    info(f"Icon: {svc['icon']}  |  Category: {svc['category']}")
    info(svc['description'])
    print()

    choice = prompt_int(f"Enable {svc['label']}? (0=No, 1=Yes)", 0, 1, 0)
    config.singleton_enabled[key] = bool(choice)
    if choice:
        success("Enabled")
    else:
        info("Disabled — skipped")


# ==============================================================================
# RAM CALCULATOR
# ==============================================================================

def calc_ram(config):
    """
    Return a list of (label, ram_mb) tuples and a total for all enabled services.
    Accounts for multi-instance multipliers and sidecars (DB, Redis).
    """
    rows = []
    total = 0

    # OS + Docker overhead (always)
    OS_OVERHEAD = 512
    rows.append(("OS + Docker daemon overhead", OS_OVERHEAD))
    total += OS_OVERHEAD

    # ── Multi-instance services ──────────────────────────────────────────────
    for key, names in config.multi_instances.items():
        if not names:
            continue
        svc = MULTI_SERVICES[key]
        ram_each = svc.get("ram_mb", 256)
        for name in names:
            rows.append((f"{svc['label'].split('(')[0].strip()} — {name}", ram_each))
            total += ram_each

    # ── Singleton services ───────────────────────────────────────────────────
    SINGLETONS_WITH_SOLR_OVERHEAD = {"solr"}  # already includes Tika in ram_mb
    for key, enabled in config.singleton_enabled.items():
        if not enabled:
            continue
        svc = SINGLETON_SERVICES[key]
        ram = svc.get("ram_mb", 0)
        if ram == 0:
            continue  # filebot / on-demand — ignore
        label = svc["label"].split("(")[0].strip()
        rows.append((label, ram))
        total += ram

    return rows, total


def format_ram_table(config):
    """Return a formatted string showing per-service RAM and a total."""
    rows, total = calc_ram(config)
    lines = []
    lines.append(f"  {'Service':<42} {'RAM (MB)':>9}  {'GB':>6}")
    lines.append("  " + "─" * 62)
    for label, mb in rows:
        gb = mb / 1024
        bar_fill = "█" * min(int(gb * 2), 20)
        lines.append(f"  {label:<42} {mb:>8} MB  {gb:>5.1f} GB  {bar_fill}")
    lines.append("  " + "─" * 62)
    gb_total = total / 1024
    lines.append(f"  {'TOTAL':<42} {total:>8} MB  {gb_total:>5.1f} GB")

    # Warning thresholds
    if gb_total > 28:
        lines.append(f"\n  \033[1;31m⚠  {gb_total:.1f} GB is very high — ensure the VM has enough RAM\033[0m")
    elif gb_total > 16:
        lines.append(f"\n  \033[0;33m⚠  {gb_total:.1f} GB — allocate at least {int(gb_total * 1.25 + 1):.0f} GB to the VM\033[0m")
    elif gb_total > 8:
        lines.append(f"\n  \033[0;36m✓  {gb_total:.1f} GB — recommend allocating {int(gb_total * 1.25 + 1):.0f} GB to the VM\033[0m")
    else:
        lines.append(f"\n  \033[1;32m✓  {gb_total:.1f} GB — comfortable; 16 GB VM allocation is fine\033[0m")

    return "\n".join(lines)

def show_summary(config):
    clear()
    header()
    section("Configuration Summary")
    print(f"\n  \033[0;37mServer IP:\033[0m  {config.ip}")
    print()

    any_service = False

    print("  \033[1;37mMulti-Instance Services:\033[0m")
    for key, names in config.multi_instances.items():
        svc = MULTI_SERVICES[key]
        if names:
            any_service = True
            print(f"    {svc['icon']} {svc['label']}")
            for name in names:
                print(f"         → {key}-{name}")
        else:
            print(f"    \033[0;90m{svc['icon']} {svc['label']}  (disabled)\033[0m")

    print()
    print("  \033[1;37mSingleton Services:\033[0m")
    for key, enabled in config.singleton_enabled.items():
        svc = SINGLETON_SERVICES[key]
        if enabled:
            any_service = True
            print(f"    {svc['icon']} {svc['label']}")
        else:
            print(f"    \033[0;90m{svc['icon']} {svc['label']}  (disabled)\033[0m")

    print()
    if not any_service:
        print("  \033[1;31m⚠  No services configured! Dashboard will be empty.\033[0m")

    # RAM summary
    section("Estimated RAM Requirements")
    print()
    print(format_ram_table(config))
    print()
    return any_service

def main_menu(config):
    while True:
        clear()
        header()

        print("  \033[1;37mMain Menu\033[0m\n")
        print("    \033[0;33m1\033[0m.  Set Server IP Address           \033[0;36m" + config.ip + "\033[0m")
        print()
        print("  \033[0;37mMulti-instance services (0–5 copies):\033[0m")

        multi_keys = list(MULTI_SERVICES.keys())
        for i, key in enumerate(multi_keys, 2):
            svc = MULTI_SERVICES[key]
            names = config.multi_instances.get(key, [])
            status = f"\033[0;32m{len(names)} instance(s)\033[0m" if names else "\033[0;90mdisabled\033[0m"
            print(f"    \033[0;33m{i}\033[0m.  {svc['icon']} {svc['label']:<35} {status}")

        print()
        print("  \033[0;37mSingleton services (on/off):\033[0m")

        singleton_keys = list(SINGLETON_SERVICES.keys())
        offset = len(multi_keys) + 2
        for i, key in enumerate(singleton_keys, offset):
            svc = SINGLETON_SERVICES[key]
            enabled = config.singleton_enabled.get(key, False)
            status = "\033[0;32mon\033[0m" if enabled else "\033[0;90moff\033[0m"
            print(f"    \033[0;33m{i}\033[0m.  {svc['icon']} {svc['label']:<35} {status}")

        total = offset + len(singleton_keys)
        print()
        print(f"    \033[0;33m{total}\033[0m.  \033[1;37mReview Summary\033[0m")
        print(f"    \033[0;33m{total+1}\033[0m.  \033[1;32mGenerate docker-compose.yml + Dashboard\033[0m")
        print(f"    \033[0;33m{total+2}\033[0m.  Quit")
        print()

        choice = prompt_int(f"Select option (1–{total+2})", 1, total+2, total+1)

        if choice == 1:
            configure_ip(config)
        elif 2 <= choice <= len(multi_keys) + 1:
            key = multi_keys[choice - 2]
            configure_multi_service(config, key)
        elif offset <= choice <= offset + len(singleton_keys) - 1:
            key = singleton_keys[choice - offset]
            configure_singleton(config, key)
        elif choice == total:
            show_summary(config)
            prompt("Press Enter to continue", "")
        elif choice == total + 1:
            show_summary(config)
            print()
            confirm = prompt("Generate files? (y/n)", "y")
            if confirm.lower() in ("y", "yes", ""):
                generate_files(config)
                return
        elif choice == total + 2:
            print("\n  Goodbye!\n")
            sys.exit(0)

# ==============================================================================
# SETUP SCRIPT GENERATOR
# ==============================================================================

def gen_setup_script(ip, config):
    """
    Generate a Debian 13 bootstrap script that:
      - Installs Docker CE (official repo) + Compose plugin
      - Installs supporting tools (curl, git, wget, jq, htop, etc.)
      - Creates /mnt/disk0/lexicon directory tree for every enabled service
      - Sets correct ownership (UID/GID 1000)
      - Creates snapcast pipe dirs if needed
      - Adds current user to docker group
      - Enables docker on boot
    """

    # ── Collect every data directory needed ──────────────────────────────────
    dirs = set()
    dirs.add("/mnt/disk0/lexicon/dashboard")

    # Multi-instance dirs
    for key, names in config.multi_instances.items():
        for name in names:
            if key == "jellyfin":
                dirs.update([
                    f"/mnt/disk0/lexicon/jellyfin-{name}/config",
                    f"/mnt/disk0/lexicon/jellyfin-{name}/cache",
                    f"/mnt/disk0/lexicon/jellyfin-{name}/media",
                ])
            elif key == "photoprism":
                dirs.update([
                    f"/mnt/disk0/lexicon/photoprism-{name}/storage",
                    f"/mnt/disk0/lexicon/photoprism-{name}/originals",
                ])
            elif key == "kavita":
                dirs.update([
                    f"/mnt/disk0/lexicon/kavita-{name}/config",
                    f"/mnt/disk0/lexicon/kavita-{name}/data",
                ])
            elif key == "navidrome":
                dirs.update([
                    f"/mnt/disk0/lexicon/navidrome-{name}/data",
                    f"/mnt/disk0/lexicon/navidrome-{name}/music",
                ])
            elif key == "webtop":
                dirs.update([
                    f"/mnt/disk0/lexicon/webtop-{name}/config",
                    f"/mnt/disk0/lexicon/webtop-{name}/home",
                    f"/mnt/disk0/lexicon/webtop-{name}/downloads",
                    f"/mnt/disk0/lexicon/webtop-{name}/documents",
                    f"/mnt/disk0/lexicon/webtop-{name}/shared",
                ])
            elif key == "manyfold":
                dirs.update([
                    f"/mnt/disk0/lexicon/manyfold-{name}/postgres",
                    f"/mnt/disk0/lexicon/manyfold-{name}/redis",
                    f"/mnt/disk0/lexicon/manyfold-{name}/libraries",
                    f"/mnt/disk0/lexicon/manyfold-{name}/data",
                ])

    # Singleton dirs
    singleton_dir_map = {
        "gitea":          [
            "/mnt/disk0/lexicon/gitea/postgres",
            "/mnt/disk0/lexicon/gitea/data",
            "/mnt/disk0/lexicon/gitea/custom/templates/custom",
        ],
        "opengrok":       [
            "/mnt/disk0/lexicon/opengrok/src",
            "/mnt/disk0/lexicon/opengrok/data",
            "/mnt/disk0/lexicon/opengrok/etc",
        ],
        "solr":           [
            "/mnt/disk0/lexicon/solr/data",
        ],
        "kiwix":          [
            "/mnt/disk0/lexicon/kiwix/data",
        ],
        "nextcloud":      [
            "/mnt/disk0/lexicon/nextcloud/db",
            "/mnt/disk0/lexicon/nextcloud/data",
        ],
        "audiobookshelf": [
            "/mnt/disk0/lexicon/audiobookshelf/config",
            "/mnt/disk0/lexicon/audiobookshelf/metadata",
            "/mnt/disk0/lexicon/audiobookshelf/audiobooks",
            "/mnt/disk0/lexicon/audiobookshelf/podcasts",
        ],
        "tvheadend":      [
            "/mnt/disk0/lexicon/tvheadend/config",
            "/mnt/disk0/lexicon/tvheadend/recordings",
        ],
        "snapserver":     [
            "/mnt/disk0/lexicon/snapserver/config",
            "/mnt/disk0/lexicon/snapserver/data",
            "/mnt/disk0/lexicon/snapserver/var/lib/snapserver",
            "/opt/snapcast",
        ],
        "mopidy":         [
            "/mnt/disk0/lexicon/mopidy",
        ],
        "music_assistant":[
            "/mnt/disk0/lexicon/music-assistant/data",
        ],
        "filebot":        [
            "/mnt/disk0/lexicon/filebot-cli/data",
        ],
        "romm":           [
            "/mnt/disk0/lexicon/romm/library",
            "/mnt/disk0/lexicon/romm/resources",
            "/mnt/disk0/lexicon/romm/assets",
            "/mnt/disk0/lexicon/romm/config",
            "/mnt/disk0/lexicon/romm/redis",
            "/mnt/disk0/lexicon/romm/db",
        ],
        "headway":        [
            "/mnt/disk0/lexicon/headway/data",
        ],
        "exodos":         [
            # collection/ is where you extract the full eXoDOS v6 download
            "/mnt/disk0/lexicon/exodos/collection",
            "/mnt/disk0/lexicon/exodos/collection/Data/Platforms",
            "/mnt/disk0/lexicon/exodos/collection/eXo/eXoDOS",
            "/mnt/disk0/lexicon/exodos/collection/Images/MS-DOS",
            "/mnt/disk0/lexicon/exodos/collection/Manuals",
            "/mnt/disk0/lexicon/exodos/collection/Videos",
            # cache/ is written by the webapp at runtime
            "/mnt/disk0/lexicon/exodos/cache",
        ],
    }
    for key, enabled in config.singleton_enabled.items():
        if enabled and key in singleton_dir_map:
            dirs.update(singleton_dir_map[key])

    # Sort dirs for readability
    sorted_dirs = sorted(dirs)
    mkdir_lines = "\n".join(f'  mkdir -p "{d}"' for d in sorted_dirs)

    # ── Snapcast named pipe setup (only if snapserver or music_assistant) ─────
    needs_snapcast = (
        config.singleton_enabled.get("snapserver", False) or
        config.singleton_enabled.get("music_assistant", False)
    )
    snapcast_block = ""
    if needs_snapcast:
        snapcast_block = """
# ── Snapcast named pipes ──────────────────────────────────────────────────────
section "Setting up Snapcast named pipes"
for PIPE in /opt/snapcast/snapfifo /opt/snapcast/mopidy-snapfifo /opt/snapcast/mopidy_snapfifo; do
  if [ ! -p "$PIPE" ]; then
    mkfifo "$PIPE"
    log "Created pipe: $PIPE"
  else
    log "Pipe already exists: $PIPE"
  fi
done
chown -R 1000:1000 /opt/snapcast
"""

    # ── Snapserver default config (only if enabled) ───────────────────────────
    snapserver_conf_block = ""
    if config.singleton_enabled.get("snapserver", False):
        snapserver_conf_block = """
# ── Snapserver default config ─────────────────────────────────────────────────
section "Creating default snapserver config"
SNAP_CONF="/mnt/disk0/lexicon/snapserver/config/snapserver.conf"
if [ ! -f "$SNAP_CONF" ]; then
  cat > "$SNAP_CONF" << 'SNAPEOF'
[server]
threads = -1

[stream]
source = pipe:///tmp/snapfifo?name=default&sampleformat=48000:16:2&codec=flac

[http]
enabled = true
port = 1780

[tcp]
enabled = true
port = 1705
SNAPEOF
  log "Created: $SNAP_CONF"
else
  log "Snapserver config already exists, skipping"
fi
"""

    # ── Mopidy default config (only if enabled) ───────────────────────────────
    mopidy_conf_block = ""
    if config.singleton_enabled.get("mopidy", False):
        mopidy_conf_block = """
# ── Mopidy default config ─────────────────────────────────────────────────────
section "Creating default Mopidy config"
MOPIDY_CONF="/mnt/disk0/lexicon/mopidy/mopidy.conf"
if [ ! -f "$MOPIDY_CONF" ]; then
  cat > "$MOPIDY_CONF" << 'MOPEOF'
[core]
data_dir = /var/lib/mopidy

[logging]
verbosity = 1

[mpd]
enabled = true
port = 6600

[http]
enabled = true
port = 6680
hostname = 0.0.0.0

[audio]
output = audioresample ! audioconvert ! audio/x-raw,rate=48000,channels=2,format=S16LE ! filesink location=/tmp/mopidy_snapfifo

[subidy]
# url = http://your-navidrome-host:port
# username = your_username
# password = your_password
MOPEOF
  log "Created: $MOPIDY_CONF"
else
  log "Mopidy config already exists, skipping"
fi
"""

    # ── Online 3D Viewer footer.tmpl (only if Gitea is enabled) ─────────────
    gitea_o3dv_block = ""
    if config.singleton_enabled.get("gitea", False):
        gitea_o3dv_block = r"""
# ── Gitea: Online 3D Viewer custom template ───────────────────────────────────
section "Installing Online 3D Viewer template for Gitea"

O3DV_TMPL="/mnt/disk0/lexicon/gitea/custom/templates/custom/footer.tmpl"
mkdir -p "$(dirname "$O3DV_TMPL")"

if [ ! -f "$O3DV_TMPL" ]; then
  cat > "$O3DV_TMPL" << 'O3DVEOF'
<script>
function onPageChange() {
  const fileTypes = ['3dm','3ds','3mf','amf','bim','brep','dae','fbx','fcstd',
                     'glb','gltf','ifc','igs','iges','stp','step','stl',
                     'obj','off','ply','wrl'];
  const links = Array.from(document.querySelectorAll('a.ui.mini.basic.button'));
  const link3D = links.find(link => {
    const href = link.href.toLowerCase();
    return href.includes('/raw/') && fileTypes.some(ext => href.endsWith('.' + ext));
  });
  if (link3D) {
    const existingScript = document.querySelector('script[src="/assets/o3dv/o3dv.min.js"]');
    const initializeViewer = () => {
      const fileUrl = link3D.getAttribute('href');
      const fileView = document.querySelector('.file-view');
      if (!fileView) return;
      const oldView3D = document.getElementById('view-3d');
      if (oldView3D) {
        oldView3D.remove();
      } else {
        while (fileView.firstChild) fileView.removeChild(fileView.firstChild);
      }
      const newView3D = document.createElement('div');
      newView3D.id = 'view-3d';
      newView3D.style.cssText = 'width:100%;padding:0;margin:0;';
      const header = document.querySelector('.ui.top.attached.header');
      const headerHeight = header ? header.offsetHeight : 0;
      newView3D.style.height = 'calc(100vh - ' + headerHeight + 'px)';
      fileView.appendChild(newView3D);
      const parentDiv = document.getElementById('view-3d');
      if (parentDiv) {
        const viewer = new OV.EmbeddedViewer(parentDiv, {
          backgroundColor: new OV.RGBAColor(59, 68, 76, 0),
          defaultColor: new OV.RGBColor(200, 200, 200),
          edgeSettings: new OV.EdgeSettings(false, new OV.RGBColor(0, 0, 0), 1),
          environmentSettings: new OV.EnvironmentSettings([
            '/assets/o3dv/envmaps/fishermans_bastion/negx.jpg',
            '/assets/o3dv/envmaps/fishermans_bastion/posx.jpg',
            '/assets/o3dv/envmaps/fishermans_bastion/posy.jpg',
            '/assets/o3dv/envmaps/fishermans_bastion/negy.jpg',
            '/assets/o3dv/envmaps/fishermans_bastion/posz.jpg',
            '/assets/o3dv/envmaps/fishermans_bastion/negz.jpg'
          ], false)
        });
        viewer.LoadModelFromUrlList([fileUrl]);
      }
    };
    if (typeof OV === 'undefined') {
      if (!existingScript) {
        const script = document.createElement('script');
        script.onload = initializeViewer;
        script.src = '/assets/o3dv/o3dv.min.js';
        document.head.appendChild(script);
      } else {
        existingScript.addEventListener('load', initializeViewer);
      }
    } else {
      initializeViewer();
    }
  }
}
document.addEventListener('DOMContentLoaded', () => {
  onPageChange();
  const observer = new MutationObserver(onPageChange);
  observer.observe(document.body, { childList: true, subtree: true });
});
</script>
O3DVEOF
  log "Created Gitea Online 3D Viewer template: $O3DV_TMPL"
  log "Supported formats: STL, OBJ, STEP, IGES, FBX, GLTF, 3MF, IFC, PLY, and more"
else
  log "Gitea 3D Viewer template already exists — skipping"
fi
"""

    # ── Build full script ──────────────────────────────────────────────────────
    script = f"""#!/usr/bin/env bash
# ==============================================================================
#  LEXICON SERVER SETUP SCRIPT
#  Target: Debian 13 (Trixie)
#  Server IP: {ip}
#  Generated by compose-gen
#
#  Run as root or with sudo:
#    sudo bash setup.sh
# ==============================================================================

set -euo pipefail

# ── Colors & helpers ──────────────────────────────────────────────────────────
RED="\\033[1;31m"; GRN="\\033[1;32m"; YEL="\\033[1;33m"
CYN="\\033[0;36m"; RST="\\033[0m"; BLD="\\033[1;37m"

log()     {{ echo -e "${{GRN}}  ✓ ${{RST}}$*"; }}
warn()    {{ echo -e "${{YEL}}  ⚠ ${{RST}}$*"; }}
err()     {{ echo -e "${{RED}}  ✗ ${{RST}}$*" >&2; exit 1; }}
section() {{ echo -e "\\n${{YEL}}── $* ${{RST}}${{CYN}}$(printf '%.0s─' {{1..40}})${{RST}}"; }}

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "This script must be run as root. Try: sudo bash $0"
fi

# ── Detect calling user (for group membership and chown) ─────────────────────
CALLING_USER="${{SUDO_USER:-$(whoami)}}"
CALLING_UID=1000
CALLING_GID=1000
if id "$CALLING_USER" &>/dev/null; then
  CALLING_UID=$(id -u "$CALLING_USER")
  CALLING_GID=$(id -g "$CALLING_USER")
fi
log "Running setup for user: $CALLING_USER (UID=$CALLING_UID GID=$CALLING_GID)"

echo ""
echo -e "${{BLD}}============================================================${{RST}}"
echo -e "${{BLD}}       LEXICON SERVER BOOTSTRAP — Debian 13 (Trixie)${{RST}}"
echo -e "${{BLD}}============================================================${{RST}}"
echo ""

# ==============================================================================
# 1. SYSTEM UPDATE & BASE PACKAGES
# ==============================================================================
section "System update and base packages"

apt-get update -qq
apt-get upgrade -y -qq
log "System updated"

apt-get install -y -qq \\
  apt-transport-https \\
  ca-certificates \\
  curl \\
  gnupg \\
  lsb-release \\
  wget \\
  git \\
  jq \\
  htop \\
  iotop \\
  ncdu \\
  unzip \\
  zip \\
  rsync \\
  net-tools \\
  dnsutils \\
  iputils-ping \\
  nmap \\
  tmux \\
  vim \\
  nano \\
  less \\
  tree \\
  pv \\
  lsof \\
  strace \\
  sysstat \\
  acl \\
  attr \\
  fuse3 \\
  udisks2 \\
  parted \\
  smartmontools \\
  hdparm \\
  nvme-cli \\
  open-iscsi \\
  nfs-common \\
  cifs-utils \\
  software-properties-common
log "Base packages installed"

# ==============================================================================
# 2. DOCKER CE (Official Repo)
# ==============================================================================
section "Installing Docker CE from official repository"

# Remove any old/distro docker packages
for PKG in docker.io docker-doc docker-compose podman-docker containerd runc; do
  apt-get remove -y "$PKG" 2>/dev/null || true
done
log "Removed legacy docker packages (if any)"

# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \\
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
log "Docker GPG key installed"

# Add Docker repo (Debian 13 uses 'trixie')
DEBIAN_CODENAME=$(lsb_release -cs 2>/dev/null || echo "trixie")
echo \\
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \\
  https://download.docker.com/linux/debian ${{DEBIAN_CODENAME}} stable" \\
  > /etc/apt/sources.list.d/docker.list
# Fallback: if trixie isn't in the repo yet, fall back to bookworm
if ! apt-get update -qq 2>&1 | grep -q "docker"; then
  warn "Debian $DEBIAN_CODENAME not found in Docker repo — falling back to bookworm"
  echo \\
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \\
    https://download.docker.com/linux/debian bookworm stable" \\
    > /etc/apt/sources.list.d/docker.list
fi
apt-get update -qq
log "Docker APT repository configured"

apt-get install -y -qq \\
  docker-ce \\
  docker-ce-cli \\
  containerd.io \\
  docker-buildx-plugin \\
  docker-compose-plugin
log "Docker CE and Compose plugin installed"

# Enable and start Docker
systemctl enable --now docker
log "Docker service enabled and started"

# ── Docker group membership ───────────────────────────────────────────────────
if ! groups "$CALLING_USER" | grep -q docker; then
  usermod -aG docker "$CALLING_USER"
  log "Added $CALLING_USER to docker group (re-login to take effect)"
else
  log "$CALLING_USER already in docker group"
fi

# ── Verify ────────────────────────────────────────────────────────────────────
DOCKER_VER=$(docker --version 2>/dev/null || echo "unknown")
COMPOSE_VER=$(docker compose version 2>/dev/null || echo "unknown")
log "Docker version: $DOCKER_VER"
log "Compose version: $COMPOSE_VER"

# ==============================================================================
# 3. OPTIONAL: GPU / HARDWARE TRANSCODING SUPPORT
# ==============================================================================
section "Hardware support packages"

# Intel VA-API (Jellyfin hardware transcoding)
if lspci 2>/dev/null | grep -qi "intel.*vga\\|intel.*display"; then
  apt-get install -y -qq \\
    intel-media-va-driver-non-free \\
    vainfo \\
    i965-va-driver 2>/dev/null || \\
  apt-get install -y -qq vainfo 2>/dev/null || true
  log "Intel VA-API drivers installed"
fi

# Mesa / AMD VA-API
if lspci 2>/dev/null | grep -qi "amd.*vga\\|radeon"; then
  apt-get install -y -qq \\
    mesa-va-drivers \\
    vainfo 2>/dev/null || true
  log "AMD/Mesa VA-API drivers installed"
fi

# DVB tuner support (TVHeadend)
if lsusb 2>/dev/null | grep -qi "dvb\\|tuner" || ls /dev/dvb &>/dev/null 2>&1; then
  apt-get install -y -qq \\
    dvb-tools \\
    v4l-utils 2>/dev/null || true
  log "DVB tools installed"
fi

# ==============================================================================
# 4. DOCKER DAEMON CONFIGURATION
# ==============================================================================
section "Configuring Docker daemon"

DOCKER_DAEMON_JSON=/etc/docker/daemon.json
if [ ! -f "$DOCKER_DAEMON_JSON" ]; then
  mkdir -p /etc/docker
  cat > "$DOCKER_DAEMON_JSON" << 'DAEMONEOF'
{{
  "log-driver": "json-file",
  "log-opts": {{
    "max-size": "20m",
    "max-file": "5"
  }},
  "storage-driver": "overlay2",
  "live-restore": true,
  "userland-proxy": false
}}
DAEMONEOF
  log "Docker daemon config written to $DOCKER_DAEMON_JSON"
  systemctl reload docker || systemctl restart docker
else
  warn "Docker daemon.json already exists — skipping (edit manually if needed)"
fi

# ==============================================================================
# 5. STORAGE — Mount point check
# ==============================================================================
section "Checking /mnt/disk0 mount point"

if mountpoint -q /mnt/disk0 2>/dev/null; then
  log "/mnt/disk0 is already a mount point"
elif [ -d /mnt/disk0 ]; then
  warn "/mnt/disk0 exists but is NOT a separate mount — using as local dir"
else
  mkdir -p /mnt/disk0
  warn "/mnt/disk0 created as local directory — attach and mount your disk if needed"
  echo ""
  echo -e "  ${{YEL}}To mount a disk, add to /etc/fstab, e.g.:${{RST}}"
  echo -e "  ${{CYN}}  UUID=<your-uuid>  /mnt/disk0  ext4  defaults,nofail  0  2${{RST}}"
  echo -e "  Then run: ${{CYN}}mount -a${{RST}}"
fi

# ==============================================================================
# 6. DIRECTORY TREE
# ==============================================================================
section "Creating Lexicon data directory tree"

{mkdir_lines}

log "All data directories created"

# ── Permissions ───────────────────────────────────────────────────────────────
section "Setting ownership on /mnt/disk0/lexicon"
chown -R "$CALLING_UID:$CALLING_GID" /mnt/disk0/lexicon
chmod -R u=rwX,g=rX,o= /mnt/disk0/lexicon
# Postgres dirs need to be owned by 999 (postgres container user)
for PGDIR in $(find /mnt/disk0/lexicon -type d -name postgres 2>/dev/null); do
  chown -R 999:999 "$PGDIR"
  log "Set postgres ownership on: $PGDIR"
done
log "Permissions set"
{snapcast_block}{snapserver_conf_block}{mopidy_conf_block}{gitea_o3dv_block}
# ==============================================================================
# 7. FIREWALL (ufw) — Optional
# ==============================================================================
section "Firewall setup (ufw)"

if command -v ufw &>/dev/null; then
  warn "ufw detected — skipping auto-configure (manage manually)"
  echo -e "  Ports to allow:"
  echo -e "  ${{CYN}}  ufw allow 22/tcp       # SSH${{RST}}"
  echo -e "  ${{CYN}}  ufw allow 8080/tcp     # Dashboard${{RST}}"
  echo -e "  ${{CYN}}  ufw allow 8100:8700/tcp# Service range${{RST}}"
else
  apt-get install -y -qq ufw
  ufw --force reset
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow ssh
  ufw allow 8080/tcp   comment "Lexicon Dashboard"
  ufw allow 8100:8700/tcp comment "Lexicon Services"
  # Snapcast ports (if applicable)
  ufw allow 1704/tcp   comment "Snapcast audio"
  ufw allow 1705/tcp   comment "Snapcast control"
  ufw allow 1780/tcp   comment "Snapcast HTTP"
  ufw --force enable
  log "ufw configured and enabled"
fi

# ==============================================================================
# 8. SYSCTL TUNING (recommended for Solr / heavy Java services)
# ==============================================================================
section "Applying sysctl tuning"

SYSCTL_CONF=/etc/sysctl.d/99-lexicon.conf
cat > "$SYSCTL_CONF" << 'SYSCTLEOF'
# Lexicon server tuning
vm.max_map_count = 262144
vm.swappiness = 10
net.core.somaxconn = 65535
net.ipv4.tcp_tw_reuse = 1
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 512
SYSCTLEOF
sysctl -p "$SYSCTL_CONF" >/dev/null 2>&1 || true
log "sysctl tuning applied (vm.max_map_count=262144 for Solr/ES)"

# ==============================================================================
# 9. LOGROTATE FOR DOCKER
# ==============================================================================
section "Configuring logrotate for Docker"

cat > /etc/logrotate.d/docker-containers << 'LOGEOF'
/var/lib/docker/containers/*/*.log {{
  rotate 7
  daily
  compress
  missingok
  delaycompress
  copytruncate
}}
LOGEOF
log "Docker log rotation configured"

# ==============================================================================
# 10. DOCKER SYSTEM PRUNE CRON
# ==============================================================================
section "Adding weekly Docker cleanup cron"

CRON_FILE=/etc/cron.weekly/docker-cleanup
cat > "$CRON_FILE" << 'CRONEOF'
#!/bin/bash
# Weekly Docker cleanup — removes unused images, volumes, networks
docker system prune -f --filter "until=168h" >> /var/log/docker-cleanup.log 2>&1
docker volume prune -f >> /var/log/docker-cleanup.log 2>&1
CRONEOF
chmod +x "$CRON_FILE"
log "Weekly Docker cleanup cron installed"

# ==============================================================================
# 11. EXODOS COLLECTION NOTE
# ==============================================================================
if [ -d /mnt/disk0/lexicon/exodos/collection ]; then
  if [ -f /mnt/disk0/lexicon/exodos/collection/Data/Platforms/MS-DOS.xml ]; then
    GAME_COUNT=$(grep -c "<Title>" /mnt/disk0/lexicon/exodos/collection/Data/Platforms/MS-DOS.xml 2>/dev/null || echo "?")
    log "eXoDOS collection found — $GAME_COUNT game entries in XML"
  else
    warn "eXoDOS collection directory exists but MS-DOS.xml not found"
    echo -e "  ${{YEL}}To populate it, extract the eXoDOS v6 torrent into:${{RST}}"
    echo -e "  ${{CYN}}  /mnt/disk0/lexicon/exodos/collection/${{RST}}"
    echo -e "  ${{CYN}}  https://www.retro-exo.com/exodos.html${{RST}}"
  fi
fi

# ==============================================================================
# DONE
# ==============================================================================
echo ""
echo -e "${{GRN}}============================================================${{RST}}"
echo -e "${{GRN}}  Setup complete!${{RST}}"
echo -e "${{GRN}}============================================================${{RST}}"
echo ""
echo -e "  ${{BLD}}Next steps:${{RST}}"
echo -e "  1. ${{CYN}}Log out and back in${{RST}} (or run ${{CYN}}newgrp docker${{RST}}) so your user"
echo -e "     can run Docker without sudo."
echo -e ""
echo -e "  2. Copy the dashboard files to the server:"
echo -e "     ${{CYN}}cp -r dashboard/ /mnt/disk0/lexicon/dashboard/${{RST}}"
echo -e ""
echo -e "  3. Deploy the stack:"
echo -e "     ${{CYN}}docker compose up -d${{RST}}"
echo -e ""
echo -e "  4. Visit your dashboard:"
echo -e "     ${{CYN}}http://{ip}:8080${{RST}}"
echo ""
"""
    return script


# ==============================================================================
# FILE GENERATION
# ==============================================================================

_EXODOS_DOCKERFILE = """\
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && \\
    apt-get install -y -qq --no-install-recommends \\
        dosbox \\
        libxml2-dev \\
        libxslt-dev && \\
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV EXODOS_ROOT=/exodos
ENV FLASK_ENV=production
ENV CACHE_DIR=/app/cache

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
"""

_EXODOS_REQUIREMENTS = """\
flask>=3.0
gunicorn>=21.0
lxml>=5.0
Pillow>=10.0
"""

_EXODOS_APP_PY = """\
\"\"\"
eXoDOS Web Player
-----------------
Reads the eXoDOS LaunchBox XML metadata and serves a searchable game browser
with in-browser DOSBox playback via js-dos v8 (WebAssembly).

Expected volume layout (read-only mount at /exodos):
  /exodos/
    Data/Platforms/MS-DOS.xml        LaunchBox game metadata XML
    eXo/eXoDOS/<GameFolder>/         Per-game zip / bat files
    Images/MS-DOS/Box - Front/       Box art PNGs
    Images/MS-DOS/Screenshot - Gameplay/
    Images/MS-DOS/Screenshot - Game Title/
\"\"\"

import os
import re
import json
import hashlib
import logging
from pathlib import Path
from functools import lru_cache
from xml.etree import ElementTree as ET
from flask import (
    Flask, render_template, jsonify, request,
    send_file, abort, Response,
)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

EXODOS_ROOT = Path(os.environ.get("EXODOS_ROOT", "/exodos"))
CACHE_DIR   = Path(os.environ.get("CACHE_DIR",   "/app/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

XML_CANDIDATES = [
    EXODOS_ROOT / "Data" / "Platforms" / "MS-DOS.xml",
    EXODOS_ROOT / "xml" / "MS-DOS.xml",
]

IMAGE_SUBDIRS = {
    "front":    ["Box - Front", "Box - 3D"],
    "title":    ["Screenshot - Game Title"],
    "gameplay": ["Screenshot - Gameplay"],
    "banner":   ["Banner"],
}

PLACEHOLDER_SVG_TPL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="280">'
    '<rect width="200" height="280" fill="#1a1f2e"/>'
    '<text x="100" y="130" font-family="monospace" font-size="11" fill="#44aaff"'
    ' text-anchor="middle">{title}</text>'
    '<text x="100" y="155" font-family="monospace" font-size="10" fill="#555"'
    ' text-anchor="middle">No Image</text>'
    '</svg>'
)

# ---------------------------------------------------------------------------

def find_xml():
    for p in XML_CANDIDATES:
        if p.exists():
            return p
    search = EXODOS_ROOT / "Data" / "Platforms"
    if search.exists():
        hits = list(search.glob("*.xml"))
        if hits:
            return hits[0]
    return None


@lru_cache(maxsize=1)
def load_games():
    xml_path = find_xml()
    if not xml_path:
        log.warning("No LaunchBox XML found under %s", EXODOS_ROOT)
        return []
    log.info("Parsing %s …", xml_path)
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as exc:
        log.error("XML parse error: %s", exc)
        return []

    games = []
    for game_el in root.iter("Game"):
        def g(tag, default=""):
            el = game_el.find(tag)
            return (el.text or "").strip() if (el is not None and el.text) else default

        title = g("Title")
        if not title:
            continue

        app_path  = g("ApplicationPath")
        year_raw  = g("ReleaseYear") or g("ReleaseDate", "")
        year      = year_raw[:4] if year_raw else ""
        genres_raw= g("Genre")
        genres    = [x.strip() for x in genres_raw.split(";") if x.strip()]
        overview  = (g("Notes") or g("Description"))[:600]
        game_id   = hashlib.md5(title.encode()).hexdigest()[:12]

        games.append({
            "id":        game_id,
            "title":     title,
            "app_path":  app_path,
            "genres":    genres,
            "year":      year,
            "overview":  overview,
            "developer": g("Developer"),
            "publisher": g("Publisher"),
            "players":   g("MaxPlayers", "1"),
            "series":    g("Series"),
        })

    games.sort(key=lambda x: re.sub(r"^(the |a |an )", "", x["title"].lower()))
    log.info("Loaded %d games", len(games))
    return games


def all_genres():
    s = set()
    for gm in load_games():
        s.update(gm["genres"])
    return sorted(x for x in s if x)


def all_years():
    return sorted({gm["year"] for gm in load_games() if gm["year"]}, reverse=True)


def find_image(title, img_type="front"):
    safe  = re.sub(r'[<>:"/\\\\|?*]', "", title)
    base  = EXODOS_ROOT / "Images" / "MS-DOS"
    subdirs = IMAGE_SUBDIRS.get(img_type, IMAGE_SUBDIRS["front"])
    for sd in subdirs:
        folder = base / sd
        if not folder.exists():
            continue
        for ext in (".png", ".jpg", ".jpeg"):
            exact = folder / (safe + ext)
            if exact.exists():
                return exact
            hits = list(folder.glob(safe + "*" + ext))
            if hits:
                return hits[0]
    return None


def find_game_zip(app_path):
    if not app_path:
        return None
    rel   = Path(app_path.replace("\\\\", "/").replace("\\", "/"))
    parts = [p for p in rel.parts if p not in ("..", ".")]
    if not parts:
        return None

    candidate = EXODOS_ROOT
    for part in parts:
        nxt = candidate / part
        if not nxt.exists():
            if candidate.exists():
                low = part.lower()
                found = next(
                    (m for m in candidate.iterdir() if m.name.lower() == low),
                    None,
                )
                if found:
                    nxt = found
                else:
                    break
        candidate = nxt

    if candidate.exists() and candidate.suffix.lower() == ".bat":
        folder = candidate.parent
        # Same-stem zip
        zp = folder / (candidate.stem + ".zip")
        if zp.exists():
            return zp
        # Parent-level zip named after the folder
        pz = folder.parent / (folder.name + ".zip")
        if pz.exists():
            return pz
        # Any zip in folder
        zips = list(folder.glob("*.zip"))
        if zips:
            return zips[0]
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/games")
def api_games():
    page     = max(1, int(request.args.get("page",     1)))
    per_page = min(120, int(request.args.get("per_page", 60)))
    q        = request.args.get("q",     "").strip().lower()
    genre    = request.args.get("genre", "").strip()
    year     = request.args.get("year",  "").strip()

    games = load_games()
    if q:
        games = [gm for gm in games
                 if q in gm["title"].lower()
                 or q in gm["developer"].lower()
                 or q in gm["overview"].lower()]
    if genre:
        games = [gm for gm in games if genre in gm["genres"]]
    if year:
        games = [gm for gm in games if gm["year"].startswith(year)]

    total  = len(games)
    start  = (page - 1) * per_page
    return jsonify({
        "total": total,
        "page":  page,
        "pages": (total + per_page - 1) // per_page if total else 1,
        "games": games[start:start + per_page],
    })


@app.route("/api/genres")
def api_genres():
    return jsonify(all_genres())


@app.route("/api/years")
def api_years():
    return jsonify(all_years())


@app.route("/api/game/<game_id>")
def api_game(game_id):
    gm = next((g for g in load_games() if g["id"] == game_id), None)
    if not gm:
        abort(404)
    return jsonify(gm)


@app.route("/image/<game_id>")
@app.route("/image/<game_id>/<img_type>")
def game_image(game_id, img_type="front"):
    gm = next((g for g in load_games() if g["id"] == game_id), None)
    if not gm:
        abort(404)
    img = find_image(gm["title"], img_type)
    if not img:
        safe_title = gm["title"][:24].replace("<", "").replace(">", "").replace("&", "&amp;")
        svg = PLACEHOLDER_SVG_TPL.format(title=safe_title)
        return Response(svg, mimetype="image/svg+xml")
    return send_file(img)


@app.route("/play/<game_id>")
def play_game(game_id):
    gm = next((g for g in load_games() if g["id"] == game_id), None)
    if not gm:
        abort(404)
    zip_path = find_game_zip(gm["app_path"])
    return render_template("play.html", game=gm, has_zip=(zip_path is not None))


@app.route("/game-zip/<game_id>")
def game_zip(game_id):
    gm = next((g for g in load_games() if g["id"] == game_id), None)
    if not gm:
        abort(404)
    zp = find_game_zip(gm["app_path"])
    if not zp:
        abort(404)
    return send_file(zp, mimetype="application/zip",
                     download_name=game_id + ".zip")


@app.route("/api/status")
def api_status():
    xml_path = find_xml()
    games    = load_games()
    return jsonify({
        "xml_found":  xml_path is not None,
        "xml_path":   str(xml_path) if xml_path else None,
        "game_count": len(games),
        "root":       str(EXODOS_ROOT),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
"""

_EXODOS_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>eXoDOS Web Player</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Oxanium:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#060a0f;--surf:#0d1117;--bord:#1c2333;--glow:#00ff88;--glow2:#00aaff;--text:#c9d1d9;--muted:#484f58;--card:#0d1520}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Oxanium',sans-serif;min-height:100vh}
header{background:var(--surf);border-bottom:1px solid var(--bord);padding:.8rem 2rem;display:flex;align-items:center;gap:1rem;position:sticky;top:0;z-index:100}
.logo{font-size:1.6rem;font-weight:800;color:#fff}.logo span{color:var(--glow)}
.badge{font-family:'Share Tech Mono',monospace;font-size:.65rem;color:var(--glow);border:1px solid var(--glow);padding:.2rem .5rem;border-radius:3px;opacity:.7}
.search-wrap{flex:1;max-width:420px;background:var(--bg);border:1px solid var(--bord);border-radius:6px;display:flex;align-items:center;padding:0 .75rem;gap:.4rem}
.search-wrap input{background:none;border:none;outline:none;color:var(--text);font-family:'Oxanium',sans-serif;font-size:.9rem;width:100%;padding:.5rem 0}
.search-wrap input::placeholder{color:var(--muted)}
.stat{margin-left:auto;font-family:'Share Tech Mono',monospace;font-size:.72rem;color:var(--muted)}
.filters{background:var(--surf);border-bottom:1px solid var(--bord);padding:.55rem 2rem;display:flex;gap:.75rem;flex-wrap:wrap;align-items:center}
.filters select,.filters button{background:var(--bg);border:1px solid var(--bord);color:var(--text);font-family:'Oxanium',sans-serif;font-size:.8rem;padding:.3rem .7rem;border-radius:5px;cursor:pointer;transition:border-color .15s}
.filters select:hover,.filters select:focus,.filters button:hover{border-color:var(--glow2);outline:none;color:#fff}
main{padding:1.5rem 2rem;max-width:1800px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:.9rem}
.card{background:var(--card);border:1px solid var(--bord);border-radius:8px;overflow:hidden;cursor:pointer;transition:transform .12s,border-color .12s,box-shadow .12s;text-decoration:none;display:block;color:inherit}
.card:hover{transform:translateY(-3px);border-color:var(--glow2);box-shadow:0 0 18px rgba(0,170,255,.15)}
.card img{width:100%;aspect-ratio:5/7;object-fit:cover;display:block;background:#0a0c12}
.card-body{padding:.55rem .65rem}
.card-title{font-size:.76rem;font-weight:700;color:#e6edf3;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-year{font-family:'Share Tech Mono',monospace;font-size:.62rem;color:var(--muted);margin-top:.25rem}
.card-genre{font-size:.6rem;color:var(--glow2);margin-top:.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pager{display:flex;justify-content:center;gap:.4rem;margin-top:2rem;padding-bottom:2rem;flex-wrap:wrap}
.pager button{background:var(--surf);border:1px solid var(--bord);color:var(--text);font-family:'Share Tech Mono',monospace;font-size:.78rem;padding:.35rem .75rem;border-radius:5px;cursor:pointer;transition:border-color .1s}
.pager button:hover,.pager button.active{border-color:var(--glow);color:var(--glow)}
.pager button:disabled{opacity:.3;cursor:default}
.msg{text-align:center;padding:4rem;font-family:'Share Tech Mono',monospace;color:var(--glow);font-size:.9rem}
.empty{text-align:center;padding:4rem;color:var(--muted)}.empty h2{color:#fff;margin-bottom:.5rem}
</style>
</head>
<body>
<header>
  <div class="logo">eXo<span>DOS</span></div>
  <div class="badge" id="badge">…</div>
  <div class="search-wrap">
    <span style="color:var(--muted)">&#9906;</span>
    <input id="q" type="text" placeholder="Search games, developers…" autocomplete="off">
  </div>
  <div class="stat" id="stat"></div>
</header>
<div class="filters">
  <select id="genre"><option value="">All Genres</option></select>
  <select id="year"><option value="">All Years</option></select>
  <button id="reset">Reset</button>
</div>
<main>
  <div class="grid" id="grid"><div class="msg">Loading game library…</div></div>
  <div class="pager" id="pager"></div>
</main>
<script>
const st={page:1,pp:60,q:'',genre:'',year:'',total:0,pages:0};
async function loadFilters(){
  const[gr,yr]=await Promise.all([fetch('/api/genres').then(r=>r.json()),fetch('/api/years').then(r=>r.json())]);
  const gs=document.getElementById('genre');
  gr.forEach(g=>{const o=document.createElement('option');o.value=g;o.textContent=g;gs.appendChild(o);});
  const ys=document.getElementById('year');
  yr.forEach(y=>{const o=document.createElement('option');o.value=y;o.textContent=y;ys.appendChild(o);});
}
async function load(){
  document.getElementById('grid').innerHTML='<div class="msg">Loading…</div>';
  const p=new URLSearchParams({page:st.page,per_page:st.pp,q:st.q,genre:st.genre,year:st.year});
  const d=await fetch('/api/games?'+p).then(r=>r.json());
  st.total=d.total;st.pages=d.pages;
  document.getElementById('badge').textContent=d.total.toLocaleString()+' games';
  document.getElementById('stat').textContent=d.total.toLocaleString()+' results — p'+st.page+'/'+st.pages;
  if(!d.games.length){
    document.getElementById('grid').innerHTML='<div class="empty"><h2>No games found</h2><p>Try adjusting filters</p></div>';
  } else {
    document.getElementById('grid').innerHTML=d.games.map(g=>`
      <a class="card" href="/play/${g.id}">
        <img src="/image/${g.id}" alt="${g.title.replace(/"/g,'')}" loading="lazy">
        <div class="card-body">
          <div class="card-title">${g.title}</div>
          <div class="card-year">${g.year||'—'}</div>
          ${g.genres[0]?`<div class="card-genre">${g.genres[0]}</div>`:''}
        </div>
      </a>`).join('');
  }
  renderPager();
  window.scrollTo({top:0,behavior:'smooth'});
}
function renderPager(){
  const el=document.getElementById('pager');el.innerHTML='';
  if(st.pages<=1)return;
  const btn=(lbl,pg,dis,act)=>{
    const b=document.createElement('button');b.textContent=lbl;b.disabled=!!dis;
    if(act)b.classList.add('active');
    if(!dis)b.onclick=()=>{st.page=pg;load();};
    el.appendChild(b);
  };
  btn('«',1,st.page===1);btn('‹',st.page-1,st.page===1);
  const s=Math.max(1,st.page-3),e=Math.min(st.pages,st.page+3);
  for(let i=s;i<=e;i++)btn(i,i,false,i===st.page);
  btn('›',st.page+1,st.page===st.pages);btn('»',st.pages,st.page===st.pages);
}
let t;
document.getElementById('q').addEventListener('input',e=>{clearTimeout(t);t=setTimeout(()=>{st.q=e.target.value;st.page=1;load();},320);});
document.getElementById('genre').addEventListener('change',e=>{st.genre=e.target.value;st.page=1;load();});
document.getElementById('year').addEventListener('change',e=>{st.year=e.target.value;st.page=1;load();});
document.getElementById('reset').addEventListener('click',()=>{
  st.q=st.genre=st.year='';st.page=1;
  document.getElementById('q').value='';
  document.getElementById('genre').value='';
  document.getElementById('year').value='';
  load();
});
loadFilters();load();
</script>
</body>
</html>
"""

_EXODOS_PLAY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ game.title }} — eXoDOS</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Oxanium:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://v8.js-dos.com/latest/js-dos.css">
<script src="https://v8.js-dos.com/latest/js-dos.js"></script>
<style>
:root{--bg:#060a0f;--surf:#0d1117;--bord:#1c2333;--glow:#00ff88;--glow2:#00aaff;--text:#c9d1d9;--muted:#484f58}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Oxanium',sans-serif;min-height:100vh}
header{background:var(--surf);border-bottom:1px solid var(--bord);padding:.8rem 2rem;display:flex;align-items:center;gap:1rem}
a.back{color:var(--glow2);text-decoration:none;font-size:.9rem}
a.back:hover{color:var(--glow)}
.htitle{font-size:1.05rem;font-weight:700;color:#fff}
.layout{display:grid;grid-template-columns:1fr 340px;gap:2rem;padding:2rem;max-width:1400px;margin:0 auto}
@media(max-width:860px){.layout{grid-template-columns:1fr}}
#dos{width:100%;aspect-ratio:4/3;background:#000;border:1px solid var(--bord);border-radius:8px;overflow:hidden}
.panel{display:flex;flex-direction:column;gap:1.25rem}
.cover{border:1px solid var(--bord);border-radius:8px;overflow:hidden}
.cover img{width:100%;display:block}
.meta,.about,.keys{background:var(--surf);border:1px solid var(--bord);border-radius:8px;padding:1.1rem}
.meta h2{font-size:1.1rem;color:#fff;margin-bottom:.9rem}
.row{display:flex;gap:.6rem;margin-bottom:.5rem;font-size:.82rem}
.lbl{color:var(--muted);font-family:'Share Tech Mono',monospace;min-width:76px;flex-shrink:0}
.about h3,.keys h3{font-family:'Share Tech Mono',monospace;font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:.6rem}
.about p{font-size:.83rem;line-height:1.7}
.keys p{font-family:'Share Tech Mono',monospace;font-size:.7rem;line-height:2;color:var(--muted)}
.keys strong{color:var(--text)}
.nozip{background:#1a0d0d;border:1px solid #5a2020;border-radius:8px;padding:1.25rem;color:#e08080;font-size:.84rem;line-height:1.7}
.nozip strong{display:block;color:#ff6b6b;margin-bottom:.5rem;font-size:.95rem}
.nozip code{font-size:.7rem;color:#aaa;word-break:break-all}
</style>
</head>
<body>
<header>
  <a class="back" href="/">&#8592; Library</a>
  <span class="htitle">{{ game.title }}</span>
</header>
<div class="layout">
  <div>
    {% if has_zip %}
    <div id="dos"></div>
    <script>
    window.addEventListener('load',()=>{
      Dos(document.getElementById('dos'),{
        url:'/game-zip/{{ game.id }}',
        autoStart:true,
      });
    });
    </script>
    {% else %}
    <div class="nozip" style="aspect-ratio:4/3;display:flex;flex-direction:column;justify-content:center">
      <strong>Game file not found</strong>
      The zip for <em>{{ game.title }}</em> could not be located in the mounted eXoDOS collection.<br><br>
      Make sure the collection is mounted at <code>/exodos</code> and that this game is part of it.<br><br>
      Metadata path: <code>{{ game.app_path }}</code>
    </div>
    {% endif %}
  </div>
  <div class="panel">
    <div class="cover">
      <img src="/image/{{ game.id }}/front" alt="{{ game.title }}">
    </div>
    <div class="meta">
      <h2>{{ game.title }}</h2>
      {% if game.year %}<div class="row"><span class="lbl">Year</span><span>{{ game.year }}</span></div>{% endif %}
      {% if game.developer %}<div class="row"><span class="lbl">Developer</span><span>{{ game.developer }}</span></div>{% endif %}
      {% if game.publisher %}<div class="row"><span class="lbl">Publisher</span><span>{{ game.publisher }}</span></div>{% endif %}
      {% if game.players %}<div class="row"><span class="lbl">Players</span><span>{{ game.players }}</span></div>{% endif %}
      {% if game.genres %}<div class="row"><span class="lbl">Genre</span><span>{{ game.genres|join(', ') }}</span></div>{% endif %}
    </div>
    {% if game.overview %}
    <div class="about"><h3>About</h3><p>{{ game.overview }}</p></div>
    {% endif %}
    <div class="keys">
      <h3>Controls</h3>
      <p>
        <strong>F11</strong> toggle fullscreen<br>
        <strong>Ctrl+F10</strong> capture / release mouse<br>
        <strong>Alt+Enter</strong> fullscreen (DOSBox)<br>
        <strong>Ctrl+Alt+F7</strong> screenshot
      </p>
    </div>
  </div>
</div>
</body>
</html>
"""

_EXODOS_README = """\
# eXoDOS Web Player

Browser-based frontend for the eXoDOS DOS game preservation collection.

## Requirements

Mount your eXoDOS collection at `/mnt/disk0/lexicon/exodos/collection/`

The directory must contain:
- `Data/Platforms/MS-DOS.xml`  — LaunchBox game metadata
- `eXo/eXoDOS/`                — per-game folder/zip/bat files
- `Images/MS-DOS/`             — box art and screenshots

## Building & running

    docker compose up -d exodos

Then open:  http://<server-ip>:8700

## How it works

- The Flask app parses the LaunchBox XML on first request and caches it in memory.
- Box art is served directly from the `Images/` tree.
- Clicking a game opens the play page, which loads the game's zip into
  js-dos v8 (DOSBox compiled to WebAssembly) running in the browser.
- The eXoDOS collection is mounted **read-only**; nothing is ever written to it.

## Notes

- Restart the container to re-scan after adding games.
- Cache files (thumbnails etc.) are stored in `/mnt/disk0/lexicon/exodos/cache/`.
- js-dos runs DOSBox entirely in the browser via WebAssembly — no server-side
  emulation is needed beyond serving the zip file.
"""


def gen_exodos_webapp():
    """Write the eXoDOS web player build context into exodos-web/."""
    os.makedirs("exodos-web/templates", exist_ok=True)

    with open("exodos-web/Dockerfile",                "w") as f: f.write(_EXODOS_DOCKERFILE)
    with open("exodos-web/requirements.txt",          "w") as f: f.write(_EXODOS_REQUIREMENTS)
    with open("exodos-web/app.py",                    "w") as f: f.write(_EXODOS_APP_PY)
    with open("exodos-web/templates/index.html",      "w") as f: f.write(_EXODOS_INDEX_HTML)
    with open("exodos-web/templates/play.html",       "w") as f: f.write(_EXODOS_PLAY_HTML)
    with open("exodos-web/README.md",                 "w") as f: f.write(_EXODOS_README)

# ==============================================================================

def generate_files(config):
    clear()
    header()
    section("Generating Files")
    print()

    ip = config.ip
    allocate_ports(config)
    pm = config.port_map

    # Create and switch into the output subfolder
    out = OUTPUT_DIR
    os.makedirs(out, exist_ok=True)
    orig_cwd = os.getcwd()
    os.chdir(out)

    compose_parts = []
    dashboard_services = []

    # ── Header ──────────────────────────────────────────────────────────────
    compose_parts.append(f"""version: '3.8'

# ==============================================================================
# GENERATED DOCKER COMPOSE
# Server IP: {ip}
# Generated by compose-gen
# ==============================================================================

networks:
  app-network:
    driver: bridge

services:
""")

    # ── Dashboard ────────────────────────────────────────────────────────────
    compose_parts.append(gen_dashboard_service(ip))
    info("Added: Dashboard (port 8080)")

    # ── Multi-instance services ───────────────────────────────────────────────
    for key, names in config.multi_instances.items():
        for name in names:
            port = pm.get((key, name), 9999)

            if key == "jellyfin":
                compose_parts.append(gen_jellyfin(name, ip, port))
            elif key == "photoprism":
                compose_parts.append(gen_photoprism(name, ip, port))
            elif key == "kavita":
                compose_parts.append(gen_kavita(name, ip, port))
            elif key == "navidrome":
                compose_parts.append(gen_navidrome(name, ip, port))
            elif key == "manyfold":
                db_port = pm.get(("manyfold_db", name), 9998)
                solr_cores = []
                compose_parts.append(gen_manyfold(name, ip, port, db_port, solr_cores))
            elif key == "webtop":
                flavor = getattr(config, "webtop_flavors", {}).get(name, "ubuntu-kde")
                password = getattr(config, "webtop_passwords", {}).get(name, None)
                compose_parts.append(gen_webtop(name, ip, port, flavor, password))

            svc = MULTI_SERVICES[key]
            dashboard_services.append({
                "name": f"{svc['label'].split('(')[0].strip()} ({name})",
                "icon": svc["icon"],
                "category": svc["category"],
                "description": svc["description"],
                "port": port,
            })
            info(f"Added: {key}-{name} → port {port}")

    # ── Singleton services ────────────────────────────────────────────────────
    singletons_with_host_network = {"snapserver", "music_assistant"}

    for key, enabled in config.singleton_enabled.items():
        if not enabled:
            continue
        svc = SINGLETON_SERVICES[key]
        ports = pm.get(key, [])

        if key == "gitea":
            compose_parts.append(gen_gitea(ip, ports[0], ports[1], ports[2]))
            dashboard_services.append({"name": "Gitea", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "opengrok":
            compose_parts.append(gen_opengrok(ip, ports[0]))
            dashboard_services.append({"name": "OpenGrok", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "solr":
            # Collect manyfold cores
            manyfold_cores = [f"manyfold-{n}" for n in config.multi_instances.get("manyfold", [])]
            cores = ["gitea"] + manyfold_cores + (["nextcloud"] if config.singleton_enabled.get("nextcloud") else [])
            compose_parts.append(gen_solr(ip, ports[0], ports[1], ports[2], cores))
            dashboard_services.append({"name": "Solr", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "kiwix":
            compose_parts.append(gen_kiwix(ip, ports[0]))
            dashboard_services.append({"name": "Kiwix", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "nextcloud":
            compose_parts.append(gen_nextcloud(ip, ports[0], ports[1]))
            dashboard_services.append({"name": "Nextcloud", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "audiobookshelf":
            compose_parts.append(gen_audiobookshelf(ip, ports[0]))
            dashboard_services.append({"name": "Audiobookshelf", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "tvheadend":
            compose_parts.append(gen_tvheadend(ip, ports[0], ports[1]))
            dashboard_services.append({"name": "TVHeadend", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "snapserver":
            compose_parts.append(gen_snapserver())
            dashboard_services.append({"name": "Snapcast", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": None})
        elif key == "mopidy":
            compose_parts.append(gen_mopidy(ip, ports[0]))
            dashboard_services.append({"name": "Mopidy", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "music_assistant":
            compose_parts.append(gen_music_assistant())
            dashboard_services.append({"name": "Music Assistant", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": None})
        elif key == "filebot":
            compose_parts.append(gen_filebot())
            # No dashboard link for on-demand tool
        elif key == "romm":
            compose_parts.append(gen_romm(ip, ports[0], ports[2]))
            dashboard_services.append({"name": "RomM", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "headway":
            compose_parts.append(gen_headway(ip, ports[0]))
            dashboard_services.append({"name": "Headway Maps", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})
        elif key == "exodos":
            compose_parts.append(gen_exodos(ip, ports[0]))
            dashboard_services.append({"name": "eXoDOS Web Player", "icon": svc["icon"],
                "category": svc["category"], "description": svc["description"], "port": ports[0]})

        if key not in ("snapserver", "music_assistant", "filebot"):
            info(f"Added: {key} → port {ports[0] if ports else 'host'}")
        else:
            info(f"Added: {key}")

    # Add dashboard to dashboard_services at top
    dashboard_services.insert(0, {
        "name": "Dashboard",
        "icon": "🏠",
        "category": "Navigation",
        "description": "This service index",
        "port": 8080,
    })

    # ── Write docker-compose.yml ──────────────────────────────────────────────
    compose_content = "".join(compose_parts)
    compose_path = "docker-compose.yml"
    with open(compose_path, "w") as f:
        f.write(compose_content)
    success(f"Written: {compose_path}")

    # ── Write dashboard HTML ──────────────────────────────────────────────────
    os.makedirs("dashboard", exist_ok=True)
    html_content = gen_dashboard_html(ip, dashboard_services)
    html_path = os.path.join("dashboard", "index.html")
    with open(html_path, "w") as f:
        f.write(html_content)
    success(f"Written: {html_path}")

    # ── Write nginx config for dashboard ─────────────────────────────────────
    nginx_conf = """server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""
    os.makedirs("dashboard/nginx", exist_ok=True)
    with open("dashboard/nginx/default.conf", "w") as f:
        f.write(nginx_conf)
    success("Written: dashboard/nginx/default.conf")

    # ── Write deploy instructions ─────────────────────────────────────────────
    webtop_names = config.multi_instances.get("webtop", [])
    exodos_on    = config.singleton_enabled.get("exodos", False)

    webtop_note = ""
    if webtop_names:
        webtop_note = """
## Webtop — pre-downloaded data layout
# Each Webtop instance stores all data under /mnt/disk0/lexicon/webtop-<name>/
#   config/    persistent session state (LinuxServer)
#   home/      user desktop / home folder
#   downloads/ browser and file downloads
#   documents/ documents folder
#   shared/    shared folder accessible from host and other containers
"""

    exodos_note = ""
    if exodos_on:
        exodos_note = """
## eXoDOS — pre-downloaded collection layout
# Download the full eXoDOS v6 collection from: https://www.retro-exo.com/exodos.html
# Extract it so the following paths exist:
#   /mnt/disk0/lexicon/exodos/collection/Data/Platforms/MS-DOS.xml
#   /mnt/disk0/lexicon/exodos/collection/eXo/eXoDOS/<GameFolder>/
#   /mnt/disk0/lexicon/exodos/collection/Images/MS-DOS/Box - Front/
# The cache dir /mnt/disk0/lexicon/exodos/cache/ is created by setup.sh
# and written by the webapp at runtime — do not mount it read-only.
"""

    instructions = f"""# DEPLOYMENT INSTRUCTIONS
# Generated for: {ip}

## 1. Run setup script on server (creates dirs, installs Docker)
#    sudo bash setup.sh

## 2. Copy dashboard files
#    sudo cp -r dashboard/ /mnt/disk0/lexicon/dashboard/

## 3. Build and deploy the stack
#    docker compose up -d
#    (first run builds the eXoDOS image if enabled, may take ~2 min)

## 4. Access dashboard
#    http://{ip}:8080
{webtop_note}{exodos_note}
## Port Map
"""
    for key, names in config.multi_instances.items():
        for name in names:
            p = pm.get((key, name))
            instructions += f"# {key}-{name}: http://{ip}:{p}\n"
    for key, enabled in config.singleton_enabled.items():
        if enabled:
            ports = pm.get(key, [])
            if ports:
                instructions += f"# {key}: http://{ip}:{ports[0]}\n"

    with open("DEPLOY.md", "w") as f:
        f.write(instructions)
    success("Written: DEPLOY.md")

    # ── Write setup.sh ────────────────────────────────────────────────────────
    setup_content = gen_setup_script(ip, config)
    with open("setup.sh", "w") as f:
        f.write(setup_content)
    os.chmod("setup.sh", 0o755)
    success("Written: setup.sh")

    # ── Write eXoDOS webapp (only if exodos enabled) ──────────────────────────
    if config.singleton_enabled.get("exodos", False):
        gen_exodos_webapp()
        success("Written: exodos-web/ (Dockerfile + Flask app)")

    out_abs = os.path.abspath(os.getcwd())
    os.chdir(orig_cwd)

    # ── Print RAM summary ────────────────────────────────────────────────────
    print()
    print("\033[1;36m" + "─" * 60)
    print("  Estimated RAM Requirements")
    print("─" * 60 + "\033[0m")
    print()
    print(format_ram_table(config))
    print()
    print("\033[1;32m" + "=" * 60)
    print("  All files generated successfully!")
    print("=" * 60 + "\033[0m")
    print()
    print(f"  Output folder: \033[1;37m{out_abs}/\033[0m")
    print()
    print("  Next steps:")
    print(f"    1. Transfer the deploy folder to \033[0;36m{ip}\033[0m:")
    print(f"       \033[0;36mscp -r {OUTPUT_DIR}/ {ip}:~/\033[0m")
    print(f"    2. SSH in and bootstrap the server:")
    print(f"       \033[0;36mcd {OUTPUT_DIR} && sudo bash setup.sh\033[0m")
    print(f"    3. Copy dashboard files:")
    print(f"       \033[0;36msudo cp -r dashboard/ /mnt/disk0/lexicon/dashboard/\033[0m")
    print(f"    4. Deploy the stack:")
    print(f"       \033[0;36mdocker compose up -d\033[0m")
    print(f"    5. Visit \033[0;36mhttp://{ip}:8080\033[0m")
    print()

# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    config = Config()

    # Initialize all multi-instance services as empty
    for key in MULTI_SERVICES:
        config.multi_instances[key] = []

    # Initialize all singleton services as enabled by default
    for key in SINGLETON_SERVICES:
        config.singleton_enabled[key] = True

    main_menu(config)

if __name__ == "__main__":
    main()


# ==============================================================================
# EXODOS WEBAPP GENERATOR
# Writes exodos-web/Dockerfile, app.py, templates, and static assets
# ==============================================================================




# ==============================================================================
# EXODOS WEBAPP GENERATOR
# Writes exodos-web/ build context: Dockerfile, app.py, templates, README
