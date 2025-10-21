# Multi-stage build producing a slim image with the FastAPI server and Dash dashboard.
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for scientific stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py README.md requirements.txt /app/
COPY moex_bot/requirements.txt /app/moex_bot/

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -e .

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "moex_bot.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
