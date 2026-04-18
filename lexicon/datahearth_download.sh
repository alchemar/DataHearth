#!/usr/bin/env bash
# =============================================================================
# DataHearth Download Manager
# Manages downloads for: Gutenberg, Exodus, Kiwix ZIMs, Headway Maps,
# Free Music Archive, Thingiverse (IA), and other Internet Archive hoards
# =============================================================================

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# --- Config ---
BASE_DIR="${DATAHEARTH_DIR:-$(pwd)/datahearth}"
LOG_DIR="$BASE_DIR/logs"
IA_PROGRESS_FILE="$BASE_DIR/ia_download_progress.txt"
IA_API_KEY_FILE="$BASE_DIR/.ia_api_key"

# Per-service download directories
GUTENBERG_DIR="$BASE_DIR/gutenberg"
EXODUS_DIR="$BASE_DIR/exodus"
ZIM_DIR="$BASE_DIR/kiwix/zims"
HEADWAY_DIR="$BASE_DIR/headway/maps"
MUSIC_DIR="$BASE_DIR/music"
IA_DIR="$BASE_DIR/internet_archive"

# Delay settings (seconds) — tune to avoid rate-limiting
IA_DELAY_BETWEEN_ITEMS=5
IA_DELAY_BETWEEN_FILES=2
GENERAL_DELAY=1

# =============================================================================
# HELPERS
# =============================================================================

log()     { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; }
info()    { echo -e "${CYAN}[i]${NC} $*"; }
header()  { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════${NC}"; echo -e "${BOLD}${BLUE}  $*${NC}"; echo -e "${BOLD}${BLUE}══════════════════════════════════════${NC}"; }
separator(){ echo -e "${BLUE}──────────────────────────────────────${NC}"; }

require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        error "Required command '$1' not found. Install it first."
        exit 1
    fi
}

# Pause with message
pause() {
    local secs="${1:-$GENERAL_DELAY}"
    sleep "$secs"
}

# Download with resume support
safe_download() {
    local url="$1"
    local dest="$2"
    local label="${3:-file}"

    mkdir -p "$(dirname "$dest")"

    if [[ -f "$dest" ]]; then
        info "Already exists, skipping: $label"
        return 0
    fi

    info "Downloading: $label"
    if command -v aria2c &>/dev/null; then
        aria2c --continue=true --max-tries=5 --retry-wait=10 \
               --dir="$(dirname "$dest")" --out="$(basename "$dest")" \
               "$url" 2>/dev/null || warn "aria2c failed for $label"
    else
        wget --continue --tries=5 --waitretry=10 --timeout=30 \
             -O "$dest" "$url" || warn "wget failed for $label"
    fi
}

# =============================================================================
# IA PROGRESS TRACKING
# =============================================================================

ia_mark_done() {
    local key="$1"
    echo "$key" >> "$IA_PROGRESS_FILE"
}

ia_is_done() {
    local key="$1"
    [[ -f "$IA_PROGRESS_FILE" ]] && grep -qxF "$key" "$IA_PROGRESS_FILE"
}

# =============================================================================
# API KEY MANAGEMENT
# =============================================================================

setup_ia_api_key() {
    mkdir -p "$BASE_DIR"
    if [[ -f "$IA_API_KEY_FILE" ]]; then
        IA_API_KEY=$(cat "$IA_API_KEY_FILE")
        info "Loaded Internet Archive API key from $IA_API_KEY_FILE"
        return 0
    fi

    header "Internet Archive API Key Setup"
    echo ""
    echo -e "  ${BOLD}You need an Internet Archive account and S3-like API keys.${NC}"
    echo -e "  ${YELLOW}1.${NC} Sign up / log in at: https://archive.org/account/login"
    echo -e "  ${YELLOW}2.${NC} Get your keys at:     https://archive.org/account/s3.php"
    echo ""
    read -rp "  Enter your IA Access Key (S3 key): " IA_ACCESS_KEY
    read -rsp "  Enter your IA Secret Key (S3 secret): " IA_SECRET_KEY
    echo ""

    # Store as "access:secret" for the ia CLI tool
    echo "${IA_ACCESS_KEY}:${IA_SECRET_KEY}" > "$IA_API_KEY_FILE"
    chmod 600 "$IA_API_KEY_FILE"
    IA_API_KEY="${IA_ACCESS_KEY}:${IA_SECRET_KEY}"

    # Configure ia CLI if installed
    if command -v ia &>/dev/null; then
        ia configure --access-key="$IA_ACCESS_KEY" --secret-key="$IA_SECRET_KEY" 2>/dev/null || true
        log "Configured 'ia' CLI tool with your credentials."
    fi

    log "API key saved to $IA_API_KEY_FILE"
}

load_ia_key_parts() {
    if [[ -f "$IA_API_KEY_FILE" ]]; then
        IA_ACCESS_KEY=$(cut -d: -f1 "$IA_API_KEY_FILE")
        IA_SECRET_KEY=$(cut -d: -f2 "$IA_API_KEY_FILE")
    else
        error "No IA API key found. Please run the setup first."
        exit 1
    fi
}

# =============================================================================
# DEPENDENCY CHECKS
# =============================================================================

check_deps() {
    header "Checking Dependencies"
    local missing=()

    for cmd in wget curl jq python3; do
        if command -v "$cmd" &>/dev/null; then
            log "$cmd found"
        else
            warn "$cmd NOT found"
            missing+=("$cmd")
        fi
    done

    # Optional but preferred tools
    for cmd in aria2c rsync; do
        if command -v "$cmd" &>/dev/null; then
            log "$cmd found (optional — will use for faster downloads)"
        else
            info "$cmd not found (optional, wget will be used)"
        fi
    done

    # ia CLI (internetarchive python package)
    if command -v ia &>/dev/null; then
        log "ia CLI found"
    else
        warn "ia CLI not found — Internet Archive downloads will be limited."
        warn "Select option [9] 'Install Prerequisites' from the main menu to install it."
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing required tools: ${missing[*]}"
        echo ""
        echo -e "  ${YELLOW}Tip:${NC} Select option [9] 'Install Prerequisites' from the main menu"
        echo -e "  to automatically install everything needed."
        echo ""
        echo "  Or install manually:"
        echo "    sudo apt install wget curl jq python3 python3-pip aria2 rsync"
        echo "    pip3 install internetarchive"
        echo ""
        read -rp "  Continue anyway? (y/N): " cont
        [[ "${cont,,}" == "y" ]] || exit 1
    else
        log "All required dependencies present."
    fi
}

# =============================================================================
# INSTALL PREREQUISITES
# =============================================================================

