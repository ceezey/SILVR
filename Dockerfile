FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADING_MODE=paper \
    LIVE_TRADING=false \
    PAPER_TRADING=true \
    TELEGRAM_ENABLED=false \
    ML_FILTER_ENABLED=false

WORKDIR /app

COPY pyproject.toml README.md ./
COPY main.py ./
COPY src ./src

# uid 1000 matches the host user that runs the systemd unit, so bind-mounted folders stay writable.
RUN pip install --no-cache-dir . \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin silvr \
    && mkdir -p /app/data /app/logs /app/models /app/reports \
    && chown -R silvr:silvr /app

USER silvr

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m silvr.health

CMD ["python", "-m", "silvr"]
