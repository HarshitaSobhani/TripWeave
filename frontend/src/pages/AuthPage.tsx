import { useState, type FormEvent } from 'react'
import { useAuth } from '../authContext'
import { ErrorBanner, Field } from '../components/ui'

export default function AuthPage() {
  const { login } = useAuth()
  const [register, setRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError('Enter a valid email address.')
    if (password.length < 8) return setError('Password must be at least 8 characters.')
    setBusy(true); setError(null)
    try { await login(email, password, register) } catch (x) { setError(x instanceof Error ? x.message : 'Failed') } finally { setBusy(false) }
  }
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 px-4">
      <header>
        <h1 className="text-3xl font-extrabold text-brand-700">TripWeave</h1>
        <p className="text-slate-600">Plan multi-stop trips that respect your time, budget and constraints.</p>
      </header>
      <form onSubmit={submit} className="card space-y-3 p-5" noValidate>
        <h2 className="text-lg font-bold">{register ? 'Create account' : 'Sign in'}</h2>
        <ErrorBanner message={error} />
        <Field label="Email" htmlFor="email"><input id="email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password" htmlFor="password"><input id="password" className="input" type="password" autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <button className="btn btn-primary w-full" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
        <button type="button" className="w-full text-sm text-brand-700 underline" onClick={() => setRegister(!register)}>
          {register ? 'Have an account? Sign in' : 'New here? Create an account'}
        </button>
      </form>
    </main>
  )
}
