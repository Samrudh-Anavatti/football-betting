import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { ErrorNote, Loading } from '../components/ui.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { Field } from './Auth.jsx'

function useSubmit(fn) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ok, setOk] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setOk(false)
    try {
      await fn()
      setOk(true)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, ok, submit }
}

function ChangePassword() {
  const { signIn } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const { busy, error, ok, submit } = useSubmit(async () => {
    signIn(await api.changePassword({ current_password: current, new_password: next }))
    setCurrent('')
    setNext('')
  })
  return (
    <form onSubmit={submit} className="panel p-6 space-y-4">
      <h2 className="text-2xl">Change password</h2>
      <Field label="Current password" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      <Field label="New password (8+ characters)" type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
      <ErrorNote error={error} />
      {ok && <p className="text-sm">Saved. Any other devices have been signed out.</p>}
      <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save new password'}</button>
    </form>
  )
}

function DeleteAccount() {
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const { busy, error, submit } = useSubmit(async () => {
    await api.deleteAccount(password)
    logout()
  })
  if (!open)
    return (
      <button type="button" className="btn-ghost text-red" onClick={() => setOpen(true)}>
        Delete my account
      </button>
    )
  return (
    <form onSubmit={submit} className="panel p-6 space-y-4 border-red/40">
      <h2 className="text-2xl">Delete account</h2>
      <p className="text-sm">This removes your account and email address straight away. It can't be undone.</p>
      <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <ErrorNote error={error} />
      <div className="flex gap-3">
        <button className="btn-primary bg-red border-red" disabled={busy}>{busy ? 'Deleting…' : 'Delete for good'}</button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  )
}

export default function Account() {
  const { user, checking, logout } = useAuth()
  if (checking) return <Loading />
  if (!user) return <Navigate to="/login?next=/account" replace />
  if (user.is_admin) return <Navigate to="/admin" replace />
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-4xl sm:text-5xl leading-none">Your account</h1>
          <p className="mt-2 text-ink-soft">{user.email}</p>
        </div>
        <button type="button" className="sm:ml-auto btn-ghost" onClick={logout}>Sign out</button>
      </div>
      <ChangePassword />
      <p className="text-sm text-ink-soft">
        Forgotten your password? Sign out and use <Link to="/forgot" className="underline underline-offset-4">reset password</Link>.
      </p>
      <DeleteAccount />
    </div>
  )
}
