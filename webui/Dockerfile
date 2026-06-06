FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-group dev

COPY . .

RUN python manage.py collectstatic --noinput --settings=webui.settings || true

EXPOSE 8080

CMD ["uv", "run", "gunicorn", "webui.wsgi:application", \
     "--bind", "0.0.0.0:8080", "--workers", "2"]