install_prerequisites() {
    header "Install Prerequisites"

    # Detect OS / package manager
    local PKG_MGR=""
    local PKG_INSTALL=""
    local APT_PKGS="wget curl jq python3 python3-pip aria2 rsync"
    local DNF_PKGS="wget curl jq python3 python3-pip aria2 rsync"
    local BREW_PKGS="wget curl jq python3 aria2 rsync"

    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt-get"
        PKG_INSTALL="sudo apt-get install -y $APT_PKGS"
    elif command -v apt &>/dev/null; then
        PKG_MGR="apt"
        PKG_INSTALL="sudo apt install -y $APT_PKGS"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
        PKG_INSTALL="sudo dnf install -y $DNF_PKGS"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
        PKG_INSTALL="sudo yum install -y $DNF_PKGS"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
        PKG_INSTALL="sudo pacman -S --noconfirm wget curl jq python python-pip aria2 rsync"
    elif command -v brew &>/dev/null; then
        PKG_MGR="brew"
        PKG_INSTALL="brew install $BREW_PKGS"
    else
        warn "Could not detect a supported package manager."
        warn "Please manually install: wget curl jq python3 pip3 aria2c rsync"
        warn "Then run:  pip3 install internetarchive"
        return 1
    fi

    info "Detected package manager: $PKG_MGR"
    echo ""
    echo -e "  ${BOLD}The following will be installed:${NC}"
    echo ""
    echo -e "  ${CYAN}System packages (via $PKG_MGR):${NC}"
    echo -e "    wget      — file downloader (required)"
    echo -e "    curl      — HTTP client for API calls (required)"
    echo -e "    jq        — JSON parser (required)"
    echo -e "    python3   — runtime for ia CLI (required)"
    echo -e "    pip3      — Python package manager (required)"
    echo -e "    aria2     — fast multi-connection downloader (recommended)"
    echo -e "    rsync     — efficient sync for Gutenberg mirror (recommended)"
    echo ""
    echo -e "  ${CYAN}Python packages (via pip3):${NC}"
    echo -e "    internetarchive — official 'ia' CLI for Internet Archive (required for IA downloads)"
    echo ""

    read -rp "  Proceed with installation? (y/N): " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        info "Installation cancelled."
        return 0
    fi

    # System packages
    echo ""
    info "Installing system packages..."
    if [[ "$PKG_MGR" == "apt-get" || "$PKG_MGR" == "apt" ]]; then
        sudo apt-get update -qq
    fi

    if eval "$PKG_INSTALL"; then
        log "System packages installed successfully."
    else
        warn "Some system packages may have failed. Check output above."
    fi

    # pip3 — internetarchive
    echo ""
    info "Installing Python 'internetarchive' package..."

    # Try pip3 first, fall back to pip, handle externally-managed envs (Debian 12+)
    local pip_cmd=""
    if command -v pip3 &>/dev/null; then
        pip_cmd="pip3"
    elif command -v pip &>/dev/null; then
        pip_cmd="pip"
    else
        warn "pip not found even after install attempt. Trying python3 -m pip..."
        pip_cmd="python3 -m pip"
    fi

    # Attempt 1: standard install
    if $pip_cmd install internetarchive 2>/dev/null; then
        log "internetarchive installed via $pip_cmd."
    # Attempt 2: --break-system-packages (Debian 12+ / Ubuntu 23.04+)
    elif $pip_cmd install --break-system-packages internetarchive 2>/dev/null; then
        log "internetarchive installed via $pip_cmd --break-system-packages."
    # Attempt 3: pipx (clean isolated install)
    elif command -v pipx &>/dev/null; then
        info "Trying pipx as fallback..."
        pipx install internetarchive && log "internetarchive installed via pipx."
    # Attempt 4: user install
    elif $pip_cmd install --user internetarchive 2>/dev/null; then
        log "internetarchive installed to user directory."
        warn "You may need to add ~/.local/bin to your PATH:"
        warn "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
    else
        warn "Could not install internetarchive automatically."
        warn "Try manually: pip3 install internetarchive"
        warn "  or:         pip3 install --break-system-packages internetarchive"
        warn "  or:         pipx install internetarchive"
    fi

    # Final verification
    echo ""
    header "Verification"
    local all_good=true
    for cmd in wget curl jq python3; do
        if command -v "$cmd" &>/dev/null; then
            log "$cmd — OK"
        else
            warn "$cmd — MISSING"
            all_good=false
        fi
    done
    for cmd in aria2c rsync; do
        if command -v "$cmd" &>/dev/null; then
            log "$cmd — OK (optional)"
        else
            info "$cmd — not found (optional)"
        fi
    done
    if command -v ia &>/dev/null; then
        log "ia CLI — OK ($(ia --version 2>/dev/null || echo 'installed'))"
    else
        warn "ia CLI — not found in PATH (may need to restart shell or fix PATH)"
        all_good=false
    fi

    echo ""
    if $all_good; then
        log "All prerequisites installed and verified!"
    else
        warn "Some items could not be verified. You may need to open a new terminal"
        warn "for PATH changes to take effect, then re-run this script."
    fi
}

# =============================================================================
# GUTENBERG
# =============================================================================

download_gutenberg() {
    header "Project Gutenberg"
    info "Source: PGDP rsync mirrors + catalog"
    mkdir -p "$GUTENBERG_DIR"

    echo ""
    echo -e "  ${BOLD}Gutenberg Download Options:${NC}"
    echo "  [1] Mirror via rsync (full — tens of GB, all formats)"
    echo "  [2] Download English EPUB catalog only (curated, ~30 GB)"
    echo "  [3] Download catalog index only (metadata CSV, small)"
    echo "  [0] Skip"
    echo ""
    read -rp "  Choice: " choice

    case "$choice" in
        1)
            info "Starting rsync mirror of Project Gutenberg..."
            info "This will be very large (100+ GB). Ctrl+C to pause; re-run to resume."
            rsync -av --progress rsync://aleph.gutenberg.org/gutenberg/ "$GUTENBERG_DIR/" || \
            rsync -av --progress rsync://gutenberg.pglaf.org/gutenberg/ "$GUTENBERG_DIR/" || \
            warn "rsync failed — try: rsync://mirrors.xmission.com/gutenberg/"
            ;;
        2)
            info "Downloading English EPUBs..."
            mkdir -p "$GUTENBERG_DIR/epub"
            if command -v ia &>/dev/null; then
                info "Querying Internet Archive for Gutenberg EPUB items..."
                # ia search outputs one JSON object per line: {"identifier": "foo"}
                ia search 'collection:gutenberg AND mediatype:texts' \
                    --fields=identifier --no-cache 2>/dev/null | \
                    python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        ident = obj.get('identifier','')
        if ident:
            print(ident)
    except Exception:
        pass
