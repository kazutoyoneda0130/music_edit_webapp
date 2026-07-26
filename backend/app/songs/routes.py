"""音源のアップロード・解析・複数ファイル連結のAPI"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.deps import get_current_user
from app.ratelimit import upload_limiter
from app.songs.schemas import (
    ConcatRequest,
    MultiTempoResultDTO,
    MultiTempoUploadResponse,
    RebuildBlocksRequest,
    RebuildBlocksResponse,
    UploadResponse,
)
from app.storage import (
    MAX_UPLOAD_BYTES,
    ensure_storage_dirs,
    find_upload_path,
    has_storage_capacity,
    new_id,
    upload_path,
)
from music_engine.analyze_bpm import (
    DEFAULT_EIGHTS_PER_BLOCK,
    build_blocks,
    detect_beats,
    detect_multi_tempo_segments,
)
from music_engine.concat_audio import concat_files
from music_engine.audio_engine import EXPORT_FORMAT_MAP

router = APIRouter(prefix="/api/songs", tags=["songs"], dependencies=[Depends(get_current_user)])

ALLOWED_SUFFIXES = {".mp3", ".m4a", ".wav"}
_READ_CHUNK_BYTES = 1024 * 1024  # 1MB
# ファイルサイズの上限だけでは、圧縮率の高いフォーマット（低ビットレートMP3等）で
# 長時間の音声をすり抜けさせられてしまう（結合後の書き出しサイズが青天井になる）ため、
# 解析後の実際の再生時間でも上限を設ける。ダンス用途の楽曲としては十分すぎる余裕。
MAX_DURATION_SECONDS = 10 * 60


def _check_duration(duration_sec: float) -> None:
    if duration_sec > MAX_DURATION_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=f"曲の長さが上限（{MAX_DURATION_SECONDS // 60}分）を超えています。",
        )


# 共有CPU上でのバーストクレジット枯渇等により解析が異常に長引くケースの安全弁。
# ローカルでは10分の曲でも数秒で終わるため、これだけ待って終わらなければ
# 何かしら異常（スロットリング等）が起きているとみなし、ハングし続けるより
# 明確なエラーを返す方がユーザー体験として良い。
DETECT_BEATS_TIMEOUT_SECONDS = 120


async def _detect_beats_with_timeout(path: str):
    try:
        return await asyncio.wait_for(run_in_threadpool(detect_beats, path), timeout=DETECT_BEATS_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail="音源の解析が時間内に終わりませんでした。時間をおいて再度お試しください。",
        ) from e


# 区間ごとのビート再検出を挟む分、通常の1曲解析より重いため通常のタイムアウトより長めに取る
DETECT_MULTI_TEMPO_TIMEOUT_SECONDS = 180


async def _detect_multi_tempo_with_timeout(path: str, eights_per_block: int):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(detect_multi_tempo_segments, path, eights_per_block),
            timeout=DETECT_MULTI_TEMPO_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail="音源の解析が時間内に終わりませんでした。時間をおいて再度お試しください。",
        ) from e


async def _read_with_size_limit(file: UploadFile, max_bytes: int) -> bytes:
    """max_bytesを超えた時点で読み込みを打ち切る（巨大ファイルを丸ごとメモリに載せない）。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"ファイルサイズが大きすぎます（{max_bytes // (1024 * 1024)}MBまで）")
        chunks.append(chunk)
    return b"".join(chunks)


def _from_schemas(beat_info, result):
    from app.songs.schemas import AnalysisResultDTO, BeatInfoDTO

    return BeatInfoDTO.from_dataclass(beat_info), AnalysisResultDTO.from_dataclass(result)


@router.post("/upload", response_model=UploadResponse)
async def upload_song(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> UploadResponse:
    upload_limiter.check(user["sub"])

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="対応していないファイル形式です（mp3, m4a, wavのみ）")

    ensure_storage_dirs()
    if not has_storage_capacity():
        raise HTTPException(status_code=503, detail="サーバーの空き容量が不足しています。しばらくしてから再度お試しください。")

    content = await _read_with_size_limit(file, MAX_UPLOAD_BYTES)

    upload_id = new_id()
    path = upload_path(upload_id, suffix)
    path.write_bytes(content)

    try:
        beat_info = await _detect_beats_with_timeout(str(path))
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as e:
        # 壊れたファイル・非対応コーデック等はlibrosa/soundfile側の様々な例外型で
        # 失敗しうるため、ValueErrorに限らず広く捕捉してユーザーに分かりやすく伝える。
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="音源を解析できませんでした。ファイルが壊れているか、非対応の形式の可能性があります。") from e

    try:
        _check_duration(beat_info.duration)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise

    result = build_blocks(beat_info, DEFAULT_EIGHTS_PER_BLOCK)
    beat_info_dto, result_dto = _from_schemas(beat_info, result)

    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename or f"{upload_id}{suffix}",
        beat_info=beat_info_dto,
        result=result_dto,
    )


