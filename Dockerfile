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

# Bind all interfaces so the public host can reach the API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
