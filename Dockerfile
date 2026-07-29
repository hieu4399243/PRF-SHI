FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app/ app/

RUN useradd --create-home appuser \
    && mkdir -p app/data/outbox \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/', timeout=3)" || exit 1

# --workers 1: SESSIONS dict and rate-limit buckets are in-memory per-process (see
# docs/project-roadmap.md P0 Redis migration) — multiple gunicorn workers would each
# get their own copy, breaking session continuity. --threads is safe: gthread runs
# multiple threads inside the SAME process, sharing memory, protected by the app's
# existing per-session threading.Lock.
CMD ["gunicorn", "--bind", "0.0.0.0:5001", \
     "--workers", "1", "--worker-class", "gthread", "--threads", "4", \
     "--timeout", "30", "--graceful-timeout", "20", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app.main:app"]
