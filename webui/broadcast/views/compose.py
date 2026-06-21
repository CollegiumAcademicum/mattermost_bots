"""Compose broadcast view — step 1 of 3."""
import logging

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from broadcast.services.channel_service import get_channels

logger = logging.getLogger(__name__)


@login_required
def compose(request):
    if request.method == "POST":
        message = request.POST.get("message", "").strip()
        selected_groups = request.POST.getlist("groups")
        selected_individual = request.POST.getlist("individual_channels")

        if not message:
            messages.error(request, "Message cannot be empty.")
        elif not selected_groups and not selected_individual:
            messages.error(request, "Select at least one channel or group.")
        else:
            request.session["broadcast_message"] = message
            request.session["broadcast_groups"] = selected_groups
            request.session["broadcast_individual"] = selected_individual
            return redirect("broadcast:confirm")

    postbot_offline = False
    try:
        channels_data = get_channels()
    except (requests.ConnectionError, requests.Timeout):
        postbot_offline = True
        channels_data = {}
    except Exception as exc:
        logger.error(f"Failed to load channels: {exc}")
        messages.warning(request, "Could not load channels — postbot may be unavailable.")
        channels_data = {}

    return render(request, "broadcast/compose.html", {
        "channels_data": channels_data,
        "postbot_offline": postbot_offline,
    })
