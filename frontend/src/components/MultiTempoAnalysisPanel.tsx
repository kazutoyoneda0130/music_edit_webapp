import { useRef, useState } from 'react'
import { analyzeMultiTempo, ApiError } from '../api/client'
import type { SegmentDTO } from '../api/types'
import { DEFAULT_UNIT, UNIT_OPTIONS } from '../store/songsStore'
import { buildMultiTempoPartsText } from '../utils/buildMultiTempoPartsText'
import { formatTime } from '../utils/formatTime'

// 3曲固定のクロスフェード結合ツールとは別に、「他アプリで最終編集済みの1本の音源
// （複数曲を繋いだもの・途中でBPMが変わりうる）」を単体でアップロードし、区間ごとの
// BPM/ブロックを検出してテキスト出力するためのパネル。
export function MultiTempoAnalysisPanel() {
  const [unit, setUnit] = useState(DEFAULT_UNIT)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [segments, setSegments] = useState<SegmentDTO[]>([])
  const [showText, setShowText] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setStatus('loading')
    setErrorMessage('')
    setShowText(false)
    try {
      const resp = await analyzeMultiTempo(file, unit)
      setSegments(resp.result.segments)
      setStatus('ready')
    } catch (e) {
      setSegments([])
      setStatus('error')
      setErrorMessage(e instanceof ApiError ? e.message : '音源を解析できませんでした。')
    }
  }

  const text = buildMultiTempoPartsText(segments)

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
    <div className="song-panel multi-tempo-panel">
      <h2>
        <span className="panel-badge">♪</span>
        最終音源の音割り解析
      </h2>
      <p className="hint">
        他アプリで最終編集済みの1本の音源（複数曲を繋いでいて途中でBPMが変わるものでもOK）をアップロードすると、
        曲ごとの区間・BPM・ブロックを自動検出してテキスト出力できます。
      </p>

      <div className="open-row">
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp3,.m4a,.wav"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleFile(file)
          }}
        />
        <button type="button" className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={status === 'loading'}>
          音源ファイルを選択
        </button>
        <label style={{ marginLeft: 12, fontSize: 13 }}>
          区切り単位：
          <select value={unit} onChange={(e) => setUnit(Number(e.target.value))} disabled={status === 'loading'}>
            {UNIT_OPTIONS.map((u) => (
              <option key={u} value={u}>
                {u}×8
              </option>
            ))}
          </select>
        </label>
      </div>

      {status === 'loading' && <div className="status">解析中...（数十秒かかることがあります）</div>}
      {status === 'error' && <div className="status error">{errorMessage}</div>}

      {status === 'ready' && (
        <>
          <div className="total-duration">{segments.length}区間を検出しました</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
            {segments.map((seg, i) => (
              <div key={i} style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}>
                <strong>{i + 1}曲目</strong>　{formatTime(seg.start_sec)}〜{formatTime(seg.end_sec)}　推定BPM {Math.round(seg.bpm)}　（{seg.blocks.length}ブロック）
              </div>
            ))}
          </div>

          <div className="parts-export-panel">
            <button type="button" className="btn btn-secondary" onClick={() => setShowText((v) => !v)}>
              {showText ? 'テキストを隠す' : 'パート一覧をテキスト出力'}
            </button>
            {showText && (
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
        </>
      )}
    </div>
  )
}
