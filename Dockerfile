FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/Handkep/werkstatt-log-mvp"
LABEL org.opencontainers.image.description="Zelter5 Raumlog – gemeinsame Räume dokumentieren"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data && chown 1000:1000 /data

ENV DATA_DIR=/data
USER 1000:1000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--limit-concurrency", "32"]
