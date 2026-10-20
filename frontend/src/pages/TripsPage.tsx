import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../authContext'
import TripSetupForm from '../components/TripSetupForm'
import { Empty, ErrorBanner, Spinner } from '../components/ui'
import { fmtDate } from '../lib/time'
import type { Destination, TripSummary } from '../types'

export function Shell({ children }: { children: React.ReactNode }) {
  const { email, logout } = useAuth()
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-4 py-2.5">
          <Link to="/" className="text-xl font-extrabold text-brand-700">TripWeave</Link>
          <div className="flex items-center gap-3 text-sm"><span className="hidden text-slate-600 sm:inline">{email}</span><button className="btn btn-sm" onClick={logout}>Sign out</button></div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1500px] px-4 py-5">{children}</main>
    </div>
  )
}

export default function TripsPage() {
  const nav = useNavigate()
  const [trips, setTrips] = useState<TripSummary[] | null>(null)
  const [dests, setDests] = useState<Destination[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    try { const [t, d] = await Promise.all([api.trips(), api.destinations()]); setTrips(t); setDests(d); setError(null) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load trips') }
  }, [])
  useEffect(() => { void load() }, [load])

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your trips</h1>
        <button className="btn btn-primary" onClick={() => setCreating(!creating)}>{creating ? 'Cancel' : 'New trip'}</button>
      </div>
      <ErrorBanner message={error} onRetry={load} />
      {creating && dests.length === 0 && <Spinner label="Loading destinations…" />}
      {creating && dests.length > 0 && (
        <div className="mb-6 max-w-3xl">
          <TripSetupForm destinations={dests} submitLabel="Create trip" onSubmit={async (body) => { const t = await api.createTrip(body); nav(`/trips/${t.id}`) }} />
        </div>
      )}
      {trips === null && !error ? <Spinner label="Loading trips…" /> : trips && trips.length === 0 ? (
        <Empty title="No trips yet">Create a trip to choose places, set constraints and generate an itinerary.</Empty>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {trips?.map((t) => (
            <li key={t.id} className="card p-4">
              <Link to={`/trips/${t.id}`} className="text-lg font-semibold text-brand-700 hover:underline">{t.name}</Link>
              <p className="text-sm text-slate-600">{t.destination.name} · {fmtDate(t.start_date)} → {fmtDate(t.end_date)}</p>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  )
}
