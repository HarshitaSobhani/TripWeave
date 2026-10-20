import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import MapView from './MapView'

beforeAll(() => {
  // jsdom has no layout; give Leaflet a size so it requests tiles.
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 800 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 600 })
})
afterEach(() => vi.restoreAllMocks())

const markers = [
  { id: 1, lat: 48.8584, lon: 2.2945, label: 'Eiffel Tower', number: 1, color: '#1f5bd6', dayIndex: 0 },
  { id: 2, lat: 48.8606, lon: 2.3376, label: 'Louvre Museum', number: 2, color: '#1f5bd6', dayIndex: 0 },
]
const props = { tileUrl: 'http://tiles.invalid/{z}/{x}/{y}.png', attribution: '&copy; OpenStreetMap contributors' }

describe('MapView', () => {
  it('renders numbered markers at stored coordinates and reports selection', () => {
    const onSelect = vi.fn()
    render(<MapView markers={markers} selectedId={null} onSelect={onSelect} {...props} />)
    const m = screen.getByTitle('1. Eiffel Tower')
    expect(m).toHaveTextContent('1')
    expect(screen.getByTitle('2. Louvre Museum')).toHaveTextContent('2')
    fireEvent.click(m)
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('labels the visit-order line as not a route and shows OSM attribution', () => {
    render(<MapView markers={markers} selectedId={null} onSelect={vi.fn()} {...props} />)
    expect(screen.getByText(/not a walking or driving route/)).toBeInTheDocument()
    expect(document.querySelector('.leaflet-control-attribution')?.textContent).toMatch(/OpenStreetMap/)
  })

  it('degrades gracefully when tiles fail: notice appears, markers remain', async () => {
    render(<MapView markers={markers} selectedId={null} onSelect={vi.fn()} {...props} />)
    const tiles = Array.from(document.querySelectorAll<HTMLImageElement>('img.leaflet-tile'))
    expect(tiles.length).toBeGreaterThan(2)
    await act(async () => { tiles.slice(0, 3).forEach((t) => t.dispatchEvent(new Event('error'))) })
    expect(await screen.findByText(/Map tiles could not be loaded/)).toBeInTheDocument()
    expect(screen.getByTitle('1. Eiffel Tower')).toBeInTheDocument()
  })

  it('highlights the selected marker', () => {
    render(<MapView markers={markers} selectedId={2} onSelect={vi.fn()} {...props} />)
    expect(screen.getByTitle('2. Louvre Museum').querySelector('.selected')).not.toBeNull()
    expect(screen.getByTitle('1. Eiffel Tower').querySelector('.selected')).toBeNull()
  })
})