" > /tmp/gutenberg_ids.txt

                local count
                count=$(wc -l < /tmp/gutenberg_ids.txt)
                info "Found $count items. Downloading EPUBs..."

                while IFS= read -r id; do
                    [[ -z "$id" ]] && continue
                    if ia_is_done "gutenberg:$id"; then
                        continue
                    fi
                    mkdir -p "$GUTENBERG_DIR/epub"
                    ia download "$id" --format="EPUB" \
                        --destdir="$GUTENBERG_DIR/epub" 2>/dev/null && \
                        ia_mark_done "gutenberg:$id" || \
                        warn "Could not download $id (may not have EPUB format)"
                    pause "$IA_DELAY_BETWEEN_ITEMS"
                done < /tmp/gutenberg_ids.txt
            else
                warn "ia CLI needed for collection search. Falling back to catalog download."
                safe_download \
                    "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv" \
                    "$GUTENBERG_DIR/pg_catalog.csv" "Gutenberg catalog"
                info "Catalog downloaded. See $GUTENBERG_DIR/pg_catalog.csv for book list."
            fi
            ;;
        3)
            safe_download \
                "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz" \
                "$GUTENBERG_DIR/pg_catalog.csv.gz" "Gutenberg catalog"
            log "Catalog saved to $GUTENBERG_DIR/pg_catalog.csv.gz"
            ;;
        *) info "Skipping Gutenberg." ;;
    esac
}

# =============================================================================
# EXODUS / eXoDOS (Game Preservation)
# =============================================================================

# Verified IA identifiers for ROM collections (confirmed via archive.org search)
declare -A EXODUS_IA_COLLECTIONS=(
    ["Proper 1G1R (2024) — Best single ROM per game, all systems (~50 GB)"]="proper1g1r-collection:no-intro"
    ["Hearto 1G1R (2021) — Clean verified dumps, all major systems (~30 GB)"]="hearto-1g1r-collection:no-intro"
    ["No-Intro Merged Sets (2021) — NES SNES Genesis GG SMS 32X (~10 GB)"]="nointro-merged:no-intro"
    ["GBA No-Intro 2024 — Game Boy Advance complete set (~5 GB)"]="ef_gba_no-intro_2024-02-21:no-intro"
    ["TOSEC — Old School Emulation (every platform ever, 100s of GB)"]="tosec:tosec"
    ["MS-DOS Games — IA Software Library (~varies)"]="softwarelibrary_msdos_games:msdos"
    ["Console Living Room — NES SNES Genesis playable (~varies)"]="consolelivingroom:console"
    ["Internet Arcade — 900+ arcade games playable (~varies)"]="internetarcade:arcade"
)

download_exodus() {
    header "eXoDOS & Retro Game Preservation"
    mkdir -p "$EXODUS_DIR"

    echo ""
    echo -e "  ${BOLD}eXoDOS v6.04 — 7,666 DOS games, pre-configured in DOSBox${NC}"
    echo -e "  ${CYAN}Official site: https://www.retro-exo.com/exodos.html${NC}"
    separator
    echo -e "  ${YELLOW}[ 1]${NC} eXoDOS Full Collection  (~638 GB, torrent)"
    echo -e "       7,666 DOS games + DOSBox + LaunchBox frontend, fully configured"
    echo -e "  ${YELLOW}[ 2]${NC} eXoDOS Media Add-On Pack (~220 GB, torrent)"
    echo -e "       Magazines, books, catalogs, soundtracks, TV docs for DOS era"
    echo -e "  ${YELLOW}[ 3]${NC} eXoDOS Lite             (~5 GB, torrent)"
    echo -e "       Frontend + metadata only; downloads each game on first launch"
    echo -e "  ${YELLOW}[ 4]${NC} eXoDOS Full + Media     (~858 GB, both torrents)"
    echo -e "  ${YELLOW}[ 5]${NC} Internet Archive ROM collections (numbered menu)"
    echo -e "  ${YELLOW}[ 6]${NC} Full eXoDOS + Media + IA ROMs (everything)"
    echo -e "  ${YELLOW}[ 0]${NC} Skip"
    separator
    echo -e "  ${CYAN}Note: Torrent downloads use aria2c if available, else prints magnet/URL.${NC}"
    echo ""
    read -rp "  Choice: " choice

    case "$choice" in
        1|4|6)
            _exodos_torrent \
                "https://www.retro-exo.com/eXoDOS.torrent" \
                "$EXODUS_DIR/eXoDOS_v6.04" \
                "eXoDOS v6.04 Full (~638 GB)"
            ;;&
        2|4|6)
            _exodos_torrent \
                "https://www.retro-exo.com/eXoDOS%20Media%20Pack.torrent" \
                "$EXODUS_DIR/eXoDOS_MediaPack" \
                "eXoDOS Media Pack (~220 GB)"
            ;;&
        3)
            _exodos_torrent \
                "https://www.retro-exo.com/eXoDOS_Lite.torrent" \
                "$EXODUS_DIR/eXoDOS_v6.04_Lite" \
                "eXoDOS Lite (~5 GB)"
            ;;
        5|6)
            _exodos_ia_menu
            ;;
        0|*)
            info "Skipping eXoDOS."
            ;;
    esac
}

# Download a torrent file then launch aria2c, or print instructions
_exodos_torrent() {
    local torrent_url="$1"
    local dest_dir="$2"
    local label="$3"

    mkdir -p "$dest_dir"
    local torrent_file="$dest_dir/$(basename "$torrent_url")"
    torrent_file="${torrent_file//%20/_}"   # decode %20 in filename

    info "Downloading torrent file for: $label"
    wget -q --show-progress -O "$torrent_file" "$torrent_url" || {
        warn "Could not download torrent file. Try manually: $torrent_url"
        return
    }

    if command -v aria2c &>/dev/null; then
        log "Starting aria2c torrent download: $label"
        info "Files will be saved to: $dest_dir"
        info "Ctrl+C pauses — re-run the script and aria2c will resume."
        aria2c \
            --dir="$dest_dir" \
            --seed-time=0 \
            --max-connection-per-server=4 \
            --continue=true \
            "$torrent_file" || warn "aria2c exited — re-run to resume."
    elif command -v transmission-cli &>/dev/null; then
        log "Starting transmission-cli torrent download: $label"
        transmission-cli --download-dir "$dest_dir" "$torrent_file"
    elif command -v qbittorrent-nox &>/dev/null; then
        log "Starting qbittorrent-nox: $label"
        qbittorrent-nox --save-path="$dest_dir" "$torrent_file"
    else
        warn "No torrent client found (aria2c recommended)."
        warn "Install with:  sudo apt install aria2"
        warn "Then run:      aria2c --dir=\"$dest_dir\" --seed-time=0 \"$torrent_file\""
        warn "Torrent saved to: $torrent_file"
        info "Alternatively visit: https://www.retro-exo.com/exodos.html"
    fi
}

