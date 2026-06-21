def bot_admin(request):
    """Expose is_bot_admin flag to all templates."""
    is_admin = (
        request.user.is_authenticated
        and (request.user.is_superuser or request.user.groups.filter(name="BotAdmins").exists())
    )
    return {"is_bot_admin": is_admin}
