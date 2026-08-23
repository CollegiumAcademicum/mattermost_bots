"""Compose broadcast view — step 1 of 3."""
import logging
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from broadcast.admin_dashboard.views import _is_bot_admin
from broadcast.services.channel_service import get_channels

logger = logging.getLogger(__name__)
_ATTACHMENTS_SESSION_KEY = "broadcast_attachments"
_ATTACHMENT_DIR_PREFIX = "broadcast-attachments-"


def _clear_saved_attachments(attachments: list[dict]) -> None:
    parent_dirs: set[Path] = set()
    for attachment in attachments:
        file_path = attachment.get("path")
        if not file_path:
            continue
        path = Path(file_path)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"Failed to remove temporary attachment file {path}: {exc}")
        parent_dirs.add(path.parent)

    for parent_dir in parent_dirs:
        if parent_dir.exists() and parent_dir.name.startswith(_ATTACHMENT_DIR_PREFIX):
            try:
                shutil.rmtree(parent_dir)
            except OSError as exc:
                logger.warning(
                    f"Failed to remove temporary attachment directory {parent_dir}: {exc}"
                )


def _store_uploaded_attachments(uploaded_files: list) -> list[dict[str, str]]:
    if not uploaded_files:
        return []

    temp_dir = Path(tempfile.mkdtemp(prefix="broadcast-attachments-", dir="/tmp"))
    stored_attachments: list[dict[str, str]] = []
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        original_name = Path(uploaded_file.name).name or f"attachment-{index}"
        target_path = temp_dir / f"{uuid4().hex}_{original_name}"
        with target_path.open("wb") as out:
            for chunk in uploaded_file.chunks():
                out.write(chunk)
        stored_attachments.append({
            "name": original_name,
            "path": str(target_path),
            "content_type": uploaded_file.content_type or "application/octet-stream",
        })
    return stored_attachments


@login_required
def compose(request):
    existing_attachments = request.session.get(_ATTACHMENTS_SESSION_KEY, [])
    if request.method == "POST":
        message = request.POST.get("message", "").strip()
        selected_groups = request.POST.getlist("groups")
        selected_individual = request.POST.getlist("individual_channels")
        excluded_channels = request.POST.getlist("excluded_channels")
        uploaded_files = request.FILES.getlist("attachments")

        attachments = existing_attachments
        if uploaded_files:
            _clear_saved_attachments(existing_attachments)
            attachments = _store_uploaded_attachments(uploaded_files)
            request.session[_ATTACHMENTS_SESSION_KEY] = attachments

        if not message:
            messages.error(request, "Message cannot be empty.")
        elif not selected_groups and not selected_individual:
            messages.error(request, "Select at least one channel or group.")
        else:
            request.session["broadcast_message"] = message
            request.session["broadcast_groups"] = selected_groups
            request.session["broadcast_individual"] = selected_individual
            request.session["broadcast_excluded"] = excluded_channels
            request.session[_ATTACHMENTS_SESSION_KEY] = attachments
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
        "private_groups": channels_data.get("private_groups") if _is_bot_admin(request.user) else None,
        "postbot_offline": postbot_offline,
        "attachments": request.session.get(_ATTACHMENTS_SESSION_KEY, []),
    })
