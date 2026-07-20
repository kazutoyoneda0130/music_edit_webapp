import { useState } from 'react'
import { usePlaybackStore } from '../store/playbackStore'
import { useSongsStore } from '../store/songsStore'
import { buildPartsText } from '../utils/buildPartsText'

export function PartsExportPanel() {
  const combinedTimeline = usePlaybackStore((s) => s.combinedTimeline)
  const panels = useSongsStore((s) => s.panels)
  const [visible, setVisible] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')

  const hasBlocks = combinedTimeline.some((e) => e.kind === 'block')
  const text = buildPartsText(combinedTimeline, panels)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopyStatus('コピーしました')
    } catch {
      setCopyStatus('コピーに失敗しました')
    }
    window.setTimeout(() => setCopyStatus(''), 2000)
  }

  return (
    <div className="parts-export-panel">
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => setVisible((v) => !v)}
        disabled={!hasBlocks}
      >
        {visible ? 'パート一覧を隠す' : 'パート一覧をテキスト出力'}
      </button>

      {visible && (
        <div className="parts-export-body">
          <textarea className="parts-export-text" value={text} readOnly rows={Math.min(20, text.split('\n').length + 1)} />
          <div className="parts-export-actions">
            <button type="button" className="btn btn-ghost" onClick={() => void handleCopy()}>
              コピー
            </button>
            {copyStatus && <span className="status">{copyStatus}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
