import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { day, metrics, run, stop, trip } from '../test/fixtures'
import type { Candidate } from '../types'
import OptimizePanel from './OptimizePanel'

const cand = (id: number): Candidate => ({ id, place_id: id, status: 'optional', interest: 3, visit_minutes: null, hours_override: null, hours_override_source: null, place: { ...stop(1, id, 'X', 0).place } })

function setup(t = trip({ candidates: [cand(1)] }), extra: Partial<Parameters<typeof OptimizePanel>[0]> = {}) {
  const onOptimize = vi.fn()
  render(<OptimizePanel trip={t} busy={false} onOptimize={onOptimize} pendingReplace={null} onCancelReplace={vi.fn()}
    previewMetrics={null} onClearPreview={vi.fn()} {...extra} />)
  return onOptimize
}

describe('OptimizePanel', () => {
  it('prompts to add places when there are no candidates', () => {
    setup(trip())
    expect(screen.getByRole('button', { name: 'Optimize itinerary' })).toBeDisabled()
    expect(screen.getByText(/Add places to the trip first/)).toBeInTheDocument()
  })

  it('optimizes with chosen advanced options', async () => {
    const onOptimize = setup()
    await userEvent.click(screen.getByText('Advanced'))
    await userEvent.selectOptions(screen.getByLabelText('Solver'), 'fallback')
    await userEvent.type(screen.getByLabelText('Interest weight'), '40')
    await userEvent.click(screen.getByRole('button', { name: 'Optimize itinerary' }))
    expect(onOptimize).toHaveBeenCalledWith({ solver: 'fallback', interest_weight: 40 })
  })

  it('shows infeasible state, unscheduled stops, issues and explanation', async () => {
    const t = trip({
      candidates: [cand(1)], days: [day(0, [stop(1, 1, 'A', 0)]), day(1, [])],
      latest_run: run({
        status: 'infeasible',
        issues: [{ severity: 'error', code: 'mandatory_unscheduled', message: 'Mandatory stop Louvre could not be scheduled', place_key: 2, day_index: null }],
        last_optimization: {
          id: 1, created_at: '', solver: 'ortools', explanation: ['Stops were ordered to reduce straight-line distance'],
          unscheduled: [{ key: 2, code: 'infeasible', detail: 'No allowed day', name: 'Louvre' }], metrics: metrics(), params: {}, input_hash: 'a'.repeat(64),
        },
      }),
    })
    setup(t)
    expect(screen.getByText('Constraints cannot all be met')).toBeInTheDocument()
    expect(screen.getByText(/Mandatory stop Louvre could not be scheduled/)).toBeInTheDocument()
    expect(screen.getByText('Louvre')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-optimize' })).toBeInTheDocument()
    await userEvent.click(screen.getByText('Why this order?'))
    expect(screen.getByText(/ordered to reduce straight-line distance/)).toBeVisible()
  })

  it('labels straight-line metrics as an estimate and never as travel time', () => {
    setup(trip({ candidates: [cand(1)], latest_run: run() }))
    expect(screen.getByText(/straight-line estimate/)).toBeInTheDocument()
    expect(screen.getByText(/Unknown, no routing data/)).toBeInTheDocument()
    expect(screen.getByText(/Not a route and not a travel time/)).toBeInTheDocument()
  })

  it('renders a before/after comparison from the last optimization', () => {
    const after = metrics({ distance_m: 2000, before: metrics({ distance_m: 5000 }) })
    setup(trip({ candidates: [cand(1)], latest_run: run({ last_optimization: { id: 1, created_at: '', solver: 'ortools', explanation: [], unscheduled: [], metrics: after, params: {}, input_hash: 'b'.repeat(64) } }) }))
    const table = screen.getByRole('table', { name: 'Before and after optimization' })
    expect(within(table).getByText('≈ 5.0 km straight-line estimate')).toBeInTheDocument()
    expect(within(table).getByText('≈ 2.0 km straight-line estimate')).toBeInTheDocument()
  })

  it('protects manual edits: replace needs explicit confirmation', async () => {
    const t = trip({ candidates: [cand(1)], days: [day(0, [stop(1, 1, 'Mine', 0, { locked: true, origin: 'manual' })]), day(1, [])] })
    const onOptimize = setup(t, { pendingReplace: ['Mine'] })
    expect(screen.getByText(/Re-optimizing keeps the 1 stop/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Replace 1 manual edit/ }))
    expect(onOptimize).toHaveBeenLastCalledWith({ solver: 'auto', interest_weight: undefined, replace_manual: true })
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/Mine/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Yes, replace them' }))
    expect(onOptimize).toHaveBeenLastCalledWith({ solver: 'auto', interest_weight: undefined, replace_manual: true, confirm_replace_manual: true })
  })

  it('shows a preview with apply', async () => {
    const onOptimize = setup(trip({ candidates: [cand(1)] }), {
      previewMetrics: { metrics: metrics({ before: metrics({ distance_m: 4000 }) }), issues: [] },
    })
    expect(screen.getByText('Preview (nothing saved)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Apply this plan' }))
    expect(onOptimize).toHaveBeenCalledWith({ solver: 'auto', interest_weight: undefined })
  })
})
