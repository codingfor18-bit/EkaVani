FROM node:22-slim AS frontend-build

WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REQUIRE_DATABASE_URL=1

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-speech.txt /app/backend/requirements-speech.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/backend/requirements.txt \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r /app/backend/requirements-speech.txt

COPY backend/app /app/backend/app
COPY --from=frontend-build /web/dist /app/frontend/dist

CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000}"]
