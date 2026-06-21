import requests
from django.shortcuts import render, redirect
from django.contrib import messages
from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin


def _build_sections(cfg: dict, by_id: dict) -> list:
    """Pre-resolve channel IDs to display names for template rendering."""
    sections = []
    for key, label in [("groups", "Gruppen"), ("private_groups", "Private Gruppen")]:
        entries = []
        for name, data in cfg.get(key, {}).items():
            entry = {
                "name": name,
                "channels": data.get("channels", []),
                "aliases": data.get("aliases", []),
                "channel_display": [
                    by_id.get(cid, cid) for cid in data.get("channels", [])
                ],
            }
            entries.append(entry)
        sections.append({"key": key, "label": label, "entries": entries})
    return sections


def _handle_post(request, cfg: dict) -> dict:
    """Process a POST action and return updated config dict."""
    action = request.POST.get("action")
    section = request.POST.get("section")  # "groups" or "private_groups"

    if action == "delete_group":
        name = request.POST.get("name")
        cfg.get(section, {}).pop(name, None)

    elif action == "add_group":
        name = request.POST.get("name", "").strip()
        channels = request.POST.getlist("channels")
        aliases_raw = request.POST.get("aliases", "")
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        if name:
            cfg.setdefault(section, {})[name] = {"channels": channels, "aliases": aliases}

    elif action == "edit_group":
        old_name = request.POST.get("old_name")
        new_name = request.POST.get("name", "").strip()
        channels = request.POST.getlist("channels")
        aliases_raw = request.POST.get("aliases", "")
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        if old_name in cfg.get(section, {}):
            cfg[section].pop(old_name)
            if new_name:
                cfg[section][new_name] = {"channels": channels, "aliases": aliases}

    elif action == "delete_whitelist":
        name = request.POST.get("name")
        cfg.get("whitelist", {}).pop(name, None)

    elif action == "add_whitelist":
        name = request.POST.get("name", "").strip()
        user_id = request.POST.get("id", "").strip()
        aliases_raw = request.POST.get("aliases", "")
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        if name and user_id:
            cfg.setdefault("whitelist", {})[name] = {"id": user_id, "aliases": aliases}

    return cfg


@require_bot_admin
def config(request):
    if request.method == "POST":
        try:
            cfg = admin_client.get_config()
            cfg = _handle_post(request, cfg)
            admin_client.put_config(cfg)
            messages.success(request, "Konfiguration gespeichert.")
        except Exception as exc:
            messages.error(request, f"Fehler beim Speichern: {exc}")
        return redirect("admin_dashboard:config")

    # GET
    cfg = {"groups": {}, "private_groups": {}, "whitelist": {}}
    channels_data = {"individual_channels": []}
    postbot_offline = False
    try:
        cfg = admin_client.get_config()
        channels_data = admin_client.get_channels()
    except (requests.ConnectionError, requests.Timeout):
        postbot_offline = True
    except Exception as exc:
        messages.error(request, f"Fehler beim Laden: {exc}")

    by_id = {ch["id"]: ch.get("display_name", ch["id"])
             for ch in channels_data.get("individual_channels", [])}
    sections = _build_sections(cfg, by_id)
    all_channels = [
        {"id": ch["id"], "display_name": ch.get("display_name", ch["id"])}
        for ch in channels_data.get("individual_channels", [])
    ]

    return render(request, "admin_dashboard/config.html", {
        "cfg": cfg,
        "sections": sections,
        "all_channels": all_channels,
        "postbot_offline": postbot_offline,
    })
