import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { FadePattern, JunctionConfigDTO } from '../api/types'
import { SONG_COUNT } from './songsStore'

export const JUNCTION_COUNT = SONG_COUNT - 1
export const DEFAULT_FADE_EIGHTS = 1.0
export const DEFAULT_FADE_PATTERN: FadePattern = 'equal_power'

export interface JunctionState {
  fadeEights: number
  fadePattern: FadePattern
  matchBpm: boolean
}

function defaultJunction(): JunctionState {
  return { fadeEights: DEFAULT_FADE_EIGHTS, fadePattern: DEFAULT_FADE_PATTERN, matchBpm: false }
}

interface JunctionsStore {
  junctions: JunctionState[]
  setFadeEights: (index: number, value: number) => void
  setFadePattern: (index: number, value: FadePattern) => void
  setMatchBpm: (index: number, value: boolean) => void
}

export const useJunctionsStore = create<JunctionsStore>()(
  persist(
    (set) => ({
      junctions: Array.from({ length: JUNCTION_COUNT }, defaultJunction),

      setFadeEights: (index, value) =>
        set((state) => ({ junctions: state.junctions.map((j, i) => (i === index ? { ...j, fadeEights: value } : j)) })),

      setFadePattern: (index, value) =>
        set((state) => ({ junctions: state.junctions.map((j, i) => (i === index ? { ...j, fadePattern: value } : j)) })),

      setMatchBpm: (index, value) =>
        set((state) => ({ junctions: state.junctions.map((j, i) => (i === index ? { ...j, matchBpm: value } : j)) })),
    }),
    { name: 'music-edit-webapp-junctions' },
  ),
)

export function junctionToDTO(j: JunctionState): JunctionConfigDTO {
  return { fade_eights: j.fadeEights, fade_pattern: j.fadePattern, match_bpm: j.matchBpm }
}
