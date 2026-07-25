"""FastAPIアプリのエントリポイント"""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# ビルド済みフロントエンドの有無で本番/開発を判定する(下のSPA配信と同じシグナル)。
_is_production = (Path(__file__).resolve().parent.parent.parent / "frontend" / "dist").is_dir()

if _is_production and settings.session_secret_key == "dev-insecure-secret-change-me":
    raise RuntimeError(
        "SESSION_SECRET_KEY is still the insecure default in a production build. "
        "Set it via `flyctl secrets set SESSION_SECRET_KEY=...` before deploying."
    )

# number_management_appのPartsページからiframe埋め込みする際、iframe内からの
# API呼び出しにもセッションCookieが乗るようSameSite=Noneが必要（本番のみ。開発時は
# Secure必須のSameSite=Noneだとhttp://localhost上でCookie自体が発行されなくなるため
# 従来通りlaxのままにする）。
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="none" if _is_production else "lax",
    https_only=_is_production,
)

# 開発時（Viteの別オリジン）からのアクセス用。本番はフロントを同一オリジンで配信するため実質不要。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# number_management_appからのiframe埋め込みのみ許可するオリジン（CSPのframe-ancestors用）。
_EMBED_ALLOWED_ORIGINS = ["https://number-management-app.fly.dev", "http://localhost:5174"]

# 状態変更系リクエスト(POST/PUT/PATCH/DELETE)のOrigin許可リスト。SameSite=None化により
# multipart/form-data等のsimple request（CORSプリフライトが発生しない）はSameSiteだけでは
# クロスサイトからの誘導を防げなくなったため、Originヘッダを見て自オリジン以外を弾く。
_ALLOWED_REQUEST_ORIGINS = {settings.backend_base_url, settings.frontend_origin}
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def origin_and_frame_protection(request: Request, call_next):
    if request.method in _UNSAFE_METHODS and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and origin not in _ALLOWED_REQUEST_ORIGINS:
            return JSONResponse({"detail": "許可されていないオリジンからのリクエストです"}, status_code=403)

    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' " + " ".join(_EMBED_ALLOWED_ORIGINS)
    return response

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