# IA ROM collection picker for Exodus
_exodos_ia_menu() {
    header "Internet Archive ROM Collections"

    local keys=("${!EXODUS_IA_COLLECTIONS[@]}")
    declare -A exsel
    for k in "${keys[@]}"; do exsel["$k"]=0; done

    numbered_select "IA ROM Collection Selection" "Sizes vary — check archive.org before downloading" keys exsel

    local any=false
    for k in "${keys[@]}"; do
        [[ "${exsel[$k]:-0}" != "1" ]] && continue
        any=true

        local val="${EXODUS_IA_COLLECTIONS[$k]}"
        local ia_id subdir
        ia_id=$(echo "$val"  | cut -d: -f1)
        subdir=$(echo "$val" | cut -d: -f2)

        local dest_dir="$EXODUS_DIR/$subdir"
        mkdir -p "$dest_dir"

        if ia_is_done "exodus:$ia_id"; then
            info "Already downloaded: $ia_id"
            continue
        fi

        info "Downloading from Internet Archive: $ia_id → $dest_dir"
        if command -v ia &>/dev/null; then
            if ia download "$ia_id" --destdir="$dest_dir"; then
                ia_mark_done "exodus:$ia_id"
            else
                warn "Download failed or requires IA login: $ia_id"
                warn "Ensure your IA account is configured (option 9 — Install Prerequisites)."
            fi
        else
            safe_download "https://archive.org/compress/$ia_id" \
                "$dest_dir/${ia_id}.zip" "$ia_id"
            ia_mark_done "exodus:$ia_id"
        fi
        pause "$IA_DELAY_BETWEEN_ITEMS"
    done

    $any || warn "No IA ROM collections selected."
}


# =============================================================================
# SHARED NUMBERED SELECTION MENU
# Usage: numbered_select "Title" "hint_line" keys_array_name sel_state_array_name
# Prints a numbered list; user types numbers separated by spaces (or 'a'/'n').
# Sets sel_state[key]=1 for chosen items.
# =============================================================================

# Parse ia search JSON output (one {"identifier":"foo"} per line)
ia_parse_ids() {
    python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        ident = obj.get('identifier','')
        if ident:
            print(ident)
    except Exception:
        pass
"
}

numbered_select() {
    local title="$1"
    local hint="$2"
    local -n _ns_keys="$3"
    local -n _ns_sel="$4"
    local num=${#_ns_keys[@]}

    echo ""
    echo -e "${BOLD}${BLUE}  $title${NC}"
    [[ -n "$hint" ]] && echo -e "  ${YELLOW}$hint${NC}"
    separator
    for i in "${!_ns_keys[@]}"; do
        printf "  ${YELLOW}[%2d]${NC} %s\n" "$((i+1))" "${_ns_keys[$i]}"
    done
    separator
    echo -e "  Enter numbers separated by spaces, ${BOLD}a${NC}=all, ${BOLD}n${NC}=none, ${BOLD}0${NC}=skip"
    echo -e "  Example: ${CYAN}1 3 5${NC}  or  ${CYAN}a${NC}"
    echo ""
    read -rp "  Selection: " raw_input

    # Reset all
    for k in "${_ns_keys[@]}"; do _ns_sel["$k"]=0; done

    case "${raw_input,,}" in
        a|all)
            for k in "${_ns_keys[@]}"; do _ns_sel["$k"]=1; done
            log "Selected all."
            ;;
        n|none|0|"")
            info "None selected."
            ;;
        *)
            local count=0
            for token in $raw_input; do
                if [[ "$token" =~ ^[0-9]+$ ]] && \
                   [[ "$token" -ge 1 ]] && \
                   [[ "$token" -le "$num" ]]; then
                    local idx=$(( token - 1 ))
                    _ns_sel["${_ns_keys[$idx]}"]=1
                    ((count++)) || true
                else
                    warn "Ignoring invalid input: $token"
                fi
            done
            log "Selected $count item(s)."
            ;;
    esac
    echo ""
}

# =============================================================================
# KIWIX ZIM FILES
# =============================================================================

# ZIM catalog: https://download.kiwix.org/zim/
declare -A ZIM_CATEGORIES=(
    ["Wikipedia (English, all articles, with pictures — ~100 GB)"]="wikipedia/wikipedia_en_all_maxi"
    ["Wikipedia (English, no pictures — ~22 GB)"]="wikipedia/wikipedia_en_all_nopic"
    ["Wikipedia (English, top articles — ~4 GB)"]="wikipedia/wikipedia_en_top_maxi"
    ["Wikibooks (English)"]="wikibooks/wikibooks_en_all_maxi"
    ["Wikinews (English)"]="wikinews/wikinews_en_all_maxi"
    ["Wikiquote (English)"]="wikiquote/wikiquote_en_all_maxi"
    ["Wikisource (English)"]="wikisource/wikisource_en_all_maxi"
    ["Wikiversity (English)"]="wikiversity/wikiversity_en_all_maxi"
    ["Wikivoyage (English)"]="wikivoyage/wikivoyage_en_all_maxi"
    ["Wiktionary (English)"]="wiktionary/wiktionary_en_all_maxi"
    ["Project Gutenberg (all languages)"]="gutenberg/gutenberg_en_all"
    ["Stack Overflow — English"]="stack_exchange/stackoverflow.com_en_all"
    ["Stack Exchange — All sites"]="stack_exchange/all_en_all"
    ["TED Talks (English)"]="ted/ted_en_all"
    ["iFixit Repair Guides"]="ifixit/ifixit_en_all"
    ["Khan Academy (English)"]="other/khan_en_all"
    ["FreeCodeCamp"]="freecodecamp/freecodecamp_en_all"
    ["Vikidia (simple encyclopaedia for kids)"]="vikidia/vikidia_en_all"
    ["OpenStreetMap (maps ZIM)"]="maps/maps"
    ["PhET Interactive Simulations"]="phet/phet_en_all"
    ["Linux Documentation Project"]="other/linuxdoc_en_all"
    ["MedlinePlus (medical encyclopedia)"]="other/medlineplus_en_all"
)

