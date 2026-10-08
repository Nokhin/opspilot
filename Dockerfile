FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPSPILOT_DATA_DIR=/app/var \
    OPSPILOT_CORPUS_DIR=/app/corpus/policies

WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY opspilot ./opspilot
COPY corpus ./corpus
RUN pip install --no-cache-dir --no-deps . \
    && groupadd --gid 10001 opspilot \
    && useradd --uid 10001 --gid 10001 --no-create-home opspilot \
    && mkdir -p /app/var \
    && chown -R opspilot:opspilot /app/var

USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=3)"
CMD ["sh", "-c", "python -m opspilot.cli bootstrap && exec uvicorn opspilot.api.main:app --host 0.0.0.0 --port 8080 --workers 1"]
