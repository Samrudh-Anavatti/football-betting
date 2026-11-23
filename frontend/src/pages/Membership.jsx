import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorNote, Loading } from '../components/ui.jsx'
import { api } from '../lib/api.js'
import { MEMBER_PERKS } from '../lib/access.js'
import { useAuth } from '../lib/auth.jsx'
import { formatPrice } from '../lib/business.js'
import { useMembershipInfo } from '../lib/membership.js'

const linkCls = 'underline underline-offset-4 hover:text-ink'

// Both boxes are required: the terms, and starting straight away (which ends the 14-day right to cancel once
// access starts; without it, UK and EU consumers could cancel within 14 days for a full refund).
function JoinForm({ price }) {
  const [terms, setTerms] = useState(false)
  const [startNow, setStartNow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const join = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      window.location.assign((await api.joinMembership({ terms, start_now: startNow })).url)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }
  return (
    <form onSubmit={join} className="space-y-3">
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={terms} onChange={(e) => setTerms(e.target.checked)} required />
        <span>
          I'm 18 or over and agree to the <Link to="/terms" className={linkCls}>terms</Link>.
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={startNow} onChange={(e) => setStartNow(e.target.checked)} required />
        <span>
          Start my membership straight away. I understand that once it starts I lose my 14-day right to cancel for a
          refund; I can still cancel any time to stop the next payment.
        </span>
      </label>
      <ErrorNote error={error} />
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? 'Opening secure checkout…' : `Join for ${formatPrice(price)} a month`}
      </button>
      <p className="text-xs text-ink-soft text-center">Payment by Whop. We never see your card details.</p>
    </form>
  )
}

function JoinPanel({ info }) {
  const { user } = useAuth()
  if (!info) return <Loading rows={2} />
  if (!info.open)
    return (
      <div className="space-y-2 text-center">
        <p className="font-display text-xl font-bold">Opening soon</p>
        <p className="text-ink-soft">Membership isn't open yet. A free account opens every page in the meantime.</p>
      </div>
    )
  if (!user)
    return (
      <div className="space-y-3 text-center">
        <p className="text-ink-soft">First, make an account with your email address.</p>
        <Link to="/signup?next=/membership" className="btn-primary w-full">Create an account</Link>
        <p className="text-sm text-ink-soft">
          Already have one? <Link to="/login?next=/membership" className={linkCls}>Sign in</Link>
        </p>
      </div>
    )
  if (user.is_admin) return <p className="text-center text-ink-soft">You're an admin, so you see everything already.</p>
  const m = user.membership
  if (m.member || ['active', 'trialing', 'past_due', 'unpaid', 'paused'].includes(m.status))
    return (
      <div className="space-y-3 text-center">
        <p className="font-display text-xl font-bold">You're a member</p>
        <Link to="/tonight" className="btn-primary w-full">Build tonight's bundles</Link>
        <Link to="/account" className={`text-sm ${linkCls}`}>Manage your membership</Link>
      </div>
    )
  return <JoinForm price={info.price} />
}

export default function Membership() {
  const info = useMembershipInfo()
  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_24rem] items-start">
      <article className="space-y-5 text-[15px] leading-relaxed max-w-prose">
        <div>
          <h1 className="text-4xl sm:text-5xl leading-none">Membership</h1>
          {info?.price && (
            <p className="mt-3 text-lg">
              <span className="num font-semibold">{formatPrice(info.price)}</span> a month. Cancel any time.
            </p>
          )}
        </div>
        <p>
          A free account already opens every page: all of our picks, every match's prices and research, the bundle of
          the day and a look at the tools. Membership takes the limits off.
        </p>
        <ul className="space-y-3">
          {MEMBER_PERKS.map(([name, text]) => (
            <li key={name} className="flex gap-3">
              <span aria-hidden className="mt-1.5 h-2.5 w-2.5 shrink-0 rotate-[10deg] rounded-[2px] bg-amber" />
              <p className="leading-snug">
                <span className="font-display font-bold">{name}.</span> <span className="text-ink-soft">{text}</span>
              </p>
            </li>
          ))}
        </ul>
        <p>
          Membership renews monthly until you cancel. Cancel from your account page whenever you like: you keep access
          to the end of the month you've paid for, and you won't be charged again.
        </p>
        <p className="text-ink-soft">
          No staking plan creates an edge on its own, and no pick is certain: you can lose money following them. Bet
          only what you can afford to lose. You must be 18 or over, and betting must be legal where you live. Free,
          confidential support at BeGambleAware.org.
        </p>
      </article>
      <aside data-tour="join" className="panel p-6">
        <JoinPanel info={info} />
      </aside>
    </div>
  )
}
