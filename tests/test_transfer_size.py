"""_requested_transfer_size のテスト。

Rangeリクエスト（<audio>要素のシーク操作等）で実際に転送されるバイト数を正しく
見積もれているかを確認する。ここを誤ってファイル全体のサイズを常に記録すると、
普通に試聴中にシークしただけで日次利用量が何倍にも水増しされてしまう。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.combine.routes import _requested_transfer_size  # noqa: E402


class _FakeRequest:
    def __init__(self, range_header: str | None) -> None:
        self.headers = {"range": range_header} if range_header is not None else {}


def test_no_range_header_returns_full_size():
    assert _requested_transfer_size(_FakeRequest(None), 1000) == 1000


def test_range_with_start_and_end_returns_exact_span():
    # bytes=100-199 は100バイト分（両端含む）
    assert _requested_transfer_size(_FakeRequest("bytes=100-199"), 1000) == 100


def test_range_with_only_start_returns_remainder():
    # bytes=900- は末尾までの100バイト分
    assert _requested_transfer_size(_FakeRequest("bytes=900-"), 1000) == 100


def test_range_end_beyond_file_size_is_clamped():
    assert _requested_transfer_size(_FakeRequest("bytes=900-999999"), 1000) == 100


def test_malformed_range_header_falls_back_to_full_size():
    assert _requested_transfer_size(_FakeRequest("bytes=not-a-range"), 1000) == 1000


def test_non_bytes_unit_falls_back_to_full_size():
    assert _requested_transfer_size(_FakeRequest("items=0-1"), 1000) == 1000
