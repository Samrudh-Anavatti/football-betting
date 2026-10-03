import { Fragment, useEffect, useState } from 'react'
import { useApi } from '../../hooks/useApi.js'
import { useRun } from '../../hooks/useRun.js'
import { api } from '../../lib/api.js'
import { ago } from '../../lib/format.js'
import RunStatus, { runSummary } from '../RunStatus.jsx'
import { ErrorNote, Freshness, LeagueBadge, Loading } from '../ui.jsx'

const MARKET_NAMES = { h2h: 'Match result', totals: 'Total goals' }
const REGION_NAMES = { uk: 'UK bookmakers', eu: 'European bookmakers' }

function QuotaMeter({ provider, onChecked }) {
  const q = provider.quota
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState(null)
  const known = q.remaining != null && q.limit
  const share = known ? q.remaining / q.limit : null
  const tone = share == null ? 'bg-ink/20' : share < 0.1 ? 'bg-red' : share < 0.3 ? 'bg-amber' : 'bg-pitch'

  const check = async () => {
    setChecking(true)
    setError(null)
    try {
      await api.checkQuota(provider.key)
      onChecked()
    } catch (e) {
      setError(e)
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-3">
        <p>
          <span className="num text-4xl font-bold">{known ? q.remaining.toLocaleString() : '?'}</span>
          <span className="text-ink-soft">
            {' '}
            {known ? `of ${q.limit.toLocaleString()}` : ''} {provider.unit} left {provider.period}
          </span>
        </p>
      </div>
      <div className="h-2.5 rounded-full bg-ink/10 overflow-hidden" role="meter" aria-valuenow={q.remaining ?? 0} aria-valuemin={0} aria-valuemax={q.limit ?? 0} aria-label={`${provider.label} allowance left`}>
        <div className={`h-full ${tone}`} style={{ width: `${(share ?? 0) * 100}%` }} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-soft">
        <span>{q.checked_at ? `Balance as of ${ago(q.checked_at)}` : 'Balance not checked yet'}</span>
        {q.plan && <span>{q.plan} plan</span>}
        <button type="button" className="font-semibold text-ink underline underline-offset-4 disabled:opacity-50" disabled={checking || !provider.configured} onClick={check}>
          {checking ? 'Checking…' : 'Check balance (free)'}
        </button>
        <a href={provider.site} target="_blank" rel="noreferrer" className="underline underline-offset-4">
          Provider dashboard
        </a>
      </div>
      {(q.last_error || error) && <ErrorNote>{error?.message || q.last_error}</ErrorNote>}
    </div>
  )
}

function Checks({ options, names, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o)
        return (
          <label key={o} className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm font-semibold ${on ? 'bg-ink text-white border-ink' : 'border-ink/15'}`}>
            <input
              type="checkbox"
              className="sr-only"
              checked={on}
              onChange={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}
            />
            {names[o]}
          </label>
        )
      })}
    </div>
  )
}

function CostLine({ cost, provider, extra }) {
  const left = provider.quota.remaining
  const over = left != null && cost > left
  return (
    <p className={`text-sm ${over ? 'text-red font-semibold' : 'text-ink-soft'}`}>
      {over ? 'Not enough allowance: ' : ''}
      Uses {provider.key === 'odds_api' ? 'up to ' : ''}
      <span className="num text-base font-semibold text-ink">{cost}</span> {provider.unit}
      {left != null ? ` of the ${left} left` : ''}. {extra}
    </p>
  )
}

function ProviderCard({ provider, onChecked, children }) {
  return (
    <section className="panel flex flex-col">
      <header className="px-5 pt-4 pb-3 border-b border-ink/10">
        <div className="flex items-center gap-3">
          <h3 className="text-2xl">{provider.label}</h3>
          <span className={`ml-auto rounded px-2 py-0.5 text-xs font-semibold ${provider.configured ? 'bg-pitch-light text-pitch' : 'bg-red-light text-red'}`}>
            {provider.configured ? 'Connected' : 'No API key'}
          </span>
        </div>
        <p className="text-sm text-ink-soft mt-0.5">{provider.feeds}</p>
      </header>
      <div className="px-5 py-4 space-y-5 flex-1">
        {provider.configured ? (
          <QuotaMeter provider={provider} onChecked={onChecked} />
        ) : (
          <ErrorNote>
            Add the API key as an App Service setting ({provider.key === 'odds_api' ? 'ODDS_API_KEY' : 'API_FOOTBALL_KEY'}) and restart the backend.
          </ErrorNote>
        )}
        {children}
      </div>
    </section>
  )
}

function FixturesAction({ provider, selected, pacing, onChange }) {
  const [standings, setStandings] = useState(true)
  const r = useRun(onChange)
  useEffect(() => {
    if (provider.running && !r.run) r.resume(provider.running)
  }, [provider.running]) // eslint-disable-line react-hooks/exhaustive-deps
  const cost = selected.length * (standings ? 2 : 1)
  const minutes = Math.ceil((cost * pacing) / 60)
  return (
    <div className="space-y-3 border-t border-ink/10 pt-4">
      <h4 className="font-display text-xl font-semibold">Fixtures and results</h4>
      <p className="text-sm text-ink-soft">
        Pulls the whole season for each selected league: upcoming fixtures, final scores (which settle tips and bets) and,
        if ticked, the league tables. Once a week is plenty, plus after a matchday to settle results.
      </p>
      <label className="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" checked={standings} onChange={(e) => setStandings(e.target.checked)} className="h-4 w-4 accent-ink" />
        Include league tables
      </label>
      <CostLine cost={cost} provider={provider} extra={pacing > 1 && cost > 1 ? `Takes about ${minutes} min on the free plan.` : ''} />
      <button
        type="button"
        className="btn-primary"
        disabled={!provider.configured || r.busy || !selected.length}
        onClick={() => r.start(() => api.syncFixtures({ league_ids: selected, include_standings: standings }))}
      >
        {r.busy ? 'Syncing…' : `Sync ${selected.length} league${selected.length === 1 ? '' : 's'}`}
      </button>
      <RunStatus run={r.run} error={r.error} />
    </div>
  )
}

function OddsAction({ provider, selected, options, onChange }) {
  const [markets, setMarkets] = useState(['h2h', 'totals'])
  const [regions, setRegions] = useState(['uk'])
  const r = useRun(onChange)
  useEffect(() => {
    if (provider.running && !r.run) r.resume(provider.running)
  }, [provider.running]) // eslint-disable-line react-hooks/exhaustive-deps
  const cost = selected.length * markets.length * regions.length
  return (
    <div className="space-y-3 border-t border-ink/10 pt-4">
      <h4 className="font-display text-xl font-semibold">Latest prices</h4>
      <p className="text-sm text-ink-soft">
        Pulls current prices for every upcoming match in the selected leagues and keeps the old ones, so we can track how
        prices moved. Pull fixtures first so prices have matches to attach to.
      </p>
      <div className="space-y-2">
        <Checks options={options.markets} names={MARKET_NAMES} value={markets} onChange={setMarkets} />
        <Checks options={options.regions} names={REGION_NAMES} value={regions} onChange={setRegions} />
      </div>
      <CostLine cost={cost} provider={provider} extra="Leagues with no upcoming matches cost nothing." />
      <button
        type="button"
        className="btn-primary"
        disabled={!provider.configured || r.busy || !selected.length || !markets.length || !regions.length}
        onClick={() => r.start(() => api.syncOdds({ league_ids: selected, markets, regions }))}
      >
        {r.busy ? 'Pulling…' : `Pull prices for ${selected.length} league${selected.length === 1 ? '' : 's'}`}
      </button>
      <RunStatus run={r.run} error={r.error} />
    </div>
  )
}

function LeagueTable({ leagues, selected, setSelected }) {
  const all = selected.length === leagues.length
  const toggle = (id) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  return (
    <section className="panel overflow-hidden">
      <header className="px-5 py-3 border-b border-ink/10 flex flex-wrap items-center gap-3">
        <h3 className="text-2xl">Leagues</h3>
        <span className="text-sm text-ink-soft">
          {selected.length} of {leagues.length} selected for the sync buttons above
        </span>
        <button type="button" className="ml-auto btn-ghost" onClick={() => setSelected(all ? [] : leagues.map((l) => l.id))}>
          {all ? 'Clear selection' : 'Select all'}
        </button>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-ink-soft text-left">
            <tr>
              <th className="px-5 py-2 w-8"><span className="sr-only">Selected</span></th>
              <th className="py-2 font-medium">League</th>
              <th className="py-2 font-medium">Fixtures and results</th>
              <th className="py-2 font-medium">League table</th>
              <th className="py-2 font-medium">Prices</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5">
            {leagues.map((lg) => (
              <Fragment key={lg.id}>
                <tr className="hover:bg-chalk/60">
                  <td className="px-5 py-2">
                    <input type="checkbox" className="h-4 w-4 accent-ink" checked={selected.includes(lg.id)} onChange={() => toggle(lg.id)} aria-label={`Select ${lg.name}`} />
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1.5">
                      <LeagueBadge league={lg} />
                      <span className="font-semibold">{lg.name}</span> <span className="text-ink-faint">{lg.country}</span>
                    </span>
                  </td>
                  <td className="py-2 pr-4"><Freshness at={lg.fixtures_synced_at} prefix="Synced" warnAfter={24 * 4} staleAfter={24 * 8} /></td>
                  <td className="py-2 pr-4"><Freshness at={lg.standings_synced_at} prefix="Synced" warnAfter={24 * 4} staleAfter={24 * 8} /></td>
                  <td className="py-2 pr-4"><Freshness at={lg.odds_synced_at} prefix="Pulled" warnAfter={12} staleAfter={48} /></td>
                </tr>
                {lg.last_error && (
                  <tr>
                    <td />
                    <td colSpan={4} className="pb-2 pr-4 text-red">Last sync failed: {lg.last_error}</td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const KIND_NAMES = { fixtures: 'Fixtures and results', odds: 'Prices', context: 'Match research', match_odds: 'Match prices' }
const STATUS_STYLE = { ok: 'bg-pitch-light text-pitch', partial: 'bg-amber-light text-amber-dark', error: 'bg-red-light text-red', running: 'bg-ink/10 text-ink' }
const STATUS_NAMES = { ok: 'Done', partial: 'Partly failed', error: 'Failed', running: 'Running' }

function History({ version }) {
  const runs = useApi(() => api.syncRuns(30), [version])
  const [open, setOpen] = useState(null)
  return (
    <section className="panel overflow-hidden">
      <header className="px-5 py-3 border-b border-ink/10">
        <h3 className="text-2xl">Sync history</h3>
        <p className="text-sm text-ink-soft">Every button press, what it fetched and what it cost.</p>
      </header>
      {runs.loading && !runs.data ? (
        <div className="px-5"><Loading /></div>
      ) : !runs.data?.length ? (
        <p className="px-5 py-4 text-ink-soft">Nothing synced yet. Start with fixtures and results above.</p>
      ) : (
        <ul className="divide-y divide-ink/5 text-sm">
          {runs.data.map((r) => (
            <li key={r.id} className="px-5 py-2.5">
              <button type="button" className="w-full text-left grid grid-cols-[6.5rem_1fr_auto] sm:grid-cols-[7rem_10rem_1fr_auto] gap-3 items-center" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                <span className="text-ink-soft">{ago(r.started_at)}</span>
                <span className="hidden sm:block font-semibold">{KIND_NAMES[r.kind]}</span>
                <span className="truncate">
                  <span className="sm:hidden font-semibold">{KIND_NAMES[r.kind]}: </span>
                  {r.scope} <span className="text-ink-faint">by {r.triggered_by}</span>
                </span>
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[r.status]}`}>{STATUS_NAMES[r.status]}</span>
              </button>
              {open === r.id && (
                <div className="mt-2 ml-0 sm:ml-[7.75rem] space-y-1 text-ink-soft">
                  <p>{runSummary(r)}.</p>
                  {r.message && <p className={r.status === 'ok' ? '' : 'text-red'}>{r.message}</p>}
                  {r.details?.leagues && (
                    <ul className="space-y-0.5">
                      {Object.entries(r.details.leagues).map(([name, d]) => (
                        <li key={name}>
                          <span className="font-semibold text-ink">{name}: </span>
                          {d.error
                            ? <span className="text-red">{d.error}</span>
                            : d.fixtures != null
                              ? `${d.fixtures} fixtures, ${d.settled} picks or bets settled`
                              : `${d.matched} of ${d.events} bookmaker events matched${d.unmatched?.length ? ` (unmatched: ${d.unmatched.join(', ')})` : ''}`}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export default function DataTab() {
  const { data, loading, error, reload } = useApi(() => api.integrations(), [])
  const [selected, setSelected] = useState(null)
  const [version, setVersion] = useState(0)
  const refresh = () => {
    reload()
    setVersion((v) => v + 1)
  }

  useEffect(() => {
    if (data && selected == null) setSelected(data.leagues.map((l) => l.id))
  }, [data, selected])

  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  const [af, odds] = ['api_football', 'odds_api'].map((k) => data.providers.find((p) => p.key === k))
  const sel = selected || []

  return (
    <div className="space-y-6">
      <p className="text-ink-soft max-w-3xl">
        The site only shows what's been pulled into our database. Nothing calls the providers automatically, so every
        request is spent from a button on this page or on a match page. Season {data.season}.
      </p>
      <div className="grid gap-6 lg:grid-cols-2">
        <ProviderCard provider={af} onChecked={refresh}>
          <FixturesAction provider={af} selected={sel} pacing={data.pacing_seconds} onChange={refresh} />
        </ProviderCard>
        <ProviderCard provider={odds} onChecked={refresh}>
          <OddsAction provider={odds} selected={sel} options={data.odds_options} onChange={refresh} />
        </ProviderCard>
      </div>
      <LeagueTable leagues={data.leagues} selected={sel} setSelected={setSelected} />
      <History version={version} />
    </div>
  )
}
