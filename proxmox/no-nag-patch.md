# Proxmox VE — No Subscription Nag Screen Removal Guide

> **Tested on:** Proxmox VE 7.x and 8.x  
> **Legal status:** Fully legal. Proxmox VE is AGPL-3.0 licensed open source software. You are not bypassing any license, only removing a UI element that promotes a paid subscription service.

---

## Overview

Proxmox VE displays a "No valid subscription" popup on every login when you are not using an enterprise subscription repo. This guide covers:

1. Switching to the free (no-subscription) package repository
2. Removing the nag screen popup from the web UI
3. (Optional) Using the community tteck helper scripts for automation

---

## Step 1 — Switch to the No-Subscription Repository

The enterprise repo requires a paid subscription key. Switch it off and enable the free community repo.

### Disable the Enterprise Repository

```bash
# Comment out the enterprise repo
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list

# Also disable Ceph enterprise repo if present (PVE 8+)
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/ceph.list 2>/dev/null || true
```

### Enable the No-Subscription Repository

```bash
# Add the free no-subscription repo (replace bookworm with your Debian release if different)
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-no-subscription.list
```

> **Note:** For Proxmox VE 7.x (Debian Bullseye), replace `bookworm` with `bullseye`.

### Update Package Lists

```bash
apt update
apt dist-upgrade -y
```

---

## Step 2 — Remove the Nag Screen (JavaScript Patch)

The nag dialog is rendered by the Proxmox web UI JavaScript. The file to patch is:

```
/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

### Manual Patch (Recommended — Understand What You're Changing)

The nag is triggered by a function call to `Ext.Msg.show(...)` inside a check for subscription status. We replace it with a void call so it never fires.

```bash
# Make a backup first
cp /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js \
   /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js.bak

# Apply the patch
sed -i.bak "s/Ext\.Msg\.show({[[:space:]]*title: gettext('No valid sub/void({title: gettext('No valid sub/" \
  /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

### Verify the Patch Worked

```bash
# Should return no output if the original call no longer exists
grep -n "Ext.Msg.show" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js

# Should return a result showing the void replacement
grep -n "void({title" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

### Restart the Web Service

```bash
systemctl restart pveproxy
```

Wait ~5 seconds, then refresh your browser (hard refresh: `Ctrl+Shift+R`). The nag dialog will be gone.

---

## Step 3 — Make the Patch Survive Updates (Optional but Recommended)

Proxmox updates will overwrite `proxmoxlib.js` and bring the nag back. Use a `dpkg` hook or a cron job to re-apply the patch after updates.

### Option A — Post-Install Hook (dpkg)

Create a hook script that runs after `proxmox-widget-toolkit` is upgraded:

```bash
cat << 'EOF' > /etc/apt/apt.conf.d/99-pve-no-nag
DPkg::Post-Invoke { "sed -i.bak \"s/Ext\\.Msg\\.show({[[:space:]]*title: gettext('No valid sub/void({title: gettext('No valid sub/\" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js && systemctl restart pveproxy || true"; };
EOF
```

### Option B — Simple Shell Script (run after each `apt upgrade`)

Save this as `/usr/local/bin/pve-nag-remove` and call it manually or from cron:

```bash
cat << 'EOF' > /usr/local/bin/pve-nag-remove
#!/bin/bash
# Proxmox VE nag screen removal script
# Run after any system update

JSFILE="/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js"

if grep -q "Ext.Msg.show" "$JSFILE"; then
  echo "[*] Nag screen detected — patching..."
  cp "$JSFILE" "${JSFILE}.bak"
  sed -i "s/Ext\.Msg\.show({[[:space:]]*title: gettext('No valid sub/void({title: gettext('No valid sub/" "$JSFILE"
  systemctl restart pveproxy
  echo "[+] Patch applied and pveproxy restarted."
else
  echo "[✓] Already patched — no action needed."
fi
EOF

chmod +x /usr/local/bin/pve-nag-remove
```

Run it:

```bash
/usr/local/bin/pve-nag-remove
```

---

## Step 4 — (Optional) Use tteck's Community Helper Scripts

The community-maintained Proxmox VE Helper Scripts project automates all of the above (and much more like LXC container creation, GPU passthrough setup, etc.).

**Website:** https://helper-scripts.com  
**GitHub:** https://github.com/community-scripts/ProxmoxVE

### Post-Install Wizard (includes nag removal)

Run this on your Proxmox host as root:

```bash
bash -c "$(wget -qLO - https://github.com/community-scripts/ProxmoxVE/raw/main/misc/post-pve-install.sh)"
```

This interactive script will:
- Switch you to the no-subscription repo
- Remove the nag screen
- Disable the enterprise repo
- Optionally enable high availability and other tweaks

> **Security note:** Always review scripts before piping them to bash. The source is publicly auditable on GitHub.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Nag returns after `apt upgrade` | `proxmox-widget-toolkit` was updated | Re-run the patch or set up the dpkg hook |
| Browser still shows nag | Browser cache | Hard refresh: `Ctrl+Shift+R` or clear cache |
| `sed` command finds nothing | PVE version changed the JS | Manually inspect the file: `grep -n "No valid sub" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js` and adapt the sed pattern |
| `pveproxy` fails to restart | Syntax error in patched JS | Restore the backup: `cp proxmoxlib.js.bak proxmoxlib.js` and try a different patch method |

---

## Restoring the Original File

If anything goes wrong, the backup is always at:

```bash
cp /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js.bak \
   /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
systemctl restart pveproxy
```

---

## References

- Proxmox VE Source Code: https://git.proxmox.com
- Proxmox Package Repositories: https://pve.proxmox.com/wiki/Package_Repositories
- Community Helper Scripts: https://helper-scripts.com
