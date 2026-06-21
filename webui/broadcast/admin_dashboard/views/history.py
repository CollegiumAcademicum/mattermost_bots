from django.shortcuts import render
from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin


@require_bot_admin
def history(request):
    page = int(request.GET.get("page", 1))
    data = admin_client.get_history(page=page, per_page=20)
    total_pages = max(1, -(-data["total"] // 20))  # ceiling division
    return render(request, "admin_dashboard/history.html", {
        "results": data["results"],
        "page": page,
        "total_pages": total_pages,
        "total": data["total"],
    })
