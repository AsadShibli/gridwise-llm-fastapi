# Django console only. FastAPI image is the root Dockerfile.
FROM python:3.11-slim

WORKDIR /web

COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web /web
# Default hours/battery profile for the notes-only form.
COPY sample.json /data/sample.json
ENV SAMPLE_JSON_PATH=/data/sample.json

EXPOSE 8001

# Migrate then serve. Bind 0.0.0.0 for compose.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8001"]
