# Immutable Python runtime for the private Quantify V1 API.
FROM python:3.12.6-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.production.lock ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.production.lock

COPY pyproject.toml README.md ./
COPY quantify ./quantify
COPY fixtures/sec ./fixtures/sec
RUN pip install --no-deps --no-cache-dir . \
    && groupadd --gid 10001 quantify \
    && useradd --uid 10001 --gid quantify --create-home --shell /usr/sbin/nologin quantify \
    && chown -R root:root /app \
    && chmod -R a=rX /app

USER quantify

EXPOSE 8080

CMD ["sh", "-c", "uvicorn --factory quantify.production:create_production_app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]
