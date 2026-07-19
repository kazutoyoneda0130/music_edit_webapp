"""LatestWinsCoordinatorの回帰テスト。

「生成中に新しいリクエストが来た場合、無視されずに最新のパラメータで
作り直され、かつ古い呼び出し元が新しいラウンドの結果で不意に上書きされて
返されることもない」という性質を検証する。

過去に「共有の1変数に結果を書き込み、待っていた側が後からそれを読みに行く」
実装では、自分のラウンドの結果を受け取る前に別ラウンドの結果で上書きされて
しまう競合状態が実際に発生した（呼び出しごとに専用Futureを持つ設計に修正済み）。
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.combine.coordinator import LatestWinsCoordinator  # noqa: E402


@pytest.mark.asyncio
async def test_single_call_returns_its_own_result():
    coordinator = LatestWinsCoordinator()
    result = await coordinator.submit("user1", "A", lambda p: f"result-for-{p}")
    assert result == "result-for-A"


@pytest.mark.asyncio
async def test_in_flight_request_is_not_overwritten_by_later_round():
    """実行中の最初の呼び出しは、自分のラウンドの結果をそのまま受け取れること
    （後から来た別リクエストによる再実行の結果に巻き込まれて上書きされないこと）。
    """
    coordinator = LatestWinsCoordinator()
    build_log: list[str] = []

    def slow_build(params: str) -> str:
        time.sleep(0.15)
        build_log.append(params)
        return f"result-for-{params}"

    async def submit_after(delay: float, params: str):
        await asyncio.sleep(delay)
        return params, await coordinator.submit("user1", params, slow_build)

    results = dict(
        await asyncio.gather(
            submit_after(0.0, "A"),  # 即座に実行が始まる
            submit_after(0.02, "B"),  # Aの実行中に来る -> 無視されず後で拾われる
            submit_after(0.04, "C"),  # Bの直後に来る -> Bの代わりにCが「最新」として拾われる
        )
    )

    assert results["A"] == "result-for-A"
    assert results["B"] == "result-for-C"
    assert results["C"] == "result-for-C"
    # ビルドは2回だけ(A用に1回、B+Cをまとめて1回)。Bのためだけの無駄なビルドは走らない
    assert build_log == ["A", "C"]


@pytest.mark.asyncio
async def test_error_propagates_to_all_coalesced_callers():
    coordinator = LatestWinsCoordinator()

    def failing_build(params: str) -> str:
        time.sleep(0.05)
        raise ValueError(f"boom-{params}")

    async def submit_after(delay: float, params: str):
        await asyncio.sleep(delay)
        with pytest.raises(ValueError, match="boom-"):
            await coordinator.submit("user1", params, failing_build)

    await asyncio.gather(submit_after(0.0, "A"), submit_after(0.01, "B"))


@pytest.mark.asyncio
async def test_different_users_do_not_interfere():
    coordinator = LatestWinsCoordinator()

    def build(params: str) -> str:
        time.sleep(0.05)
        return f"result-for-{params}"

    result_a, result_b = await asyncio.gather(
        coordinator.submit("user_a", "A-params", build),
        coordinator.submit("user_b", "B-params", build),
    )
    assert result_a == "result-for-A-params"
    assert result_b == "result-for-B-params"


@pytest.mark.asyncio
async def test_sequential_calls_each_get_correct_result():
    """重ならないタイミングで呼べば、それぞれ独立して正しい結果を得ること"""
    coordinator = LatestWinsCoordinator()

    def build(params: str) -> str:
        return f"result-for-{params}"

    for params in ["A", "B", "C"]:
        result = await coordinator.submit("user1", params, build)
        assert result == f"result-for-{params}"
