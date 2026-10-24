FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADING_MODE=paper \
    LIVE_TRADING=false \
    PAPER_TRADING=true \
    ML_REGISTRY_PATH=models/model_registry.json \
    TELEGRAM_ENABLED=false \
    ML_FILTER_ENABLED=false

WORKDIR /app

COPY pyproject.toml README.md ./
COPY main.py ./
COPY src ./src
COPY deploy/railway/start.sh ./deploy/railway/start.sh

RUN pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin silverbot \
    && mkdir -p /app/data /app/logs /app/models /app/reports /app/var \
    && chown -R silverbot:silverbot /app

USER silverbot

# No VOLUME line: Railway rejects it. Compose bind-mounts the directories; Railway mounts its volume at /app/var.

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m silver_bot.health

CMD ["python", "-m", "silver_bot"]
