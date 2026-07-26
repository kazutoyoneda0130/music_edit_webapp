// バックエンドAPIを呼び出すための薄いラッパー。
// 開発時はvite.config.tsのproxy設定により、/api/*は同一オリジンとしてバックエンドへ転送される。

import type {
  AnalysisResultDTO,
  BeatInfoDTO,
  ConcatMode,
  ExportFormat,
  ExportResponse,
  JunctionConfigDTO,
  MultiTempoUploadResponse,
  PreviewResponse,
  RebuildBlocksResponse,
  SeekTargetDTO,
  SongSpecDTO,
  TimelineResponse,
  UploadResponse,
  User,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData（ファイルアップロード）の場合はContent-Typeを明示的に設定してはいけない。
  // 設定すると、ブラウザが本来自動付与するmultipart/form-dataの境界(boundary)情報が
  // 失われ、サーバー側でファイルフィールドを一切受け取れなくなる（実際に発生を確認済み）。
  const isFormData = init?.body instanceof FormData
  const headers = init?.body && !isFormData ? { 'Content-Type': 'application/json' } : undefined

  const res = await fetch(path, {
    credentials: 'include',
    headers,
    ...init,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // レスポンスボディがJSONでない場合はstatusTextのままにする
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

// ---- 認証 ----

export function loginUrl(): string {
  return '/api/auth/login'
}

export async function fetchMe(): Promise<User> {
  return request<User>('/api/auth/me')
}

export async function logout(): Promise<void> {
  await request('/api/auth/logout', { method: 'POST' })
}

// ---- 曲 ----

export async function uploadSong(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return request<UploadResponse>('/api/songs/upload', { method: 'POST', body: form })
}

export async function analyzeMultiTempo(file: File, eightsPerBlock: number): Promise<MultiTempoUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('eights_per_block', String(eightsPerBlock))
  return request<MultiTempoUploadResponse>('/api/songs/analyze-multi-tempo', { method: 'POST', body: form })
}

export async function rebuildBlocks(
  uploadId: string,
  beatInfo: BeatInfoDTO,
  eightsPerBlock: number,
): Promise<RebuildBlocksResponse> {
  return request<RebuildBlocksResponse>(`/api/songs/${uploadId}/rebuild-blocks`, {
    method: 'POST',
    body: JSON.stringify({ beat_info: beatInfo, eights_per_block: eightsPerBlock }),
  })
}

export async function concatSongs(
  uploadIds: string[],
  mode: ConcatMode,
  crossfadeSec: number,
): Promise<UploadResponse> {
  return request<UploadResponse>('/api/songs/concat', {
    method: 'POST',
    body: JSON.stringify({ upload_ids: uploadIds, mode, crossfade_sec: crossfadeSec }),
  })
}

// ---- 結合 ----

interface CombineBody {
  songs: SongSpecDTO[]
  junctions: JunctionConfigDTO[]
}

export async function fetchTimeline(songs: SongSpecDTO[], junctions: JunctionConfigDTO[]): Promise<TimelineResponse> {
  const body: CombineBody = { songs, junctions }
  return request<TimelineResponse>('/api/combine/timeline', { method: 'POST', body: JSON.stringify(body) })
}

export async function createPreview(
  songs: SongSpecDTO[],
  junctions: JunctionConfigDTO[],
  seekTarget?: SeekTargetDTO,
): Promise<PreviewResponse> {
  const body: CombineBody & { seek_target?: SeekTargetDTO } = { songs, junctions, seek_target: seekTarget }
  return request<PreviewResponse>('/api/combine/preview', { method: 'POST', body: JSON.stringify(body) })
}

export async function createExport(
  songs: SongSpecDTO[],
  junctions: JunctionConfigDTO[],
  format: ExportFormat,
): Promise<ExportResponse> {
  const body: CombineBody & { format: ExportFormat } = { songs, junctions, format }
  return request<ExportResponse>('/api/combine/export', { method: 'POST', body: JSON.stringify(body) })
}

export type { AnalysisResultDTO }