download_kiwix() {
    header "Kiwix ZIM Files"
    info "Source: https://download.kiwix.org/zim/"
    mkdir -p "$ZIM_DIR"

    local keys=("${!ZIM_CATEGORIES[@]}")
    declare -A sel_state
    for k in "${keys[@]}"; do sel_state["$k"]=0; done

    numbered_select "Kiwix ZIM Selection" "Large files — Wikipedia full = ~100 GB" keys sel_state

    local selected=()
    for k in "${keys[@]}"; do
        [[ "${sel_state[$k]:-0}" == "1" ]] && selected+=("${ZIM_CATEGORIES[$k]}")
    done

    if [[ ${#selected[@]} -eq 0 ]]; then
        warn "No ZIM files selected. Skipping Kiwix."
        return
    fi

    log "Selected ${#selected[@]} ZIM file(s). Starting downloads..."

    for zim_path in "${selected[@]}"; do
        local category_dir
        category_dir=$(dirname "$zim_path")
        local zim_prefix
        zim_prefix=$(basename "$zim_path")

        info "Finding latest version of: $zim_prefix"
        local listing_url="https://download.kiwix.org/zim/${category_dir}/"
        local latest
        latest=$(curl -s "$listing_url" | \
            grep -oP "href=\"${zim_prefix}_[0-9]{4}-[0-9]{2}\.zim\"" | \
            sed 's/href="//;s/"//' | \
            sort -r | head -1)

        if [[ -z "$latest" ]]; then
            warn "Could not find ZIM for: $zim_prefix — check https://download.kiwix.org/zim/$category_dir/"
            continue
        fi

        local zim_url="https://download.kiwix.org/zim/${category_dir}/${latest}"
        local dest="$ZIM_DIR/${latest}"

        if [[ -f "$dest" ]]; then
            log "Already downloaded: $latest"
            continue
        fi

        safe_download "$zim_url" "$dest" "$latest"
        pause "$GENERAL_DELAY"
    done

    log "Kiwix ZIM downloads complete. Files in: $ZIM_DIR"
}

# =============================================================================
# HEADWAY MAPS (OSM PBF via Geofabrik)
# =============================================================================

declare -A HEADWAY_REGIONS=(
    # Continents
    ["🌍 Africa (continent)"]="https://download.geofabrik.de/africa-latest.osm.pbf"
    ["🌏 Asia (continent)"]="https://download.geofabrik.de/asia-latest.osm.pbf"
    ["🌎 Central America"]="https://download.geofabrik.de/central-america-latest.osm.pbf"
    ["🌎 North America (continent)"]="https://download.geofabrik.de/north-america-latest.osm.pbf"
    ["🌎 South America (continent)"]="https://download.geofabrik.de/south-america-latest.osm.pbf"
    ["🌍 Europe (continent ~32 GB)"]="https://download.geofabrik.de/europe-latest.osm.pbf"
    ["🌏 Australia + Oceania"]="https://download.geofabrik.de/australia-oceania-latest.osm.pbf"
    ["🌐 Antarctica"]="https://download.geofabrik.de/antarctica-latest.osm.pbf"
    # Popular countries
    ["🇺🇸 United States (all)"]="https://download.geofabrik.de/north-america/us-latest.osm.pbf"
    ["🇨🇦 Canada"]="https://download.geofabrik.de/north-america/canada-latest.osm.pbf"
    ["🇲🇽 Mexico"]="https://download.geofabrik.de/north-america/mexico-latest.osm.pbf"
    ["🇬🇧 Great Britain"]="https://download.geofabrik.de/europe/great-britain-latest.osm.pbf"
    ["🇩🇪 Germany"]="https://download.geofabrik.de/europe/germany-latest.osm.pbf"
    ["🇫🇷 France"]="https://download.geofabrik.de/europe/france-latest.osm.pbf"
    ["🇮🇹 Italy"]="https://download.geofabrik.de/europe/italy-latest.osm.pbf"
    ["🇪🇸 Spain"]="https://download.geofabrik.de/europe/spain-latest.osm.pbf"
    ["🇵🇱 Poland"]="https://download.geofabrik.de/europe/poland-latest.osm.pbf"
    ["🇸🇪 Sweden"]="https://download.geofabrik.de/europe/sweden-latest.osm.pbf"
    ["🇳🇱 Netherlands"]="https://download.geofabrik.de/europe/netherlands-latest.osm.pbf"
    ["🇺🇦 Ukraine"]="https://download.geofabrik.de/europe/ukraine-latest.osm.pbf"
    ["🇷🇺 Russia"]="https://download.geofabrik.de/russia-latest.osm.pbf"
    ["🇧🇷 Brazil"]="https://download.geofabrik.de/south-america/brazil-latest.osm.pbf"
    ["🇦🇷 Argentina"]="https://download.geofabrik.de/south-america/argentina-latest.osm.pbf"
    ["🇨🇴 Colombia"]="https://download.geofabrik.de/south-america/colombia-latest.osm.pbf"
    ["🇨🇳 China"]="https://download.geofabrik.de/asia/china-latest.osm.pbf"
    ["🇮🇳 India"]="https://download.geofabrik.de/asia/india-latest.osm.pbf"
    ["🇯🇵 Japan"]="https://download.geofabrik.de/asia/japan-latest.osm.pbf"
    ["🇰🇷 South Korea"]="https://download.geofabrik.de/asia/south-korea-latest.osm.pbf"
    ["🇮🇩 Indonesia"]="https://download.geofabrik.de/asia/indonesia-latest.osm.pbf"
    ["🇳🇬 Nigeria"]="https://download.geofabrik.de/africa/nigeria-latest.osm.pbf"
    ["🇿🇦 South Africa"]="https://download.geofabrik.de/africa/south-africa-latest.osm.pbf"
    ["🇦🇺 Australia"]="https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf"
    ["🇳🇿 New Zealand"]="https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf"
    ["🌐 ENTIRE PLANET (~90 GB!)"]="https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf"
)

download_headway() {
    header "Headway Maps (OpenStreetMap PBF)"
    info "Source: Geofabrik / planet.openstreetmap.org"
    info "Note: Files are large — continents = 1–32 GB, full planet = ~90 GB"
    mkdir -p "$HEADWAY_DIR"

    local keys=("${!HEADWAY_REGIONS[@]}")
    declare -A hsel_state
    for k in "${keys[@]}"; do hsel_state["$k"]=0; done

    numbered_select "Headway Map Region Selection" "Continents = 1–32 GB each | Planet = ~90 GB" keys hsel_state

    local any=false
    for k in "${keys[@]}"; do
        if [[ "${hsel_state[$k]:-0}" == "1" ]]; then
            any=true
            local url="${HEADWAY_REGIONS[$k]}"
            local fname
            fname=$(basename "$url")
            local dest="$HEADWAY_DIR/$fname"
            safe_download "$url" "$dest" "$k"
            pause "$GENERAL_DELAY"
        fi
    done

    $any || warn "No map regions selected. Skipping Headway."
    $any && log "Map downloads complete. Files in: $HEADWAY_DIR"
}

# =============================================================================
# FREE MUSIC ARCHIVE
# =============================================================================

download_music() {
    header "Free Music Archive (FMA)"
    info "106,000+ Creative Commons tracks, 917 GiB total"
    info "Source: https://github.com/mdeff/fma — hosted on various mirrors"
    mkdir -p "$MUSIC_DIR"

    echo ""
    echo -e "  ${BOLD}FMA Dataset Options:${NC}"
    echo "  [1] fma_small  — 8,000 tracks × 30s,  8 genres   (~7.2 GB)"
    echo "  [2] fma_medium — 25,000 tracks × 30s, 16 genres  (~22 GB)"
    echo "  [3] fma_large  — 106,574 clips × 30s, 161 genres (~93 GB)"
    echo "  [4] fma_full   — 106,574 full tracks, 161 genres (~879 GB)"
    echo "  [5] Metadata only (track listings, CSV, no audio)"
    echo "  [6] FMA + Jamendo via Internet Archive (community audio)"
    echo "  [0] Skip"
    echo ""
    read -rp "  Choice: " choice

    local fma_base="https://os.unil.cloud.switch.ch/fma"

    case "$choice" in
        1)
            safe_download "$fma_base/fma_small.zip"    "$MUSIC_DIR/fma_small.zip"  "FMA Small"
            safe_download "$fma_base/fma_metadata.zip" "$MUSIC_DIR/fma_metadata.zip" "FMA Metadata"
            ;;
        2)
            safe_download "$fma_base/fma_medium.zip"   "$MUSIC_DIR/fma_medium.zip" "FMA Medium"
            safe_download "$fma_base/fma_metadata.zip" "$MUSIC_DIR/fma_metadata.zip" "FMA Metadata"
            ;;
        3)
            safe_download "$fma_base/fma_large.zip"    "$MUSIC_DIR/fma_large.zip"  "FMA Large"
            safe_download "$fma_base/fma_metadata.zip" "$MUSIC_DIR/fma_metadata.zip" "FMA Metadata"
            ;;
        4)
            warn "fma_full is ~879 GB. This will take a very long time."
            read -rp "  Are you sure? (yes/no): " confirm
            if [[ "$confirm" == "yes" ]]; then
                safe_download "$fma_base/fma_full.zip" "$MUSIC_DIR/fma_full.zip" "FMA Full"
                safe_download "$fma_base/fma_metadata.zip" "$MUSIC_DIR/fma_metadata.zip" "FMA Metadata"
            fi
            ;;
        5)
            safe_download "$fma_base/fma_metadata.zip" "$MUSIC_DIR/fma_metadata.zip" "FMA Metadata"
            ;;
        6)
            info "Downloading FMA community audio collections from Internet Archive..."
            local ia_music_ids=(
                "audio_bookspoetry"
                "netlabels"
                "GratefulDead"
                "etree"
            )
            for id in "${ia_music_ids[@]}"; do
                if ia_is_done "music_ia:$id"; then continue; fi
                info "Downloading collection: $id"
                if command -v ia &>/dev/null; then
                    ia download "$id" --destdir="$MUSIC_DIR/ia_audio/$id" && \
                        ia_mark_done "music_ia:$id"
                fi
                pause "$IA_DELAY_BETWEEN_ITEMS"
            done
            ;;
        *) info "Skipping music." ;;
    esac
}

