# 🖥️ DataHearth

> **An Internet at Home Project**  
> *DataHearth.net*

---

## 📋 Overview

A custom-built server designed to replace commonly used internet services with locally-run alternatives. This project prioritizes:

- **Disaster Preparedness** — Functions without internet during natural or man-made disasters
- **Backup Power Compatibility** — Designed to work with backup power systems
- **Privacy Control** — Keep your data local instead of sending it to external servers

---
# Current State of Project
Still setting up the project. Got the core working, but most of the scripts are vibe coded and still need to test. Not Close to Production Ready
## 🔧 Hardware

### Motherboard

**HUANANZHI X99 F8D Plus** — Selected for its **6 PCIe x16 slots** (three are x8 electrical but accept x16 cards), enabling multiple GPUs for AI generation workloads. Dual Xeon CPUs provide the necessary cores to run all services.

### GPUs

| Card | Quantity | Purpose |
|------|----------|---------|
| **NVIDIA P40** | 3 | LLM inference (lacks tensor cores for image/video generation) |
| **NVIDIA V100** | 1 | Image and video generation (has tensor cores) |

> 💡 **Note:** Two P40s and the V100 are optional. Removing them significantly reduces GPU costs and eliminates the need for dual power supplies and the sync adapter.

### Cooling Solution

Server-class GPUs lack built-in cooling fans. The solution:

- **3D-printed shrouds** with **Arctic CPU fans**
- Blower fans were too loud
- Single Arctic fans provided insufficient cooling
- **Two Arctic fans back-to-back** increases pressure enough to cool cards quietly

### Build Configuration

An open-frame build was necessary due to:

- Two-slot-wide GPU cards cannot all install directly on the motherboard
- Cards with cooling are too large for standard cases
- eATX motherboard doesn't fit standard cases
- Dual power supply requirement

---

## 💻 Software Stack

### Hypervisor

**Proxmox** — The main server runs Proxmox as the virtualization platform.

> 📝 Instructions for running as open-source software and eliminating the subscription nag screen are included in [`proxmox/no-nag-patch.md`](proxmox/no-nag-patch.md).

---

## 🖥️ Virtual Machines

Each VM has a **Python helper script** that lets you configure desired services and IP address, then generates a `docker-compose.yml` and installation script.

There is also an extra script in Lexicon that download various media files from free sources. Kiwix Guttenburg. Internet Archive.

---

### 🛡️ Sentinel — *The Gatekeeper*

**Purpose:** Network gateway and infrastructure management

| Service | Function |
|---------|----------|
| **Tailscale** | Routing enabled — any connected computer can access the Proxmox network |
| **Backup Services** | System backup management |
| **Omada Controller** | Manage Netgear routers, access points, and homelab network |
| **VPN + Proxy** | Route traffic for anonymity |

---

### 📚 Lexicon — *Media Server*

**Purpose:** Central media and content management

| Service | Function | Status |
|---------|----------|--------|
| **Jellyfin** | Movies & TV | ✅ Active |
| **PhotoPrism** | Image management | ✅ Active |
| **Kavita** | eBooks | ✅ Active |
| **Audiobookshelf** | Audiobooks | ✅ Active |
| **Navidrome** | Web-based music streaming | ✅ Active |
| **Snapcast + Mopidy** | Smart speaker music streaming | ✅ Active |
| **Kiwix** | Offline Wikipedia & similar services | ✅ Active |
| **Nextcloud** | File storage | ✅ Active |
| **Gitea** | Project/code storage | ✅ Active |
| **Manyfold** | STL file storage | ✅ Active |
| **Headway** | Offline maps | 🔧 Setup pending |
| **Solr + Grok** | Search functionality | 🔧 Setup pending |
| **TVHeadEnd** | DVR functionality | 🔧 Setup pending |
| **romM** | RetroArch Archive | 🔧 Setup pending |
| **exoDos** | Collection of Dos games | 🔧 Setup pending |

> 💡 **Tip:** Most services support multiple instances, allowing you to separate content into **curated**, **everything**, and **adult-only** servers.

---

### 🎙️ Echo — *Voice Assistant AI*

**Purpose:** AI services for Home Assistant voice control

| Service | Function |
|---------|----------|
| **Ollama** | Home Assistant conversation agent |
| **Whisper** | Speech-to-text conversion |

---

### 🏠 Citadel — *Home Automation*

**Purpose:** Home Assistant hub

| Feature | Description |
|---------|-------------|
| **Home Assistant** | Central home automation platform |
| **USB Passthrough** | Zigbee/Z-Wave adapter for light control |

> 🎯 **Goal:** Migrate away from any IoT devices that require internet to function.

---

### 🧠 Deepthought — *LLM Server*

**Purpose:** Local large language model inference

| Service | Function |
|---------|----------|
| **Ollama** | Run LLM models locally |
| **Open WebUI** | Web interface for model interaction |

**Use Cases:**
- Run RooCode or other AI agents without internet
- Uncensored and unmonitored usage

---

### 🎨 Canvas — *Creative AI*

**Purpose:** Image and video generation

| Service | Function |
|---------|----------|
| **ComfyUI** | AI image/video generation interface |

**Benefits:**
- Uncensored and unmonitored creative generation
- Full local control over outputs

---

## 📁 Project Structure

```
DataHearth/
├── Citadel/          # Home Assistant configuration
├── deepthought/      # LLM server setup
├── echo/             # Voice assistant AI
├── lexicon/          # Media server configuration
├── proxmox/          # Hypervisor documentation
├── Sentinel/         # Gateway services
└── readme.md         # This file
```

---

## 📄 License

This project is designed for personal use and disaster preparedness.

---

*Built with ❤️ for privacy, resilience, and independence.*
