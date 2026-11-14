import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Empty, ErrorNote, LeagueBadge, Loading, Price, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { dayLabel, kickoffTime, money, odds, pct, pickLabel, shortDate } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'
import { ResultMark, Stat } from './Staking.jsx'

// Tonight's bundles: for someone sitting down to watch a few matches. They pick the session, tick the matches they're
// watching and a target, and the AI's surest legs on those matches become up to three bundles, each at one bookmaker.
// Flat stakes (the stake box just scales the figures), and every bundle shown is settled onto the record.

const STAKE_KEY = 'fb.tonight'
const TARGETS = [
  { key: 'safer', label: 'Safer', odds: 3.0, note: 'two or three short legs' },
  { key: 'standard', label: 'Standard', odds: 6.0, note: 'the usual night' },
  { key: 'big', label: 'Big night', odds: 10.0, note: 'more legs, longer odds' },
]

const readStake = () => {
  try {
    return Number(localStorage.getItem(STAKE_KEY)) || 10
  } catch {
    return 10
  }
}

// A session is a cluster of kick-offs: "Today 20:00–20:45".
function sessionLabel(s) {
  const from = kickoffTime(s.at)
  const to = kickoffTime(s.until)
  return `${dayLabel(s.at)}, ${from}${to !== from ? `–${to}` : ''}`
}

function SessionPicker({ sessions, value, onChange }) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap" role="tablist" aria-label="Sessions">
      {sessions.map((s) => {
        const on = s.at === value
        return (
          <button
            key={s.at}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(s.at)}
            className={`shrink-0 rounded-xl px-4 py-2.5 text-left transition ${on ? 'bg-ink text-white shadow-lift' : 'panel hover:bg-paper/70 text-ink'}`}
          >
            <p className={`font-display font-bold leading-tight ${on ? 'text-amber' : ''}`}>{sessionLabel(s)}</p>
            <p className={`text-xs mt-0.5 ${on ? 'text-white/65' : 'text-ink-soft'}`}>
              {s.matches.length} matches · {s.legs} legs
            </p>
          </button>
        )
      })}
    </div>
  )
}

