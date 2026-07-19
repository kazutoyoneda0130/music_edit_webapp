"""Googleログイン・ログアウト・現在のユーザー情報のAPI"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth.oauth import oauth
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    redirect_uri = f"{settings.backend_base_url}/api/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:  # noqa: BLE001 - authlibの例外型を網羅的に捕捉してエラーページへ誘導する
        raise HTTPException(status_code=400, detail=f"認証に失敗しました: {e}") from e

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()

    if not email:
        raise HTTPException(status_code=400, detail="メールアドレスを取得できませんでした")

    if email not in settings.allowed_emails_set:
        raise HTTPException(status_code=403, detail="このメールアドレスはこのアプリの利用を許可されていません")

    request.session["user"] = {
        "sub": userinfo.get("sub"),
        "email": email,
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }

    return RedirectResponse(url=settings.frontend_origin)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="ログインしていません")
    return user
