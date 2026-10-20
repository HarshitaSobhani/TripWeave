import L from 'leaflet'
import { useEffect, useRef, useState } from 'react'
import type { MarkerModel } from '../lib/itinerary'

interface Props {
  markers: MarkerModel[]
  selectedId: number | null
  onSelect: (id: number) => void
  tileUrl: string
  attribution: string
  /** Dashed visit-order guide per day (explicitly NOT a route). */
  showOrderLines?: boolean
  height?: string
}

function icon(m: MarkerModel, selected: boolean): L.DivIcon {
  const size = selected ? 34 : 28
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="tw-marker${selected ? ' selected' : ''}" style="width:${size}px;height:${size}px;background:${m.color}">${m.number ?? ''}</div>`,
  })
}

export default function MapView({ markers, selectedId, onSelect, tileUrl, attribution, showOrderLines = true, height = '100%' }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const tileErrors = useRef(0)
  const [tilesFailed, setTilesFailed] = useState(false)
  const onSelectRef = useRef(onSelect)
  const markersRef = useRef(markers)
  useEffect(() => {
    onSelectRef.current = onSelect
    markersRef.current = markers
  })

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true }).setView([48.8566, 2.3522], 12)
    const tiles = L.tileLayer(tileUrl, { attribution, maxZoom: 19 })
    tiles.on('tileerror', () => {
      tileErrors.current += 1
      if (tileErrors.current >= 3) setTilesFailed(true)
    })
    tiles.on('tileload', () => { tileErrors.current = 0; setTilesFailed(false) })
    tiles.addTo(m)
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [tileUrl, attribution])

  useEffect(() => {
    const m = map.current
    const g = layer.current
    if (!m || !g) return
    g.clearLayers()
    markers.forEach((mk) => {
      const marker = L.marker([mk.lat, mk.lon], {
        icon: icon(mk, mk.id === selectedId),
        title: mk.number ? `${mk.number}. ${mk.label}` : mk.label,
        keyboard: true,
        alt: mk.label,
      })
      marker.on('click', () => onSelectRef.current(mk.id))
      marker.addTo(g)
    })
    if (showOrderLines) {
      const byDay = new Map<number, MarkerModel[]>()
      markers.filter((x) => x.number != null && x.dayIndex != null).forEach((x) => {
        byDay.set(x.dayIndex!, [...(byDay.get(x.dayIndex!) ?? []), x])
      })
      byDay.forEach((list) => {
        if (list.length > 1) {
          L.polyline(list.map((x) => [x.lat, x.lon] as [number, number]), {
            color: list[0].color, weight: 2, opacity: 0.7, dashArray: '4 8',
            interactive: false,
          }).addTo(g)
        }
      })
    }
  }, [markers, selectedId, showOrderLines])

  const fitKey = markers.map((m) => m.id).join(',')
  useEffect(() => {
    const m = map.current
    const list = markersRef.current
    if (!m || list.length === 0) return
    m.fitBounds(L.latLngBounds(list.map((x) => [x.lat, x.lon] as [number, number])), { padding: [40, 40], maxZoom: 15 })

  }, [fitKey])

  useEffect(() => {
    const sel = markersRef.current.find((x) => x.id === selectedId)
    if (sel && map.current) map.current.panTo([sel.lat, sel.lon])

  }, [selectedId])

  return (
    <div className="relative h-full w-full" style={{ height }}>
      <section ref={el} className="h-full w-full rounded-lg bg-slate-200" aria-label="Map of stops" />
      {tilesFailed && (
        <output className="absolute inset-x-2 top-2 z-[1000] block rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 shadow">
          Map tiles could not be loaded. Markers still show stored coordinates; the list and timeline are unaffected.
        </output>
      )}
      {showOrderLines && markers.some((m) => m.number != null) && (
        <div className="absolute bottom-6 left-2 z-[1000] rounded bg-white/90 px-2 py-1 text-[11px] text-slate-700 shadow">
          Dashed line = visit order only, not a walking or driving route.
        </div>
      )}
    </div>
  )
}
