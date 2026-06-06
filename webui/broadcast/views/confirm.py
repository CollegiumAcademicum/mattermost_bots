"""Confirm broadcast view — step 2 of 3."""
import logging

import requests as http_requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from broadcast.services.channel_service import get_channels
from broadcast.services.postbot_client import send_broadcast

logger = logging.getLogger(__name__)


def _resolve_channel_ids(
    selected_groups: list[str],
    selected_individual: list[str],
    channels_data: dict,
) -> tuple[list[str], list[str]]:
    """Return (deduplicated channel_ids, human-readable names) from session selections."""
    channel_ids: set[str] = set()
    resolved_names: list[str] = []

    all_groups = {
        **channels_data.get("groups", {}),
        **channels_data.get("private_groups", {}),
    }
    for group_name in selected_groups:
        for ch in all_groups.get(group_name, []):
            if ch["id"] not in channel_ids:
                channel_ids.add(ch["id"])
                resolved_names.append(f"{ch['display_name']} (group: {group_name})")

    by_id = {c["id"]: c for c in channels_data.get("individual_channels", [])}
    for ch_id in selected_individual:
        if ch_id not in channel_ids and ch_id in by_id:
            channel_ids.add(ch_id)
            resolved_names.append(by_id[ch_id]["display_name"])

    return list(channel_ids), resolved_names


@login_required
def confirm(request):
    message = request.session.get("broadcast_message")
    if not message:
        return redirect("broadcast:compose")

    selected_groups = request.session.get("broadcast_groups", [])
    selected_individual = request.session.get("broadcast_individual", [])
    try:
        channels_data = get_channels()
    except Exception as exc:
        logger.error(f"Failed to load channels for confirm: {exc}")
        messages.error(request, "Could not load channels. Please try composing again.")
        return redirect("broadcast:compose")
    channel_ids, resolved_names = _resolve_channel_ids(
        selected_groups, selected_individual, channels_data
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "back":
            return redirect("broadcast:compose")
        if action == "send":
            try:
                result = send_broadcast(
                    message, channel_ids, sender=request.user.username
                )
                for key in ("broadcast_message", "broadcast_groups", "broadcast_individual"):
                    request.session.pop(key, None)
                request.session["broadcast_result"] = result
                return redirect("broadcast:result")
            except http_requests.ConnectionError:
                messages.error(
                    request, "postbot is unreachable. Please try again later."
                )
            except http_requests.HTTPError as exc:
                messages.error(request, f"Broadcast failed: {exc}")

    return render(
        request,
        "broadcast/confirm.html",
        {"message": message, "resolved_names": resolved_names, "channel_ids": channel_ids},
    )
