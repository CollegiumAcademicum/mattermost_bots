FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY . .

RUN uv sync

CMD ["uv", "run", "python", "postbot/main.py"]