# =============================================================================
# INTERNET ARCHIVE — THINGIVERSE
# =============================================================================

download_thingiverse() {
    header "Thingiverse Archive (Internet Archive)"
    info "Collection identifier: thingiverse (~6.2 TB, 12M+ files)"
    info "Source: https://archive.org/details/thingiverse"
    mkdir -p "$IA_DIR/thingiverse"

    echo ""
    echo -e "  ${BOLD}Thingiverse Download Options:${NC}"
    echo "  [1] Download entire collection (6.2 TB — use ia CLI, resumable)"
    echo "  [2] Download specific item IDs from a file (one per line)"
    echo "  [3] Search and download by keyword (uses IA API)"
    echo "  [0] Skip"
    echo ""
    read -rp "  Choice: " choice

    case "$choice" in
        1)
            if ! command -v ia &>/dev/null; then
                error "ia CLI required. Install: pip3 install internetarchive"
                return
            fi
            info "Fetching all Thingiverse item IDs..."
            info "This will query the IA API. May take a while to list items."

            local id_file="$IA_DIR/thingiverse_ids.txt"
            if [[ ! -f "$id_file" ]]; then
                ia search 'collection:thingiverse' --fields=identifier --no-cache \
                    2>/dev/null | ia_parse_ids > "$id_file"
                log "Found $(wc -l < "$id_file") items."
            else
                info "Using cached ID list: $id_file ($(wc -l < "$id_file") items)"
            fi

            download_ia_id_list "$id_file" "$IA_DIR/thingiverse" "thingiverse"
            ;;
        2)
            read -rp "  Path to ID file: " id_file_path
            if [[ ! -f "$id_file_path" ]]; then
                error "File not found: $id_file_path"
                return
            fi
            download_ia_id_list "$id_file_path" "$IA_DIR/thingiverse" "thingiverse"
            ;;
        3)
            read -rp "  Search keyword (e.g. 'mechanical keyboard'): " keyword
            local id_file="$IA_DIR/thingiverse_search_${keyword// /_}.txt"
            ia search "collection:thingiverse AND $keyword" \
                --fields=identifier --no-cache 2>/dev/null | \
                ia_parse_ids > "$id_file"
            info "Found $(wc -l < "$id_file") results for '$keyword'"
            download_ia_id_list "$id_file" "$IA_DIR/thingiverse/$keyword" "thingiverse"
            ;;
        *) info "Skipping Thingiverse." ;;
    esac
}

# Generic IA ID list downloader with progress tracking
download_ia_id_list() {
    local id_file="$1"
    local dest_dir="$2"
    local tag="$3"
    mkdir -p "$dest_dir"

    if ! command -v ia &>/dev/null; then
        error "ia CLI required: pip3 install internetarchive"
        return 1
    fi

    local total
    total=$(wc -l < "$id_file")
    local done_count=0
    local skip_count=0

    info "Starting download of $total items → $dest_dir"
    info "Progress is tracked in: $IA_PROGRESS_FILE"
    info "If interrupted, re-run and already-downloaded items will be skipped."

    while IFS= read -r item_id; do
        [[ -z "$item_id" ]] && continue
        local progress_key="${tag}:${item_id}"
        ((done_count++)) || true

        if ia_is_done "$progress_key"; then
            ((skip_count++)) || true
            continue
        fi

        printf "${CYAN}[%d/%d]${NC} Downloading: %s\n" "$done_count" "$total" "$item_id"

        if ia download "$item_id" --destdir="$dest_dir" --no-derive 2>/dev/null; then
            ia_mark_done "$progress_key"
        else
            warn "Failed: $item_id (will retry on next run)"
        fi

        pause "$IA_DELAY_BETWEEN_ITEMS"
    done < "$id_file"

    log "Completed: $((done_count - skip_count)) new, $skip_count already done."
}

# =============================================================================
# INTERNET ARCHIVE — OTHER DATA HOARDS
# =============================================================================

declare -A IA_HOARDS=(
    ["📚 OpenLibrary — Open Access Books (~10M books metadata)"]="opensource_books"
    ["🎮 Internet Arcade (900+ classic browser-playable games)"]="internetarcade"
    ["💾 MS-DOS Games (1000s of vintage PC games)"]="softwarelibrary_msdos_games"
    ["📼 Prelinger Archives (20th century ephemeral films)"]="prelinger"
    ["📺 Classic TV Commercials (Vintage ads)"]="classic_tv_commercials"
    ["🎵 Netlabels (CC-licensed full albums, music)"]="netlabels"
    ["🎵 Grateful Dead Concerts (thousands of recordings)"]="GratefulDead"
    ["🎵 etree — Live Concert Recordings"]="etree"
    ["📻 Old Time Radio (vintage radio programs)"]="oldtimeradio"
    ["📡 NASA Images Archive"]="nasa"
    ["📰 Folkscanomy — Books by Subject (public domain)"]="folkscanomy"
    ["🔬 Biodiversity Heritage Library (natural history)"]="biodiversity"
    ["🗺️ USGS Maps — Historical Topographic Maps"]="usgsmaps"
    ["🧬 Government Documents (US federal docs)"]="USGovernmentDocuments"
    ["🖥️ Vintage Software Library (historic software)"]="softwarelibrary"
    ["📖 Children's Library (historical children's books)"]="ChildrenLibrary"
    ["🎓 Smithsonian Institution Libraries"]="smithsonian-institution-libraries"
    ["🇨🇳 Chinese Texts (classical literature)"]="chinesetexts"
    ["🎬 Democracy Now! (news archive 1996-present)"]="democracynow"
    ["🎙️ LibriVox (public domain audiobooks)"]="librivox"
)

