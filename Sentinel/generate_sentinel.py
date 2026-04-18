#!/usr/bin/env python3
"""
Sentinel — DataHearth Master Node Generator
=============================================
Generates:
  sentinel/docker-compose.yml   — dashboard homepage + optional Omada controller
  sentinel/setup.sh             — Debian 13 bootstrap: Docker CE, optional
                                    openvpn (host apt), optional borgbackup (host apt)
  sentinel/servers.json         — editable config: name/ip/port of every other
                                    DataHearth server's homepage to link to
  sentinel/dashboard/index.html — master DataHearth homepage (auto-built from
                                    servers.json + any local services)
  sentinel/DEPLOY.md            — deployment reference

Services (Docker)
-----------------
  homepage   Master DataHearth dashboard    port 80   — singleton, default ON
  omada      TP-Link Omada SDN controller   port 8043 — singleton, default OFF

Host packages (apt-installed, not Docker)
-----------------------------------------
  openvpn    OpenVPN client                           — optional, default OFF
  borgbackup BorgBackup deduplicating backup          — optional, default OFF

servers.json format (edit after generation):
  [
    {"name": "Lexicon",     "ip": "10.50.0.13", "port": 8080, "icon": "🎬"},
    {"name": "Gitea",       "ip": "10.50.0.12", "port": 8600, "icon": "🐙"},
    ...
  ]
"""

import os
import sys
import json

OUTPUT_DIR = "sentinel"

# ──────────────────────────────────────────────────────────────────────────────
# Terminal helpers
# ──────────────────────────────────────────────────────────────────────────────

def clear():
    os.system("clear" if os.name == "posix" else "cls")

def header():
    print("\033[1;33m" + "=" * 62)
    print("   SENTINEL — DATAHEARTH MASTER NODE GENERATOR")
    print("=" * 62 + "\033[0m")
    print()

def section(title):
    pad = max(1, 55 - len(title))
    print(f"\n\033[1;36m── {title} \033[0m" + "─" * pad)

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

def prompt_int(msg, lo=0, hi=9999, default=0):
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


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

# Default linked servers — edit after generation in servers.json
DEFAULT_SERVERS = [
    # homepage_port = the port the VM's own homepage/dashboard is served on.
    # port          = the primary service port shown as secondary info on the card.
    # Cards link to http://ip:homepage_port  and ping that port for status.
    {"name": "Citadel (Home)",   "ip": "10.50.0.30", "homepage_port": 8123, "port": 8123, "icon": "🏠",
     "desc": "Home Assistant, Zigbee2MQTT, Z-Wave, Node-RED, ESPHome"},
    {"name": "Lexicon (Media)",  "ip": "10.50.0.13", "homepage_port": 8080, "port": 8080, "icon": "🎬",
     "desc": "Jellyfin, Kavita, Navidrome, Audiobookshelf"},
    {"name": "Codex (Services)", "ip": "10.50.0.12", "homepage_port": 8080, "port": 8080, "icon": "📦",
     "desc": "Gitea, Nextcloud, Kiwix, Manyfold, RomM"},
    {"name": "Deepthought (AI)", "ip": "10.50.0.14", "homepage_port": 8080, "port": 8080, "icon": "🤖",
     "desc": "Ollama, OpenWebUI"},
    {"name": "Echo (STT)",       "ip": "10.50.0.20", "homepage_port": 8080, "port": 8080, "icon": "🎙️",
     "desc": "Ollama, Whisper STT"},
]

OMADA_PORTS = [8088, 8043, 8843, 29810, 29811, 29812, 29813, 29814]

class Config:
    def __init__(self):
        self.ip                = "10.50.0.10"
        self.homepage_port     = 80
        self.omada_enabled     = False
        self.omada_http_port   = 8088
        self.omada_https_port  = 8043
        self.openvpn_enabled   = False
        self.borgbackup_enabled = False
        self.data_dir          = "/mnt/disk0/sentinel"
        self.servers           = [dict(s) for s in DEFAULT_SERVERS]


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard HTML generator
# ──────────────────────────────────────────────────────────────────────────────