@router.post("/analyze-multi-tempo", response_model=MultiTempoUploadResponse)
async def analyze_multi_tempo(
    file: UploadFile = File(...),
    eights_per_block: int = Form(DEFAULT_EIGHTS_PER_BLOCK, ge=1, le=64),
    user: dict = Depends(get_current_user),
) -> MultiTempoUploadResponse:
    """複数曲を繋げた「最終版音源」（他アプリで編集済みのもの含む）を、
    曲ごとにBPMが変わる前提で区間検出する。通常の/uploadと違い、
    全体を1つのBPMとして扱わない。
    """
    upload_limiter.check(user["sub"])

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="対応していないファイル形式です（mp3, m4a, wavのみ）")

    ensure_storage_dirs()
    if not has_storage_capacity():
        raise HTTPException(status_code=503, detail="サーバーの空き容量が不足しています。しばらくしてから再度お試しください。")

    content = await _read_with_size_limit(file, MAX_UPLOAD_BYTES)

    upload_id = new_id()
    path = upload_path(upload_id, suffix)
    path.write_bytes(content)

    try:
        result = await _detect_multi_tempo_with_timeout(str(path), eights_per_block)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="音源を解析できませんでした。ファイルが壊れているか、非対応の形式の可能性があります。") from e

    try:
        _check_duration(result.duration)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise

    return MultiTempoUploadResponse(
        upload_id=upload_id,
        filename=file.filename or f"{upload_id}{suffix}",
        result=MultiTempoResultDTO.from_dataclass(result),
    )


@router.post("/{upload_id}/rebuild-blocks", response_model=RebuildBlocksResponse)
async def rebuild_blocks(upload_id: str, body: RebuildBlocksRequest) -> RebuildBlocksResponse:
    if find_upload_path(upload_id) is None:
        raise HTTPException(status_code=404, detail="アップロードが見つかりません")

    beat_info = body.beat_info.to_dataclass()
    result = build_blocks(beat_info, body.eights_per_block)
    _, result_dto = _from_schemas(beat_info, result)
    return RebuildBlocksResponse(result=result_dto)


@router.post("/concat", response_model=UploadResponse)
async def concat_songs(body: ConcatRequest, user: dict = Depends(get_current_user)) -> UploadResponse:
    upload_limiter.check(user["sub"])

    if len(body.upload_ids) < 2:
        raise HTTPException(status_code=400, detail="2つ以上のファイルを指定してください")

    paths: list[str] = []
    for uid in body.upload_ids:
        p = find_upload_path(uid)
        if p is None:
            raise HTTPException(status_code=404, detail=f"アップロードが見つかりません: {uid}")
        paths.append(str(p))

    if not has_storage_capacity():
        raise HTTPException(status_code=503, detail="サーバーの空き容量が不足しています。しばらくしてから再度お試しください。")

    try:
        combined = await run_in_threadpool(concat_files, paths, body.mode, body.crossfade_sec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ensure_storage_dirs()
    upload_id = new_id()
    out_path = upload_path(upload_id, ".mp3")
    fmt = EXPORT_FORMAT_MAP[".mp3"]
    await run_in_threadpool(combined.export, str(out_path), format=fmt)

    try:
        beat_info = await _detect_beats_with_timeout(str(out_path))
    except HTTPException:
        out_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        out_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="音源を解析できませんでした。ファイルが壊れているか、非対応の形式の可能性があります。") from e

    try:
        _check_duration(beat_info.duration)
    except HTTPException:
        out_path.unlink(missing_ok=True)
        raise

    result = build_blocks(beat_info, DEFAULT_EIGHTS_PER_BLOCK)
    beat_info_dto, result_dto = _from_schemas(beat_info, result)

    return UploadResponse(
        upload_id=upload_id,
        filename="連結された音源.mp3",
        beat_info=beat_info_dto,
        result=result_dto,
    )
