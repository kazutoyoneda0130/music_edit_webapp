# ---- フロントエンドのビルド ----
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- バックエンド実行環境 ----
FROM python:3.11-slim AS runtime

# pydub(mp3/m4a書き出し)・librosa(mp3読み込みのフォールバック)がffmpegを必要とする
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY music_engine/ ./music_engine/
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

WORKDIR /app/backend
# music_engine（/app配下）をbackend/app（cwd）から解決できるようにする
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
