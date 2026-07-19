import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { rebuildBlocks, uploadSong } from '../api/client'
import type { AnalysisResultDTO, BeatInfoDTO, SongSpecDTO } from '../api/types'

export const DEFAULT_UNIT = 4
export const UNIT_OPTIONS = [1, 2, 4, 8]
export const SONG_COUNT = 3

export type SongPanelStatus = 'empty' | 'loading' | 'ready' | 'error'

export interface SongPanelState {
  uploadId: string | null
  filename: string
  beatInfo: BeatInfoDTO | null
  result: AnalysisResultDTO | null
  unit: number
  // 全ブロックの元index配列を、現在の表示順で保持する(スキップ中のブロックも含む)
  blockOrder: number[]
  // スキップ中のブロックの元index一覧
  skippedBlocks: number[]
  includeIntro: boolean
  includeOutro: boolean
  status: SongPanelStatus
  errorMessage: string | null
}

function emptyPanel(): SongPanelState {
  return {
    uploadId: null,
    filename: '',
    beatInfo: null,
    result: null,
    unit: DEFAULT_UNIT,
    blockOrder: [],
    skippedBlocks: [],
    includeIntro: true,
    includeOutro: true,
    status: 'empty',
    errorMessage: null,
  }
}

interface SongsState {
  panels: SongPanelState[]
  loadFile: (slotIndex: number, file: File) => Promise<void>
  loadFromUpload: (slotIndex: number, uploadId: string, filename: string, beatInfo: BeatInfoDTO, result: AnalysisResultDTO) => void
  setUnit: (slotIndex: number, unit: number) => Promise<void>
  toggleSkipBlock: (slotIndex: number, blockIndex: number) => void
  toggleIncludeIntro: (slotIndex: number) => void
  toggleIncludeOutro: (slotIndex: number) => void
  reorderBlocks: (slotIndex: number, newBlockOrder: number[]) => void
  toSongSpec: (slotIndex: number) => SongSpecDTO
  activeOrder: (slotIndex: number) => number[]
  // localStorageから復元したパネルについて、アップロード済みファイルがサーバー側に
  // まだ残っているか確認する（TTL経過で消えていた場合はそのパネルを空に戻す）。
  revalidatePanel: (slotIndex: number) => Promise<void>
  revalidateAll: () => Promise<void>
}

export const useSongsStore = create<SongsState>()(
  persist(
    (set, get) => ({
  panels: Array.from({ length: SONG_COUNT }, emptyPanel),

  loadFile: async (slotIndex, file) => {
    set((state) => ({
      panels: state.panels.map((p, i) => (i === slotIndex ? { ...emptyPanel(), status: 'loading' } : p)),
    }))
    try {
      const resp = await uploadSong(file)
      get().loadFromUpload(slotIndex, resp.upload_id, resp.filename, resp.beat_info, resp.result)
    } catch (e) {
      set((state) => ({
        panels: state.panels.map((p, i) =>
          i === slotIndex ? { ...emptyPanel(), status: 'error', errorMessage: (e as Error).message } : p,
        ),
      }))
    }
  },

  loadFromUpload: (slotIndex, uploadId, filename, beatInfo, result) => {
    set((state) => ({
      panels: state.panels.map((p, i) =>
        i === slotIndex
          ? {
              ...emptyPanel(),
              uploadId,
              filename,
              beatInfo,
              result,
              unit: DEFAULT_UNIT,
              blockOrder: result.blocks.map((_, idx) => idx),
              skippedBlocks: [],
              includeIntro: true,
              includeOutro: true,
              status: 'ready',
            }
          : p,
      ),
    }))
  },

  setUnit: async (slotIndex, unit) => {
    const panel = get().panels[slotIndex]
    if (!panel.uploadId || !panel.beatInfo) return

    set((state) => ({
      panels: state.panels.map((p, i) => (i === slotIndex ? { ...p, status: 'loading' } : p)),
    }))
    try {
      const resp = await rebuildBlocks(panel.uploadId, panel.beatInfo, unit)
      set((state) => ({
        panels: state.panels.map((p, i) =>
          i === slotIndex
            ? {
                ...p,
                unit,
                result: resp.result,
                blockOrder: resp.result.blocks.map((_, idx) => idx),
                skippedBlocks: [],
                status: 'ready',
              }
            : p,
        ),
      }))
    } catch (e) {
      set((state) => ({
        panels: state.panels.map((p, i) => (i === slotIndex ? { ...p, status: 'error', errorMessage: (e as Error).message } : p)),
      }))
    }
  },

  toggleSkipBlock: (slotIndex, blockIndex) => {
    set((state) => ({
      panels: state.panels.map((p, i) => {
        if (i !== slotIndex) return p
        const isSkipped = p.skippedBlocks.includes(blockIndex)
        return {
          ...p,
          skippedBlocks: isSkipped ? p.skippedBlocks.filter((b) => b !== blockIndex) : [...p.skippedBlocks, blockIndex],
        }
      }),
    }))
  },

  toggleIncludeIntro: (slotIndex) => {
    set((state) => ({
      panels: state.panels.map((p, i) => (i === slotIndex ? { ...p, includeIntro: !p.includeIntro } : p)),
    }))
  },

  toggleIncludeOutro: (slotIndex) => {
    set((state) => ({
      panels: state.panels.map((p, i) => (i === slotIndex ? { ...p, includeOutro: !p.includeOutro } : p)),
    }))
  },

  reorderBlocks: (slotIndex, newBlockOrder) => {
    set((state) => ({
      panels: state.panels.map((p, i) => (i === slotIndex ? { ...p, blockOrder: newBlockOrder } : p)),
    }))
  },

  activeOrder: (slotIndex) => {
    const p = get().panels[slotIndex]
    return p.blockOrder.filter((b) => !p.skippedBlocks.includes(b))
  },

  toSongSpec: (slotIndex) => {
    const p = get().panels[slotIndex]
    if (!p.uploadId || !p.result) {
      return { upload_id: null, result: null, order: [], include_intro: true, include_outro: true }
    }
    return {
      upload_id: p.uploadId,
      result: p.result,
      order: get().activeOrder(slotIndex),
      include_intro: p.includeIntro,
      include_outro: p.includeOutro,
    }
  },

  revalidatePanel: async (slotIndex) => {
    const panel = get().panels[slotIndex]
    if (panel.status !== 'ready' || !panel.uploadId || !panel.beatInfo) return
    try {
      // rebuild-blocksはupload_idに対応するファイルが存在しないと404を返すため、
      // 「localStorageから復元したuploadIdがサーバー側にまだ残っているか」の確認を兼ねる。
      await rebuildBlocks(panel.uploadId, panel.beatInfo, panel.unit)
    } catch {
      set((state) => ({
        panels: state.panels.map((p, i) =>
          i === slotIndex
            ? {
                ...emptyPanel(),
                status: 'error',
                errorMessage: '保存されていた音源の有効期限が切れました。もう一度アップロードしてください。',
              }
            : p,
        ),
      }))
    }
  },

  revalidateAll: async () => {
    await Promise.all(get().panels.map((_, i) => get().revalidatePanel(i)))
  },
    }),
    {
      name: 'music-edit-webapp-songs',
      // 'loading'/'error'状態は再読み込み後に引き継ぐ意味がないため、'ready'なパネルだけ保存する
      partialize: (state) => ({
        panels: state.panels.map((p) => (p.status === 'ready' ? p : emptyPanel())),
      }),
    },
  ),
)
