"""ユーザーごとの簡易レート制限。

DBを持たないステートレス設計のため、単一プロセス内のインメモリ状態として保持する
（Fly.io等での単一インスタンス運用を前提とする。複数インスタンスに水平分散する場合は
 別途Redis等の共有ストアへの置き換えが必要）。

DailyByteQuotaのみ、月間の実費用上限に直結するため永続化ボリュームにも保存し、
プロセス再起動（デプロイ・クラッシュ・オートストップ等）をまたいでも累計使用量が
リセットされないようにする（SlidingWindowLimiterは時間あたりの操作回数を平滑化する
だけでコスト上限には直結しないため、再起動でリセットされても実害はなく永続化しない）。
"""

import json
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock

from fastapi import HTTPException

from app.config import settings


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """window_seconds以内にmax_callsを超えていれば429を送出し、そうでなければ呼び出しを記録する。"""
        now = time.monotonic()
        with self._lock:
            timestamps = self._calls[key]
            cutoff = now - self._window_seconds
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            if len(timestamps) >= self._max_calls:
                raise HTTPException(
                    status_code=429,
                    detail="短時間に操作が集中しています。しばらく時間をおいてから再度お試しください。",
                )
            timestamps.append(now)


# アップロード・曲連結（ファイル書き込み+音声解析を伴う重い操作）
upload_limiter = SlidingWindowLimiter(max_calls=10, window_seconds=3600)
# 試聴プレビュー・書き出し生成（音声結合処理を伴う重い操作）
combine_limiter = SlidingWindowLimiter(max_calls=30, window_seconds=3600)


class DailyByteQuota:
    """ユーザーごとに、直近24時間で生成した音声ファイルの累計サイズを制限する。

    時間あたりの回数制限(SlidingWindowLimiter)だけでは「上限ギリギリを1ヶ月間
    使い続けられたら合計は青天井」になってしまうため、日次の累計バイト数で
    実際のコストに直結する本当の上限を作る。

    persist_pathを指定すると、record()のたびに永続化ボリューム上のJSONファイルへ
    保存し、プロセス再起動をまたいでも累計使用量が失われないようにする
    （time.monotonic()はプロセスごとに基準点がリセットされるため使えず、
    再起動をまたいでも意味を保つtime.time()（壁時計時刻）で記録する）。
    """

    def __init__(self, max_bytes: int, window_seconds: float = 24 * 3600, persist_path: Path | None = None) -> None:
        self._max_bytes = max_bytes
        self._window_seconds = window_seconds
        self._entries: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = Lock()
        self._persist_path = persist_path
        if self._persist_path is not None:
            self._load()

    def _load(self) -> None:
        assert self._persist_path is not None
        if not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text())
            for key, entries in raw.items():
                self._entries[key] = [(float(ts), int(size)) for ts, size in entries]
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            # 壊れた永続化ファイルのせいで起動できなくなるのは避け、0件から始める
            pass

    def _save(self) -> None:
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_suffix(".tmp")
            serializable = {key: entries for key, entries in self._entries.items() if entries}
            tmp_path.write_text(json.dumps(serializable))
            tmp_path.replace(self._persist_path)  # 書き込み途中でのファイル破損を避けるためアトミックに置き換える
        except OSError:
            # 永続化に失敗しても、その回の制限判定自体は継続させる（次回save時に再試行される）
            pass

    def _prune(self, key: str) -> int:
        """期限切れのエントリを取り除き、現在の累計使用量を返す（呼び出し元でロック済みの前提）"""
        now = time.time()
        entries = self._entries[key]
        cutoff = now - self._window_seconds
        while entries and entries[0][0] < cutoff:
            entries.pop(0)
        return sum(size for _, size in entries)

    def check_available(self, key: str) -> None:
        """既に上限に達していないかだけを確認する（重い生成処理を始める前に呼ぶ）。"""
        with self._lock:
            used = self._prune(key)
            if used >= self._max_bytes:
                raise HTTPException(
                    status_code=429,
                    detail="本日の利用量上限に達しました。時間をおいて（日付が変わってから）再度お試しください。",
                )

    def record(self, key: str, size_bytes: int) -> None:
        """生成が完了した後に、実際のサイズを使用量として記録する。"""
        now = time.time()
        with self._lock:
            self._prune(key)
            self._entries[key].append((now, size_bytes))
            self._save()


# 試聴プレビュー・書き出しで生成した音声ファイルの、ユーザーごとの1日あたり累計サイズ上限。
# storage_dir配下（永続ボリューム上）に保存するため、プロセス再起動をまたいでも維持される。
daily_generation_quota = DailyByteQuota(
    max_bytes=int(1.8 * 1024 * 1024 * 1024),  # 1.8GB/日/ユーザー（東京$0.04/GB・2GB VM・最大3人想定で月$20以内）
    persist_path=settings.storage_dir / "daily_quota_state.json",
)
