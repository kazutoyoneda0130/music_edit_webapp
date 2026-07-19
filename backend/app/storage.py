"""アップロード・試聴用・書き出し用ファイルの保存、パス解決、期限切れファイルの掃除。"""

import time
import uuid
from pathlib import Path

from app.config import settings

UPLOADS_DIR = settings.storage_dir / "uploads"
PREVIEWS_DIR = settings.storage_dir / "previews"
EXPORTS_DIR = settings.storage_dir / "exports"

# 各ディレクトリの掃除対象TTL（秒）
_TTL_SECONDS = {
    UPLOADS_DIR: 24 * 3600,
    PREVIEWS_DIR: 1 * 3600,
    EXPORTS_DIR: 2 * 3600,
}

# 誰かが桁違いの量を使い続けてディスク容量・通信量を圧迫するのを防ぐための上限。
# TTLによる自動掃除はあるが、掃除が追いつく前に一時的に溜め込まれるケースに備える。
STORAGE_CAP_BYTES = 3 * 1024 * 1024 * 1024  # 3GB
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB/ファイル


def ensure_storage_dirs() -> None:
    for d in (UPLOADS_DIR, PREVIEWS_DIR, EXPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def new_id() -> str:
    return uuid.uuid4().hex


def upload_path(upload_id: str, suffix: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}{suffix}"


def preview_path(preview_id: str) -> Path:
    return PREVIEWS_DIR / f"{preview_id}.wav"


def export_path(export_id: str, suffix: str) -> Path:
    return EXPORTS_DIR / f"{export_id}{suffix}"


def find_upload_path(upload_id: str) -> Path | None:
    """upload_idに対応する実ファイル（拡張子は保存時に決まる）を探す"""
    matches = list(UPLOADS_DIR.glob(f"{upload_id}.*"))
    return matches[0] if matches else None


def total_storage_bytes() -> int:
    """uploads/previews/exports全体の合計サイズ（バイト）"""
    total = 0
    for directory in (UPLOADS_DIR, PREVIEWS_DIR, EXPORTS_DIR):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_file():
                total += path.stat().st_size
    return total


def has_storage_capacity() -> bool:
    return total_storage_bytes() < STORAGE_CAP_BYTES


def sweep_expired() -> int:
    """TTLを過ぎたファイルを削除する。削除した件数を返す。"""
    removed = 0
    now = time.time()
    for directory, ttl in _TTL_SECONDS.items():
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file():
                continue
            age = now - path.stat().st_mtime
            if age > ttl:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed
