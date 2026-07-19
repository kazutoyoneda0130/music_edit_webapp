# 音源編集アプリ (Web)

FastAPI + React製のWebアプリ。複数楽曲のアップロード、BPM/ビート解析、ブロック単位の並び替え/スキップ、曲間のクロスフェード設定、プレビュー、そして結合ミックスの書き出しができる。デスクトップ版 (`../music_edit_app`) のWeb移植版で、コアの解析・結合アルゴリズムは共通(`music_engine/`)。

Googleログイン制(許可メールアドレスのみ)。Fly.ioにデプロイ済み: https://music-edit-webapp.fly.dev/

## Setup

Python 3.11.4 (asdf管理)、`ffmpeg`がPATH上に必要。

Backend:
```bash
uvicorn app.main:app --reload --app-dir backend
```

Frontend:
```bash
cd frontend && npm run dev
npm run build   # backend/app/main.pyがdistを配信
```

Tests:
```bash
PYTHONPATH=$(pwd) python3 -m pytest tests/ -q
```

Docker (本番構成と同じ):
```bash
docker compose up --build
```

## Architecture

- `music_engine/` — UI非依存のコア(BPM解析・クロスフェード結合)。`music_edit_app`からポート
- `backend/app/` — FastAPI: `auth/`(Google OAuth)、`songs/`(アップロード・解析)、`combine/`(タイムライン・プレビュー・書き出し)
- `frontend/src/` — React 19 + TypeScript + Zustand + Vite

詳細は `CLAUDE.md`・`HOSTING.md` を参照。

## Status

稼働中(デプロイ済み)。
