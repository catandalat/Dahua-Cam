FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY apps ./apps

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/packages:/app/apps
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
