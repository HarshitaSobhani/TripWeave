import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import type { Budget, Expense, Trip } from '../types'
import { Empty, ErrorBanner, Field, Spinner } from './ui'

const CATS = ['food', 'transport', 'admission', 'accommodation', 'other'] as const

export default function BudgetPanel({ trip, refreshKey }: { trip: Trip; refreshKey: number }) {
  const [budget, setBudget] = useState<Budget | null>(null)
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ category: 'food', description: '', amount: '', currency: trip.currency })

  const load = useCallback(async () => {
    try {
      const [b, e] = await Promise.all([api.budget(trip.id), api.expenses(trip.id)])
      setBudget(b); setExpenses(e); setError(null)
    } catch (x) { setError(x instanceof Error ? x.message : 'Failed to load budget') }
  }, [trip.id])
  useEffect(() => { void load() }, [load, refreshKey])

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!/^\d+(\.\d{1,2})?$/.test(form.amount)) return setError('Amount must be a positive number with at most 2 decimals.')
    if (!/^[A-Za-z]{3}$/.test(form.currency)) return setError('Currency must be a 3-letter code.')
    try {
      await api.addExpense(trip.id, { ...form, currency: form.currency.toUpperCase(), description: form.description || null })
      setForm({ ...form, description: '', amount: '' }); await load()
    } catch (x) { setError(x instanceof Error ? x.message : 'Failed') }
  }

  if (!budget && !error) return <Spinner label="Loading budget…" />
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section aria-labelledby="bud-h" className="space-y-3">
        <h2 id="bud-h" className="text-lg font-bold">Budget breakdown</h2>
        <ErrorBanner message={error} onRetry={load} />
        {budget && (
          <div className="card space-y-3 p-4 text-sm">
            <dl className="grid grid-cols-2 gap-y-1">
              <dt className="text-slate-500">Budget</dt><dd>{budget.budget ? `${budget.budget} ${budget.currency}` : 'Not set'}</dd>
              <dt className="text-slate-500">Estimated in {budget.currency}</dt><dd>{budget.in_trip_currency} {budget.currency}</dd>
              {budget.remaining_in_trip_currency && (<><dt className="text-slate-500">Remaining</dt><dd className={budget.over_budget ? 'font-semibold text-red-700' : ''}>{budget.remaining_in_trip_currency} {budget.currency}{budget.over_budget ? ' (over budget)' : ''}</dd></>)}
            </dl>
            <div>
              <h3 className="mb-1 font-semibold">Totals by currency</h3>
              {Object.keys(budget.totals_by_currency).length === 0 ? <p className="text-slate-500">Nothing recorded yet.</p> : (
                <ul>{Object.entries(budget.totals_by_currency).map(([c, a]) => <li key={c}>{a} {c}</li>)}</ul>
              )}
              {budget.conversion.note && <p className="mt-1 rounded bg-sky-50 px-2 py-1 text-xs text-sky-900">{budget.conversion.note}</p>}
              {budget.conversion.converted_total && budget.conversion.rates.length > 0 && (
                <p className="mt-1 text-xs text-slate-600">Converted total {budget.conversion.converted_total} {budget.currency} using {budget.conversion.rates.map((r) => `1 ${r.from} = ${r.rate} ${r.to} (${r.provider}, ${r.as_of})`).join('; ')}</p>
              )}
            </div>
            <div>
              <h3 className="mb-1 font-semibold">Planned admission</h3>
              {Object.keys(budget.planned_admission).length === 0 ? <p className="text-slate-500">No recorded admission costs on scheduled stops.</p> : (
                <ul>{Object.entries(budget.planned_admission).map(([c, a]) => <li key={c}>{a} {c} ({budget.travelers} traveller{budget.travelers > 1 ? 's' : ''})</li>)}</ul>
              )}
              {budget.stops_without_known_cost > 0 && <p className="text-xs text-amber-800">{budget.stops_without_known_cost} scheduled stop(s) have no recorded cost and count as unknown, not free.</p>}
            </div>
            <div>
              <h3 className="mb-1 font-semibold">Your estimates by category</h3>
              {Object.keys(budget.expenses_by_category).length === 0 ? <p className="text-slate-500">None yet.</p> : (
                <ul>{Object.entries(budget.expenses_by_category).map(([cat, v]) => <li key={cat} className="capitalize">{cat}: {Object.entries(v).map(([c, a]) => `${a} ${c}`).join(', ')}</li>)}</ul>
              )}
            </div>
            {budget.notes.map((n) => <p key={n} className="text-xs text-slate-500">{n}</p>)}
          </div>
        )}
      </section>
      <section aria-labelledby="exp-h" className="space-y-3">
        <h2 id="exp-h" className="text-lg font-bold">Expense estimates</h2>
        <form onSubmit={add} className="card grid grid-cols-2 gap-2 p-3" noValidate>
          <Field label="Category" htmlFor="ex-cat"><select id="ex-cat" className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{CATS.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
          <Field label="Description" htmlFor="ex-desc"><input id="ex-desc" className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <Field label="Amount" htmlFor="ex-amt"><input id="ex-amt" className="input" inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
          <Field label="Currency" htmlFor="ex-ccy"><input id="ex-ccy" className="input" maxLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></Field>
          <div className="col-span-2"><button className="btn btn-primary">Add expense</button></div>
        </form>
        {expenses.length === 0 ? <Empty title="No expenses yet">Enter your own estimates for food, transport, accommodation and more.</Empty> : (
          <ul className="space-y-1.5">
            {expenses.map((e) => (
              <li key={e.id} className="card flex items-center justify-between p-2.5 text-sm">
                <span><span className="capitalize">{e.category}</span>{e.description ? ` · ${e.description}` : ''} · <strong>{e.amount} {e.currency}</strong></span>
                <button className="btn btn-sm btn-danger" aria-label={`Delete ${e.category} expense ${e.amount} ${e.currency}`} onClick={async () => { await api.deleteExpense(trip.id, e.id); await load() }}>Delete</button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
