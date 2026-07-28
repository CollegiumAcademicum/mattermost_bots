FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml .
COPY postbot/pyproject.toml postbot/
COPY postbot/README.md postbot/
COPY mmbot_framework/pyproject.toml mmbot_framework/
COPY mmbot_framework/README.md mmbot_framework/
COPY mmbot_framework/mmbot_framework/ mmbot_framework/mmbot_framework/
COPY webui/pyproject.toml webui/

RUN apt-get update && apt-get install -y --no-install-recommends libreoffice && rm -rf /var/lib/apt/lists/*

RUN uv sync --package mailman

COPY . .

CMD ["uv", "run", "python", "postbot/main.py"]
