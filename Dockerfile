# Slim Python image; CBC solver is used by PuLP for the energy LP.
FROM python:3.11-slim

WORKDIR /app

# System CBC binary as a fallback if the wheel does not bundle it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends coinor-cbc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code only — do not COPY .env (no baked-in secrets).
COPY app ./app

EXPOSE 8000

# Bind all interfaces. Use host PORT (Render/Railway) when set, else 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
