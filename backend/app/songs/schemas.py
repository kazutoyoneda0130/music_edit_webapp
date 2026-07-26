"""曲アップロード・解析まわりのリクエスト/レスポンス型"""

from typing import Literal

from pydantic import BaseModel

from music_engine.analyze_bpm import AnalysisResult, BeatInfo, Segment


class BlockDTO(BaseModel):
    eights: float
    start_sec: float
    end_sec: float


class BeatInfoDTO(BaseModel):
    bpm: float
    duration: float
    first_beat: float
    last_beat: float
    beat_times: list[float] = []

    def to_dataclass(self) -> BeatInfo:
        return BeatInfo(
            bpm=self.bpm,
            duration=self.duration,
            first_beat=self.first_beat,
            last_beat=self.last_beat,
            beat_times=list(self.beat_times),
        )

    @classmethod
    def from_dataclass(cls, beat_info: BeatInfo) -> "BeatInfoDTO":
        return cls(
            bpm=beat_info.bpm,
            duration=beat_info.duration,
            first_beat=beat_info.first_beat,
            last_beat=beat_info.last_beat,
            beat_times=list(beat_info.beat_times),
        )


class AnalysisResultDTO(BaseModel):
    bpm: float
    duration: float
    intro_sec: float
    outro_sec: float
    blocks: list[BlockDTO]

    @classmethod
    def from_dataclass(cls, result: AnalysisResult) -> "AnalysisResultDTO":
        return cls(
            bpm=result.bpm,
            duration=result.duration,
            intro_sec=result.intro_sec,
            outro_sec=result.outro_sec,
            blocks=[BlockDTO(eights=b.eights, start_sec=b.start_sec, end_sec=b.end_sec) for b in result.blocks],
        )


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    beat_info: BeatInfoDTO
    result: AnalysisResultDTO


class RebuildBlocksRequest(BaseModel):
    beat_info: BeatInfoDTO
    eights_per_block: int = 4


class RebuildBlocksResponse(BaseModel):
    result: AnalysisResultDTO


class ConcatRequest(BaseModel):
    upload_ids: list[str]
    mode: Literal["a", "b"]
    crossfade_sec: float = 2.0


class SegmentRangeInput(BaseModel):
    """区間指定は自動検出ではなく利用者が手入力する（自動検出は精度不足のため廃止）。"""

    start_sec: float
    end_sec: float


class SegmentDTO(BaseModel):
    bpm: float
    start_sec: float
    end_sec: float
    blocks: list[BlockDTO]

    @classmethod
    def from_dataclass(cls, segment: Segment) -> "SegmentDTO":
        return cls(
            bpm=segment.bpm,
            start_sec=segment.start_sec,
            end_sec=segment.end_sec,
            blocks=[BlockDTO(eights=b.eights, start_sec=b.start_sec, end_sec=b.end_sec) for b in segment.blocks],
        )


class ManualSegmentsResponse(BaseModel):
    upload_id: str
    filename: str
    segments: list[SegmentDTO]
