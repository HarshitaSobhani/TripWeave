export function fmtClock(min: number | null | undefined): string {
  if (min == null) return '--:--'
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export function fmtDuration(min: number | null | undefined): string {
  if (min == null) return '-'
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h && m) return `${h} h ${m} min`
  if (h) return `${h} h`
  return `${m} min`
}

export function fmtDistance(m: number | null | undefined): string {
  if (m == null) return '-'
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

export function fmtDate(iso: string): string {
  const [y, mo, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, d)).toLocaleDateString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC',
  })
}
