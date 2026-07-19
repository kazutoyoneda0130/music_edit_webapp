"""複数曲結合まわりのリクエスト/レスポンス型"""

from typing import Literal

from pydantic import BaseModel

from app.songs.schemas import AnalysisResultDTO
from music_engine.audio_engine import CombinedTimelineEntry, JunctionConfig, ResolvedJunction, SongAudioSpec


class SongSpecDTO(BaseModel):
    upload_id: str | None = None
    result: AnalysisResultDTO | None = None
    order: list[int] = []
    include_intro: bool = True
    include_outro: bool = True

    def to_audio_spec(self, file_path: str | None) -> SongAudioSpec:
        if self.upload_id is None or self.result is None or file_path is None:
            return SongAudioSpec(None, None, [], True, True)
        from music_engine.analyze_bpm import AnalysisResult, Block

        result = AnalysisResult(
            bpm=self.result.bpm,
            duration=self.result.duration,
            intro_sec=self.result.intro_sec,
            outro_sec=self.result.outro_sec,
            blocks=[Block(eights=b.eights, start_sec=b.start_sec, end_sec=b.end_sec) for b in self.result.blocks],
        )
        return SongAudioSpec(
            file_path=file_path,
            result=result,
            order=list(self.order),
            include_intro=self.include_intro,
            include_outro=self.include_outro,
        )


class JunctionConfigDTO(BaseModel):
    fade_eights: float
    fade_pattern: Literal["linear", "equal_power", "scurve"] = "equal_power"
    match_bpm: bool = False

    def to_junction_config(self) -> JunctionConfig:
        return JunctionConfig(fade_eights=self.fade_eights, fade_pattern=self.fade_pattern, match_bpm=self.match_bpm)


class SeekTargetDTO(BaseModel):
    song_index: int
    kind: Literal["intro", "block", "outro"]
    block_index: int | None = None


class CombineRequest(BaseModel):
    songs: list[SongSpecDTO]
    junctions: list[JunctionConfigDTO]


class PreviewRequest(CombineRequest):
    seek_target: SeekTargetDTO | None = None


class ExportRequest(CombineRequest):
    format: Literal["mp3", "m4a", "wav"] = "mp3"


class CombinedTimelineEntryDTO(BaseModel):
    song_index: int
    kind: str
    block_index: int | None
    start_ms: int
    end_ms: int

    @classmethod
    def from_dataclass(cls, e: CombinedTimelineEntry) -> "CombinedTimelineEntryDTO":
        return cls(song_index=e.song_index, kind=e.kind, block_index=e.block_index, start_ms=e.start_ms, end_ms=e.end_ms)


class ResolvedJunctionDTO(BaseModel):
    reference_bpm: float | None
    requested_ms: int
    effective_ms: int

    @classmethod
    def from_dataclass(cls, r: ResolvedJunction) -> "ResolvedJunctionDTO":
        return cls(reference_bpm=r.reference_bpm, requested_ms=r.requested_ms, effective_ms=r.effective_ms)


class TimelineResponse(BaseModel):
    timeline: list[CombinedTimelineEntryDTO]
    total_ms: int
    junctions_resolved: list[ResolvedJunctionDTO]


class PreviewResponse(BaseModel):
    preview_id: str
    audio_url: str
    timeline: list[CombinedTimelineEntryDTO]
    total_ms: int
    resolved_seek_ms: int | None = None


class ExportResponse(BaseModel):
    export_id: str
    download_url: str
