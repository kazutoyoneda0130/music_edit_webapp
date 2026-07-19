"""複数曲のタイムライン計算・試聲用プレビュー生成・書き出しのAPI"""

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.combine.coordinator import export_coordinator, preview_coordinator
from app.combine.schemas import (
    CombinedTimelineEntryDTO,
    CombineRequest,
    ExportRequest,
    ExportResponse,
    PreviewRequest,
    PreviewResponse,
    ResolvedJunctionDTO,
    SeekTargetDTO,
    TimelineResponse,
)
from app.deps import get_current_user
from app.ratelimit import combine_limiter, daily_generation_quota
from app.storage import (
    EXPORTS_DIR,
    ensure_storage_dirs,
    export_path,
    find_upload_path,
    has_storage_capacity,
    new_id,
    preview_path,
)
from music_engine.audio_engine import (
    EXPORT_FORMAT_MAP,
    CombinedTimelineEntry,
    JunctionConfig,
    SongAudioSpec,
    build_combined_timeline,
    build_multi_combined_audio,
    resolve_junction_specs,
    resolve_junctions,
)

router = APIRouter(prefix="/api/combine", tags=["combine"], dependencies=[Depends(get_current_user)])

_SUFFIX_BY_FORMAT = {"mp3": ".mp3", "m4a": ".m4a", "wav": ".wav"}
_MEDIA_TYPE_BY_SUFFIX = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav"}


@dataclass
class _ResolvedInput:
    songs: list[SongAudioSpec]
    junctions: list[JunctionConfig]
    seek_target: SeekTargetDTO | None = None
    export_format: str = "mp3"


def _resolve_songs_and_junctions(req: CombineRequest) -> tuple[list[SongAudioSpec], list[JunctionConfig]]:
    songs: list[SongAudioSpec] = []
    for spec in req.songs:
        file_path = None
        if spec.upload_id is not None:
            p = find_upload_path(spec.upload_id)
            if p is None:
                raise HTTPException(status_code=404, detail=f"アップロードが見つかりません: {spec.upload_id}")
            file_path = str(p)
        songs.append(spec.to_audio_spec(file_path))
    junctions = [j.to_junction_config() for j in req.junctions]
    return songs, junctions


def _requested_transfer_size(request: Request, total_size: int) -> int:
    """このリクエストで実際に転送されるバイト数を返す。

    <audio>要素のシーク操作はHTTP Rangeリクエストになり、毎回ファイル全体ではなく
    一部だけが転送される。日次上限をファイル全体のサイズで記録すると、普通に試聴中に
    シークしただけで何倍もカウントされてしまう（実際の通信量と乖離する）ため、
    Rangeヘッダがあればその範囲のバイト数を、なければファイル全体のサイズを使う。
    """
    range_header = request.headers.get("range")
    if not range_header or not range_header.lower().startswith("bytes="):
        return total_size
    try:
        range_spec = range_header[len("bytes=") :].split(",")[0].strip()
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else total_size - 1
        end = min(end, total_size - 1)
        return max(0, end - start + 1)
    except (ValueError, IndexError):
        return total_size


def _find_seek_ms(timeline: list[CombinedTimelineEntry], seek_target: SeekTargetDTO | None) -> int | None:
    if seek_target is None:
        return None
    for e in timeline:
        if e.song_index == seek_target.song_index and e.kind == seek_target.kind and e.block_index == seek_target.block_index:
            return e.start_ms
    return None


def _build_preview_sync(resolved: _ResolvedInput) -> dict:
    timeline = build_combined_timeline(resolved.songs, resolved.junctions)
    junction_specs = resolve_junction_specs(resolved.songs, resolved.junctions)
    audio = build_multi_combined_audio(resolved.songs, junction_specs)

    ensure_storage_dirs()
    preview_id = new_id()
    out_path = preview_path(preview_id)
    audio.export(str(out_path), format="wav")
    # 通信量（＝実際の費用）が発生するのはダウンロード時なので、日次上限のカウントも
    # 生成時ではなくダウンロード時（get_preview_audio）で行う。ここでは記録しない。

    return {
        "preview_id": preview_id,
        "timeline": timeline,
        "total_ms": timeline[-1].end_ms if timeline else 0,
        "resolved_seek_ms": _find_seek_ms(timeline, resolved.seek_target),
    }


