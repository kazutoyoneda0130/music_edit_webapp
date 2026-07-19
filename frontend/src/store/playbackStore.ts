import { create } from 'zustand'
import { createExport, createPreview } from '../api/client'
import type {
  CombinedTimelineEntryDTO,
  ExportFormat,
  JunctionConfigDTO,
  ResolvedJunctionDTO,
  SeekTargetDTO,
  SongSpecDTO,
  TimelineKind,
} from '../api/types'

// <audio>要素はReactのstateではなく、デスクトップ版の単一QMediaPlayerに相当する
// モジュールレベルの単一インスタンスとして扱う（再生位置はReactの外で進行するため）。
const audio = new Audio()

export interface Highlighted {
  songIndex: number
  kind: TimelineKind
  blockIndex: number | null
}

function findHighlighted(timeline: CombinedTimelineEntryDTO[], positionMs: number): Highlighted | null {
  if (timeline.length === 0) return null
  const entry =
    timeline.find((e) => positionMs >= e.start_ms && positionMs < e.end_ms) ??
    (positionMs >= timeline[timeline.length - 1].end_ms ? timeline[timeline.length - 1] : null)
  if (!entry) return null
  return { songIndex: entry.song_index, kind: entry.kind, blockIndex: entry.block_index }
}

interface PlaybackState {
  combinedTimeline: CombinedTimelineEntryDTO[]
  totalMs: number
  junctionsResolved: ResolvedJunctionDTO[]
  highlighted: Highlighted | null
  isPlaying: boolean
  isBusy: boolean
  statusMessage: string
  errorMessage: string | null

  setCombinedTimeline: (timeline: CombinedTimelineEntryDTO[], totalMs: number, junctionsResolved: ResolvedJunctionDTO[]) => void
  play: (songs: SongSpecDTO[], junctions: JunctionConfigDTO[], seekTarget?: SeekTargetDTO) => Promise<void>
  stop: () => void
  exportAudio: (songs: SongSpecDTO[], junctions: JunctionConfigDTO[], format: ExportFormat) => Promise<string>
}

// play()の呼び出しごとに増分するシーケンス番号。
// レスポンス到着時、自分より新しい呼び出しが既に発生していれば結果を捨てる(latest-wins)。
// バックエンドのLatestWinsCoordinatorと同じ理由: 古いリクエストの応答が新しいリクエストの
// 応答より後に届いた場合に、画面が古い結果で上書きされるのを防ぐ。
let playRequestSeq = 0

export const usePlaybackStore = create<PlaybackState>((set, get) => {
  audio.addEventListener('timeupdate', () => {
    const positionMs = audio.currentTime * 1000
    set({ highlighted: findHighlighted(get().combinedTimeline, positionMs) })
  })
  audio.addEventListener('play', () => set({ isPlaying: true }))
  audio.addEventListener('pause', () => set({ isPlaying: false }))
  audio.addEventListener('ended', () => set({ isPlaying: false, highlighted: null }))

  return {
    combinedTimeline: [],
    totalMs: 0,
    junctionsResolved: [],
    highlighted: null,
    isPlaying: false,
    isBusy: false,
    statusMessage: '',
    errorMessage: null,

    setCombinedTimeline: (timeline, totalMs, junctionsResolved) =>
      set({ combinedTimeline: timeline, totalMs, junctionsResolved }),

    play: async (songs, junctions, seekTarget) => {
      const mySeq = ++playRequestSeq
      set({ isBusy: true, statusMessage: '試聴用の音源を生成中…', errorMessage: null })
      try {
        const resp = await createPreview(songs, junctions, seekTarget)
        if (mySeq !== playRequestSeq) return
        set({
          combinedTimeline: resp.timeline,
          totalMs: resp.total_ms,
          isBusy: false,
          statusMessage: '',
        })
        audio.pause()
        audio.src = resp.audio_url
        const onLoaded = () => {
          audio.currentTime = resp.resolved_seek_ms !== null ? resp.resolved_seek_ms / 1000 : 0
          void audio.play()
          audio.removeEventListener('loadedmetadata', onLoaded)
        }
        audio.addEventListener('loadedmetadata', onLoaded)
        audio.load()
      } catch (e) {
        if (mySeq !== playRequestSeq) return
        set({ isBusy: false, statusMessage: '', errorMessage: (e as Error).message })
      }
    },

    stop: () => {
      playRequestSeq += 1 // 生成中だった古いプレビュー応答が後から届いても再生させない
      audio.pause()
      set({ isPlaying: false, highlighted: null })
    },

    exportAudio: async (songs, junctions, format) => {
      set({ isBusy: true, statusMessage: '書き出し中…', errorMessage: null })
      try {
        const resp = await createExport(songs, junctions, format)
        set({ isBusy: false, statusMessage: '' })
        return resp.download_url
      } catch (e) {
        set({ isBusy: false, statusMessage: '', errorMessage: (e as Error).message })
        throw e
      }
    },
  }
})
