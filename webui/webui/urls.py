from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from mozilla_django_oidc import views as oidc_views

from broadcast.auth import KeycloakCallbackView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", RedirectView.as_view(url="/broadcast/", permanent=False)),
    path("admin/", admin.site.urls),
    path("login/", oidc_views.OIDCAuthenticationRequestView.as_view(), name="login"),
    path("oidc/callback/", KeycloakCallbackView.as_view(), name="oidc_authentication_callback"),
    path("logout/", oidc_views.OIDCLogoutView.as_view(), name="logout"),
    # Same views under the library's names: SessionRefresh reverses these to exempt them.
    path("login/", oidc_views.OIDCAuthenticationRequestView.as_view(), name="oidc_authentication_init"),
    path("logout/", oidc_views.OIDCLogoutView.as_view(), name="oidc_logout"),
    path(
        "login/failed/",
        TemplateView.as_view(
            template_name="registration/status.html",
            extra_context={
                "status_class": "error",
                "status_message": "Die Anmeldung ist fehlgeschlagen.",
                "action_label": "Erneut versuchen",
            },
        ),
    ),
    path(
        "logged-out/",
        TemplateView.as_view(
            template_name="registration/status.html",
            extra_context={
                "status_class": "success",
                "status_message": "Du wurdest abgemeldet.",
                "action_label": "Anmelden",
            },
        ),
    ),
    path("broadcast/", include("broadcast.urls")),
    path("admin-dashboard/", include("broadcast.admin_dashboard.urls")),
    path("health/", health),
]
