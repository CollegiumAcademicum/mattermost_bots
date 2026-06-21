from datetime import datetime

import requests
from django.contrib import messages
from django.shortcuts import redirect, render

from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin


def _format_last_run(last_run_str: str | None) -> str:
    if not last_run_str:
        return "Noch nie"
    dt = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
    return dt.strftime("%d.%m.%Y %H:%M UTC")


@require_bot_admin
def tasks_view(request):
    if request.method == "POST":
        action = request.POST.get("action")
        name = request.POST.get("name", "")

        if action == "run":
            try:
                admin_client.run_task(name)
                messages.success(request, f"Aufgabe '{name}' gestartet.")
            except Exception as exc:
                messages.error(request, f"Fehler beim Starten von '{name}': {exc}")

        elif action == "set_schedule":
            cron = request.POST.get("cron") or None
            try:
                admin_client.set_task_schedule(name, cron)
                if cron:
                    messages.success(request, f"Zeitplan für '{name}' auf '{cron}' gesetzt.")
                else:
                    messages.success(request, f"Zeitplan für '{name}' entfernt.")
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 422:
                    detail = exc.response.json().get("detail", str(exc))
                    messages.error(request, f"Ungültiger Cron-Ausdruck: {detail}")
                else:
                    messages.error(request, f"Fehler beim Setzen des Zeitplans: {exc}")
            except Exception as exc:
                messages.error(request, f"Fehler beim Setzen des Zeitplans: {exc}")

        return redirect("admin_dashboard:tasks")

    # GET
    task_list = []
    try:
        data = admin_client.get_tasks()
        for t in data.get("tasks", []):
            t["last_run_display"] = _format_last_run(t.get("last_run"))
            task_list.append(t)
    except Exception as exc:
        messages.error(request, f"Fehler beim Laden der Aufgaben: {exc}")

    return render(request, "admin_dashboard/tasks.html", {"tasks": task_list})
