import { DndContext, closestCenter } from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { BlockListItem } from './BlockListItem'
import type { AnalysisResultDTO } from '../api/types'
import { formatTime } from '../utils/formatTime'

interface BlockListProps {
  result: AnalysisResultDTO
  blockOrder: number[]
  skippedBlocks: number[]
  includeIntro: boolean
  includeOutro: boolean
  onToggleSkipBlock: (blockIndex: number) => void
  onToggleIntro: () => void
  onToggleOutro: () => void
  onReorder: (newBlockOrder: number[]) => void
  onDoubleClickIntro?: () => void
  onDoubleClickOutro?: () => void
  onDoubleClickBlock?: (blockIndex: number) => void
  highlightedKind?: 'intro' | 'block' | 'outro' | null
  highlightedBlockIndex?: number | null
}

export function BlockList({
  result,
  blockOrder,
  skippedBlocks,
  includeIntro,
  includeOutro,
  onToggleSkipBlock,
  onToggleIntro,
  onToggleOutro,
  onReorder,
  onDoubleClickIntro,
  onDoubleClickOutro,
  onDoubleClickBlock,
  highlightedKind,
  highlightedBlockIndex,
}: BlockListProps) {
  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = blockOrder.findIndex((b) => String(b) === active.id)
    const newIndex = blockOrder.findIndex((b) => String(b) === over.id)
    if (oldIndex === -1 || newIndex === -1) return
    onReorder(arrayMove(blockOrder, oldIndex, newIndex))
  }

  const outroStart = result.duration - result.outro_sec

  return (
    <ul className="block-list">
      <BlockListItem
        id="intro"
        label={`イントロ ${result.intro_sec.toFixed(0)}秒 (00:00~${formatTime(result.intro_sec)})`}
        checked={!includeIntro}
        onToggle={onToggleIntro}
        onDoubleClick={onDoubleClickIntro}
        draggable={false}
        highlighted={highlightedKind === 'intro'}
      />

      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={blockOrder.map(String)} strategy={verticalListSortingStrategy}>
          {blockOrder.map((blockIndex, position) => {
            const block = result.blocks[blockIndex]
            const endDisplay = Math.max(block.start_sec, block.end_sec - 1)
            return (
              <BlockListItem
                key={blockIndex}
                id={String(blockIndex)}
                label={`${position + 1}. ${block.eights}×8 (${formatTime(block.start_sec)}~${formatTime(endDisplay)})`}
                checked={skippedBlocks.includes(blockIndex)}
                onToggle={() => onToggleSkipBlock(blockIndex)}
                onDoubleClick={() => onDoubleClickBlock?.(blockIndex)}
                draggable
                highlighted={highlightedKind === 'block' && highlightedBlockIndex === blockIndex}
              />
            )
          })}
        </SortableContext>
      </DndContext>

      <BlockListItem
        id="outro"
        label={`アウトロ ${result.outro_sec.toFixed(0)}秒 (${formatTime(outroStart)}~${formatTime(result.duration)})`}
        checked={!includeOutro}
        onToggle={onToggleOutro}
        onDoubleClick={onDoubleClickOutro}
        draggable={false}
        highlighted={highlightedKind === 'outro'}
      />
    </ul>
  )
}
