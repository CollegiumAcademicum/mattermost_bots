from broadcast.admin_dashboard.views import _is_bot_admin


def bot_admin(request):
    """Expose is_bot_admin flag to all templates."""
    is_admin = request.user.is_authenticated and _is_bot_admin(request.user)
    return {"is_bot_admin": is_admin}
