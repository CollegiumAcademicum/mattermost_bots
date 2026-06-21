# Podman Deployment Guide

Two options for deploying postbot + webui on a rootless Podman server.

## Architecture

Two containers, one `.env`, one shared `data/` directory tree:

```
~/mattermost-bots/               (server host)
├── .env                         ← one file, used by both containers
├── data/
│   ├── postbot/                 → mounted into postbot at /app/data
│   │   ├── channels.toml
│   │   ├── broadcast_log.db
│   │   └── logs/
│   ├── webui/                   → mounted into webui at /app/data
│   │   └── webui.sqlite3
│   └── certs/                   → mounted into webui at /app/certs (read-only)
│       └── ca.pem
```

- **postbot** handles the Mattermost WebSocket connection and exposes a FastAPI on port 8000 (internal only)
- **webui** is the Django admin UI, exposed on port 8080
- Both run on an internal Podman network; webui reaches postbot at `http://postbot:8000`
- postbot mounts `.env` as a file (reads it with `dotenv_values()`); webui receives it as environment variables via systemd's `EnvironmentFile=` — same result either way

---

## Comparison

| | Option A: podman-compose | Option B: Quadlet |
|---|---|---|
| Setup effort | Low | Medium |
| Config files | existing `docker-compose.yaml` | 3 files in `deploy/quadlet/` |
| Process manager | podman-compose (must be running) | systemd (native) |
| Start on boot | manual / cron workaround | `loginctl enable-linger` |
| Logs | `podman-compose logs` | `journalctl --user -u <name>` |
| Updates | pull + restart manually | pull + `systemctl --user restart` |
| Production fit | OK for quick setups | Recommended |

**TL;DR:** Use Option A to get something running fast. Use Option B if this is a permanent deployment.

---

## Prerequisites (both options)

On your local machine, build and push the images first:

```bash
./publish.sh
```

On the server, create the data directories and `.env`:

```bash
mkdir -p ~/mattermost-bots/data/{postbot,webui,certs}
cd ~/mattermost-bots
cp /path/to/.env .env
nano .env   # adjust the values for the server (see table below)

# Optional: place your LDAP CA cert
cp /path/to/ca.pem data/certs/ca.pem
```

### .env values that differ on the server

| Variable | Local dev value | Server value |
|---|---|---|
| `POSTBOT_API_URL` | `http://localhost:8000` | `http://postbot:8000` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `yourdomain.com,localhost` |
| `LDAP_CA_CERT_PATH` | `scripts/ca.cert` | `/app/certs/ca.pem` |
| `LOG_FILE` | `data/logs/bot.log` | `/app/data/logs/bot.log` |
| `CHANNELS_TOML_PATH` | `data/postbot/channels.toml` | `/app/data/channels.toml` |
| `DB_PATH` | `data/postbot/broadcast_log.db` | `/app/data/broadcast_log.db` |
| `TASKS_DIR` | `data/tasks` | `/app/data/tasks` |

---

## Option A: podman-compose

### 1. Install podman-compose

```bash
pip install --user podman-compose
# or on Fedora/RHEL:
sudo dnf install podman-compose
```

### 2. Get the compose file

```bash
cd ~/mattermost-bots
# copy docker-compose.yaml from the repo, then edit it:
nano docker-compose.yaml
```

Replace the `build:` blocks with `image:` so it pulls from Docker Hub instead of building:

```yaml
services:
  postbot:
    image: philippbtz/mattermost-postbot:latest
    # (remove the build: block)
    ...
  webui:
    image: philippbtz/mattermost-webui:latest
    # (remove the build: block)
    ...
```

### 3. Start

```bash
podman-compose pull
podman-compose up -d
```

### 4. Verify

```bash
podman-compose ps
podman-compose logs -f postbot
podman-compose logs -f webui
```

### 5. Auto-start on boot

podman-compose has no native systemd integration. Workaround:

```bash
crontab -e
# Add:
@reboot cd ~/mattermost-bots && podman-compose up -d
```

Or use `loginctl enable-linger` + a manual systemd unit — at that point Option B is cleaner.

### Updating

```bash
podman-compose pull
podman-compose up -d
```

---

## Option B: Quadlet (recommended)

Quadlet reads `.container` and `.network` files and generates systemd units automatically.
The ready-to-use files are in `deploy/quadlet/` in this repo.

### 1. Copy the Quadlet files

```bash
mkdir -p ~/.config/containers/systemd
cp /path/to/repo/deploy/quadlet/* ~/.config/containers/systemd/
```

### 2. Reload systemd and start

```bash
systemctl --user daemon-reload

# Check that units were generated correctly
systemctl --user list-unit-files | grep -E 'postbot|webui|internal'

systemctl --user start postbot
systemctl --user start webui
```

### 3. Enable auto-start on boot

```bash
loginctl enable-linger
```

This keeps your user's systemd session alive even when not logged in, so the `WantedBy=default.target` entries take effect on reboot.

### 4. Verify

```bash
systemctl --user status postbot
systemctl --user status webui
journalctl --user -u postbot -f
journalctl --user -u webui -f
```

### Updating

```bash
podman pull philippbtz/mattermost-postbot:latest
systemctl --user restart postbot

podman pull philippbtz/mattermost-webui:latest
systemctl --user restart webui
```

### Common commands

```bash
systemctl --user stop webui          # stop
systemctl --user restart postbot     # restart
systemctl --user disable webui       # remove from auto-start
podman logs postbot                  # raw container logs
```

---

## Troubleshooting

**`podman pull` fails with auth error**
```bash
podman login docker.io
```

**webui can't reach postbot**
Verify `ContainerName=postbot` is set and both containers are on `internal.network`:
```bash
podman network inspect internal | grep -A5 containers
```

**Port 8080 not reachable**
Check the firewall:
```bash
sudo firewall-cmd --add-port=8080/tcp --permanent && sudo firewall-cmd --reload
# or on Debian/Ubuntu:
sudo ufw allow 8080/tcp
```

**Quadlet units not appearing after `daemon-reload`**
Check for syntax errors:
```bash
/usr/lib/systemd/system-generators/podman-system-generator --user --dryrun 2>&1
```
