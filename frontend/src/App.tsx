import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth'
import { useAuth } from './authContext'
import { Spinner } from './components/ui'
import AuthPage from './pages/AuthPage'
import TripPage from './pages/TripPage'
import TripsPage from './pages/TripsPage'

function Gate() {
  const { email, ready } = useAuth()
  if (!ready) return <Spinner label="Starting…" />
  if (!email) return <AuthPage />
  return (
    <Routes>
      <Route path="/" element={<TripsPage />} />
      <Route path="/trips/:id" element={<TripPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </BrowserRouter>
  )
}
