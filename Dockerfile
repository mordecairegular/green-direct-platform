# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    GREEN_DIRECT_ENABLE_PILOT_AUTH=1 \
    GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0 \
    GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store \
    GREEN_DIRECT_MAX_UPLOAD_MB=20 \
    GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8503 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fonts-noto-cjk \
        libglib2.0-0 \
        libnss3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-runtime.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY samples ./samples

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data/pilot_store /app/.streamlit \
    && chown -R appuser:appuser /data /app

USER appuser

EXPOSE 8503

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8503/_stcore/health', timeout=3).read()"

CMD ["python", "-m", "streamlit", "run", "src/green_direct/ui/app.py", "--server.address=0.0.0.0", "--server.port=8503", "--server.headless=true", "--browser.gatherUsageStats=false"]
