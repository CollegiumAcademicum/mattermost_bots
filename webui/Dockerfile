FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-group dev

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uv run python manage.py migrate --settings=webui.settings && uv run python manage.py collectstatic --noinput --settings=webui.settings && uv run python manage.py createsuperuser --noinput --settings=webui.settings || true && uv run gunicorn webui.wsgi:application --config gunicorn.conf.py"]
