import type { ChangeEvent } from 'react'
import type { FadePattern } from '../api/types'
import { useJunctionsStore } from '../store/junctionsStore'
import { usePlaybackStore } from '../store/playbackStore'

const FADE_PATTERN_LABELS: Record<FadePattern, string> = {
  equal_power: 'イコールパワー',
  linear: 'リニア',
  scurve: 'Sカーブ',
}

interface JunctionControlsProps {
  index: number
  fromTitle: string
  toTitle: string
}

export function JunctionControls({ index, fromTitle, toTitle }: JunctionControlsProps) {
  const junction = useJunctionsStore((s) => s.junctions[index])
  const setFadeEights = useJunctionsStore((s) => s.setFadeEights)
  const setFadePattern = useJunctionsStore((s) => s.setFadePattern)
  const setMatchBpm = useJunctionsStore((s) => s.setMatchBpm)
  const resolved = usePlaybackStore((s) => s.junctionsResolved[index])

  function handleFadeEightsChange(e: ChangeEvent<HTMLInputElement>) {
    const value = Number(e.target.value)
    if (Number.isFinite(value) && value >= 0) setFadeEights(index, value)
  }

  return (
    <div className="junction-controls">
      <h3>
        接続部: {fromTitle} → {toTitle}
      </h3>
      <div className="junction-row">
        <label>
          クロスフェード長
          <input type="number" min={0} step={0.25} value={junction.fadeEights} onChange={handleFadeEightsChange} />
          ×8
        </label>
        <label>
          フェードカーブ
          <select value={junction.fadePattern} onChange={(e) => setFadePattern(index, e.target.value as FadePattern)}>
            {(Object.keys(FADE_PATTERN_LABELS) as FadePattern[]).map((p) => (
              <option key={p} value={p}>
                {FADE_PATTERN_LABELS[p]}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={junction.matchBpm} onChange={(e) => setMatchBpm(index, e.target.checked)} />
          BPMを合わせる
        </label>
      </div>
      {resolved && (
        <p className="junction-hint">
          {resolved.reference_bpm !== null ? `基準BPM ${resolved.reference_bpm.toFixed(2)} / ` : ''}
          クロスフェード {(resolved.effective_ms / 1000).toFixed(2)}秒
          {resolved.effective_ms !== resolved.requested_ms &&
            `（要求 ${(resolved.requested_ms / 1000).toFixed(2)}秒から自動調整されました）`}
        </p>
      )}
    </div>
  )
}
