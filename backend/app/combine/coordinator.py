"""ユーザーごとに、結合処理を「常に最新のパラメータで」実行するコーディネーター。

生成中に新しいリクエストが来た場合、そのリクエストを無視するのではなく、
実行中の処理が完了し次第、最新のパラメータで再実行する。すべての呼び出し元は、
自分専用のFutureを通じて、自分が送ったパラメータ以降の内容に基づく結果を必ず受け取る。

（共有の1個の変数に結果を書き込み、待っていた側が後からそれを読みに行く方式は、
自分のラウンドの結果を受け取る前に別ラウンドの結果で上書きされる競合状態を
起こしうる（実際に発生を確認済み）ため、呼び出しごとに専用Futureを使う設計にしている。）

デスクトップ版（gui_app.py）のCombinedPreviewWorker + _queued_previewの
挙動をHTTPリクエスト/レスポンスの世界に移植したもの。
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class _PendingCall:
    seq: int
    future: asyncio.Future


@dataclass
class _UserState:
    seq_counter: int = 0
    latest_seq: int = 0
    latest_params: Any = None
    pending: list[_PendingCall] = field(default_factory=list)
    runner_active: bool = False


class LatestWinsCoordinator:
    def __init__(self) -> None:
        self._states: dict[str, _UserState] = {}

    def _get_state(self, user_id: str) -> _UserState:
        # 辞書の参照・作成はawaitを挟まない同期処理なので、ロックなしでも競合しない
        state = self._states.get(user_id)
        if state is None:
            state = _UserState()
            self._states[user_id] = state
        return state

    async def submit(self, user_id: str, params: Any, build_fn: Callable[[Any], Any]) -> Any:
        state = self._get_state(user_id)
        loop = asyncio.get_running_loop()

        state.seq_counter += 1
        my_seq = state.seq_counter
        state.latest_seq = my_seq
        state.latest_params = params

        my_future: asyncio.Future = loop.create_future()
        state.pending.append(_PendingCall(seq=my_seq, future=my_future))

        if not state.runner_active:
            state.runner_active = True
            asyncio.ensure_future(self._run_rounds(state, build_fn))

        return await my_future

    async def _run_rounds(self, state: _UserState, build_fn: Callable[[Any], Any]) -> None:
        try:
            while True:
                seq_to_run = state.latest_seq
                params_to_run = state.latest_params

                try:
                    value = await asyncio.to_thread(build_fn, params_to_run)
                    error: BaseException | None = None
                except Exception as e:  # noqa: BLE001 - 呼び出し元のFutureに伝播させるため保持する
                    value = None
                    error = e

                # このラウンド(seq_to_run)以下の要求は全員この結果で満たされる。
                # 各Futureに直接結果を渡すため、後から共有変数を読みに行く競合状態が起きない。
                still_pending: list[_PendingCall] = []
                for call in state.pending:
                    if call.future.done():
                        continue
                    if call.seq <= seq_to_run:
                        if error is not None:
                            call.future.set_exception(error)
                        else:
                            call.future.set_result(value)
                    else:
                        still_pending.append(call)
                state.pending = still_pending

                if state.latest_seq == seq_to_run:
                    break  # このラウンド開始後に新しい要求が来ていなければ終了
        finally:
            state.runner_active = False


preview_coordinator = LatestWinsCoordinator()
export_coordinator = LatestWinsCoordinator()
