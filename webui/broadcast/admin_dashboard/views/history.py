import math

import requests
from django.contrib import messages
from django.shortcuts import render

from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin


@require_bot_admin
def history(request):
    page = int(request.GET.get("page", 1))
    postbot_offline = False
    results = []
    total_pages = 1
    total = 0
    try:
        data = admin_client.get_history(page=page, per_page=20)
        total_pages = max(1, math.ceil(data["total"] / 20))
        results = data["results"]
        total = data["total"]
    except (requests.ConnectionError, requests.Timeout):
        postbot_offline = True
    except Exception as exc:
        messages.error(request, f"Fehler beim Laden des Verlaufs: {exc}")
    return render(request, "admin_dashboard/history.html", {
        "results": results,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "postbot_offline": postbot_offline,
    })
