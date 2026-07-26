import { useRef, useState } from 'react'
import { analyzeSegments, ApiError } from '../api/client'
import type { SegmentDTO } from '../api/types'
import { DEFAULT_UNIT, UNIT_OPTIONS } from '../store/songsStore'
import { buildSegmentPartsText } from '../utils/buildSegmentPartsText'
import { formatTime } from '../utils/formatTime'

type Row = { start: string; end: string }

const EMPTY_ROWS: Row[] = [
  { start: '0:00', end: '' },
  { start: '', end: '' },
]

// mm:ss または m:ss 形式の文字列を秒に変換する。パースできなければnull。
function parseTimeToSec(text: string): number | null {
  const m = text.trim().match(/^(\d+):(\d{1,2})$/)
  if (!m) return null
  const minutes = Number(m[1])
  const seconds = Number(m[2])
  if (seconds >= 60) return null
  return minutes * 60 + seconds
}

// 3曲固定のクロスフェード結合ツールとは別に、「他アプリで最終編集済みの1本の音源
// （複数曲を繋いでいて途中でBPMが変わりうる）」を単体でアップロードし、曲ごとの
// 開始/終了時刻を手入力で指定して、区間ごとのBPM/ブロックを検出するためのパネル。
// 境目を自動検出する方式は精度が不十分だったため採用していない。
export function SegmentAnalysisPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [rows, setRows] = useState<Row[]>(EMPTY_ROWS)
  const [unit, setUnit] = useState(DEFAULT_UNIT)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [segments, setSegments] = useState<SegmentDTO[]>([])
  const [showText, setShowText] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  function updateRow(index: number, field: 'start' | 'end', value: string) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)))
  }

  function addRow() {
    setRows((prev) => [...prev, { start: prev[prev.length - 1]?.end ?? '', end: '' }])
  }

  function removeRow(index: number) {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== index)))
  }

  const parsedRanges = rows.map((r) => ({ start: parseTimeToSec(r.start), end: parseTimeToSec(r.end) }))
  const hasInvalidRow = parsedRanges.some(
    (r, i) => rows[i].start !== '' || rows[i].end !== ''
      ? r.start === null || r.end === null || r.start >= r.end
      : true,
  )

  async function handleAnalyze() {
    if (!file || hasInvalidRow) return
    setStatus('loading')
    setErrorMessage('')
    setShowText(false)
    try {
      const ranges = parsedRanges.map((r) => ({ start_sec: r.start as number, end_sec: r.end as number }))
      const resp = await analyzeSegments(file, ranges, unit)
      setSegments(resp.segments)
      setStatus('ready')
    } catch (e) {
      setSegments([])
      setStatus('error')
      setErrorMessage(e instanceof ApiError ? e.message : '音源を解析できませんでした。')
    }
  }

  const text = buildSegmentPartsText(segments)

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
    <div className="song-panel segment-analysis-panel">
      <h2>
        <span className="panel-badge">♪</span>
        最終音源の音割り解析
      </h2>
      <p className="hint">
        他アプリで最終編集済みの1本の音源（複数曲を繋いでいて途中でBPMが変わるものでもOK）をアップロードし、
        曲ごとの開始〜終了時刻をmm:ss形式で入力してください。境目の自動検出は精度が不十分だったため行わず、
        指定した区間だけをそれぞれ解析します。
      </p>

      <div className="open-row">
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp3,.m4a,.wav"
          style={{ display: 'none' }}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button type="button" className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={status === 'loading'}>
          音源ファイルを選択
        </button>
        {file && <span className="filename">{file.name}</span>}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, margin: '12px 0' }}>
        {rows.map((row, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, width: 48 }}>{i + 1}曲目</span>
            <input
              type="text"
              placeholder="0:00"
              value={row.start}
              onChange={(e) => updateRow(i, 'start', e.target.value)}
              style={{ width: 70 }}
              disabled={status === 'loading'}
            />
            <span>〜</span>
            <input
              type="text"
              placeholder="1:30"
              value={row.end}
              onChange={(e) => updateRow(i, 'end', e.target.value)}
              style={{ width: 70 }}
              disabled={status === 'loading'}
            />
            <button type="button" className="btn btn-ghost" onClick={() => removeRow(i)} disabled={rows.length <= 1 || status === 'loading'}>
              削除
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost" onClick={addRow} disabled={status === 'loading'} style={{ alignSelf: 'flex-start' }}>
          + 区間を追加
        </button>
      </div>

      <div className="unit-row">
        <label>
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

      <button
        type="button"
        className="btn btn-primary"
        onClick={() => void handleAnalyze()}
        disabled={!file || hasInvalidRow || status === 'loading'}
      >
        {status === 'loading' ? '解析中...' : '解析する'}
      </button>

      {status === 'error' && <div className="status error">{errorMessage}</div>}

      {status === 'ready' && (
        <>
          <div className="total-duration">{segments.length}区間を解析しました</div>
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
