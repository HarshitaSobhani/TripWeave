import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { AuthCtx } from '../authContext'
import { day, place, run, stop, trip } from '../test/fixtures'
import type { Candidate, Trip } from '../types'
import AuthPage from './AuthPage'
import TripPage from './TripPage'

vi.mock('../api', async (orig) => {
  const real = await orig<typeof import('../api')>()
  return {
    ...real,
    downloadExport: vi.fn(),
    api: {
      trip: vi.fn(), destinations: vi.fn(), config: vi.fn(), optimize: vi.fn(), patchStop: vi.fn(),
      reschedule: vi.fn(), budget: vi.fn(), expenses: vi.fn(), places: vi.fn(),
    },
  }
})
import { api } from '../api'
const A = vi.mocked(api, true)

const cand = (id: number, name: string): Candidate => ({ id, place_id: id, status: 'optional', interest: 3, visit_minutes: null, hours_override: null, hours_override_source: null, place: place(id, name) })

function planned(): Trip {
  return trip({
    candidates: [cand(1, 'Eiffel Tower'), cand(2, 'Louvre Museum')],
    days: [day(0, [stop(1, 1, 'Eiffel Tower', 0), stop(2, 2, 'Louvre Museum', 1, { origin: 'manual', locked: true })]), day(1, [])],
    latest_run: run(),
  })
}

function renderTrip() {
  render(
    <AuthCtx.Provider value={{ email: 'a@b.co', ready: true, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={['/trips/1']}>
        <Routes><Route path="/trips/:id" element={<TripPage />} /></Routes>
      </MemoryRouter>
    </AuthCtx.Provider>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  A.trip.mockResolvedValue(planned())
  A.destinations.mockResolvedValue([])
  A.config.mockResolvedValue({ routing_provider: 'none', fx_provider: 'none', tile_url: 'http://t.invalid/{z}/{x}/{y}.png', tile_attribution: 'OSM' })
})

describe('TripPage', () => {
  it('loads a saved trip, then shows itinerary and map markers synchronised with selection', async () => {
    renderTrip()
    expect(await screen.findByRole('heading', { name: 'Paris' })).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Eiffel Tower' })[0])
    const card = document.getElementById('stop-1')!
    expect(card).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTitle('1. Eiffel Tower').querySelector('.selected')).not.toBeNull()
  })

  it('shows an error with retry when loading fails', async () => {
    A.trip.mockRejectedValueOnce(new ApiError(0, 'Cannot reach the TripWeave server.', null))
    renderTrip()
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the TripWeave server.')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { name: 'Paris' })).toBeInTheDocument()
  })

  it('asks for confirmation before replacing manual edits (409 flow)', async () => {
    A.optimize.mockRejectedValueOnce(new ApiError(409, 'needs confirmation', { message: 'needs confirmation', manual_stops: ['Louvre Museum'] }))
    renderTrip()
    await screen.findByRole('heading', { name: 'Paris' })
    await userEvent.click(screen.getByRole('button', { name: /Replace 1 manual edit/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/Louvre Museum/)).toBeInTheDocument()
    A.optimize.mockResolvedValueOnce({ persisted: true, run_id: 2, trip: planned(), result: { status: 'feasible', issues: [], unscheduled: [], explanation: [], metrics: planned().latest_run!.metrics, matrix_kind: 'straight_line_estimate', days: [] } })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Yes, replace them' }))
    await waitFor(() => expect(A.optimize).toHaveBeenLastCalledWith(1, expect.objectContaining({ replace_manual: true, confirm_replace_manual: true })))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })

  it('moving a stop calls the API and shows the returned plan', async () => {
    const moved = planned()
    moved.days = [day(0, [stop(2, 2, 'Louvre Museum', 0, { origin: 'manual', locked: true })]), day(1, [stop(1, 1, 'Eiffel Tower', 0, { origin: 'manual', locked: true })])]
    A.patchStop.mockResolvedValueOnce(moved)
    renderTrip()
    await screen.findByRole('heading', { name: 'Paris' })
    await userEvent.selectOptions(screen.getByLabelText('Move Eiffel Tower to day'), '1')
    expect(A.patchStop).toHaveBeenCalledWith(1, 1, { day_index: 1, position: 9999 })
    await waitFor(() => expect(within(document.getElementById('stop-1')!).getByText('Manual')).toBeInTheDocument())
  })

  it('switches tabs with arrow keys', async () => {
    renderTrip()
    await screen.findByRole('heading', { name: 'Paris' })
    A.places.mockResolvedValue([])
    const tab = screen.getByRole('tab', { name: 'Itinerary' })
    tab.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Places' })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('AuthPage', () => {
  it('validates before calling login', async () => {
    const login = vi.fn().mockResolvedValue(undefined)
    render(<AuthCtx.Provider value={{ email: null, ready: true, login, logout: vi.fn() }}><AuthPage /></AuthCtx.Provider>)
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/valid email/)
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.co')
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 8/)
    await userEvent.clear(screen.getByLabelText('Password'))
    await userEvent.type(screen.getByLabelText('Password'), 'longenough1')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(login).toHaveBeenCalledWith('a@b.co', 'longenough1', false)
  })
})