def gen_dashboard_html(cfg):
    """Generate the master DataHearth homepage HTML."""

    # Build server cards from servers list
    server_cards_js = json.dumps(cfg.servers, indent=2)

    # Local service cards (Omada if enabled)
    local_services = []
    if cfg.omada_enabled:
        local_services.append({
            "name": "Omada Controller",
            "icon": "📡",
            "desc": "TP-Link SDN Network Controller",
            "url":  f"http://{cfg.ip}:{cfg.omada_https_port}",
            "port": cfg.omada_https_port,
        })

    local_js = json.dumps(local_services, indent=2)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>DataHearth — Sentinel</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Oxanium:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:      #07090e;
    --surf:    #0d1117;
    --surf2:   #111820;
    --border:  #1c2535;
    --accent:  #f0a500;
    --accent2: #00bfff;
    --glow:    rgba(240,165,0,.12);
    --text:    #cdd6e0;
    --muted:   #4a5568;
    --green:   #3fb950;
    --red:     #f85149;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Oxanium', sans-serif;
    min-height: 100vh;
  }}

  /* ── Header ── */
  header {{
    background: var(--surf);
    border-bottom: 1px solid var(--border);
    padding: 1.2rem 2.5rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    position: sticky;
    top: 0;
    z-index: 100;
  }}
  .logo {{
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #fff;
  }}
  .logo span {{ color: var(--accent); }}
  .logo-sub {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .7rem;
    color: var(--muted);
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-left: .25rem;
  }}
  .host-badge {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .72rem;
    color: var(--accent);
    border: 1px solid var(--accent);
    padding: .2rem .6rem;
    border-radius: 4px;
    opacity: .75;
  }}
  .clock {{
    margin-left: auto;
    font-family: 'Share Tech Mono', monospace;
    font-size: .85rem;
    color: var(--muted);
  }}

  /* ── Layout ── */
  main {{ padding: 2rem 2.5rem; max-width: 1600px; margin: 0 auto; }}

  /* ── Section headers ── */
  .section-title {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .15em;
    color: var(--muted);
    margin: 2rem 0 1rem;
    padding-left: .2rem;
    display: flex;
    align-items: center;
    gap: .75rem;
  }}
  .section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}

  /* ── Server grid ── */
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }}
  .card {{
    background: var(--surf);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.4rem;
    text-decoration: none;
    color: var(--text);
    display: flex;
    flex-direction: column;
    gap: .5rem;
    transition: border-color .15s, transform .15s, box-shadow .15s;
    position: relative;
    overflow: hidden;
    cursor: pointer;
  }}
  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    opacity: 0;
    transition: opacity .15s;
  }}
  .card:hover {{
    border-color: var(--accent2);
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0,191,255,.08);
  }}
  .card:hover::before {{ opacity: 1; }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: .75rem;
  }}
  .card-icon {{ font-size: 1.6rem; }}
  .card-name {{
    font-size: 1rem;
    font-weight: 700;
    color: #e6edf3;
    flex: 1;
  }}
  .status-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted);
    flex-shrink: 0;
  }}
  .status-dot.up    {{ background: var(--green); box-shadow: 0 0 6px var(--green); }}
  .status-dot.down  {{ background: var(--red);   box-shadow: 0 0 6px var(--red); }}
  .card-desc {{
    font-size: .78rem;
    color: var(--muted);
    line-height: 1.5;
  }}
  .card-meta {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: .25rem;
  }}
  .card-ip {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .68rem;
    color: var(--accent2);
  }}
  .card-port {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .65rem;
    color: var(--muted);
  }}

  /* ── Local services ── */
  .local-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: .75rem;
  }}
  .local-card {{
    background: var(--surf2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.1rem;
    text-decoration: none;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: .85rem;
    transition: border-color .15s, transform .12s;
  }}
  .local-card:hover {{
    border-color: var(--accent);
    transform: translateY(-1px);
  }}
  .local-icon {{ font-size: 1.4rem; }}
  .local-info {{ flex: 1; }}
  .local-name {{ font-size: .9rem; font-weight: 600; color: #fff; }}
  .local-desc {{ font-size: .7rem; color: var(--muted); margin-top: .15rem; }}
  .local-port {{
    font-family: 'Share Tech Mono', monospace;
    font-size: .65rem;
    color: var(--accent);
  }}

  footer {{
    margin-top: 3rem;
    padding: 1.5rem 2.5rem;
    border-top: 1px solid var(--border);
    font-family: 'Share Tech Mono', monospace;
    font-size: .65rem;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">Data<span>Hearth</span><span class="logo-sub"> / Sentinel</span></div>
  </div>
  <div class="host-badge" id="host-badge">{cfg.ip}</div>
  <div class="clock" id="clock"></div>
</header>

<main>
  <!-- ── Remote servers ── -->
  <div class="section-title">DataHearth Nodes</div>
  <div class="grid" id="server-grid">Loading…</div>

  <!-- ── Local services (Omada etc.) ── -->
  <div id="local-section" style="display:none">
    <div class="section-title">Local Services</div>
    <div class="local-grid" id="local-grid"></div>
  </div>
</main>

<footer>
  <span>DataHearth · Sentinel</span>
  <span id="footer-time"></span>
</footer>

<script>
// ── Data ─────────────────────────────────────────────────────────────────────
// Remote servers — edit sentinel/servers.json to update this list.
// The dashboard reads servers.json at load time; just refresh to pick up changes.
const SERVERS = {server_cards_js};
const LOCAL   = {local_js};

// ── Clock ────────────────────────────────────────────────────────────────────
function tick() {{
  const now = new Date();
  const ts  = now.toLocaleTimeString('en-US', {{hour12: false}});
  const dt  = now.toLocaleDateString('en-US', {{weekday:'short', month:'short', day:'numeric'}});
  document.getElementById('clock').textContent = dt + '  ' + ts;
  document.getElementById('footer-time').textContent = 'Last refresh: ' + ts;
}}
tick();
setInterval(tick, 1000);

// ── Ping servers ─────────────────────────────────────────────────────────────
async function checkServer(ip, port) {{
  const url = `http://${{ip}}:${{port}}`;
  try {{
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3000);
    await fetch(url, {{ mode: 'no-cors', signal: ctrl.signal, cache: 'no-store' }});
    clearTimeout(timer);
    return 'up';
  }} catch (e) {{
    return 'down';
  }}
}}

// ── Render servers ────────────────────────────────────────────────────────────
async function renderServers() {{
  const grid = document.getElementById('server-grid');
  grid.innerHTML = '';

  for (const s of SERVERS) {{
    // homepage_port = the port the VM's dashboard is served on (what we link to).
    // port          = the primary service port (shown as secondary info).
    const hport = s.homepage_port || s.port;
    const url   = `http://${{s.ip}}:${{hport}}`;
    const card  = document.createElement('a');
    card.href   = url;
    card.target = '_blank';
    card.className = 'card';
    // Show homepage port as the clickable destination; show service port if different
    const portLabel = (s.port && s.port !== hport)
      ? `:${{hport}} <span style="color:var(--muted);font-size:.6rem">(svc :${{s.port}})</span>`
      : `:${{hport}}`;
    card.innerHTML = `
      <div class="card-header">
        <span class="card-icon">${{s.icon || '🖥️'}}</span>
        <span class="card-name">${{s.name}}</span>
        <span class="status-dot" id="dot-${{s.ip}}-${{hport}}"></span>
      </div>
      <div class="card-desc">${{s.desc || ''}}</div>
      <div class="card-meta">
        <span class="card-ip">${{s.ip}}</span>
        <span class="card-port">${{portLabel}}</span>
      </div>`;
    grid.appendChild(card);

    // Async status check against the homepage port
    checkServer(s.ip, hport).then(status => {{
      const dot = document.getElementById(`dot-${{s.ip}}-${{hport}}`);
      if (dot) dot.className = `status-dot ${{status}}`;
    }});
  }}
}}

// ── Render local services ─────────────────────────────────────────────────────
function renderLocal() {{
  if (!LOCAL.length) return;
  document.getElementById('local-section').style.display = 'block';
  const grid = document.getElementById('local-grid');
  for (const svc of LOCAL) {{
    const a = document.createElement('a');
    a.href   = svc.url;
    a.target = '_blank';
    a.className = 'local-card';
    a.innerHTML = `
      <span class="local-icon">${{svc.icon}}</span>
      <div class="local-info">
        <div class="local-name">${{svc.name}}</div>
        <div class="local-desc">${{svc.desc}}</div>
      </div>
      <span class="local-port">:${{svc.port}}</span>`;
    grid.appendChild(a);
  }}
}}

renderServers();
renderLocal();
</script>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Compose generators
# ──────────────────────────────────────────────────────────────────────────────

def gen_compose_header(cfg):
    return f"""\
version: '3.8'
# ==============================================================================
# SENTINEL — DATAHEARTH MASTER NODE
# Host: {cfg.ip}
# Generated by generate_sentinel.py
# ==============================================================================

services:
"""


def gen_homepage_service(cfg):
    return f"""
  # ============================================================================
  # DATAHEARTH HOMEPAGE — Master dashboard linking all DataHearth nodes
  # Edit sentinel/servers.json to add/remove servers.
  # The page auto-refreshes every 60 s and pings each server for live status.
  # ============================================================================
  homepage:
    image: nginx:alpine
    container_name: datahearth-homepage
    restart: unless-stopped
    ports:
      - "{cfg.homepage_port}:80"
    volumes:
      - {cfg.data_dir}/homepage:/usr/share/nginx/html:ro
      - {cfg.data_dir}/homepage/nginx.conf:/etc/nginx/conf.d/default.conf:ro
"""


def gen_omada_service(cfg):
    return f"""
  # ============================================================================
  # OMADA SDN CONTROLLER — TP-Link network management
  # Management HTTPS: https://{cfg.ip}:{cfg.omada_https_port}
  # Management HTTP:  http://{cfg.ip}:{cfg.omada_http_port}
  #
  # IMPORTANT: Stop with  docker stop --time 60 omada-controller
  #            to allow MongoDB to shut down cleanly. Abrupt stops
  #            can cause database corruption.
  # ============================================================================
  omada-controller:
    image: mbentley/omada-controller:latest
    container_name: omada-controller
    restart: unless-stopped
    network_mode: host
    stop_grace_period: 60s
    ulimits:
      nofile:
        soft: 4096
        hard: 8192
    environment:
      - MANAGE_HTTP_PORT={cfg.omada_http_port}
      - MANAGE_HTTPS_PORT={cfg.omada_https_port}
      - PORTAL_HTTP_PORT={cfg.omada_http_port}
      - PORTAL_HTTPS_PORT={cfg.omada_https_port}
      - SHOW_SERVER_LOGS=true
      - SHOW_MONGODB_LOGS=false
      - TZ=America/Chicago
    volumes:
      - {cfg.data_dir}/omada/data:/opt/tplink/EAPController/data
      - {cfg.data_dir}/omada/logs:/opt/tplink/EAPController/logs
      - {cfg.data_dir}/omada/work:/opt/tplink/EAPController/work
"""


def gen_nginx_conf():
    return """\
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Serve servers.json so the page can be updated without rebuilding
    location /servers.json {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Access-Control-Allow-Origin "*";
    }
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Setup script generator
# ──────────────────────────────────────────────────────────────────────────────

def gen_setup_script(cfg):
    ip = cfg.ip

    # ── Directories ───────────────────────────────────────────────────────────
    dirs = [
        f"{cfg.data_dir}/homepage",
    ]
    if cfg.omada_enabled:
        dirs += [
            f"{cfg.data_dir}/omada/data",
            f"{cfg.data_dir}/omada/logs",
            f"{cfg.data_dir}/omada/work",
        ]

    mkdir_lines = "\n".join(f'  mkdir -p "{d}"' for d in sorted(dirs))

    # ── Host package installs ─────────────────────────────────────────────────
    host_pkgs = []
    openvpn_section = ""
    if cfg.openvpn_enabled:
        host_pkgs.append("openvpn")
        openvpn_section = """\

# ==============================================================================
# OPENVPN CLIENT — installed on host (not in Docker)
# Config files go in /etc/openvpn/client/<name>.conf
# Start a VPN:   sudo systemctl start openvpn-client@<name>
# Enable on boot: sudo systemctl enable openvpn-client@<name>
# ==============================================================================
section "Configuring OpenVPN client"

mkdir -p /etc/openvpn/client
log "OpenVPN client installed. Place your .ovpn / .conf files in /etc/openvpn/client/"
log "Example: sudo systemctl start openvpn-client@myvpn"
warn "Copy your .ovpn config to /etc/openvpn/client/ before starting the service."
"""

    borg_section = ""
    if cfg.borgbackup_enabled:
        host_pkgs.append("borgbackup")
        borg_section = """\

# ==============================================================================
# BORGBACKUP — installed on host (not in Docker)
# Usage:  borg init --encryption=repokey /path/to/repo
#         borg create /path/to/repo::archive-$(date +%Y-%m-%d) /data/to/back/up
# Remote: borg init --encryption=repokey user@backup-host:/path/to/repo
# ==============================================================================
section "BorgBackup post-install notes"

log "borgbackup installed. Quick reference:"
log "  Init local repo:  borg init --encryption=repokey /mnt/backup/sentinel"
log "  Create archive:   borg create /mnt/backup/sentinel::daily-\\$(date +%F) /mnt/disk0"
log "  List archives:    borg list /mnt/backup/sentinel"
log "  Mount for restore: borg mount /mnt/backup/sentinel /tmp/restore"
warn "Remember to store your BORG_PASSPHRASE securely!"
"""

    if host_pkgs:
        host_install = (
            f"apt-get install -y -qq {' '.join(host_pkgs)}\n"
            f'log "Host packages installed: {", ".join(host_pkgs)}"'
        )
        host_section = f"""\

# ==============================================================================
# HOST PACKAGES — installed directly on the host (not in Docker)
# ==============================================================================
section "Installing host packages: {', '.join(host_pkgs)}"

{host_install}
"""
    else:
        host_section = ""

    # ── Omada firewall note ───────────────────────────────────────────────────
    omada_ufw = ""
    if cfg.omada_enabled:
        omada_ufw = f"""\

# Omada controller ports (host network mode)
ufw allow {cfg.omada_http_port}/tcp  comment "Omada HTTP"
ufw allow {cfg.omada_https_port}/tcp comment "Omada HTTPS"
ufw allow 8843/tcp   comment "Omada Portal HTTPS"
ufw allow 29810/udp  comment "Omada discovery"
ufw allow 29811/tcp  comment "Omada device mgmt"
ufw allow 29812/tcp  comment "Omada device mgmt"
ufw allow 29813/tcp  comment "Omada device mgmt"
ufw allow 29814/tcp  comment "Omada device mgmt"
log "Omada ports opened in ufw"
"""

    services_str = "Homepage"
    if cfg.omada_enabled:
        services_str += ", Omada SDN Controller"
    if cfg.openvpn_enabled:
        services_str += ", OpenVPN client (host)"
    if cfg.borgbackup_enabled:
        services_str += ", BorgBackup (host)"

    return f"""\
#!/usr/bin/env bash
# ==============================================================================
#  SENTINEL — DATAHEARTH MASTER NODE BOOTSTRAP
#  Target:   Debian 13 (Trixie)
#  Host IP:  {ip}
#  Services: {services_str}
#  Generated by generate_sentinel.py
#
#  Run as root:  sudo bash setup.sh
# ==============================================================================

set -euo pipefail

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
echo -e "${{BLD}}   SENTINEL — DATAHEARTH MASTER NODE — Debian 13${{RST}}"
echo -e "${{BLD}}   Host: {ip}${{RST}}"
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
  tmux \\
  vim \\
  nano \\
  net-tools \\
  dnsutils \\
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

if ! apt-cache show docker-ce &>/dev/null 2>&1; then
  warn "Docker repo has no packages for $CODENAME — using bookworm"
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
{host_section}
# ==============================================================================
# 3. STORAGE — /mnt/disk0 check
# ==============================================================================
section "Checking /mnt/disk0 mount"

if mountpoint -q /mnt/disk0 2>/dev/null; then
  log "/mnt/disk0 is mounted"
elif [ -d /mnt/disk0 ]; then
  warn "/mnt/disk0 exists but is not a separate mount — using as local dir"
else
  mkdir -p /mnt/disk0
  warn "/mnt/disk0 created. Mount your disk here if needed."
fi

# ==============================================================================
# 4. DIRECTORIES
# ==============================================================================
section "Creating Sentinel data directories"

{mkdir_lines}

chown -R "$CALLING_UID:$CALLING_GID" {cfg.data_dir} 2>/dev/null || true
log "Directories created"

# ==============================================================================
# 5. DOCKER DAEMON CONFIG
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
  "live-restore": true,
  "userland-proxy": false
}}
DAEMONEOF
  systemctl reload docker || systemctl restart docker
  log "Docker daemon config written"
else
  warn "/etc/docker/daemon.json already exists — skipping"
fi

# ==============================================================================
# 6. FIREWALL (ufw)
# ==============================================================================
section "Configuring firewall (ufw)"

if command -v ufw &>/dev/null; then
  warn "ufw already present — adding rules only"
else
  apt-get install -y -qq ufw
fi

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow {cfg.homepage_port}/tcp  comment "DataHearth Homepage"
{omada_ufw}
ufw --force enable
log "ufw configured"

# ==============================================================================
# 7. SYSCTL TUNING
# ==============================================================================
section "Applying sysctl tuning"

cat > /etc/sysctl.d/99-sentinel.conf << 'SYSCTLEOF'
# Sentinel tuning
vm.swappiness = 10
net.core.somaxconn = 65535
net.ipv4.tcp_tw_reuse = 1
fs.inotify.max_user_watches = 524288
SYSCTLEOF
sysctl -p /etc/sysctl.d/99-sentinel.conf >/dev/null 2>&1 || true
log "sysctl tuning applied"

# ==============================================================================
# 8. WEEKLY DOCKER CLEANUP
# ==============================================================================
section "Weekly Docker cleanup cron"
cat > /etc/cron.weekly/docker-cleanup << 'CRONEOF'
#!/bin/bash
docker system prune -f --filter "until=168h" >> /var/log/docker-cleanup.log 2>&1
CRONEOF
chmod +x /etc/cron.weekly/docker-cleanup
log "Cron installed"
{openvpn_section}{borg_section}
# ==============================================================================
# DONE
# ==============================================================================
echo ""
echo -e "${{GRN}}============================================================${{RST}}"
echo -e "${{GRN}}  Sentinel bootstrap complete!${{RST}}"
echo -e "${{GRN}}============================================================${{RST}}"
echo ""
echo -e "  ${{BLD}}Next steps:${{RST}}"
echo -e "  1. ${{CYN}}Re-login${{RST}} (or ${{CYN}}newgrp docker${{RST}}) for docker group"
echo -e "  2. Deploy the stack:"
echo -e "     ${{CYN}}docker compose up -d${{RST}}"
echo -e "  3. Master dashboard:"
echo -e "     ${{CYN}}http://{ip}:{cfg.homepage_port}${{RST}}"
{"".join([f'  echo -e "  4. Omada controller (HTTPS):\\n     ${{CYN}}https://{ip}:{cfg.omada_https_port}${{RST}}"' if cfg.omada_enabled else ''])}
echo ""
"""


# ──────────────────────────────────────────────────────────────────────────────
# DEPLOY.md
# ──────────────────────────────────────────────────────────────────────────────

def gen_deploy_md(cfg):
    omada_note = (
        f"\n## Omada Controller\n"
        f"#   HTTPS: https://{cfg.ip}:{cfg.omada_https_port}\n"
        f"#   HTTP:  http://{cfg.ip}:{cfg.omada_http_port}\n"
        f"#   STOP SAFELY: docker stop --time 60 omada-controller\n"
        f"#   (abrupt stop risks MongoDB corruption)\n"
        if cfg.omada_enabled else ""
    )
    openvpn_note = (
        "\n## OpenVPN client (host)\n"
        "#   Config dir: /etc/openvpn/client/\n"
        "#   Start:   sudo systemctl start openvpn-client@<name>\n"
        "#   Enable:  sudo systemctl enable openvpn-client@<name>\n"
        if cfg.openvpn_enabled else ""
    )
    borg_note = (
        "\n## BorgBackup (host)\n"
        "#   Init:    borg init --encryption=repokey /mnt/backup/sentinel\n"
        "#   Backup:  borg create /mnt/backup/sentinel::daily-$(date +%F) /mnt/disk0\n"
        "#   List:    borg list /mnt/backup/sentinel\n"
        "#   Mount:   borg mount /mnt/backup/sentinel /tmp/restore\n"
        if cfg.borgbackup_enabled else ""
    )

    return f"""\
# SENTINEL — DATAHEARTH MASTER NODE DEPLOYMENT
# Host: {cfg.ip}
# Generated by generate_sentinel.py

## Quick start

# 1. Copy this folder to the server
#    scp -r sentinel/ {cfg.ip}:~/

# 2. Bootstrap
#    ssh {cfg.ip} "cd sentinel && sudo bash setup.sh"

# 3. Copy homepage files
#    ssh {cfg.ip} "sudo cp -r dashboard/* /mnt/disk0/sentinel/homepage/"

# 4. Start the stack
#    ssh {cfg.ip} "cd sentinel && docker compose up -d"

# 5. Master dashboard
#    http://{cfg.ip}:{cfg.homepage_port}

## Updating the server list
#   Edit sentinel/servers.json (or /mnt/disk0/sentinel/homepage/servers.json
#   on the host). The page reloads it on every browser refresh — no rebuild needed.

## Services
#   DataHearth Homepage:  http://{cfg.ip}:{cfg.homepage_port}
{omada_note}{openvpn_note}{borg_note}
## servers.json format
#   [
#     {{"name": "Lexicon", "ip": "10.50.0.13", "port": 8080,
#       "icon": "🎬", "desc": "Jellyfin, Kavita, Navidrome"}},
#     ...
#   ]
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
    parts = [gen_compose_header(cfg), gen_homepage_service(cfg)]
    if cfg.omada_enabled:
        parts.append(gen_omada_service(cfg))

    with open("docker-compose.yml", "w") as f:
        f.write("".join(parts))
    success("Written: docker-compose.yml")

    # ── setup.sh ──────────────────────────────────────────────────────────────
    with open("setup.sh", "w") as f:
        f.write(gen_setup_script(cfg))
    os.chmod("setup.sh", 0o755)
    success("Written: setup.sh")

    # ── servers.json ──────────────────────────────────────────────────────────
    with open("servers.json", "w") as f:
        json.dump(cfg.servers, f, indent=2, ensure_ascii=False)
        f.write("\n")
    success("Written: servers.json  ← edit this to add/remove servers")

    # ── dashboard/index.html ──────────────────────────────────────────────────
    os.makedirs("dashboard", exist_ok=True)
    with open("dashboard/index.html", "w") as f:
        f.write(gen_dashboard_html(cfg))
    success("Written: dashboard/index.html")

    # ── nginx config ──────────────────────────────────────────────────────────
    with open("dashboard/nginx.conf", "w") as f:
        f.write(gen_nginx_conf())
    success("Written: dashboard/nginx.conf")

    # ── DEPLOY.md ─────────────────────────────────────────────────────────────
    with open("DEPLOY.md", "w") as f:
        f.write(gen_deploy_md(cfg))
    success("Written: DEPLOY.md")

    os.chdir(orig_cwd)

    print()
    print("\033[1;32m" + "=" * 62)
    print("  Sentinel files generated!")
    print("=" * 62 + "\033[0m")
    print()
    print(f"  Output: \033[1;37m{out_abs}/\033[0m")
    print()
    print("  Next steps:")
    print(f"    1. Edit \033[0;36m{OUTPUT_DIR}/servers.json\033[0m to list your other servers")
    print(f"    2. \033[0;36mscp -r {OUTPUT_DIR}/ {cfg.ip}:~/\033[0m")
    print(f"    3. \033[0;36mssh {cfg.ip} 'cd {OUTPUT_DIR} && sudo bash setup.sh'\033[0m")
    print(f"    4. \033[0;36mssh {cfg.ip} 'sudo cp -r {OUTPUT_DIR}/dashboard/* /mnt/disk0/sentinel/homepage/'\033[0m")
    print(f"    5. \033[0;36mssh {cfg.ip} 'cd {OUTPUT_DIR} && docker compose up -d'\033[0m")
    print(f"    6. \033[0;36mhttp://{cfg.ip}:{cfg.homepage_port}\033[0m")
    print()
    print("  To update the server list later:")
    print(f"    Edit \033[0;36m/mnt/disk0/sentinel/homepage/servers.json\033[0m on the host")
    print(f"    and refresh the browser — no restart needed.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Menu — server list editor
# ──────────────────────────────────────────────────────────────────────────────

COMMON_ICONS = ["🖥️","🎬","📦","🤖","🎙️","📡","🐙","☁️","📚","🔊","🎵","📺","🏠","⚙️","🔒"]

def screen_servers(cfg):
    while True:
        clear(); header()
        section("DataHearth Nodes (servers.json)")
        info("These are the other DataHearth servers linked from the master homepage.")
        info("homepage_port = port the VM's dashboard is served on (card link target).")
        info("port          = primary service port (shown as secondary info on card).")
        info("Edit freely — saved to servers.json; no rebuild needed to update.")
        print()
        if cfg.servers:
            for i, s in enumerate(cfg.servers, 1):
                hport = s.get('homepage_port', s['port'])
                sport = s['port']
                port_str = (f"\033[0;36m→:{hport}\033[0m  svc:{sport}"
                            if hport != sport else f"\033[0;36m:{hport}\033[0m")
                print(f"    \033[0;33m{i}\033[0m.  {s['icon']}  {s['name']:<22} "
                      f"{s['ip']}  {port_str}")
        else:
            print("    \033[0;90m(no servers configured yet)\033[0m")
        print()
        print(f"    \033[0;33ma\033[0m.  Add server")
        print(f"    \033[0;33md\033[0m.  Delete server")
        print(f"    \033[0;33mb\033[0m.  Back")
        print()

        choice = prompt("Select (number to edit, a=add, d=delete, b=back)", "b").strip().lower()

        if choice == "b":
            return
        elif choice == "a":
            print()
            name = prompt("  Server name (e.g. Lexicon, Gitea…)", "")
            if not name:
                continue
            ip          = prompt("  IP address", "10.50.0.")
            homepage_port = prompt_int("  Homepage port (dashboard link target)", 1, 65535, 8080)
            port        = prompt_int("  Service port (primary app port, shown as info)", 1, 65535, homepage_port)
            desc        = prompt("  Description (optional)", "")
            print()
            info("Available icons: " + "  ".join(COMMON_ICONS))
            icon = prompt("  Icon (emoji)", "🖥️")
            cfg.servers.append({"name": name, "ip": ip,
                                  "homepage_port": homepage_port, "port": port,
                                  "icon": icon, "desc": desc})
            success(f"Added: {name}")
        elif choice == "d":
            if not cfg.servers:
                continue
            idx_str = prompt("  Delete which number?", "")
            try:
                idx = int(idx_str) - 1
                if 0 <= idx < len(cfg.servers):
                    removed = cfg.servers.pop(idx)
                    success(f"Removed: {removed['name']}")
            except (ValueError, TypeError):
                pass
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(cfg.servers):
                    s = cfg.servers[idx]
                    print()
                    s['name']         = prompt("  Name", s['name']) or s['name']
                    s['ip']           = prompt("  IP",   s['ip'])   or s['ip']
                    s['homepage_port'] = prompt_int("  Homepage port (dashboard link target)",
                                                    1, 65535, s.get('homepage_port', s['port']))
                    s['port']         = prompt_int("  Service port (primary app, shown as info)",
                                                    1, 65535, s['port'])
                    s['desc']         = prompt("  Description", s.get('desc',''))
                    s['icon']         = prompt("  Icon", s.get('icon','🖥️'))
                    success(f"Updated: {s['name']}")
            except (ValueError, TypeError):
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Menu screens
# ──────────────────────────────────────────────────────────────────────────────

def screen_ip(cfg):
    clear(); header(); section("Server IP Address"); print()
    cfg.ip = prompt("Enter Sentinel server IP", cfg.ip)
    success(f"IP set to {cfg.ip}")

def screen_services(cfg):
    clear(); header()
    section("Docker Services")
    info("Homepage is always on (it's the whole point of Sentinel).")
    print()
    info("Omada SDN Controller — TP-Link network management via Docker.")
    info("Uses host networking so it can discover devices on the LAN.")
    cfg.omada_enabled = prompt_bool("Enable Omada SDN Controller?", cfg.omada_enabled)
    if cfg.omada_enabled:
        cfg.omada_http_port  = prompt_int("  Omada HTTP port",  1, 65535, cfg.omada_http_port)
        cfg.omada_https_port = prompt_int("  Omada HTTPS port", 1, 65535, cfg.omada_https_port)
        success(f"Omada enabled — HTTPS on port {cfg.omada_https_port}")
    else:
        info("Omada disabled.")

def screen_host_pkgs(cfg):
    clear(); header()
    section("Host Packages (apt-installed on host, not Docker)")
    print()
    info("OpenVPN client — installed on host, lets the server connect")
    info("to a remote VPN. Place .ovpn files in /etc/openvpn/client/.")
    cfg.openvpn_enabled = prompt_bool("Install OpenVPN client on host?", cfg.openvpn_enabled)
    print()
    info("BorgBackup — deduplicating, encrypted backup tool installed")
    info("on host. Use to back up /mnt/disk0 or other data to a remote server.")
    cfg.borgbackup_enabled = prompt_bool("Install BorgBackup on host?", cfg.borgbackup_enabled)

def screen_paths(cfg):
    clear(); header(); section("Storage Paths"); print()
    cfg.data_dir       = prompt("Data directory base", cfg.data_dir)
    cfg.homepage_port  = prompt_int("Homepage port", 1, 65535, cfg.homepage_port)

def show_summary(cfg):
    clear(); header(); section("Configuration Summary")
    print(f"\n  \033[0;37mHost IP:\033[0m        {cfg.ip}")
    print(f"  \033[0;37mData dir:\033[0m       {cfg.data_dir}")
    print(f"  \033[0;37mHomepage port:\033[0m  {cfg.homepage_port}")
    print()
    print("  \033[1;37mDocker services:\033[0m")
    print(f"    \033[1;32m✓\033[0m  DataHearth Homepage    port {cfg.homepage_port}")
    if cfg.omada_enabled:
        print(f"    \033[1;32m✓\033[0m  Omada SDN Controller   HTTPS:{cfg.omada_https_port}  HTTP:{cfg.omada_http_port}")
    else:
        print(f"    \033[0;90m✗  Omada SDN Controller   (disabled)\033[0m")
    print()
    print("  \033[1;37mHost packages (apt):\033[0m")
    print(f"    {'✓' if cfg.openvpn_enabled else '✗'}  OpenVPN client"
          + ("" if cfg.openvpn_enabled else "  \033[0;90m(disabled)\033[0m"))
    print(f"    {'✓' if cfg.borgbackup_enabled else '✗'}  BorgBackup"
          + ("" if cfg.borgbackup_enabled else "  \033[0;90m(disabled)\033[0m"))
    print()
    print(f"  \033[1;37mLinked servers ({len(cfg.servers)}):\033[0m")
    for s in cfg.servers:
        hport = s.get('homepage_port', s['port'])
        sport = s['port']
        port_str = (f"→:{hport}  svc:{sport}" if hport != sport else f":{hport}")
        print(f"    {s['icon']}  {s['name']:<22} {s['ip']}  {port_str}")
    print()


def main_menu(cfg):
    while True:
        clear(); header()
        print("  \033[1;37mMain Menu\033[0m\n")
        print(f"    \033[0;33m1\033[0m.  Server IP              \033[0;36m{cfg.ip}\033[0m")
        print(f"    \033[0;33m2\033[0m.  Docker services        "
              f"Homepage=on  Omada={'on' if cfg.omada_enabled else 'off'}")
        print(f"    \033[0;33m3\033[0m.  Host packages (apt)    "
              f"OpenVPN={'on' if cfg.openvpn_enabled else 'off'}  "
              f"Borg={'on' if cfg.borgbackup_enabled else 'off'}")
        print(f"    \033[0;33m4\033[0m.  Storage / ports        "
              f"port {cfg.homepage_port}  →  {cfg.data_dir}")
        print(f"    \033[0;33m5\033[0m.  Linked servers         "
              f"{len(cfg.servers)} configured")
        print()
        print(f"    \033[0;33m6\033[0m.  Review summary")
        print(f"    \033[0;33m7\033[0m.  \033[1;32mGenerate files\033[0m")
        print(f"    \033[0;33m8\033[0m.  Quit")
        print()

        choice = prompt_int("Select option (1–8)", 1, 8, 7)
        if   choice == 1: screen_ip(cfg)
        elif choice == 2: screen_services(cfg)
        elif choice == 3: screen_host_pkgs(cfg)
        elif choice == 4: screen_paths(cfg)
        elif choice == 5: screen_servers(cfg)
        elif choice == 6:
            show_summary(cfg)
            prompt("Press Enter to continue", "")
        elif choice == 7:
            show_summary(cfg)
            print()
            if prompt_bool("Generate files now?", True):
                generate_files(cfg)
                return
        elif choice == 8:
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
