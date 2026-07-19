import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { UNIT_OPTIONS, useSongsStore } from '../store/songsStore'
import { BlockList } from './BlockList'
import { fetchTimeline } from '../api/client'
import { formatTime } from '../utils/formatTime'
import { useCombineInputs } from '../hooks/useCombineInputs'
import { usePlaybackStore } from '../store/playbackStore'

interface SongPanelProps {
  slotIndex: number
  title: string
}

export function SongPanel({ slotIndex, title }: SongPanelProps) {
  const panel = useSongsStore((s) => s.panels[slotIndex])
  const loadFile = useSongsStore((s) => s.loadFile)
  const setUnit = useSongsStore((s) => s.setUnit)
  const toggleSkipBlock = useSongsStore((s) => s.toggleSkipBlock)
  const toggleIncludeIntro = useSongsStore((s) => s.toggleIncludeIntro)
  const toggleIncludeOutro = useSongsStore((s) => s.toggleIncludeOutro)
  const reorderBlocks = useSongsStore((s) => s.reorderBlocks)
  const toSongSpec = useSongsStore((s) => s.toSongSpec)

  const { songs, junctions } = useCombineInputs()
  const highlighted = usePlaybackStore((s) => s.highlighted)
  const play = usePlaybackStore((s) => s.play)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [totalMs, setTotalMs] = useState<number | null>(null)

  useEffect(() => {
    if (panel.status !== 'ready' || !panel.result) {
      setTotalMs(null)
      return
    }
    let cancelled = false
    fetchTimeline([toSongSpec(slotIndex)], [])
      .then((resp) => {
        if (!cancelled) setTotalMs(resp.total_ms)
      })
      .catch(() => {
        if (!cancelled) setTotalMs(null)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slotIndex, panel.status, panel.blockOrder, panel.skippedBlocks, panel.includeIntro, panel.includeOutro, panel.result])

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) loadFile(slotIndex, file)
    e.target.value = ''
  }

  function handleDoubleClickIntro() {
    void play(songs, junctions, { song_index: slotIndex, kind: 'intro', block_index: null })
  }

  function handleDoubleClickOutro() {
    void play(songs, junctions, { song_index: slotIndex, kind: 'outro', block_index: null })
  }

  function handleDoubleClickBlock(blockIndex: number) {
    void play(songs, junctions, { song_index: slotIndex, kind: 'block', block_index: blockIndex })
  }

  const highlightedKind = highlighted?.songIndex === slotIndex ? highlighted.kind : null
  const highlightedBlockIndex = highlighted?.songIndex === slotIndex ? highlighted.blockIndex : null

  return (
    <div className="song-panel">
      <h2>
        <span className="panel-badge">{slotIndex + 1}</span>
        {title}
      </h2>

      <div className="open-row">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={panel.status === 'loading'}
        >
          音源を開く…
        </button>
        <input ref={fileInputRef} type="file" accept=".mp3,.m4a,.wav" hidden onChange={handleFileChange} />
      </div>

      <p className="filename">{panel.filename || 'ファイル未選択'}</p>

      {panel.status === 'loading' && <p className="status">解析中…</p>}
      {panel.status === 'error' && <p className="status error">{panel.errorMessage}</p>}

      {panel.result && (
        <>
          <p className="bpm">BPM: {panel.result.bpm.toFixed(2)}</p>

          <div className="unit-row">
            <label>
              ブロック単位:
              <select value={panel.unit} onChange={(e) => setUnit(slotIndex, Number(e.target.value))}>
                {UNIT_OPTIONS.map((u) => (
                  <option key={u} value={u}>
                    {u}×8
                  </option>
                ))}
              </select>
            </label>
          </div>

          <BlockList
            result={panel.result}
            blockOrder={panel.blockOrder}
            skippedBlocks={panel.skippedBlocks}
            includeIntro={panel.includeIntro}
            includeOutro={panel.includeOutro}
            onToggleSkipBlock={(i) => toggleSkipBlock(slotIndex, i)}
            onToggleIntro={() => toggleIncludeIntro(slotIndex)}
            onToggleOutro={() => toggleIncludeOutro(slotIndex)}
            onReorder={(order) => reorderBlocks(slotIndex, order)}
            onDoubleClickIntro={handleDoubleClickIntro}
            onDoubleClickOutro={handleDoubleClickOutro}
            onDoubleClickBlock={handleDoubleClickBlock}
            highlightedKind={highlightedKind}
            highlightedBlockIndex={highlightedBlockIndex}
          />

          <p className="total-duration">
            {totalMs !== null ? `再生対象合計: ${(totalMs / 1000).toFixed(0)}秒 (${formatTime(totalMs / 1000)})` : ''}
          </p>
        </>
      )}
    </div>
  )
}
