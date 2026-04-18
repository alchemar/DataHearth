#!/usr/bin/env python3
"""
Citadel — Home Assistant Stack Generator
==========================================
DataHearth (Internet at Home) project.

Generates:
  citadel/docker-compose.yml        — full HA stack
  citadel/setup.sh                  — Debian 13 bootstrap:
                                        Docker CE install
                                        directory creation
                                        Mosquitto passwd file
                                        USB device notes
                                        sysctl + daemon tuning
  citadel/DEPLOY.md                 — deployment reference
  citadel/config/mosquitto/         — mosquitto.conf
  citadel/config/zigbee2mqtt/       — configuration.yaml template
  citadel/config/nodered/           — settings.js with credential secret
  citadel/config/grafana/           — provisioning datasource for InfluxDB

Core services (always included)
--------------------------------
  homeassistant   Web UI + automation engine     port 8123
  mosquitto       MQTT broker                    port 1883 / 9001
  zigbee2mqtt     Zigbee coordinator bridge      port 8080
  zwavejs-ui      Z-Wave coordinator bridge      port 8091 / 3000
  node-red        Visual automation flows        port 1880
  influxdb        Long-term sensor metrics       port 8086
  grafana         Metrics dashboards             port 3001
  esphome         ESP8266/ESP32 device manager   port 6052

Optional add-ons
-----------------
  nginx-proxy-manager   SSL reverse proxy / Let's Encrypt  80 / 443 / 81
  portainer             Docker web GUI                      9000 / 9443
  code-server           VS Code in browser (edit HA config) 8443
  vaultwarden           Self-hosted Bitwarden               8880
  wireguard             VPN remote access                   51820/udp
  frigate               NVR with AI object detection        5000

Target: Proxmox VM · Debian 13 (Trixie) · x86-64
"""

import os
import sys
import secrets
import string

OUTPUT_DIR = "citadel"

# ──────────────────────────────────────────────────────────────────────────────
# Terminal helpers  (same style as generate_echo.py)
# ──────────────────────────────────────────────────────────────────────────────

def clear():
    os.system("clear" if os.name == "posix" else "cls")

def header():
    print("\033[1;34m" + "=" * 60)
    print("     CITADEL — HOME ASSISTANT STACK GENERATOR")
    print("=" * 60 + "\033[0m")
    print()

def section(title):
    pad = max(1, 55 - len(title))
    print(f"\n\033[1;33m── {title} \033[0m" + "─" * pad)

def success(msg):  print(f"\033[1;32m  ✓ {msg}\033[0m")
def info(msg):     print(f"\033[0;36m    {msg}\033[0m")
def warn(msg):     print(f"\033[0;33m  ⚠  {msg}\033[0m")

def prompt(msg, default=None):
    hint = f" [{default}]" if default is not None else ""
    try:
        val = input(f"\033[0;37m  {msg}{hint}: \033[0m").strip()
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    return val if val else default

def prompt_int(msg, lo=0, hi=99, default=0):
    while True:
        raw = prompt(msg, default)
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
            print(f"\033[1;31m    Enter a number between {lo} and {hi}\033[0m")
        except (ValueError, TypeError):
            print("\033[1;31m    Invalid number\033[0m")

def prompt_bool(msg, default=True):
    hint = "Y/n" if default else "y/N"
    raw = prompt(f"{msg} ({hint})", "").lower()
    if raw == "":
        return default
    return raw in ("y", "yes", "1", "true")

def pick_menu(title, options, default_idx=0):
    print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        marker = "  \033[0;32m←\033[0m" if i - 1 == default_idx else ""
        print(f"    \033[0;33m{i}\033[0m. {opt}{marker}")
    while True:
        raw = prompt(f"Select (1–{len(options)})", default_idx + 1)
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except (ValueError, TypeError):
            pass
        print("\033[1;31m    Invalid choice\033[0m")

def randpass(length=20):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

class Config:
    def __init__(self):
        # Network
        self.ip             = "10.50.0.30"
        self.tz             = "America/Chicago"
        self.data_dir       = "/opt/citadel"
        self.ha_port        = 8123
        self.ha_network     = "host"   # "host" or "bridge"
        self.homepage_port  = 8123     # port the VM's own dashboard/homepage is served on

        # USB adapters
        self.zigbee_device  = "/dev/ttyUSB0"
        self.zwave_device   = "/dev/ttyUSB1"

        # Secrets (pre-filled with random values; user can override)
        self.mqtt_pass      = randpass()
        self.nodered_secret = randpass()
        self.influx_pass    = randpass()
        self.influx_token   = secrets.token_hex(32)
        self.grafana_pass   = randpass()

        # Optional add-ons
        self.use_npm        = True    # Nginx Proxy Manager
        self.use_portainer  = True
        self.use_vscode     = True
        self.vscode_pass    = randpass()
        self.use_vault      = False
        self.use_wireguard  = False
        self.wg_host        = ""
        self.wg_port        = 51820
        self.use_frigate    = False

        # InfluxDB
        self.influx_org     = "homeassistant"
        self.influx_bucket  = "homeassistant"

        # Node-RED
        self.nodered_port   = 1880


# ──────────────────────────────────────────────────────────────────────────────
# Compose fragment generators
# ──────────────────────────────────────────────────────────────────────────────

def gen_header(cfg):
    return f"""\
version: '3.8'
# ==============================================================================
# CITADEL — HOME ASSISTANT STACK
# Host: {cfg.ip}
# Target: Proxmox VM · Debian 13 (Trixie) · x86-64
# Generated by generate_citadel.py
# ==============================================================================

"""


def gen_network_block(cfg):
    if cfg.ha_network == "bridge":
        return """\
networks:
  citadel:
    driver: bridge
    name: citadel

"""
    return ""  # host mode — no custom network needed


def gen_homeassistant(cfg):
    net_lines = ""
    port_lines = ""
    if cfg.ha_network == "host":
        net_lines = "    network_mode: host\n"
    else:
        port_lines = f'      - "{cfg.ha_port}:{cfg.ha_port}"\n'
        net_lines = "    networks:\n      - citadel\n"

    return f"""services:

  # ============================================================================
  # HOME ASSISTANT — Core automation engine
  # UI: http://{cfg.ip}:{cfg.ha_port}
  # network_mode: {cfg.ha_network}
  #   host  = full device discovery (mDNS/Chromecast/Sonos/UPnP) — recommended
  #   bridge = isolated network, loses auto-discovery
  # ============================================================================
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    privileged: true
{net_lines}{'    ports:\n' + port_lines if port_lines else ''}\
    volumes:
      - {cfg.data_dir}/homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro
    environment:
      - TZ={cfg.tz}
"""


