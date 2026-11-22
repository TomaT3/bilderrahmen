FROM python:3.13.9-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home rahmen \
    && mkdir -p /data /config && chown rahmen /data

USER rahmen
EXPOSE 8080 8081
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=4)"
CMD ["python", "-m", "bilderrahmen.main"]
