import type {
  AppConfig, Budget, Candidate, Destination, Expense, OptimizeResult, Place, Trip, TripSummary,
} from './types'

const TOKEN_KEY = 'tripweave.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null): void {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function describe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== 'body').join('.') : ''
      return `${loc ? loc + ': ' : ''}${d?.msg ?? 'invalid'}`
    }).join('; ')
  }
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message)
  return 'Request failed'
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'Cannot reach the TripWeave server. Check your connection and try again.', null)
  }
  if (res.status === 204) return undefined as T
  let data: unknown = null
  try { data = await res.json() } catch { /* non-JSON body */ }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail ?? data
    throw new ApiError(res.status, describe(detail), detail)
  }
  return data as T
}

export const api = {
  register: (email: string, password: string) => request<{ access_token: string }>('POST', '/auth/register', { email, password }),
  login: (email: string, password: string) => request<{ access_token: string }>('POST', '/auth/login', { email, password }),
  me: () => request<{ id: number; email: string }>('GET', '/auth/me'),
  config: () => request<AppConfig>('GET', '/config'),
  destinations: () => request<Destination[]>('GET', '/destinations'),
  places: (destinationId: number, q = '') =>
    request<Place[]>('GET', `/places?destination_id=${destinationId}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  createPlace: (body: unknown) => request<Place>('POST', '/places', body),
  trips: () => request<TripSummary[]>('GET', '/trips'),
  trip: (id: number) => request<Trip>('GET', `/trips/${id}`),
  createTrip: (body: unknown) => request<Trip>('POST', '/trips', body),
  updateTrip: (id: number, body: unknown) => request<Trip>('PUT', `/trips/${id}`, body),
  deleteTrip: (id: number) => request<void>('DELETE', `/trips/${id}`),
  upsertCandidate: (id: number, body: unknown) => request<Candidate>('PUT', `/trips/${id}/candidates`, body),
  patchCandidate: (id: number, placeId: number, body: unknown) => request<Candidate>('PATCH', `/trips/${id}/candidates/${placeId}`, body),
  deleteCandidate: (id: number, placeId: number) => request<void>('DELETE', `/trips/${id}/candidates/${placeId}`),
  setPin: (id: number, placeId: number, dayIndex: number) => request('PUT', `/trips/${id}/pins`, { place_id: placeId, day_index: dayIndex }),
  clearPin: (id: number, placeId: number) => request<void>('DELETE', `/trips/${id}/pins/${placeId}`),
  optimize: (id: number, body: unknown) => request<OptimizeResult>('POST', `/trips/${id}/optimize`, body),
  reschedule: (id: number) => request<Trip>('POST', `/trips/${id}/reschedule`),
  addStop: (id: number, body: unknown) => request<Trip>('POST', `/trips/${id}/stops`, body),
  patchStop: (id: number, stopId: number, body: unknown) => request<Trip>('PATCH', `/trips/${id}/stops/${stopId}`, body),
  deleteStop: (id: number, stopId: number) => request<Trip>('DELETE', `/trips/${id}/stops/${stopId}`),
  budget: (id: number) => request<Budget>('GET', `/trips/${id}/budget`),
  expenses: (id: number) => request<Expense[]>('GET', `/trips/${id}/expenses`),
  addExpense: (id: number, body: unknown) => request<Expense>('POST', `/trips/${id}/expenses`, body),
  deleteExpense: (id: number, eid: number) => request<void>('DELETE', `/trips/${id}/expenses/${eid}`),
}

export async function downloadExport(tripId: number, format: 'json' | 'csv' | 'ics'): Promise<void> {
  const token = getToken()
  const res = await fetch(`/api/trips/${tripId}/export?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, 'Export failed', null)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = `tripweave-${tripId}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