def gen_mosquitto(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # MOSQUITTO — MQTT Broker
  # Port 1883: MQTT  |  Port 9001: WebSocket
  # Config:  {cfg.data_dir}/mosquitto/config/mosquitto.conf
  # Passwd:  {cfg.data_dir}/mosquitto/config/passwd  (created by setup.sh)
  # ============================================================================
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - {cfg.data_dir}/mosquitto/config:/mosquitto/config:ro
      - {cfg.data_dir}/mosquitto/data:/mosquitto/data
      - {cfg.data_dir}/mosquitto/log:/mosquitto/log
{net}"""


def gen_zigbee2mqtt(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # ZIGBEE2MQTT — Zigbee coordinator bridge (no proprietary hub needed)
  # UI:     http://{cfg.ip}:8080
  # Dongle: {cfg.zigbee_device}
  # On first run: open UI to complete coordinator setup wizard
  # ============================================================================
  zigbee2mqtt:
    image: ghcr.io/koenkk/zigbee2mqtt:latest
    container_name: zigbee2mqtt
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - {cfg.data_dir}/zigbee2mqtt/data:/app/data
      - /run/udev:/run/udev:ro
    devices:
      - {cfg.zigbee_device}:/dev/ttyUSB0
    environment:
      - TZ={cfg.tz}
      - ZIGBEE2MQTT_DATA=/app/data
    depends_on:
      - mosquitto
{net}"""


def gen_zwavejs(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # Z-WAVE JS UI — Z-Wave coordinator bridge
  # UI:        http://{cfg.ip}:8091
  # WebSocket: ws://{cfg.ip}:3000  (add in HA Z-Wave JS integration)
  # Dongle:    {cfg.zwave_device}
  # ============================================================================
  zwavejs-ui:
    image: zwavejs/zwave-js-ui:latest
    container_name: zwavejs-ui
    restart: unless-stopped
    tty: true
    stop_signal: SIGINT
    ports:
      - "8091:8091"
      - "3000:3000"
    volumes:
      - {cfg.data_dir}/zwavejs/store:/usr/src/app/store
    devices:
      - {cfg.zwave_device}:/dev/ttyUSB1
    environment:
      - TZ={cfg.tz}
{net}"""


def gen_nodered(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # NODE-RED — Visual automation flows
  # UI: http://{cfg.ip}:{cfg.nodered_port}
  # Credential secret set via NODE_RED_CREDENTIAL_SECRET
  # ============================================================================
  node-red:
    image: nodered/node-red:latest
    container_name: node-red
    restart: unless-stopped
    ports:
      - "{cfg.nodered_port}:{cfg.nodered_port}"
    volumes:
      - {cfg.data_dir}/nodered/data:/data
    environment:
      - TZ={cfg.tz}
      - NODE_RED_CREDENTIAL_SECRET={cfg.nodered_secret}
{net}"""


def gen_influxdb(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # INFLUXDB 2 — Long-term sensor metrics store
  # UI:    http://{cfg.ip}:8086
  # HA integration: Settings → Devices & Services → InfluxDB
  #   URL: http://influxdb:8086  org: {cfg.influx_org}
  #   token: (from .env INFLUXDB_TOKEN)  bucket: {cfg.influx_bucket}
  # ============================================================================
  influxdb:
    image: influxdb:2
    container_name: influxdb
    restart: unless-stopped
    ports:
      - "8086:8086"
    volumes:
      - {cfg.data_dir}/influxdb/data:/var/lib/influxdb2
      - {cfg.data_dir}/influxdb/config:/etc/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD={cfg.influx_pass}
      - DOCKER_INFLUXDB_INIT_ORG={cfg.influx_org}
      - DOCKER_INFLUXDB_INIT_BUCKET={cfg.influx_bucket}
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN={cfg.influx_token}
{net}"""


def gen_grafana(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # GRAFANA — Metrics dashboards
  # UI: http://{cfg.ip}:3001  (admin / see GRAFANA_PASS in .env)
  # InfluxDB datasource auto-provisioned via config/grafana/
  # ============================================================================
  grafana:
    image: grafana/grafana-oss:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3001:3000"
    volumes:
      - {cfg.data_dir}/grafana/data:/var/lib/grafana
      - {cfg.data_dir}/grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD={cfg.grafana_pass}
      - GF_INSTALL_PLUGINS=grafana-clock-panel
    depends_on:
      - influxdb
{net}"""


def gen_esphome(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # ESPHOME — ESP8266 / ESP32 device manager
  # UI: http://{cfg.ip}:6052
  # Edit device YAML configs here; flashes directly via USB or OTA
  # ============================================================================
  esphome:
    image: ghcr.io/esphome/esphome:latest
    container_name: esphome
    restart: unless-stopped
    ports:
      - "6052:6052"
    volumes:
      - {cfg.data_dir}/esphome/config:/config
      - /etc/localtime:/etc/localtime:ro
    environment:
      - TZ={cfg.tz}
{net}"""


def gen_npm(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # NGINX PROXY MANAGER — SSL reverse proxy / Let's Encrypt
  # Admin UI: http://{cfg.ip}:81  (default: admin@example.com / changeme)
  # Change default credentials immediately after first login!
  # ============================================================================
  nginx-proxy-manager:
    image: jc21/nginx-proxy-manager:latest
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    volumes:
      - {cfg.data_dir}/npm/data:/data
      - {cfg.data_dir}/npm/letsencrypt:/etc/letsencrypt
{net}"""


def gen_portainer(cfg):
    # Portainer always needs docker socket — no custom network needed
    return f"""
  # ============================================================================
  # PORTAINER — Docker web GUI
  # UI: https://{cfg.ip}:9443  (create admin on first visit)
  # ============================================================================
  portainer:
    image: portainer/portainer-ce:latest
    container_name: portainer
    restart: unless-stopped
    ports:
      - "9000:9000"
      - "9443:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - {cfg.data_dir}/portainer/data:/data
"""


def gen_vscode(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # CODE SERVER — VS Code in browser (edit HA configs directly)
  # UI: http://{cfg.ip}:8443  Password: see VSCODE_PASSWORD in .env
  # Opens directly into the HA config directory
  # ============================================================================
  code-server:
    image: lscr.io/linuxserver/code-server:latest
    container_name: code-server
    restart: unless-stopped
    ports:
      - "8443:8443"
    volumes:
      - {cfg.data_dir}/homeassistant/config:/config/workspace
      - {cfg.data_dir}/code-server:/config
    environment:
      - PUID=1000
      - PGID=1000
      - TZ={cfg.tz}
      - PASSWORD={cfg.vscode_pass}
      - SUDO_PASSWORD={cfg.vscode_pass}
      - DEFAULT_WORKSPACE=/config/workspace
{net}"""


def gen_vaultwarden(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # VAULTWARDEN — Self-hosted Bitwarden-compatible password manager
  # UI: http://{cfg.ip}:8880
  # Set SIGNUPS_ALLOWED=false after creating your account
  # ============================================================================
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: unless-stopped
    ports:
      - "8880:80"
    volumes:
      - {cfg.data_dir}/vaultwarden/data:/data
    environment:
      - TZ={cfg.tz}
      - WEBSOCKET_ENABLED=true
      - SIGNUPS_ALLOWED=true
{net}"""


def gen_wireguard(cfg):
    return f"""
  # ============================================================================
  # WIREGUARD — VPN remote access
  # Port: {cfg.wg_port}/udp  |  UI: http://{cfg.ip}:51821
  # Peers: 5 generated by default (QR codes in UI)
  # ============================================================================
  wireguard:
    image: lscr.io/linuxserver/wireguard:latest
    container_name: wireguard
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
    ports:
      - "{cfg.wg_port}:{cfg.wg_port}/udp"
      - "51821:51821/tcp"
    volumes:
      - {cfg.data_dir}/wireguard/config:/config
      - /lib/modules:/lib/modules:ro
    environment:
      - PUID=1000
      - PGID=1000
      - TZ={cfg.tz}
      - SERVERURL={cfg.wg_host or cfg.ip}
      - SERVERPORT={cfg.wg_port}
      - PEERS=5
      - PEERDNS=auto
      - INTERNAL_SUBNET=10.13.13.0
"""


def gen_frigate(cfg):
    net = "    networks:\n      - citadel\n" if cfg.ha_network == "bridge" else ""
    return f"""
  # ============================================================================
  # FRIGATE — NVR with AI object detection
  # UI:   http://{cfg.ip}:5000
  # RTSP: rtsp://{cfg.ip}:8554/<camera_name>
  # Edit {cfg.data_dir}/frigate/config/config.yaml to add cameras
  # Coral USB TPU: uncomment the devices block below
  # Intel GPU hw decode: uncomment renderD128 device
  # ============================================================================
  frigate:
    image: ghcr.io/blakeblackshear/frigate:stable
    container_name: frigate
    restart: unless-stopped
    privileged: true
    shm_size: "256mb"
    ports:
      - "5000:5000"
      - "8554:8554"
      - "8555:8555/tcp"
      - "8555:8555/udp"
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - {cfg.data_dir}/frigate/config:/config
      - {cfg.data_dir}/frigate/media:/media/frigate
      - type: tmpfs
        target: /tmp/cache
        tmpfs:
          size: 1000000000
    environment:
      - FRIGATE_RTSP_PASSWORD=changeme
    # devices:
    #   - /dev/bus/usb:/dev/bus/usb    # Coral USB TPU
    #   - /dev/dri/renderD128          # Intel GPU hw decode
{net}"""


# ──────────────────────────────────────────────────────────────────────────────
# Config file generators
# ──────────────────────────────────────────────────────────────────────────────

def gen_mosquitto_conf(cfg):
    return f"""\
# Mosquitto MQTT Broker — generated by generate_citadel.py
# Mosquitto 2.x requires explicit authentication config

listener 1883
listener 9001
protocol websockets

# Authentication — passwd file created by setup.sh
allow_anonymous false
password_file /mosquitto/config/passwd

persistence true
persistence_location /mosquitto/data/

log_dest file /mosquitto/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
log_timestamp true
"""


def gen_zigbee2mqtt_config(cfg):
    return f"""\
# Zigbee2MQTT configuration — generated by generate_citadel.py
# Finish setup via the web UI at http://{cfg.ip}:8080

homeassistant: true
permit_join: false

mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://mosquitto:1883
  user: homeassistant
  password: "{cfg.mqtt_pass}"

serial:
  port: /dev/ttyUSB0
  # adapter: auto   # uncomment to force: zstack, deconz, ezsp, zigate, zboss

frontend:
  port: 8080
  host: 0.0.0.0

advanced:
  log_level: info
  homeassistant_legacy_entity_attributes: false
  legacy_api: false
  legacy_availability_payload: false
  channel: 11   # change if channel conflicts; restart after changing
"""


def gen_nodered_settings(cfg):
    return f"""\
// Node-RED settings.js — generated by generate_citadel.py
module.exports = {{
    uiPort: {cfg.nodered_port},
    credentialSecret: "{cfg.nodered_secret}",
    httpAdminRoot: "/",
    httpNodeRoot: "/",
    userDir: "/data",
    flowFile: "flows.json",
    logging: {{
        console: {{
            level: "info",
            metrics: false,
            audit: false,
        }},
    }},
    editorTheme: {{
        projects: {{ enabled: false }},
    }},
}};
"""


def gen_grafana_datasource(cfg):
    return f"""\
# Grafana InfluxDB 2 datasource provisioning
# generated by generate_citadel.py

apiVersion: 1

datasources:
  - name: InfluxDB
    type: influxdb
    access: proxy
    url: http://influxdb:8086
    jsonData:
      version: Flux
      organization: {cfg.influx_org}
      defaultBucket: {cfg.influx_bucket}
      tlsSkipVerify: true
    secureJsonData:
      token: {cfg.influx_token}
    isDefault: true
"""


def gen_env_file(cfg):
    lines = [
        "# Citadel .env — generated by generate_citadel.py",
        "# Keep this file private — do NOT commit to git!",
        "",
        f"TZ={cfg.tz}",
        f"INSTALL_DIR={cfg.data_dir}",
        "",
        "# MQTT",
        "MQTT_USER=homeassistant",
        f"MQTT_PASSWORD={cfg.mqtt_pass}",
        "",
        "# Node-RED",
        f"NODERED_SECRET={cfg.nodered_secret}",
        "",
        "# InfluxDB",
        f"INFLUXDB_PASSWORD={cfg.influx_pass}",
        f"INFLUXDB_TOKEN={cfg.influx_token}",
        f"INFLUXDB_ORG={cfg.influx_org}",
        f"INFLUXDB_BUCKET={cfg.influx_bucket}",
        "",
        "# Grafana",
        f"GRAFANA_PASSWORD={cfg.grafana_pass}",
        "",
    ]
    if cfg.use_vscode:
        lines += [f"VSCODE_PASSWORD={cfg.vscode_pass}", ""]
    if cfg.use_wireguard:
        lines += [f"WG_HOST={cfg.wg_host or cfg.ip}", f"WG_PORT={cfg.wg_port}", ""]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Setup script
# ──────────────────────────────────────────────────────────────────────────────

def gen_setup_script(cfg):
    # Build directory list
    core_dirs = [
        f"{cfg.data_dir}/homeassistant/config",
        f"{cfg.data_dir}/mosquitto/config",
        f"{cfg.data_dir}/mosquitto/data",
        f"{cfg.data_dir}/mosquitto/log",
        f"{cfg.data_dir}/zigbee2mqtt/data",
        f"{cfg.data_dir}/zwavejs/store",
        f"{cfg.data_dir}/nodered/data",
        f"{cfg.data_dir}/influxdb/data",
        f"{cfg.data_dir}/influxdb/config",
        f"{cfg.data_dir}/grafana/data",
        f"{cfg.data_dir}/grafana/provisioning/datasources",
        f"{cfg.data_dir}/esphome/config",
    ]
    opt_dirs = []
    if cfg.use_npm:
        opt_dirs += [f"{cfg.data_dir}/npm/data", f"{cfg.data_dir}/npm/letsencrypt"]
    if cfg.use_portainer:
        opt_dirs.append(f"{cfg.data_dir}/portainer/data")
    if cfg.use_vscode:
        opt_dirs.append(f"{cfg.data_dir}/code-server")
    if cfg.use_vault:
        opt_dirs.append(f"{cfg.data_dir}/vaultwarden/data")
    if cfg.use_wireguard:
        opt_dirs.append(f"{cfg.data_dir}/wireguard/config")
    if cfg.use_frigate:
        opt_dirs += [f"{cfg.data_dir}/frigate/config", f"{cfg.data_dir}/frigate/media"]

    all_dirs = sorted(set(core_dirs + opt_dirs))
    mkdir_lines = "\n".join(f'  mkdir -p "{d}"' for d in all_dirs)

    addons = []
    if cfg.use_npm:        addons.append("Nginx Proxy Manager")
    if cfg.use_portainer:  addons.append("Portainer")
    if cfg.use_vscode:     addons.append("Code Server")
    if cfg.use_vault:      addons.append("Vaultwarden")
    if cfg.use_wireguard:  addons.append("WireGuard")
    if cfg.use_frigate:    addons.append("Frigate")
    addon_str = ", ".join(addons) if addons else "none"

    return f"""\
#!/usr/bin/env bash
# ==============================================================================
#  CITADEL — HOME ASSISTANT STACK BOOTSTRAP
#  Target:  Debian 13 (Trixie) · x86-64 · Proxmox VM
#  Host IP: {cfg.ip}
#  Data:    {cfg.data_dir}
#  Add-ons: {addon_str}
#  Generated by generate_citadel.py
#
#  Run as root:  sudo bash setup.sh
# ==============================================================================

set -euo pipefail
REBOOT_NEEDED=false

# ── Colours & helpers ─────────────────────────────────────────────────────────
RED="\\033[1;31m"; GRN="\\033[1;32m"; YEL="\\033[1;33m"
CYN="\\033[0;36m"; RST="\\033[0m";   BLD="\\033[1;37m"

log()     {{ echo -e "${{GRN}}  ✓ ${{RST}}$*"; }}
warn()    {{ echo -e "${{YEL}}  ⚠ ${{RST}}$*"; }}
err()     {{ echo -e "${{RED}}  ✗ ${{RST}}$*" >&2; exit 1; }}
section() {{ echo -e "\\n${{YEL}}── $* ${{RST}}${{CYN}}$(printf '%.0s─' {{1..40}})${{RST}}"; }}

[[ $EUID -ne 0 ]] && err "Run as root: sudo bash $0"

CALLING_USER="${{SUDO_USER:-$(whoami)}}"
CALLING_UID=$(id -u "$CALLING_USER" 2>/dev/null || echo 1000)
CALLING_GID=$(id -g "$CALLING_USER" 2>/dev/null || echo 1000)

echo ""
echo -e "${{BLD}}============================================================${{RST}}"
echo -e "${{BLD}}       CITADEL BOOTSTRAP — Debian 13 Trixie${{RST}}"
echo -e "${{BLD}}       Host: {cfg.ip}  |  Data: {cfg.data_dir}${{RST}}"
echo -e "${{BLD}}============================================================${{RST}}"
echo ""

# ==============================================================================
# 1. SYSTEM UPDATE & BASE PACKAGES
# ==============================================================================
section "System update and base packages"

apt-get update -qq
apt-get upgrade -y -qq
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
  tmux \\
  vim \\
  nano \\
  net-tools \\
  dnsutils \\
  pciutils \\
  usbutils \\
  mosquitto-clients \\
  rsync \\
  unzip \\
  software-properties-common
log "Base packages installed"

# ==============================================================================
# 2. DOCKER CE (Official Repo)
# ==============================================================================
section "Installing Docker CE"

for PKG in docker.io docker-doc docker-compose podman-docker containerd runc; do
  apt-get remove -y "$PKG" 2>/dev/null || true
done

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \\
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

CODENAME=$(lsb_release -cs 2>/dev/null || echo "bookworm")
echo \\
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \\
  https://download.docker.com/linux/debian ${{CODENAME}} stable" \\
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq

# Debian 13 (Trixie) may not yet have Docker CE packages; fall back to bookworm
if ! apt-cache show docker-ce &>/dev/null 2>&1; then
  warn "No Docker CE for $CODENAME — falling back to bookworm repo"
  echo \\
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \\
    https://download.docker.com/linux/debian bookworm stable" \\
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
fi

apt-get install -y -qq \\
  docker-ce \\
  docker-ce-cli \\
  containerd.io \\
  docker-buildx-plugin \\
  docker-compose-plugin
systemctl enable --now docker
log "Docker CE installed and started"

if ! groups "$CALLING_USER" | grep -q docker; then
  usermod -aG docker "$CALLING_USER"
  log "Added $CALLING_USER to docker group"
fi

# ==============================================================================
# 3. DIRECTORIES
# ==============================================================================
section "Creating Citadel data directories"

{mkdir_lines}

chown -R "$CALLING_UID:$CALLING_GID" "{cfg.data_dir}" 2>/dev/null || true
log "Directories created and owned by $CALLING_USER"

# ==============================================================================
# 4. MOSQUITTO PASSWORD FILE
# ==============================================================================
section "Creating Mosquitto password file"

PASSWD_FILE="{cfg.data_dir}/mosquitto/config/passwd"
MQTT_USER="homeassistant"
MQTT_PASS="{cfg.mqtt_pass}"

if [ -f "$PASSWD_FILE" ]; then
  warn "Mosquitto passwd file already exists — skipping"
else
  # mosquitto_passwd is in the mosquitto-clients package (installed above)
  mosquitto_passwd -b -c "$PASSWD_FILE" "$MQTT_USER" "$MQTT_PASS"
  chmod 600 "$PASSWD_FILE"
  chown "$CALLING_UID:$CALLING_GID" "$PASSWD_FILE"
  log "Mosquitto passwd created  user=$MQTT_USER"
fi

# ==============================================================================
# 5. COPY CONFIG FILES
# ==============================================================================
section "Installing service config files"

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# mosquitto.conf
if [ -f "$SCRIPT_DIR/config/mosquitto/mosquitto.conf" ]; then
  cp "$SCRIPT_DIR/config/mosquitto/mosquitto.conf" \\
     "{cfg.data_dir}/mosquitto/config/mosquitto.conf"
  log "mosquitto.conf installed"
else
  warn "config/mosquitto/mosquitto.conf not found — skipping"
fi

# zigbee2mqtt configuration.yaml (only if not already present)
Z2M_CFG="{cfg.data_dir}/zigbee2mqtt/data/configuration.yaml"
if [ ! -f "$Z2M_CFG" ] && [ -f "$SCRIPT_DIR/config/zigbee2mqtt/configuration.yaml" ]; then
  cp "$SCRIPT_DIR/config/zigbee2mqtt/configuration.yaml" "$Z2M_CFG"
  log "zigbee2mqtt configuration.yaml installed"
elif [ -f "$Z2M_CFG" ]; then
  warn "Zigbee2MQTT config already exists — not overwriting"
fi

# Node-RED settings.js
NR_SETTINGS="{cfg.data_dir}/nodered/data/settings.js"
if [ ! -f "$NR_SETTINGS" ] && [ -f "$SCRIPT_DIR/config/nodered/settings.js" ]; then
  cp "$SCRIPT_DIR/config/nodered/settings.js" "$NR_SETTINGS"
  log "Node-RED settings.js installed"
fi

# Grafana InfluxDB datasource
GF_DS_DIR="{cfg.data_dir}/grafana/provisioning/datasources"
if [ -f "$SCRIPT_DIR/config/grafana/influxdb.yaml" ]; then
  cp "$SCRIPT_DIR/config/grafana/influxdb.yaml" "$GF_DS_DIR/influxdb.yaml"
  log "Grafana InfluxDB datasource provisioned"
fi

chown -R "$CALLING_UID:$CALLING_GID" "{cfg.data_dir}" 2>/dev/null || true

# ==============================================================================
# 6. USB DEVICE CHECK
# ==============================================================================
section "Checking USB adapters"

echo ""
ZIGBEE="{cfg.zigbee_device}"
ZWAVE="{cfg.zwave_device}"

if [ -e "$ZIGBEE" ]; then
  log "Zigbee adapter found: $ZIGBEE"
else
  warn "Zigbee adapter NOT found at $ZIGBEE"
  warn "Available serial devices:"
  ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | while read d; do
    echo "    $d"
  done || echo "    (none found)"
  warn "Update ZIGBEE2MQTT_DEVICE in docker-compose.yml before starting"
fi

if [ -e "$ZWAVE" ]; then
  log "Z-Wave adapter found: $ZWAVE"
else
  warn "Z-Wave adapter NOT found at $ZWAVE"
  warn "Update the devices: entry for zwavejs-ui in docker-compose.yml"
fi

# Proxmox tip
echo ""
info() {{ echo -e "${{CYN}}    ${{RST}}$*"; }}
info "Proxmox tip: if USB adapters are not visible here, add them via"
info "  Datacenter → VM → Hardware → Add → USB Device"
info "  Use 'Use USB device' (not port) so they survive VM reboots."
info "  Stable device IDs: ls /dev/serial/by-id/"

# ==============================================================================
# 7. SYSCTL TUNING
# ==============================================================================
section "Applying sysctl tuning"

cat > /etc/sysctl.d/99-citadel.conf << 'SYSCTLEOF'
# Citadel / Home Assistant tuning
vm.swappiness = 10
vm.overcommit_memory = 1
net.core.somaxconn = 65535
net.ipv4.tcp_tw_reuse = 1
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 512
SYSCTLEOF
sysctl -p /etc/sysctl.d/99-citadel.conf >/dev/null 2>&1 || true
log "sysctl tuning applied"

# ==============================================================================
# 8. DOCKER DAEMON CONFIG
# ==============================================================================
section "Configuring Docker daemon"

mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json << 'DAEMONEOF'
{{
  "log-driver": "json-file",
  "log-opts": {{
    "max-size": "20m",
    "max-file": "5"
  }},
  "storage-driver": "overlay2",
  "live-restore": true
}}
DAEMONEOF
  systemctl reload docker || systemctl restart docker
  log "Docker daemon config written"
else
  warn "/etc/docker/daemon.json already exists — skipping"
fi

# ==============================================================================
# 9. WEEKLY DOCKER CLEANUP
# ==============================================================================
section "Installing weekly Docker cleanup cron"

cat > /etc/cron.weekly/docker-cleanup << 'CRONEOF'
#!/bin/bash
docker system prune -f --filter "until=168h" >> /var/log/docker-cleanup.log 2>&1
CRONEOF
chmod +x /etc/cron.weekly/docker-cleanup
log "Weekly cleanup cron installed"

# ==============================================================================
# DONE
# ==============================================================================
echo ""
echo -e "${{GRN}}============================================================${{RST}}"
echo -e "${{GRN}}  Citadel bootstrap complete!${{RST}}"
echo -e "${{GRN}}============================================================${{RST}}"
echo ""
echo -e "  ${{BLD}}Next steps:${{RST}}"
echo -e "  1. ${{CYN}}newgrp docker${{RST}}  (or log out and back in)"
echo -e "  2. ${{CYN}}docker compose up -d${{RST}}"
echo -e "  3. ${{CYN}}docker compose logs -f${{RST}}  (watch startup)"
echo ""
echo -e "  ${{BLD}}Service URLs:${{RST}}"
echo -e "  Home Assistant  ${{CYN}}http://{cfg.ip}:{cfg.ha_port}${{RST}}"
echo -e "  Zigbee2MQTT     ${{CYN}}http://{cfg.ip}:8080${{RST}}"
echo -e "  Z-Wave JS UI    ${{CYN}}http://{cfg.ip}:8091${{RST}}"
echo -e "  Node-RED        ${{CYN}}http://{cfg.ip}:{cfg.nodered_port}${{RST}}"
echo -e "  InfluxDB        ${{CYN}}http://{cfg.ip}:8086${{RST}}"
echo -e "  Grafana         ${{CYN}}http://{cfg.ip}:3001${{RST}}"
echo -e "  ESPHome         ${{CYN}}http://{cfg.ip}:6052${{RST}}"
{"echo -e '  NPM             ${{CYN}}http://" + cfg.ip + ":81${{RST}}'" if cfg.use_npm else ""}
{"echo -e '  Portainer       ${{CYN}}https://" + cfg.ip + ":9443${{RST}}'" if cfg.use_portainer else ""}
{"echo -e '  Code Server     ${{CYN}}http://" + cfg.ip + ":8443${{RST}}'" if cfg.use_vscode else ""}
{"echo -e '  Vaultwarden     ${{CYN}}http://" + cfg.ip + ":8880${{RST}}'" if cfg.use_vault else ""}
{"echo -e '  Frigate         ${{CYN}}http://" + cfg.ip + ":5000${{RST}}'" if cfg.use_frigate else ""}
echo ""
echo -e "  ${{YEL}}HA quick-start tips:${{RST}}"
echo -e "  - First run takes 2–3 min; wait before opening the UI"
echo -e "  - Add MQTT integration: Settings → Devices → MQTT"
echo -e "    Broker: mosquitto  Port: 1883  User/Pass: see .env"
echo -e "  - Add Z-Wave: Settings → Devices → Z-Wave JS"
echo -e "    WebSocket: ws://{cfg.ip}:3000"
echo -e "  - Add InfluxDB: Settings → Devices → InfluxDB"
echo -e "    URL: http://influxdb:8086  (token in .env)"
echo ""
"""


# ──────────────────────────────────────────────────────────────────────────────
# DEPLOY.md
# ──────────────────────────────────────────────────────────────────────────────

def gen_deploy_md(cfg):
    services = [
        f"  Home Assistant  http://{cfg.ip}:{cfg.ha_port}",
        f"  Mosquitto       mqtt://{cfg.ip}:1883  (MQTT)",
        f"  Zigbee2MQTT     http://{cfg.ip}:8080",
        f"  Z-Wave JS UI    http://{cfg.ip}:8091   ws://{cfg.ip}:3000",
        f"  Node-RED        http://{cfg.ip}:{cfg.nodered_port}",
        f"  InfluxDB        http://{cfg.ip}:8086",
        f"  Grafana         http://{cfg.ip}:3001   (admin / see .env)",
        f"  ESPHome         http://{cfg.ip}:6052",
    ]
    if cfg.use_npm:       services.append(f"  NPM Admin       http://{cfg.ip}:81")
    if cfg.use_portainer: services.append(f"  Portainer       https://{cfg.ip}:9443")
    if cfg.use_vscode:    services.append(f"  Code Server     http://{cfg.ip}:8443")
    if cfg.use_vault:     services.append(f"  Vaultwarden     http://{cfg.ip}:8880")
    if cfg.use_wireguard: services.append(f"  WireGuard       {cfg.wg_host or cfg.ip}:{cfg.wg_port}/udp")
    if cfg.use_frigate:   services.append(f"  Frigate         http://{cfg.ip}:5000")

    return f"""\
# CITADEL — HOME ASSISTANT STACK DEPLOYMENT
# Host: {cfg.ip}
# Data: {cfg.data_dir}
# Generated by generate_citadel.py

## Quick start

# 1. Copy this folder to the Citadel VM
#    scp -r citadel/ {cfg.ip}:~/

# 2. Bootstrap (installs Docker CE, creates dirs, sets up Mosquitto auth)
#    ssh {cfg.ip} "cd citadel && sudo bash setup.sh"

# 3. Start the stack
#    ssh {cfg.ip} "cd citadel && docker compose up -d"

# 4. Watch startup logs
#    ssh {cfg.ip} "cd citadel && docker compose logs -f"

## Services
{chr(10).join(services)}

## Home Assistant integrations to add after first boot

# MQTT (required for Zigbee2MQTT and ESPHome)
#   Settings → Devices & Services → Add Integration → MQTT
#   Broker: mosquitto   Port: 1883
#   Username: homeassistant   Password: (see .env MQTT_PASSWORD)

# Z-Wave JS
#   Settings → Devices & Services → Add Integration → Z-Wave JS
#   WebSocket URL: ws://{cfg.ip}:3000

# InfluxDB
#   Settings → Devices & Services → Add Integration → InfluxDB
#   URL: http://influxdb:8086   (or http://{cfg.ip}:8086 from outside)
#   Token: (see .env INFLUXDB_TOKEN)
#   Org: {cfg.influx_org}   Bucket: {cfg.influx_bucket}

# ESPHome
#   Settings → Devices & Services → Add Integration → ESPHome
#   Host: esphome   Port: 6052

## Useful commands

# View all container status
#   docker compose ps

# Tail logs for a specific service
#   docker compose logs -f homeassistant
#   docker compose logs -f zigbee2mqtt
#   docker compose logs -f mosquitto

# Restart a single service
#   docker compose restart homeassistant

# Update all images
#   docker compose pull && docker compose up -d

# HA config check (before restart)
#   docker exec homeassistant python -m homeassistant --script check_config --config /config

# Test MQTT from host
#   mosquitto_sub -h {cfg.ip} -p 1883 -u homeassistant -P "<mqtt_pass>" -t "#" -v

## USB device paths (Proxmox)
#   Pass through via: Datacenter → VM → Hardware → Add → USB Device
#   Zigbee: {cfg.zigbee_device}
#   Z-Wave: {cfg.zwave_device}
#   Stable IDs: ls /dev/serial/by-id/

## Secrets reference  (from .env)
#   MQTT_PASSWORD       {cfg.mqtt_pass}
#   NODERED_SECRET      {cfg.nodered_secret}
#   INFLUXDB_PASSWORD   {cfg.influx_pass}
#   INFLUXDB_TOKEN      {cfg.influx_token[:16]}...
#   GRAFANA_PASSWORD    {cfg.grafana_pass}
{"#   VSCODE_PASSWORD     " + cfg.vscode_pass if cfg.use_vscode else ""}
"""


# ──────────────────────────────────────────────────────────────────────────────
# File generation
# ──────────────────────────────────────────────────────────────────────────────

def generate_files(cfg):
    orig_cwd = os.getcwd()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(OUTPUT_DIR)
    out_abs = os.path.abspath(".")

    # ── docker-compose.yml ────────────────────────────────────────────────────
    parts = [gen_header(cfg), gen_network_block(cfg), gen_homeassistant(cfg)]
    parts.append(gen_mosquitto(cfg))
    parts.append(gen_zigbee2mqtt(cfg))
    parts.append(gen_zwavejs(cfg))
    parts.append(gen_nodered(cfg))
    parts.append(gen_influxdb(cfg))
    parts.append(gen_grafana(cfg))
    parts.append(gen_esphome(cfg))
    if cfg.use_npm:        parts.append(gen_npm(cfg))
    if cfg.use_portainer:  parts.append(gen_portainer(cfg))
    if cfg.use_vscode:     parts.append(gen_vscode(cfg))
    if cfg.use_vault:      parts.append(gen_vaultwarden(cfg))
    if cfg.use_wireguard:  parts.append(gen_wireguard(cfg))
    if cfg.use_frigate:    parts.append(gen_frigate(cfg))

    with open("docker-compose.yml", "w") as f:
        f.write("".join(parts))
    success("Written: docker-compose.yml")

    # ── setup.sh ──────────────────────────────────────────────────────────────
    with open("setup.sh", "w") as f:
        f.write(gen_setup_script(cfg))
    os.chmod("setup.sh", 0o755)
    success("Written: setup.sh")

    # ── .env ──────────────────────────────────────────────────────────────────
    with open(".env", "w") as f:
        f.write(gen_env_file(cfg))
    os.chmod(".env", 0o600)
    success("Written: .env  (chmod 600 — keep private)")

    # ── DEPLOY.md ─────────────────────────────────────────────────────────────
    with open("DEPLOY.md", "w") as f:
        f.write(gen_deploy_md(cfg))
    success("Written: DEPLOY.md")

    # ── Config files ──────────────────────────────────────────────────────────
    os.makedirs("config/mosquitto",             exist_ok=True)
    os.makedirs("config/zigbee2mqtt",           exist_ok=True)
    os.makedirs("config/nodered",               exist_ok=True)
    os.makedirs("config/grafana",               exist_ok=True)

    with open("config/mosquitto/mosquitto.conf", "w") as f:
        f.write(gen_mosquitto_conf(cfg))
    success("Written: config/mosquitto/mosquitto.conf")

    with open("config/zigbee2mqtt/configuration.yaml", "w") as f:
        f.write(gen_zigbee2mqtt_config(cfg))
    success("Written: config/zigbee2mqtt/configuration.yaml")

    with open("config/nodered/settings.js", "w") as f:
        f.write(gen_nodered_settings(cfg))
    success("Written: config/nodered/settings.js")

    with open("config/grafana/influxdb.yaml", "w") as f:
        f.write(gen_grafana_datasource(cfg))
    success("Written: config/grafana/influxdb.yaml")

    os.chdir(orig_cwd)

    print()
    print("\033[1;32m" + "=" * 60)
    print("  Citadel files generated successfully!")
    print("=" * 60 + "\033[0m")
    print()
    print(f"  Output: \033[1;37m{out_abs}/\033[0m")
    print()
    print("  Next steps:")
    print(f"    1. \033[0;36mscp -r {OUTPUT_DIR}/ {cfg.ip}:~/\033[0m")
    print(f"    2. \033[0;36mssh {cfg.ip} 'cd {OUTPUT_DIR} && sudo bash setup.sh'\033[0m")
    print(f"    3. \033[0;36mssh {cfg.ip} 'cd {OUTPUT_DIR} && docker compose up -d'\033[0m")
    print(f"    4. \033[0;36mssh {cfg.ip} 'docker compose logs -f'\033[0m")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Menu screens
# ──────────────────────────────────────────────────────────────────────────────

NETWORK_OPTIONS = [
    "host   — full device discovery (mDNS/Chromecast/Sonos/UPnP) — recommended",
    "bridge — isolated Docker network (use with Nginx Proxy Manager)",
]


def screen_network(cfg):
    clear(); header(); section("Host IP & Network")
    print()
    cfg.ip = prompt("Citadel VM IP address", cfg.ip)
    cfg.tz = prompt("Timezone", cfg.tz)
    cfg.data_dir = prompt("Data directory on VM", cfg.data_dir)
    print()
    info("host mode: HA uses the VM network directly — needed for mDNS auto-discovery")
    info("bridge mode: isolated, loses auto-discovery, but works with reverse proxy")
    print()
    ni = pick_menu("HA network mode:", NETWORK_OPTIONS,
                   0 if cfg.ha_network == "host" else 1)
    cfg.ha_network = "host" if ni == 0 else "bridge"
    cfg.ha_port = prompt_int("Home Assistant port", 1024, 65535, cfg.ha_port)
    print()
    info("homepage_port is the port Sentinel uses to link to this VM's dashboard.")
    info("For Citadel this is 8123 (HA itself). If you add a separate homepage")
    info("service later (e.g. nginx on 8080), update this to match.")
    cfg.homepage_port = prompt_int("Homepage / dashboard port (for Sentinel card link)", 1024, 65535, cfg.homepage_port)
    success(f"IP: {cfg.ip}  network: {cfg.ha_network}  HA port: {cfg.ha_port}  homepage: {cfg.homepage_port}")


def screen_usb(cfg):
    clear(); header(); section("USB Adapters")
    print()
    info("Proxmox: pass through USB devices via")
    info("  Datacenter → VM → Hardware → Add → USB Device")
    info("  Use 'Use USB device' (not port) to persist across VM reboots")
    info("  Find stable IDs:  ls /dev/serial/by-id/")
    print()
    info("Common paths:")
    info("  Sonoff Zigbee 3.0 / CC2652P:  /dev/ttyUSB0 or /dev/ttyACM0")
    info("  ConBee II:                     /dev/ttyACM0")
    info("  Aeotec Z-Stick Gen5+:          /dev/ttyUSB0 or /dev/ttyACM0")
    info("  HUSBZB-1 (combo Zigbee+ZWave): /dev/ttyUSB0 (Zigbee) /dev/ttyUSB1 (ZWave)")
    print()
    cfg.zigbee_device = prompt("Zigbee USB device path", cfg.zigbee_device)
    cfg.zwave_device  = prompt("Z-Wave USB device path", cfg.zwave_device)
    success(f"Zigbee: {cfg.zigbee_device}  Z-Wave: {cfg.zwave_device}")


def screen_secrets(cfg):
    clear(); header(); section("Passwords & Secrets")
    print()
    info("Passwords are pre-filled with secure random values.")
    info("Press Enter to keep, or type your own.")
    print()
    cfg.mqtt_pass      = prompt("MQTT password (homeassistant user)", cfg.mqtt_pass)
    cfg.nodered_secret = prompt("Node-RED credential secret",         cfg.nodered_secret)
    cfg.influx_pass    = prompt("InfluxDB admin password",            cfg.influx_pass)
    cfg.grafana_pass   = prompt("Grafana admin password",             cfg.grafana_pass)
    cfg.influx_org     = prompt("InfluxDB org name",                  cfg.influx_org)
    cfg.influx_bucket  = prompt("InfluxDB bucket name",               cfg.influx_bucket)
    if cfg.use_vscode:
        cfg.vscode_pass = prompt("Code Server password", cfg.vscode_pass)


def screen_addons(cfg):
    clear(); header(); section("Optional Add-ons")
    print()
    cfg.use_npm       = prompt_bool("Nginx Proxy Manager (SSL / Let's Encrypt)?", cfg.use_npm)
    cfg.use_portainer = prompt_bool("Portainer (Docker web GUI)?",                cfg.use_portainer)
    cfg.use_vscode    = prompt_bool("Code Server (VS Code in browser)?",          cfg.use_vscode)
    cfg.use_vault     = prompt_bool("Vaultwarden (self-hosted Bitwarden)?",       cfg.use_vault)
    cfg.use_wireguard = prompt_bool("WireGuard VPN (remote access)?",             cfg.use_wireguard)
    if cfg.use_wireguard:
        cfg.wg_host = prompt("WireGuard public IP or domain", cfg.wg_host or cfg.ip)
        cfg.wg_port = prompt_int("WireGuard UDP port", 1024, 65535, cfg.wg_port)
    cfg.use_frigate   = prompt_bool("Frigate NVR (AI camera detection)?",         cfg.use_frigate)


def show_summary(cfg):
    clear(); header(); section("Configuration Summary")
    print(f"\n  \033[0;37mHost IP:\033[0m   {cfg.ip}")
    print(f"  \033[0;37mTimezone:\033[0m  {cfg.tz}")
    print(f"  \033[0;37mData dir:\033[0m  {cfg.data_dir}")
    print(f"  \033[0;37mHA port:\033[0m   {cfg.ha_port}  (network: {cfg.ha_network})")
    print(f"  \033[0;37mHomepage:\033[0m  :{cfg.homepage_port}  (Sentinel card link target)")
    print(f"  \033[0;37mZigbee:\033[0m    {cfg.zigbee_device}")
    print(f"  \033[0;37mZ-Wave:\033[0m    {cfg.zwave_device}")
    print()
    print("  \033[1;37mCore services (always on):\033[0m")
    for svc, port in [("Home Assistant", cfg.ha_port), ("Mosquitto MQTT", "1883"),
                      ("Zigbee2MQTT", "8080"), ("Z-Wave JS UI", "8091"),
                      ("Node-RED", cfg.nodered_port), ("InfluxDB", "8086"),
                      ("Grafana", "3001"), ("ESPHome", "6052")]:
        print(f"    \033[1;32m✓\033[0m  {svc:<20} port {port}")
    print()
    print("  \033[1;37mOptional add-ons:\033[0m")
    addons = [
        ("Nginx Proxy Manager", cfg.use_npm,       "80/443/81"),
        ("Portainer",           cfg.use_portainer, "9000/9443"),
        ("Code Server",         cfg.use_vscode,    "8443"),
        ("Vaultwarden",         cfg.use_vault,     "8880"),
        ("WireGuard",           cfg.use_wireguard, str(cfg.wg_port)+"/udp"),
        ("Frigate",             cfg.use_frigate,   "5000"),
    ]
    for name, enabled, port in addons:
        if enabled:
            print(f"    \033[1;32m✓\033[0m  {name:<20} port {port}")
        else:
            print(f"    \033[0;90m✗  {name:<20} (disabled)\033[0m")
    print()


def main_menu(cfg):
    while True:
        clear(); header()
        print("  \033[1;37mMain Menu\033[0m\n")
        print(f"    \033[0;33m1\033[0m.  Network & IP          \033[0;36m{cfg.ip}  ({cfg.ha_network})  homepage:{cfg.homepage_port}\033[0m")
        print(f"    \033[0;33m2\033[0m.  USB adapters          "
              f"Zigbee: {cfg.zigbee_device}  Z-Wave: {cfg.zwave_device}")
        print(f"    \033[0;33m3\033[0m.  Passwords & secrets")
        print(f"    \033[0;33m4\033[0m.  Optional add-ons      "
              + "  ".join(n for n, e, _ in [
                  ("NPM", cfg.use_npm, ""),("Portainer", cfg.use_portainer, ""),
                  ("VSCode", cfg.use_vscode, ""),("Vault", cfg.use_vault, ""),
                  ("WG", cfg.use_wireguard, ""),("Frigate", cfg.use_frigate, ""),
              ] if e) or "none")
        print()
        print(f"    \033[0;33m5\033[0m.  Review summary")
        print(f"    \033[0;33m6\033[0m.  \033[1;32mGenerate files\033[0m")
        print(f"    \033[0;33m7\033[0m.  Quit")
        print()
        choice = prompt_int("Select option (1–7)", 1, 7, 6)
        if   choice == 1: screen_network(cfg)
        elif choice == 2: screen_usb(cfg)
        elif choice == 3: screen_secrets(cfg)
        elif choice == 4: screen_addons(cfg)
        elif choice == 5:
            show_summary(cfg)
            prompt("Press Enter to continue", "")
        elif choice == 6:
            show_summary(cfg)
            print()
            if prompt_bool("Generate files now?", True):
                generate_files(cfg)
                return
        elif choice == 7:
            print("\n  Goodbye!\n")
            sys.exit(0)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    cfg = Config()
    main_menu(cfg)

if __name__ == "__main__":
    main()
