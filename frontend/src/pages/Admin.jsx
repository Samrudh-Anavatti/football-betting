import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AccountsTab from '../components/admin/AccountsTab.jsx'
import DataTab from '../components/admin/DataTab.jsx'
import PicksTab from '../components/admin/PicksTab.jsx'
import { ErrorNote, Loading } from '../components/ui.jsx'
import { useAuth } from '../lib/auth.jsx'

const TABS = [
  { key: 'data', label: 'Data', el: DataTab },
  { key: 'picks', label: 'Picks', el: PicksTab },
  { key: 'accounts', label: 'Accounts', el: AccountsTab },
]

function SignIn() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username, password)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="panel max-w-sm mx-auto mt-10 p-6 space-y-4">
      <h1 className="text-3xl">Sign in</h1>
      <label className="block">
        <span className="label">Username</span>
        <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label className="block">
        <span className="label">Password</span>
        <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <ErrorNote error={error} />
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}

export default function Admin() {
  const { user, checking, logout } = useAuth()
  const [params, setParams] = useSearchParams()
  if (checking) return <Loading />
  if (!user) return <SignIn />

  const active = TABS.find((t) => t.key === params.get('tab')) || TABS[0]
  const Tab = active.el
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-4xl">Admin</h1>
        <nav className="flex gap-1 rounded-md bg-ink/5 p-0.5" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-current={t.key === active.key ? 'page' : undefined}
              onClick={() => setParams({ tab: t.key })}
              className={`px-4 py-1.5 rounded text-sm font-semibold ${t.key === active.key ? 'bg-white shadow-sm' : 'text-ink-soft hover:text-ink'}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <button type="button" className="sm:ml-auto btn-ghost" onClick={logout}>
          Sign out {user.display_name}
        </button>
      </div>
      <Tab />
    </div>
  )
}
