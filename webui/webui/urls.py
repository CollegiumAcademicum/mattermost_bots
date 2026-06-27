from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView

from broadcast.views.login import LDAPAwareLoginView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", RedirectView.as_view(url="/broadcast/", permanent=False)),
    path("admin/", admin.site.urls),
    path(
        "login/",
        LDAPAwareLoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("broadcast/", include("broadcast.urls")),
    path("admin-dashboard/", include("broadcast.admin_dashboard.urls")),
    path("health/", health),
]
