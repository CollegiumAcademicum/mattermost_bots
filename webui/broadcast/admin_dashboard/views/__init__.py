from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def require_bot_admin(view_func):
    """Decorator: require authenticated BotAdmins group member."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.get_full_path()}")
        if not request.user.groups.filter(name="BotAdmins").exists():
            return HttpResponseForbidden("Zugang nur für BotAdmins.")
        return view_func(request, *args, **kwargs)
    return wrapper
