import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ErrorNote, Loading } from '../components/ui.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { WHATSAPP_URL } from '../lib/support.js'

// Where to go once signed in: ?next= if it's one of our pages, else Admin or Account.
function useDone() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  return (user) => {
    const next = params.get('next')
    navigate(next?.startsWith('/') && !next.startsWith('//') ? next : user.is_admin ? '/admin' : '/account', { replace: true })
  }
}

// A form card that tracks busy/error around one async submit.
function AuthForm({ title, onSubmit, submit, busyLabel, children, footer }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const handle = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit()
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }
  return (
    <div className="max-w-sm mx-auto mt-10 space-y-4">
      <form onSubmit={handle} className="panel p-6 space-y-4">
        <h1 className="text-3xl">{title}</h1>
        {children}
        <ErrorNote error={error} />
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? busyLabel : submit}
        </button>
      </form>
      {footer && <div className="text-sm text-ink-soft text-center space-y-1">{footer}</div>}
    </div>
  )
}

export function Field({ label, ...input }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input className="input" required {...input} />
    </label>
  )
}

const linkCls = 'underline underline-offset-4 hover:text-ink'

export function Login() {
  const { user, checking, login } = useAuth()
  const done = useDone()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  if (checking) return <Loading />
  if (user) return <Navigate to={user.is_admin ? '/admin' : '/account'} replace />
  return (
    <AuthForm
      title="Sign in"
      submit="Sign in"
      busyLabel="Signing in…"
      onSubmit={async () => done(await login(name, password))}
      footer={
        <p>
          <Link to="/forgot" className={linkCls}>Forgot your password?</Link>
        </p>
      }
    >
      <Field label="Email" autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} />
      <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
    </AuthForm>
  )
}

export function Signup() {
  const { user, checking, signIn } = useAuth()
  const done = useDone()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [adult, setAdult] = useState(false)
  if (checking) return <Loading />
  if (user) return <Navigate to={user.is_admin ? '/admin' : '/account'} replace />
  return (
    <AuthForm
      title="Create an account"
      submit="Create account"
      busyLabel="Creating…"
      onSubmit={async () => done(signIn(await api.signup({ email, password, adult })))}
      footer={
        <p>
          Already have one? <Link to="/login" className={linkCls}>Sign in</Link>
        </p>
      }
    >
      <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="Password (8+ characters)" type="password" autoComplete="new-password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={adult} onChange={(e) => setAdult(e.target.checked)} required />
        <span>
          I'm 18 or over, and I've read the <Link to="/privacy" className={linkCls}>privacy notice</Link>.
        </span>
      </label>
    </AuthForm>
  )
}

export function Forgot() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(null)
  if (sent)
    return (
      <div className="panel max-w-sm mx-auto mt-10 p-6 space-y-3">
        <h1 className="text-3xl">Check your email</h1>
        <p>{sent}</p>
        <p className="text-sm text-ink-soft">
          The link expires in an hour. Nothing arrived? Check your spam folder, or{' '}
          <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className={linkCls}>message us on WhatsApp</a>.
        </p>
      </div>
    )
  return (
    <AuthForm
      title="Reset your password"
      submit="Email me a link"
      busyLabel="Sending…"
      onSubmit={async () => setSent((await api.forgot(email)).detail)}
      footer={
        <>
          <p>
            Remembered it? <Link to="/login" className={linkCls}>Sign in</Link>
          </p>
          <p>
            Can't get into that email any more?{' '}
            <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className={linkCls}>Message us on WhatsApp</a>
          </p>
        </>
      }
    >
      <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
    </AuthForm>
  )
}

export function Reset() {
  const { signIn } = useAuth()
  const done = useDone()
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token'))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  // Take the token out of the address bar (and so out of history) once it's read.
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname)
  }, [])
  if (!token)
    return (
      <div className="panel max-w-sm mx-auto mt-10 p-6 space-y-3">
        <h1 className="text-3xl">Link not valid</h1>
        <p>
          Open the link from your email again, or <Link to="/forgot" className={linkCls}>ask for a new one</Link>.
        </p>
      </div>
    )
  return (
    <AuthForm
      title="Choose a new password"
      submit="Save password"
      busyLabel="Saving…"
      onSubmit={async () => {
        if (password !== confirm) throw new Error("The two passwords don't match")
        done(signIn(await api.resetPassword(token, password)))
      }}
    >
      <Field label="New password (8+ characters)" type="password" autoComplete="new-password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
      <Field label="Type it again" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
    </AuthForm>
  )
}
