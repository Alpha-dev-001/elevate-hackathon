# Production image for Alibaba Cloud Function Compute (custom container).
# No volume mounts, no --reload. FC calls the container on caPort 9000.
FROM python:3.10-slim

WORKDIR /app

# System deps occasionally needed by asyncpg/Pillow wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY . .

EXPOSE 9000

# FC sends HTTP to the container's listen port. Single worker keeps the
# in-process asyncio outcome-observer timers and WS manager coherent; scale via
# FC concurrency/instances, not gunicorn workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
