import type { CombinedTimelineEntryDTO } from '../api/types'
import type { SongPanelState } from '../store/songsStore'
import { formatTime } from './formatTime'

// 結合後タイムライン（intro/block/outro、曲2以降も出力音源上の秒数で計算済み）から、
// 選択中のブロック（kind==='block'、スキップ済みは元々含まれない）だけを曲ごとに
// 「○N曲目 / ・4×8(00:00~00:15)」形式のテキストにする。
export function buildPartsText(timeline: CombinedTimelineEntryDTO[], panels: SongPanelState[]): string {
  const lines: string[] = []
  let currentSongIndex: number | null = null

  for (const entry of timeline) {
    if (entry.kind !== 'block' || entry.block_index === null) continue

    if (entry.song_index !== currentSongIndex) {
      currentSongIndex = entry.song_index
      lines.push(`○${entry.song_index + 1}曲目`)
    }

    const eights = panels[entry.song_index]?.result?.blocks[entry.block_index]?.eights
    const startSec = entry.start_ms / 1000
    // ブロック一覧の表示（BlockList.tsx）と同じく、末尾は次ブロックの開始秒と
    // 重複しないよう1秒引く。
    const endSec = Math.max(startSec, entry.end_ms / 1000 - 1)
    lines.push(`・${eights ?? '?'}×8(${formatTime(startSec)}~${formatTime(endSec)})`)
  }

  return lines.join('\n')
}
