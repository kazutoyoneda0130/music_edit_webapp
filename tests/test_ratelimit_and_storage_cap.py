"""レート制限（SlidingWindowLimiter）とストレージ容量上限のテスト。

「誰かが桁違いの量を使い続ける」ことを防ぐための安全弁が、意図通りに
働く（超えたら弾く／時間が経てば・空き容量が戻れば再び使える）ことを確認する。
"""

import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ratelimit import DailyByteQuota, SlidingWindowLimiter  # noqa: E402


def test_allows_up_to_max_calls_within_window():
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        limiter.check("user1")  # 例外が出なければOK


def test_rejects_the_call_that_exceeds_max_calls():
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        limiter.check("user1")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("user1")
    assert exc_info.value.status_code == 429


def test_limits_are_tracked_independently_per_key():
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    limiter.check("user1")
    limiter.check("user2")  # user1が使い切っていてもuser2は別枠なので通る


def test_old_calls_fall_out_of_the_window():
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=0.05)
    limiter.check("user1")
    with pytest.raises(HTTPException):
        limiter.check("user1")
    time.sleep(0.1)
    limiter.check("user1")  # window経過後は再び使える


def test_storage_capacity_blocks_once_cap_exceeded(tmp_path, monkeypatch):
    import app.storage as storage

    uploads = tmp_path / "uploads"
    previews = tmp_path / "previews"
    exports = tmp_path / "exports"
    for d in (uploads, previews, exports):
        d.mkdir()

    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(storage, "PREVIEWS_DIR", previews)
    monkeypatch.setattr(storage, "EXPORTS_DIR", exports)
    monkeypatch.setattr(storage, "STORAGE_CAP_BYTES", 1000)

    assert storage.has_storage_capacity() is True

    (uploads / "a.wav").write_bytes(b"x" * 500)
    assert storage.has_storage_capacity() is True

    (previews / "b.wav").write_bytes(b"x" * 600)
    assert storage.total_storage_bytes() == 1100
    assert storage.has_storage_capacity() is False

    # 掃除されて空き容量が戻れば、再び使えるようになる
    (previews / "b.wav").unlink()
    assert storage.has_storage_capacity() is True


def test_daily_quota_allows_until_recorded_usage_reaches_cap():
    quota = DailyByteQuota(max_bytes=1000)
    quota.check_available("user1")  # まだ何も記録していないので通る
    quota.record("user1", 600)
    quota.check_available("user1")  # 600 < 1000なのでまだ通る
    quota.record("user1", 500)  # 合計1100（実際の生成後に記録するので、この1回はすり抜ける）
    with pytest.raises(HTTPException) as exc_info:
        quota.check_available("user1")  # 次の呼び出しからは上限超過でブロックされる
    assert exc_info.value.status_code == 429


def test_daily_quota_is_tracked_independently_per_key():
    quota = DailyByteQuota(max_bytes=1000)
    quota.record("user1", 1000)
    with pytest.raises(HTTPException):
        quota.check_available("user1")
    quota.check_available("user2")  # user1が使い切っていてもuser2は別枠なので通る


def test_daily_quota_resets_after_window_passes():
    quota = DailyByteQuota(max_bytes=1000, window_seconds=0.05)
    quota.record("user1", 1000)
    with pytest.raises(HTTPException):
        quota.check_available("user1")
    time.sleep(0.1)
    quota.check_available("user1")  # window経過後は再び使える


def test_daily_quota_survives_process_restart(tmp_path):
    """time.monotonic()ベースだと、プロセス再起動のたびに基準点がリセットされて
    上限が無効化されてしまう（実際にこの問題を指摘され、time.time()+永続化に修正した）。
    ここでは「別インスタンスが同じファイルを読み込む」ことで再起動を模擬する。
    """
    persist_path = tmp_path / "daily_quota_state.json"

    quota_before_restart = DailyByteQuota(max_bytes=1000, persist_path=persist_path)
    quota_before_restart.record("user1", 900)
    quota_before_restart.check_available("user1")  # 900 < 1000なのでまだ通る
    quota_before_restart.record("user1", 100)  # 合計1000

    # プロセス再起動を模擬: 新しいインスタンスを同じ永続化ファイルで作り直す
    quota_after_restart = DailyByteQuota(max_bytes=1000, persist_path=persist_path)
    with pytest.raises(HTTPException) as exc_info:
        quota_after_restart.check_available("user1")  # 再起動しても使用量が引き継がれ、まだ上限に達している
    assert exc_info.value.status_code == 429


def test_daily_quota_without_persist_path_does_not_touch_disk(tmp_path):
    quota = DailyByteQuota(max_bytes=1000)  # persist_path未指定
    quota.record("user1", 500)
    assert list(tmp_path.iterdir()) == []
