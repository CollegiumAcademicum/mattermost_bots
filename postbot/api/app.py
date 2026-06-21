"""FastAPI application for the postbot HTTP API."""
from fastapi import FastAPI

app = FastAPI(title="postbot API", docs_url=None, redoc_url=None)

# Import routers after app creation to avoid circular imports.
from api.routes import broadcast, channels, config, history  # noqa: E402

app.include_router(channels.router)
app.include_router(broadcast.router)
app.include_router(history.router)
app.include_router(config.router)