def _build_export_sync(resolved: _ResolvedInput) -> dict:
    junction_specs = resolve_junction_specs(resolved.songs, resolved.junctions)
    audio = build_multi_combined_audio(resolved.songs, junction_specs)

    ensure_storage_dirs()
    export_id = new_id()
    suffix = _SUFFIX_BY_FORMAT[resolved.export_format]
    fmt = EXPORT_FORMAT_MAP[suffix]
    out_path = export_path(export_id, suffix)
    audio.export(str(out_path), format=fmt)
    # 通信量（＝実際の費用）が発生するのはダウンロード時なので、日次上限のカウントも
    # 生成時ではなくダウンロード時（download_export）で行う。ここでは記録しない。

    return {"export_id": export_id, "suffix": suffix}


@router.post("/timeline", response_model=TimelineResponse)
async def get_timeline(req: CombineRequest) -> TimelineResponse:
    songs, junctions = _resolve_songs_and_junctions(req)
    timeline = build_combined_timeline(songs, junctions)
    resolved_junctions = resolve_junctions(songs, junctions)

    return TimelineResponse(
        timeline=[CombinedTimelineEntryDTO.from_dataclass(e) for e in timeline],
        total_ms=timeline[-1].end_ms if timeline else 0,
        junctions_resolved=[ResolvedJunctionDTO.from_dataclass(r) for r in resolved_junctions],
    )


@router.post("/preview", response_model=PreviewResponse)
async def create_preview(req: PreviewRequest, user: dict = Depends(get_current_user)) -> PreviewResponse:
    combine_limiter.check(user["sub"])
    daily_generation_quota.check_available(user["sub"])  # 既に上限に達していれば、無駄な生成をせず早期に断る

    songs, junctions = _resolve_songs_and_junctions(req)
    resolved = _ResolvedInput(songs=songs, junctions=junctions, seek_target=req.seek_target)

    if not has_storage_capacity():
        raise HTTPException(status_code=503, detail="サーバーの空き容量が不足しています。しばらくしてから再度お試しください。")

    try:
        result = await preview_coordinator.submit(user["sub"], resolved, _build_preview_sync)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return PreviewResponse(
        preview_id=result["preview_id"],
        audio_url=f"/api/combine/preview/{result['preview_id']}/audio",
        timeline=[CombinedTimelineEntryDTO.from_dataclass(e) for e in result["timeline"]],
        total_ms=result["total_ms"],
        resolved_seek_ms=result["resolved_seek_ms"],
    )


@router.get("/preview/{preview_id}/audio")
async def get_preview_audio(preview_id: str, request: Request, user: dict = Depends(get_current_user)) -> FileResponse:
    path = preview_path(preview_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="試聴用ファイルが見つかりません（期限切れの可能性があります）")
    # 通信量に直結するのはこのダウンロードなので、日次上限のチェック・記録はここで行う。
    # 同じファイルを繰り返しダウンロードされても、その都度カウントされるようにする。
    transfer_size = _requested_transfer_size(request, path.stat().st_size)
    daily_generation_quota.check_available(user["sub"])
    daily_generation_quota.record(user["sub"], transfer_size)
    return FileResponse(path, media_type="audio/wav")


@router.post("/export", response_model=ExportResponse)
async def create_export(req: ExportRequest, user: dict = Depends(get_current_user)) -> ExportResponse:
    combine_limiter.check(user["sub"])
    daily_generation_quota.check_available(user["sub"])  # 既に上限に達していれば、無駄な生成をせず早期に断る

    songs, junctions = _resolve_songs_and_junctions(req)
    resolved = _ResolvedInput(songs=songs, junctions=junctions, export_format=req.format)

    if not has_storage_capacity():
        raise HTTPException(status_code=503, detail="サーバーの空き容量が不足しています。しばらくしてから再度お試しください。")

    try:
        result = await export_coordinator.submit(user["sub"], resolved, _build_export_sync)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ExportResponse(
        export_id=result["export_id"],
        download_url=f"/api/combine/export/{result['export_id']}/download",
    )


@router.get("/export/{export_id}/download")
async def download_export(export_id: str, request: Request, user: dict = Depends(get_current_user)) -> FileResponse:
    matches = list(EXPORTS_DIR.glob(f"{export_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="書き出しファイルが見つかりません（期限切れの可能性があります）")
    path = matches[0]
    transfer_size = _requested_transfer_size(request, path.stat().st_size)
    daily_generation_quota.check_available(user["sub"])
    daily_generation_quota.record(user["sub"], transfer_size)
    media_type = _MEDIA_TYPE_BY_SUFFIX.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=f"combined{path.suffix}")
