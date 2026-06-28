# Deployment Guide

Deploy postbot + webui using podman compose on a rootless Podman server.

## Architecture

```
~/postbot/               (server host)
├── .env                 ← one file for both containers
├── docker-compose.yaml
└── data/
    ├── postbot/         → mounted into postbot at /app/data
    │   ├── channels.toml
    │   ├── broadcast_log.db
    │   ├── tasks/
    │   └── logs/
    ├── webui/           → mounted into webui at /app/data
    └── certs/           → mounted into webui at /app/certs (read-only)
        └── ca.pem
```

Use the [mattermost_bots_deployment](https://github.com/philippbtz/mattermost_bots_deployment) repo — it contains the `docker-compose.yaml`, `.env.example`, `init.sh`, and `update.sh` ready to use on the server.
