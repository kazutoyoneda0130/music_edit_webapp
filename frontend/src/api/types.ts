// バックエンド（backend/app/**/schemas.py）のPydanticモデルに対応する型定義

export interface User {
  sub: string
  email: string
  name: string | null
  picture: string | null
}

export interface BlockDTO {
  eights: number
  start_sec: number
  end_sec: number
}

export interface BeatInfoDTO {
  bpm: number
  duration: number
  first_beat: number
  last_beat: number
  beat_times: number[]
}

export interface AnalysisResultDTO {
  bpm: number
  duration: number
  intro_sec: number
  outro_sec: number
  blocks: BlockDTO[]
}

export interface UploadResponse {
  upload_id: string
  filename: string
  beat_info: BeatInfoDTO
  result: AnalysisResultDTO
}

export interface RebuildBlocksResponse {
  result: AnalysisResultDTO
}

export type ConcatMode = 'a' | 'b'

export type FadePattern = 'linear' | 'equal_power' | 'scurve'

export interface SongSpecDTO {
  upload_id: string | null
  result: AnalysisResultDTO | null
  order: number[]
  include_intro: boolean
  include_outro: boolean
}

export interface JunctionConfigDTO {
  fade_eights: number
  fade_pattern: FadePattern
  match_bpm: boolean
}

export type TimelineKind = 'intro' | 'block' | 'outro'

export interface SeekTargetDTO {
  song_index: number
  kind: TimelineKind
  block_index: number | null
}

export interface CombinedTimelineEntryDTO {
  song_index: number
  kind: TimelineKind
  block_index: number | null
  start_ms: number
  end_ms: number
}

export interface ResolvedJunctionDTO {
  reference_bpm: number | null
  requested_ms: number
  effective_ms: number
}

export interface TimelineResponse {
  timeline: CombinedTimelineEntryDTO[]
  total_ms: number
  junctions_resolved: ResolvedJunctionDTO[]
}

export interface PreviewResponse {
  preview_id: string
  audio_url: string
  timeline: CombinedTimelineEntryDTO[]
  total_ms: number
  resolved_seek_ms: number | null
}

export interface ExportResponse {
  export_id: string
  download_url: string
}

export type ExportFormat = 'mp3' | 'm4a' | 'wav'