download_ia_hoards() {
    header "Internet Archive — Other Data Hoards"

    local keys=("${!IA_HOARDS[@]}")
    declare -A hoard_sel
    for k in "${keys[@]}"; do hoard_sel["$k"]=0; done

    numbered_select "Internet Archive Collection Selector" "" keys hoard_sel

    for k in "${keys[@]}"; do
        if [[ "${hoard_sel[$k]:-0}" == "1" ]]; then
            local collection_id="${IA_HOARDS[$k]}"
            info "Queuing collection: $collection_id"

            local id_file="$IA_DIR/collections/${collection_id}_ids.txt"
            mkdir -p "$(dirname "$id_file")"

            if [[ ! -f "$id_file" ]] || [[ ! -s "$id_file" ]]; then
                info "Fetching item list for: $collection_id"
                if command -v ia &>/dev/null; then
                    ia search "collection:${collection_id}" --fields=identifier --no-cache \
                        2>/dev/null | ia_parse_ids > "$id_file"
                else
                    # Fallback: IA search API via curl
                    curl -s "https://archive.org/advancedsearch.php?q=collection:${collection_id}&fl[]=identifier&rows=10000&output=json" | \
                        python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data.get('response', {}).get('docs', []):
    ident = d.get('identifier', '')
    if ident:
        print(ident)
" > "$id_file" 2>/dev/null || true
                fi
            fi

            local count
            count=$(wc -l < "$id_file" 2>/dev/null || echo 0)
            info "Found $count items in $collection_id"

            download_ia_id_list "$id_file" "$IA_DIR/collections/$collection_id" "$collection_id"
        fi
    done
}

# =============================================================================
# MOVIES (Public Domain & Open License — Internet Archive)
# =============================================================================

declare -A MOVIE_COLLECTIONS=(
    ["🎬 Feature Films — Public Domain (IA main collection, 1000s of films)"]="feature_films"
    ["🎞️  Silent Films — Classic 1900s–1920s cinema"]="silent_films"
    ["🎨 Animation & Cartoons — Fleischer, early Disney, Looney Tunes etc."]="animationandcartoons"
    ["📽️  Ephemeral Films — Prelinger Archives (ads, educational, industrial)"]="prelinger"
    ["🎥 Open Source Movies — CC-licensed independent films"]="opensource_movies"
    ["🎭 Arts & Music Videos — Performances, concerts, documentaries"]="artsandmusicvideos"
    ["📚 Cultural & Academic Films — Educational documentaries"]="culturalandacademicfilms"
    ["👁️  Film Noir & Classic Horror — Public domain genre films"]="film_noir"
    ["🌍 World Cinema — Non-English public domain films"]="world_cinema"
    ["📺 Classic TV — Public domain television episodes"]="classic_tv"
)

download_movies() {
    header "Movies & Video (Public Domain / Open License)"
    info "Source: Internet Archive — all collections are free to download"
    info "Note: feature_films alone has tens of thousands of items — filter with 'ia' CLI"
    mkdir -p "$BASE_DIR/movies"

    local keys=("${!MOVIE_COLLECTIONS[@]}")
    declare -A msel
    for k in "${keys[@]}"; do msel["$k"]=0; done

    numbered_select "Movie Collection Selection" "Feature films = very large; start with a specific genre" keys msel

    local any=false
    for k in "${keys[@]}"; do
        [[ "${msel[$k]:-0}" != "1" ]] && continue
        any=true

        local collection_id="${MOVIE_COLLECTIONS[$k]}"
        local dest_dir="$BASE_DIR/movies/$collection_id"
        local id_file="$BASE_DIR/movies/${collection_id}_ids.txt"
        mkdir -p "$dest_dir"

        if [[ ! -f "$id_file" ]] || [[ ! -s "$id_file" ]]; then
            info "Fetching item list for: $collection_id"
            if command -v ia &>/dev/null; then
                ia search "collection:${collection_id} AND mediatype:movies" \
                    --fields=identifier --no-cache 2>/dev/null | \
                    ia_parse_ids > "$id_file"
            else
                curl -s "https://archive.org/advancedsearch.php?q=collection:${collection_id}+AND+mediatype:movies&fl[]=identifier&rows=10000&output=json" | \
                    python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data.get('response', {}).get('docs', []):
    ident = d.get('identifier', '')
    if ident:
        print(ident)
" > "$id_file" 2>/dev/null || true
            fi
        fi

        local count
        count=$(wc -l < "$id_file" 2>/dev/null || echo 0)
        info "Found $count items in $collection_id"

        if [[ "$count" -gt 500 ]]; then
            warn "$count items is a large download. This could be hundreds of GB."
            read -rp "  Continue downloading all $count items? (yes/no): " conf
            [[ "${conf,,}" != "yes" ]] && { info "Skipping $collection_id."; continue; }
        fi

        download_ia_id_list "$id_file" "$dest_dir" "movies_${collection_id}"
    done

    $any || warn "No movie collections selected."
    $any && log "Movie downloads complete. Files in: $BASE_DIR/movies"
}

# =============================================================================
# AUDIOBOOKS (LibriVox & IA Collections)
# =============================================================================

declare -A AUDIOBOOK_COLLECTIONS=(
    ["📖 LibriVox — Full collection (public domain, human-read, ~1TB+)"]="librivoxaudio:librivox"
    ["📖 LibriVox — English only (search-filtered subset)"]="librivoxaudio_en:librivox_en"
    ["📖 Audio Books & Poetry — IA community collection"]="audio_bookspoetry:ia_audiobooks"
    ["📖 LibriVox M4B — Bookmarkable audiobook format collection"]="LibrivoxM4bCollectionAudiobooksMain:librivox_m4b"
    ["🎙️ Spoken Word — Speeches, readings, poetry (IA collection)"]="audio_spoken_word:spoken_word"
    ["📻 Old Time Radio — Classic radio dramas & comedies"]="oldtimeradio:old_time_radio"
)

