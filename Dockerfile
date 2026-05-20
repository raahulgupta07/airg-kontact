FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libzbar0 \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt chromadb sentence-transformers
COPY . .
COPY --from=frontend /build/build /app/frontend/build
ENV PORT=8000
EXPOSE ${PORT}
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:${PORT}/health || exit 1
# Single worker: ChromaDB PersistentClient is single-process only — multiple
# workers corrupt/deadlock its SQLite store. Concurrency comes from FastAPI's
# threadpool (sync `def` routes) + asyncio.to_thread for blocking calls in
# async routes. To scale past this, run ChromaDB in server mode + HttpClient.
# --proxy-headers + --forwarded-allow-ips trust Caddy's X-Forwarded-For so
# request.client.host is the REAL client IP, not Caddy's container IP. Without
# this every user shares one IP bucket → login rate-limit (10/min) is hit
# org-wide after a handful of logins. Container is only reachable via Caddy.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-1} \
    --proxy-headers --forwarded-allow-ips="*"
