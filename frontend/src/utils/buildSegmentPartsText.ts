import type { SegmentDTO } from '../api/types'
import { formatTime } from './formatTime'

// 手入力の区間ごとの解析結果(SegmentDTO[])を、buildPartsTextと同じ
// 「○N曲目 / ・4×8(00:00~00:15)」形式のテキストにする。
export function buildSegmentPartsText(segments: SegmentDTO[]): string {
  const lines: string[] = []

  segments.forEach((segment, i) => {
    lines.push(`○${i + 1}曲目（推定BPM ${Math.round(segment.bpm)}）`)
    for (const block of segment.blocks) {
      const endSec = Math.max(block.start_sec, block.end_sec - 1)
      lines.push(`・${block.eights}×8(${formatTime(block.start_sec)}~${formatTime(endSec)})`)
    }
  })

  return lines.join('\n')
}
