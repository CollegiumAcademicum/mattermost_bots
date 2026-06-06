"""Bearer token authentication dependency for the postbot HTTP API."""
import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.context import get_bot

_bearer = HTTPBearer()


def verify_api_secret(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> None:
    """Raise 401 if the Bearer token does not match WEBUI_API_SECRET."""
    bot = get_bot()
    if not bot.config.webui_api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not available",
        )
    if not hmac.compare_digest(credentials.credentials, bot.config.webui_api_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API secret",
            headers={"WWW-Authenticate": "Bearer"},
        )
