from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def _is_bot_admin(user) -> bool:
    return user.is_superuser or user.groups.filter(name="BotAdmins").exists()


def require_bot_admin(view_func):
    """Decorator: require authenticated BotAdmins group member."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")
        if not _is_bot_admin(request.user):
            return HttpResponseForbidden("Zugang nur für BotAdmins.")
        return view_func(request, *args, **kwargs)
    return wrapper
