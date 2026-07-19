import { useState } from 'react'
import type { ExportFormat, JunctionConfigDTO, SongSpecDTO } from '../api/types'
import { usePlaybackStore } from '../store/playbackStore'
import { formatTime } from '../utils/formatTime'

const EXPORT_FORMAT_LABELS: Record<ExportFormat, string> = {
  mp3: 'MP3',
  m4a: 'M4A',
  wav: 'WAV',
}

interface TransportBarProps {
  songs: SongSpecDTO[]
  junctions: JunctionConfigDTO[]
}

export function TransportBar({ songs, junctions }: TransportBarProps) {
  const isPlaying = usePlaybackStore((s) => s.isPlaying)
  const isBusy = usePlaybackStore((s) => s.isBusy)
  const statusMessage = usePlaybackStore((s) => s.statusMessage)
  const errorMessage = usePlaybackStore((s) => s.errorMessage)
  const totalMs = usePlaybackStore((s) => s.totalMs)
  const play = usePlaybackStore((s) => s.play)
  const stop = usePlaybackStore((s) => s.stop)
  const exportAudio = usePlaybackStore((s) => s.exportAudio)

  const [format, setFormat] = useState<ExportFormat>('mp3')

  const readyCount = songs.filter((s) => s.upload_id !== null).length

  function handlePlayToggle() {
    if (isPlaying) {
      stop()
    } else {
      void play(songs, junctions)
    }
  }

  async function handleExport() {
    try {
      const url = await exportAudio(songs, junctions, format)
      window.location.href = url
    } catch {
      // エラー内容はerrorMessageとして下に表示される
    }
  }

  return (
    <div className="transport-bar">
      <button type="button" className="btn btn-primary" onClick={handlePlayToggle} disabled={readyCount === 0 || isBusy}>
        {isPlaying ? '■ 停止' : '▶ 全体を試聴'}
      </button>

      <span className="total-duration">合計: {formatTime(totalMs / 1000)}</span>

      <label className="format-select">
        書き出し形式
        <select value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)}>
          {(Object.keys(EXPORT_FORMAT_LABELS) as ExportFormat[]).map((f) => (
            <option key={f} value={f}>
              {EXPORT_FORMAT_LABELS[f]}
            </option>
          ))}
        </select>
      </label>

      <button type="button" className="btn btn-secondary" onClick={() => void handleExport()} disabled={readyCount === 0 || isBusy}>
        書き出し
      </button>

      {statusMessage && <span className="status">{statusMessage}</span>}
      {errorMessage && <span className="status error">{errorMessage}</span>}
    </div>
  )
}
