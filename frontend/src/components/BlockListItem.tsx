import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { CSSProperties } from 'react'

interface BlockListItemProps {
  id: string
  label: string
  checked: boolean
  onToggle: () => void
  onDoubleClick?: () => void
  draggable: boolean
  highlighted?: boolean
}

export function BlockListItem({ id, label, checked, onToggle, onDoubleClick, draggable, highlighted }: BlockListItemProps) {
  const sortable = useSortable({ id, disabled: !draggable })

  const style: CSSProperties | undefined = draggable
    ? {
        transform: CSS.Transform.toString(sortable.transform),
        transition: sortable.transition,
      }
    : undefined

  const classNames = [
    'block-item',
    checked ? 'skipped' : '',
    draggable ? 'draggable' : 'pinned',
    highlighted ? 'highlighted' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <li
      ref={draggable ? sortable.setNodeRef : undefined}
      style={style}
      className={classNames}
      onDoubleClick={onDoubleClick}
      {...(draggable ? sortable.attributes : {})}
      {...(draggable ? sortable.listeners : {})}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        onClick={(e) => e.stopPropagation()}
        // dnd-kitのドラッグ用センサーはpointerdownで発火するため、clickだけstopPropagationしても
        // 親要素(li)のドラッグリスナーがpointerdown段階で反応し、チェックボックスへのReactの
        // onChangeが正しく届かないことがある(実際に発生を確認済み)。pointerdown自体も止める。
        onPointerDown={(e) => e.stopPropagation()}
      />
      <span>{label}</span>
    </li>
  )
}
