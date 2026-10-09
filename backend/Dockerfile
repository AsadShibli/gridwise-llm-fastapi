# Docker fallback for the API. Secrets are passed at runtime, never baked in.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8000
# Use the host PORT when set (Render/Railway/Fly), else 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
