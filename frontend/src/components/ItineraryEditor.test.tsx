import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { day, place, stop } from '../test/fixtures'
import type { Candidate } from '../types'
import ItineraryEditor, { type EditorActions } from './ItineraryEditor'

const actions = (): EditorActions => ({ move: vi.fn(), patch: vi.fn(), remove: vi.fn(), add: vi.fn() })

function setup(extra: Partial<Parameters<typeof ItineraryEditor>[0]> = {}) {
  const a = actions()
  const days = [
    day(0, [
      stop(1, 1, 'Eiffel Tower', 0, { start_min: 540, end_min: 600 }),
      stop(2, 2, 'Louvre Museum', 1, {
        origin: 'manual', locked: true, start_min: 660, end_min: 720, leg_minutes: 15, leg_basis: 'user_buffer',
        leg_distance_m: 2400, leg_distance_kind: 'straight_line_estimate', warnings: ['Closed on this day'],
      }),
    ]),
    day(1, []),
  ]
  render(<ItineraryEditor days={days} candidates={[]} selectedId={null} onSelect={vi.fn()} actions={a} busy={false} {...extra} />)
  return a
}

describe('ItineraryEditor', () => {
  it('shows ordered stops with times, origin indicators and leg wording', () => {
    setup()
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText('Eiffel Tower')).toBeInTheDocument()
    expect(within(items[0]).getByText(/09:00–10:00/)).toBeInTheDocument()
    expect(within(items[0]).getByText('Optimized')).toBeInTheDocument()
    expect(within(items[1]).getByText('Manual')).toBeInTheDocument()
    expect(within(items[1]).getByText(/straight line \(estimate, not a route or travel time\)/)).toBeInTheDocument()
    expect(within(items[1]).getByText(/Closed on this day/)).toBeInTheDocument()
    expect(screen.getByText('No stops on this day.')).toBeInTheDocument()
  })

  it('reorders via keyboard-accessible buttons and respects the edges', async () => {
    const a = setup()
    expect(screen.getByRole('button', { name: 'Move Eiffel Tower earlier' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move Louvre Museum later' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Move Louvre Museum earlier' }))
    expect(a.move).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }), 0, 0)
    await userEvent.click(screen.getByRole('button', { name: 'Move Eiffel Tower later' }))
    expect(a.move).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 0, 1)
  })

  it('moves a stop to another day, edits duration and notes, removes and unlocks', async () => {
    const a = setup()
    await userEvent.selectOptions(screen.getByLabelText('Move Eiffel Tower to day'), '1')
    expect(a.move).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 1, 9999)

    const [minutes] = screen.getAllByLabelText('Minutes')
    await userEvent.clear(minutes)
    await userEvent.type(minutes, '90')
    await userEvent.tab()
    expect(a.patch).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), { visit_minutes: 90 })

    const [notes] = screen.getAllByLabelText('Notes')
    await userEvent.type(notes, 'sunset')
    await userEvent.tab()
    expect(a.patch).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), { notes: 'sunset' })

    await userEvent.click(screen.getByRole('button', { name: 'Remove Louvre Museum' }))
    expect(a.remove).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))

    const keep = within(screen.getAllByRole('listitem')[1]).getByLabelText('Keep here')
    expect(keep).toBeChecked()
    await userEvent.click(keep)
    expect(a.patch).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }), { locked: false })
  })

  it('ignores invalid duration input and restores the value', async () => {
    const a = setup()
    const [minutes] = screen.getAllByLabelText('Minutes')
    await userEvent.clear(minutes)
    await userEvent.type(minutes, '0')
    await userEvent.tab()
    expect(a.patch).not.toHaveBeenCalled()
    expect(minutes).toHaveValue(60)
  })

  it('adds an unscheduled candidate to a day', async () => {
    const cand: Candidate = { id: 9, place_id: 9, status: 'optional', interest: 3, visit_minutes: null, hours_override: null, hours_override_source: null, place: place(9, 'Panthéon') }
    const a = setup({ candidates: [cand] })
    await userEvent.selectOptions(screen.getByLabelText('Add a place to day 2'), '9')
    await userEvent.click(screen.getByRole('button', { name: 'Add to day 2' }))
    expect(a.add).toHaveBeenCalledWith(9, 1)
  })

  it('disables controls while busy', () => {
    setup({ busy: true })
    expect(screen.getByRole('button', { name: 'Remove Eiffel Tower' })).toBeDisabled()
  })
})
