import { useSongsStore } from '../store/songsStore'

// number_management_appからiframe埋め込みされた場合のみ表示するボタン。
// 送信先オリジンはクエリパラメータをそのまま信用せず、既知のnumber_management_app
// オリジンのallowlistと突き合わせてから使う（そうしないと、攻撃者が
// ?embed=1&parentOrigin=https://evil.com という形でこのページを別サイトに
// iframe埋め込みし、ログイン中のユーザーに「反映する」を押させて曲構成データを
// 盗み取れてしまう）。
const LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

const ALLOWED_PARENT_ORIGINS = ['https://number-management-app.fly.dev', 'http://localhost:5174']

function getEmbedParentOrigin(): string | null {
  const params = new URLSearchParams(window.location.search)
  if (params.get('embed') !== '1') return null
  const requested = params.get('parentOrigin')
  if (!requested) return null
  let parsed: string
  try {
    parsed = new URL(requested).origin
  } catch {
    return null
  }
  return ALLOWED_PARENT_ORIGINS.includes(parsed) ? parsed : null
}

export function ReflectPartsButton() {
  const parentOrigin = getEmbedParentOrigin()
  // activeOrder(0)はZustandのuseStore内で呼ぶと毎回新しい配列を返してしまい、
  // useSyncExternalStoreのスナップショット比較が不安定になって無限レンダリングループ
  // (React error #185)を起こす。blockOrder/skippedBlocksという安定した参照だけを
  // 購読し、フィルタ計算はレンダー本体側で行う。
  const panel = useSongsStore((s) => s.panels[0])

  if (!parentOrigin) return null

  const handleReflect = () => {
    const result = panel.result
    if (!result) return

    const activeOrder = panel.blockOrder.filter((b) => !panel.skippedBlocks.includes(b))
    let cursor = 1
    const parts = activeOrder.map((blockIndex, i) => {
      const block = result.blocks[blockIndex]
      const start = cursor
      const end = cursor + block.eights - 1
      cursor = end + 1
      return { name: `${LABELS[i % LABELS.length]}パート`, start_eight: start, end_eight: end }
    })

    window.parent.postMessage(
      { type: 'music-edit-webapp:parts-reflect', bpm: result.bpm, eights: cursor - 1, parts },
      parentOrigin,
    )
  }

  return (
    <div className="parts-export-panel">
      <button type="button" className="btn btn-primary" onClick={handleReflect} disabled={!panel.result}>
        曲1のパート割りを反映する
      </button>
      <p className="hint">曲1のブロック分割結果を、埋め込み元のダンス管理アプリに送信します。</p>
    </div>
  )
}
