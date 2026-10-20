import type { ReactNode } from 'react'
import type { Issue } from '../types'

export function ErrorBanner({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
      <span>{message}</span>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <output className="flex items-center gap-2 p-4 text-sm text-slate-600">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" aria-hidden />
      {label}
    </output>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  )
}

const SEV: Record<Issue['severity'], string> = {
  error: 'border-red-300 bg-red-50 text-red-900',
  warning: 'border-amber-300 bg-amber-50 text-amber-900',
  info: 'border-sky-200 bg-sky-50 text-sky-900',
}
const SEV_LABEL: Record<Issue['severity'], string> = { error: 'Problem', warning: 'Warning', info: 'Note' }

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null
  const order: Issue['severity'][] = ['error', 'warning', 'info']
  const sorted = [...issues].sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity))
  return (
    <ul className="space-y-1.5" aria-label="Constraint messages">
      {sorted.map((i, n) => (
        <li key={`${i.code}-${n}`} className={`rounded-md border px-2.5 py-1.5 text-sm ${SEV[i.severity]}`}>
          <strong className="mr-1">{SEV_LABEL[i.severity]}:</strong>
          {i.message}
        </li>
      ))}
    </ul>
  )
}

export function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="label">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}
