import { useEffect } from 'react'
import { AuthGate } from './components/AuthGate'
import { SongPanel } from './components/SongPanel'
import { JunctionControls } from './components/JunctionControls'
import { TransportBar } from './components/TransportBar'
import { PartsExportPanel } from './components/PartsExportPanel'
import { MultiTempoAnalysisPanel } from './components/MultiTempoAnalysisPanel'
import { useAuthStore } from './store/authStore'
import { SONG_COUNT, useSongsStore } from './store/songsStore'
import { JUNCTION_COUNT } from './store/junctionsStore'
import { useCombineInputs } from './hooks/useCombineInputs'
import { usePlaybackStore } from './store/playbackStore'
import { fetchTimeline } from './api/client'
import './App.css'

// 並び替え・スキップ・接続部設定の変更のたびに毎回叩くと連打時に無駄が多いため、
// 落ち着いてからまとめて1回だけ結合タイムラインを取得する。
const TIMELINE_DEBOUNCE_MS = 300

function MainApp() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { songs, junctions } = useCombineInputs()
  const setCombinedTimeline = usePlaybackStore((s) => s.setCombinedTimeline)

  useEffect(() => {
    // localStorageから復元した状態は、サーバー側のアップロード済みファイルがまだ
    // 残っているとは限らない（TTL経過で消えている可能性がある）ため、初回マウント時に
    // 1回だけ検証し、消えていたパネルは空に戻す。
    void useSongsStore.getState().revalidateAll()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const readyCount = songs.filter((s) => s.upload_id !== null).length
      if (readyCount === 0) {
        setCombinedTimeline([], 0, [])
        return
      }
      fetchTimeline(songs, junctions)
        .then((resp) => setCombinedTimeline(resp.timeline, resp.total_ms, resp.junctions_resolved))
        .catch(() => {
          /* ヒント表示のみに使う値なので、失敗時は前回値のまま据え置く */
        })
    }, TIMELINE_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(songs), JSON.stringify(junctions)])

  return (
    <div className="app">
      <header className="app-header">
        <h1>BPM解析 / 複数曲クロスフェード連結ツール</h1>
        <div className="user-info">
          <span className="user-avatar">{(user?.name ?? user?.email ?? '?').charAt(0).toUpperCase()}</span>
          <span className="user-name">{user?.name ?? user?.email}</span>
          <button type="button" className="btn btn-ghost" onClick={() => logout()}>
            ログアウト
          </button>
        </div>
      </header>
      <main>
        <p className="hint">
          曲1〜曲{SONG_COUNT}それぞれで音源を開き、ブロック（イントロ・アウトロ含む）の並び替え・スキップができます
          （ドラッグは各曲内のみ）。ブロックをダブルクリックするとその位置から全体を試聴できます。
        </p>
        <div className="panels-row">
          {Array.from({ length: SONG_COUNT }, (_, i) => (
            <SongPanel key={i} slotIndex={i} title="曲" />
          ))}
        </div>

        <div className="junctions-row">
          {Array.from({ length: JUNCTION_COUNT }, (_, i) => (
            <JunctionControls key={i} index={i} fromTitle={`曲${i + 1}`} toTitle={`曲${i + 2}`} />
          ))}
        </div>

        <TransportBar songs={songs} junctions={junctions} />
        <PartsExportPanel />

        <MultiTempoAnalysisPanel />
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthGate>
      <MainApp />
    </AuthGate>
  )
}

export default App
