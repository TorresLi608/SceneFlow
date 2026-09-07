FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/app.db

WORKDIR /app/backend

# ffmpeg/ffprobe are runtime dependencies for audio audition and media merging
# with ffprobe, and voice-sheet and export concatenation shell out to ffmpeg.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/sceneflow-entrypoint

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/backend/private_generated /app/data \
    && chown -R app:app /app/backend /app/data \
    && chmod 700 /app/data \
    && chmod 755 /usr/local/bin/sceneflow-entrypoint

# The entrypoint fixes bind-mount ownership before dropping to the app user.
ENTRYPOINT ["sceneflow-entrypoint"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
