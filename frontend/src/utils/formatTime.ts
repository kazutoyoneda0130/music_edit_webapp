export function formatTime(sec: number): string {
  const s = Math.max(0, sec)
  const minutes = Math.floor(s / 60)
  const seconds = Math.floor(s % 60)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
