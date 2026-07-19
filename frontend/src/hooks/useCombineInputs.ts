import type { JunctionConfigDTO, SongSpecDTO } from '../api/types'
import { junctionToDTO, useJunctionsStore } from '../store/junctionsStore'
import { useSongsStore } from '../store/songsStore'

// 全パネル・全接続部の現在値を結合APIへ渡せる形にまとめる。
// songsStore/junctionsStoreはグローバルなので、どのコンポーネントからも同じ値が取れる。
export function useCombineInputs(): { songs: SongSpecDTO[]; junctions: JunctionConfigDTO[] } {
  const panels = useSongsStore((s) => s.panels)
  const toSongSpec = useSongsStore((s) => s.toSongSpec)
  const junctionStates = useJunctionsStore((s) => s.junctions)

  const songs = panels.map((_, i) => toSongSpec(i))
  const junctions = junctionStates.map(junctionToDTO)
  return { songs, junctions }
}