download_audiobooks() {
    header "Audiobooks & Spoken Word"
    info "Source: Internet Archive — LibriVox + community collections"
    info "LibriVox full collection = ~1 TB+; English-only is much smaller"
    mkdir -p "$BASE_DIR/audiobooks"

    local keys=("${!AUDIOBOOK_COLLECTIONS[@]}")
    declare -A absel
    for k in "${keys[@]}"; do absel["$k"]=0; done

    numbered_select "Audiobook Collection Selection" "LibriVox has 20,000+ books across all languages" keys absel

    local any=false
    for k in "${keys[@]}"; do
        [[ "${absel[$k]:-0}" != "1" ]] && continue
        any=true

        local val="${AUDIOBOOK_COLLECTIONS[$k]}"
        local collection_id subdir
        collection_id=$(echo "$val" | cut -d: -f1)
        subdir=$(echo "$val" | cut -d: -f2)

        local dest_dir="$BASE_DIR/audiobooks/$subdir"
        local id_file="$BASE_DIR/audiobooks/${subdir}_ids.txt"
        mkdir -p "$dest_dir"

        # English-only LibriVox uses a search filter rather than a separate collection
        if [[ "$collection_id" == "librivoxaudio_en" ]]; then
            if [[ ! -f "$id_file" ]] || [[ ! -s "$id_file" ]]; then
                info "Searching LibriVox for English-language audiobooks..."
                if command -v ia &>/dev/null; then
                    ia search 'collection:librivoxaudio AND language:English' \
                        --fields=identifier --no-cache 2>/dev/null | \
                        ia_parse_ids > "$id_file"
                else
                    curl -s "https://archive.org/advancedsearch.php?q=collection:librivoxaudio+AND+language:English&fl[]=identifier&rows=50000&output=json" | \
                        python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data.get('response', {}).get('docs', []):
    ident = d.get('identifier', '')
    if ident:
        print(ident)
" > "$id_file" 2>/dev/null || true
                fi
            fi
        else
            if [[ ! -f "$id_file" ]] || [[ ! -s "$id_file" ]]; then
                info "Fetching item list for: $collection_id"
                if command -v ia &>/dev/null; then
                    ia search "collection:${collection_id}" \
                        --fields=identifier --no-cache 2>/dev/null | \
                        ia_parse_ids > "$id_file"
                else
                    curl -s "https://archive.org/advancedsearch.php?q=collection:${collection_id}&fl[]=identifier&rows=50000&output=json" | \
                        python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data.get('response', {}).get('docs', []):
    ident = d.get('identifier', '')
    if ident:
        print(ident)
" > "$id_file" 2>/dev/null || true
                fi
            fi
        fi

        local count
        count=$(wc -l < "$id_file" 2>/dev/null || echo 0)
        info "Found $count items in $collection_id"

        if [[ "$count" -gt 1000 ]]; then
            warn "$count items detected. LibriVox full = ~1 TB+."
            warn "Consider the English-only option to reduce scope."
            read -rp "  Continue downloading all $count items? (yes/no): " conf
            [[ "${conf,,}" != "yes" ]] && { info "Skipping $collection_id."; continue; }
        fi

        download_ia_id_list "$id_file" "$dest_dir" "audiobook_${subdir}"
    done

    $any || warn "No audiobook collections selected."
    $any && log "Audiobook downloads complete. Files in: $BASE_DIR/audiobooks"
}

# =============================================================================
# MAIN MENU
# =============================================================================

main_menu() {
    local services=(
        "📚 Gutenberg (books)"
        "🎮 eXoDOS / Retro Game ROMs"
        "🌐 Kiwix ZIM files (offline Wikipedia etc.)"
        "🗺️  Headway Maps (OSM PBF files)"
        "🎵 Free Music Archive (CC-licensed music)"
        "🎬 Movies (public domain films, cartoons, documentaries)"
        "🎙️  Audiobooks (LibriVox, Old Time Radio, spoken word)"
        "🖨️  Thingiverse / 3D Models (Internet Archive)"
        "📦 Other Internet Archive Hoards"
        "⬇️  Download ALL above (configure each then run all)"
        "🔧 Install Prerequisites (wget, curl, jq, aria2, ia CLI...)"
    )

    while true; do
        header "DataHearth Download Manager"
        echo ""
        echo -e "  ${BOLD}Download Directory:${NC} $BASE_DIR"
        echo -e "  ${BOLD}IA Progress File: ${NC} $IA_PROGRESS_FILE"
        echo ""
        echo -e "  Select services to configure:"
        echo ""

        for i in "${!services[@]}"; do
            echo -e "  [${YELLOW}$((i+1))${NC}] ${services[$i]}"
        done
        echo -e "  [${RED}0${NC}] Exit"
        echo ""

        read -rp "  Enter choices (space-separated, e.g. '1 3 5'): " -a choices

        local do_gutenberg=false  do_exodus=false   do_kiwix=false
        local do_headway=false    do_music=false     do_movies=false
        local do_audiobooks=false do_thingi=false    do_hoards=false
        local do_install=false    do_any=false

        for c in "${choices[@]}"; do
            case "$c" in
                1)  do_gutenberg=true;  do_any=true ;;
                2)  do_exodus=true;     do_any=true ;;
                3)  do_kiwix=true;      do_any=true ;;
                4)  do_headway=true;    do_any=true ;;
                5)  do_music=true;      do_any=true ;;
                6)  do_movies=true;     do_any=true ;;
                7)  do_audiobooks=true; do_any=true ;;
                8)  do_thingi=true;     do_any=true ;;
                9)  do_hoards=true;     do_any=true ;;
                10) do_gutenberg=true; do_exodus=true;     do_kiwix=true
                    do_headway=true;   do_music=true;      do_movies=true
                    do_audiobooks=true; do_thingi=true;    do_hoards=true
                    do_any=true ;;
                11) do_install=true;    do_any=true ;;
                0)  log "Goodbye!"; exit 0 ;;
                *)  warn "Unknown option: $c" ;;
            esac
        done

        if ! $do_any; then
            warn "No valid option selected — please enter a number from the menu."
            continue
        fi

        # Install prerequisites first if requested
        $do_install    && install_prerequisites

        $do_gutenberg  && download_gutenberg
        $do_exodus     && download_exodus
        $do_kiwix      && download_kiwix
        $do_headway    && download_headway
        $do_music      && download_music
        $do_movies     && { setup_ia_api_key; download_movies; }
        $do_audiobooks && { setup_ia_api_key; download_audiobooks; }
        $do_thingi     && { setup_ia_api_key; download_thingiverse; }
        $do_hoards     && { setup_ia_api_key; download_ia_hoards; }

        log "All selected tasks complete!"
        info "Files saved to: $BASE_DIR"
        echo ""
        read -rp "  Press Enter to return to the menu..." _dummy
    done
}

# =============================================================================
# ENTRYPOINT
# =============================================================================

mkdir -p "$BASE_DIR" "$LOG_DIR" "$IA_DIR/collections"
touch "$IA_PROGRESS_FILE"

check_deps
main_menu
