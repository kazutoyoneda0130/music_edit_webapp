"""共通の依存関係（未ログイン時に401を返すガードなど）"""

from fastapi import HTTPException, Request


def get_current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user
