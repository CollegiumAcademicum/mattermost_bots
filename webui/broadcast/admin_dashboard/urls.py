from django.urls import path
from broadcast.admin_dashboard.views import history as history_view
from broadcast.admin_dashboard.views import config as config_view
from broadcast.admin_dashboard.views import tasks as tasks_view

app_name = "admin_dashboard"

urlpatterns = [
    path("history/", history_view.history, name="history"),
    path("config/", config_view.config, name="config"),
    path("tasks/", tasks_view.tasks_view, name="tasks"),
]
