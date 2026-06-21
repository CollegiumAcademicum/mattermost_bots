FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml .
COPY postbot/pyproject.toml postbot/
COPY postbot/README.md postbot/
COPY mmbot_framework/pyproject.toml mmbot_framework/
COPY mmbot_framework/README.md mmbot_framework/

RUN uv sync --package mailman

COPY . .

CMD ["uv", "run", "python", "postbot/main.py"]
