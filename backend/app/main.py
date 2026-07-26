"""FastAPIアプリのエントリポイント"""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse

from app.auth.routes import router as auth_router
from app.combine.routes import router as combine_router
from app.config import settings
from app.songs.routes import router as songs_router
from app.storage import ensure_storage_dirs, sweep_expired

logger = logging.getLogger("music_edit_webapp")

app = FastAPI(title="Music Edit Web App")

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key, same_site="lax")

# 開発時（Viteの別オリジン）からのアクセス用。本番はフロントを同一オリジンで配信するため実質不要。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 期限切れファイルの掃除間隔（秒）
_SWEEP_INTERVAL_SECONDS = 3600
_sweep_task: asyncio.Task | None = None


async def _sweep_loop() -> None:
    while True:
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
        try:
            removed = await asyncio.to_thread(sweep_expired)
            if removed:
                logger.info("storage sweep: removed %d expired file(s)", removed)
        except Exception:
            logger.exception("storage sweep failed")


@app.on_event("startup")
async def on_startup() -> None:
    global _sweep_task
    ensure_storage_dirs()
    _sweep_task = asyncio.create_task(_sweep_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if _sweep_task is not None:
        _sweep_task.cancel()


app.include_router(auth_router)
app.include_router(songs_router)
app.include_router(combine_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# ビルド済みフロントエンド(frontend/dist)を同一オリジンで配信する。
# 開発時（Viteの別オリジン+distなし）は単に何もマウントされない。
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        # /api/* はここに来る前にルーターで処理済み。それ以外は全部SPAのindex.htmlを返す
        # （Reactのクライアントサイドルーティングに委ねるため）。
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
