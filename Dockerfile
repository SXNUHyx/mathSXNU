# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_DEBUG=0 DJANGO_DB_PATH=/data/db.sqlite3
WORKDIR /app
COPY requirements.txt .
# The optional build secret supports managed proxies without weakening TLS.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi
RUN groupadd --gid 10001 classroom && useradd --uid 10001 --gid classroom --no-create-home classroom \
    && mkdir /data && chown classroom:classroom /data /app
COPY --chown=10001:10001 manage.py ./
COPY --chown=10001:10001 mathsxnu ./mathsxnu
COPY --chown=10001:10001 feedback ./feedback
COPY --chown=10001:10001 templates ./templates
COPY --chown=10001:10001 static ./static
COPY --chown=10001:10001 scripts/container-entrypoint.sh ./scripts/container-entrypoint.sh
USER classroom
# This disposable value is only for static collection; it is never the runtime key.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=static-build-only-not-a-runtime-key \
    DJANGO_DB_PATH=/tmp/build.sqlite3 python manage.py collectstatic --noinput
EXPOSE 8000
ENTRYPOINT ["sh", "/app/scripts/container-entrypoint.sh"]
CMD ["gunicorn", "mathsxnu.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "--access-logfile", "-"]
