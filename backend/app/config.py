"""アプリ設定。環境変数（または.env）から読み込む。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google OAuth（Google Cloud ConsoleでOAuthクライアントを発行して設定する）
    google_client_id: str = ""
    google_client_secret: str = ""

    # セッションCookieの署名に使う秘密鍵。本番では必ず十分ランダムな値に変更すること。
    session_secret_key: str = "dev-insecure-secret-change-me"

    # ログインを許可するメールアドレス（カンマ区切り）。空の場合は誰もログインできない。
    allowed_emails: str = ""

    # フロントエンドの開発サーバーのオリジン（開発時のCORS/リダイレクト用）
    frontend_origin: str = "http://localhost:5173"

    # バックエンド自身のベースURL（OAuthコールバックURLの組み立てに使用）
    backend_base_url: str = "http://localhost:8000"

    # 音源・生成ファイルの保存先
    storage_dir: Path = Path(__file__).resolve().parent.parent / "storage"

    @property
    def allowed_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}


settings = Settings()