function MatchPicker({ session, picked, onToggle, onAll }) {
  const all = picked.size === session.matches.length
  return (
    <div className="panel">
      <div className="px-4 pt-3 pb-2 flex items-center gap-3">
        <p className="font-display font-bold">Watching</p>
        <button type="button" className="ml-auto text-sm text-ink-soft underline underline-offset-4 hover:text-ink" onClick={() => onAll(!all)}>
          {all ? 'None' : 'All'}
        </button>
      </div>
      <ul className="divide-y divide-ink/5">
        {session.matches.map((m) => (
          <li key={m.id}>
            <label className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-ink/[0.03]">
              <input type="checkbox" className="h-4 w-4 accent-ink" checked={picked.has(m.id)} onChange={() => onToggle(m.id)} />
              <LeagueBadge league={m.league} />
              <span className="min-w-0 flex-1 truncate text-[15px]">
                {m.home.name} v {m.away.name}
              </span>
              <span className="num text-sm text-ink-soft shrink-0">{kickoffTime(m.kickoff)}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Controls({ target, onTarget, stake, onStake }) {
  return (
    <div className="panel p-4 space-y-4">
      <div>
        <span className="label">How big a night</span>
        <div className="segmented w-full">
          {TARGETS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-pressed={t.odds === target}
              onClick={() => onTarget(t.odds)}
              className={`segment flex-1 ${t.odds === target ? 'segment-on' : ''}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-ink-soft">
          About <span className="num">{odds(target)}</span>: {TARGETS.find((t) => t.odds === target)?.note}
        </p>
      </div>
      <label className="block">
        <span className="label">Your stake on each</span>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft">£</span>
          <input type="number" min="1" step="1" inputMode="decimal" className="input pl-7 num text-lg" value={stake}
            onChange={(e) => onStake(Number(e.target.value))} />
        </div>
      </label>
    </div>
  )
}

// One bundle as a slip. Legs link to the match; the AI's one-line reason sits behind a tap.
function Slip({ bundle, index, stake }) {
  const settled = bundle.status !== 'pending'
  return (
    <div className="slip-shadow">
      <article className="perforated rounded-t-xl bg-paper">
        <header className="px-4 pt-3.5 pb-2 flex items-baseline gap-x-3 text-sm text-ink-soft">
          <span className="font-display font-bold text-ink">Bundle {index + 1}</span>
          {bundle.bookmaker && <span>at {bundle.bookmaker}</span>}
          {bundle.stretch && (
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-dark" title="A thin night: the AI's surest legs on these matches couldn't reach the target on their own">
              with longer shots
            </span>
          )}
          {settled && (
            <span className={`ml-auto font-semibold ${bundle.status === 'won' ? 'text-pitch' : bundle.status === 'lost' ? 'text-red' : ''}`}>
              {bundle.status === 'won' ? 'Landed' : bundle.status === 'lost' ? 'Missed' : 'Void'}
            </span>
          )}
        </header>
        <ol className="divide-y divide-dashed divide-ink/15 border-y border-dashed border-ink/15">
          {bundle.legs.map(({ tip_id, odds: price, tip }) => (
            <li key={tip_id} className="px-4 py-2.5">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-display font-extrabold text-[1.05rem] leading-tight tracking-tight">
                    {pickLabel(tip, tip.fixture)}
                    {tip.source === 'ai' && (
                      <span className="ml-2 align-middle rounded bg-amber-light px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-dark">
                        longer shot
                      </span>
                    )}
                  </p>
                  <Link to={matchPath(tip.fixture)} className="mt-0.5 flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink">
                    <LeagueBadge league={tip.fixture.league} />
                    <span className="truncate">
                      {tip.fixture.home.name} v {tip.fixture.away.name}
                    </span>
                    <span className="shrink-0 num">· {kickoffTime(tip.fixture.kickoff)}</span>
                  </Link>
                </div>
                {tip.status !== 'pending' && <ResultMark status={tip.status} />}
                <Price value={price} />
              </div>
              {tip.reasoning && (
                <details className="mt-1.5 text-sm text-ink-soft">
                  <summary className="cursor-pointer select-none text-xs font-semibold uppercase tracking-wider text-amber-dark">Why</summary>
                  <p className="mt-1 leading-snug">{tip.reasoning}</p>
                </details>
              )}
            </li>
          ))}
        </ol>
        <footer className="px-4 pt-3 pb-6 grid grid-cols-3 gap-3 items-end">
          <div className="min-w-0">
            <p className="text-sm text-ink-soft">Odds</p>
            <Price value={bundle.odds} board />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-ink-soft">Stake</p>
            <p className="num text-xl sm:text-2xl font-bold truncate">{money(stake)}</p>
          </div>
          <div className="min-w-0 text-right">
            <p className="text-sm text-ink-soft">Returns</p>
            <p className="num text-xl sm:text-2xl font-bold text-pitch truncate">{money(stake * bundle.odds)}</p>
          </div>
        </footer>
      </article>
    </div>
  )
}

function Record({ record, stake }) {
  if (!record) return null
  if (!record.bundles)
    return (
      <p className="text-sm text-ink-soft">
        Nothing settled yet{record.pending ? ` (${record.pending} bundle${record.pending === 1 ? '' : 's'} waiting on results)` : ''}.
        Every bundle shown here lands on this record, hit or miss.
      </p>
    )
  const profit = record.profit_units * stake
  const legs = record.legs || {}
  const legLine = (r, what) =>
    r?.settled ? (
      <p>
        {what}: landed <span className="num font-semibold">{r.won}</span> of <span className="num">{r.settled}</span> (
        <span className="num font-semibold">{pct(r.hit_rate, 0)}</span>; the prices implied{' '}
        <span className="num">{pct(r.implied_rate, 0)}</span>).
      </p>
    ) : null
  return (
    <div className="space-y-4">
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <Stat label="Bundles shown" value={record.bundles} />
        <Stat label="Landed" value={`${record.won} of ${record.bundles}`} />
        <Stat label={`At ${money(stake)} each`} value={`${profit > 0 ? '+' : profit < 0 ? '−' : ''}${money(Math.abs(profit))}`}
          tone={profit > 0 ? 'text-pitch' : profit < 0 ? 'text-red' : ''} />
        <Stat label="Waiting on results" value={record.pending} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 items-start">
        <ol className="panel divide-y divide-ink/5 text-sm">
          {TARGETS.map((t) => {
            const r = record.by_target?.[t.key]
            if (!r) return null
            const p = r.profit_units * stake
            return (
              <li key={t.key} className="px-4 py-2 flex items-center gap-3">
                <span className="font-semibold">{t.label}</span>
                <span className="num text-ink-soft">about {odds(t.odds)}</span>
                <span className="ml-auto num">{r.bundles ? `${r.won} of ${r.bundles} landed` : 'none settled'}</span>
                {r.bundles > 0 && (
                  <span className={`num w-20 text-right font-semibold ${p > 0 ? 'text-pitch' : p < 0 ? 'text-red' : 'text-ink-soft'}`}>
                    {p > 0 ? '+' : p < 0 ? '−' : ''}{money(Math.abs(p))}
                  </span>
                )}
              </li>
            )
          })}
        </ol>
        <div className="panel p-4 text-sm space-y-1.5">
          <p className="text-ink-soft">The legs themselves, each counted once. This is what has to beat the prices.</p>
          {legLine(legs.sure, 'Surest legs')}
          {legLine(legs.longer, 'Longer shots')}
          {!legs.sure?.settled && !legs.longer?.settled && <p className="text-ink-soft">None settled yet.</p>}
        </div>
      </div>
      <ol className="panel divide-y divide-ink/5 text-sm">
        {record.sessions.map((s) => (
          <li key={s.at} className="px-4 py-2.5">
            <div className="flex items-center gap-3">
              <span className="font-semibold">{shortDate(s.at)}, {kickoffTime(s.at)}</span>
              <span className={`ml-auto num font-semibold ${s.won ? 'text-pitch' : 'text-red'}`}>
                {s.won} of {s.bundles.length} landed
              </span>
            </div>
            <ul className="mt-1 space-y-0.5 text-ink-soft">
              {s.bundles.map((b) => (
                <li key={b.id} className="flex items-center gap-2">
                  <ResultMark status={b.status} />
                  <span className="truncate">{b.legs.map((l) => pickLabel(l.tip, l.tip.fixture)).join(' · ')}</span>
                  <span className="ml-auto num shrink-0">{odds(b.odds)}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  )
}

function TonightInner() {
  const sessions = useApi(() => api.tonightSessions(), [])
  const record = useApi(() => api.tonightRecord(), [])
  const [sessionAt, setSessionAt] = useState(null)
  const [picked, setPicked] = useState(new Set())
  const [target, setTarget] = useState(6.0)
  const [stake, setStake] = useState(readStake)
  const [bundles, setBundles] = useState(null) // null: not built for this selection yet
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)

  const list = sessions.data?.sessions || []
  const session = list.find((s) => s.at === sessionAt) || list[0] || null

  // A new session starts with every match ticked; the first set of bundles is built straight away.
  useEffect(() => {
    if (!session) return
    setPicked(new Set(session.matches.map((m) => m.id)))
    setBundles(null)
    setDirty(true)
  }, [session?.at]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!session || !dirty || building) return undefined
    if (!picked.size) {
      setBundles([])
      setDirty(false)
      return undefined
    }
    let alive = true
    setBuilding(true)
    setError(null)
    api
      .tonightBuild({ session_at: session.at, fixture_ids: [...picked], target })
      .then((r) => alive && setBundles(r.bundles))
      .catch((e) => alive && setError(e))
      .finally(() => {
        if (alive) {
          setBuilding(false)
          setDirty(false)
        }
      })
    return () => {
      alive = false
    }
  }, [dirty]) // eslint-disable-line react-hooks/exhaustive-deps

  const changeStake = (v) => {
    setStake(v)
    try {
      localStorage.setItem(STAKE_KEY, String(v))
    } catch {
      /* private mode: keep it for this visit */
    }
  }
  const toggle = (id) => {
    const next = new Set(picked)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPicked(next)
    setBundles(null)
  }
  const pickAll = (on) => {
    setPicked(new Set(on ? session.matches.map((m) => m.id) : []))
    setBundles(null)
  }
  const changeTarget = (t) => {
    setTarget(t)
    setBundles(null)
    setDirty(true)
  }

  if (sessions.loading && !sessions.data) return <Loading rows={4} />
  if (sessions.error) return <ErrorNote error={sessions.error} />

  return (
    <div className="space-y-10">
      {!list.length ? (
        <Empty title="No sessions in the next three days">
          The AI needs a couple of matches with legs kicking off around the same time. Check back nearer the weekend.
        </Empty>
      ) : (
        <>
          <SessionPicker sessions={list} value={session.at} onChange={setSessionAt} />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[22rem_minmax(0,1fr)] items-start">
            <div className="space-y-4">
              <MatchPicker session={session} picked={picked} onToggle={toggle} onAll={pickAll} />
              <Controls target={target} onTarget={changeTarget} stake={stake} onStake={changeStake} />
            </div>
            <div className="space-y-4">
              {bundles === null || dirty ? (
                <div className="panel px-5 py-8 text-center space-y-3">
                  {building ? (
                    <Loading label="Building" rows={3} />
                  ) : (
                    <>
                      <p className="text-ink-soft">
                        {picked.size} match{picked.size === 1 ? '' : 'es'} ticked, aiming for about {odds(target)}.
                      </p>
                      <button type="button" className="btn-primary" disabled={!picked.size} onClick={() => setDirty(true)}>
                        Build my bundles
                      </button>
                    </>
                  )}
                </div>
              ) : bundles.length ? (
                <div className={`grid grid-cols-1 gap-5 ${bundles.length > 1 ? 'xl:grid-cols-2' : ''} ${bundles.length > 2 ? '2xl:grid-cols-3' : ''}`}>
                  {bundles.map((b, i) => <Slip key={b.id} bundle={b} index={i} stake={stake} />)}
                </div>
              ) : (
                <div className="panel px-5 py-8 text-center space-y-2">
                  <p className="font-display text-xl font-bold">Nothing the AI would back at {odds(target)}</p>
                  <p className="text-ink-soft max-w-prose mx-auto">
                    Even with its longer shots, its calls on {picked.size === 1 ? 'this match' : 'these matches'} don't reach that.
                    Tick more matches, or try a safer target.
                  </p>
                </div>
              )}
              <ErrorNote error={error} />
              <p className="text-sm text-ink-soft max-w-prose">
                These are the AI's surest calls, not certainties: short-priced favourites lose all the time, and a bundle
                needs every leg. Stake only what you can afford to lose. 18+, free support at BeGambleAware.org.
              </p>
            </div>
          </div>
        </>
      )}

      <section>
        <SectionHead title="On the record" />
        <ErrorNote error={record.error} />
        <Record record={record.data} stake={stake} />
      </section>
    </div>
  )
}

export default function Tonight() {
  const { user, checking } = useAuth()
  if (checking) return <Loading />
  if (!user) return <Navigate to="/login?next=/tonight" replace />
  if (!user.is_admin) return <Navigate to="/" replace /> // admins only while it's tested
  return (
    <div className="space-y-6">
      <div data-tour="tonight">
        <h1 className="text-4xl sm:text-5xl leading-none">Tonight's bundles</h1>
        <p className="mt-3 max-w-prose text-[17px] text-ink-soft leading-relaxed">
          Sitting down for a few matches? Tick the ones you're watching and the AI builds up to three bundles from its
          surest legs on them. Something to cheer for in every game.
        </p>
      </div>
      <TonightInner />
    </div>
  )
}
