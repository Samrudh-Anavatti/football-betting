import { useState } from 'react'
import FixtureList from '../components/FixtureList.jsx'
import LeagueFilter from '../components/LeagueFilter.jsx'
import { Empty, ErrorNote, Loading } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'

const RANGES = [3, 7, 14]
const TIERS = [
  ['main', 'Top leagues'],
  ['more', 'More leagues'],
]

// "More leagues": second and third tiers, South America, Scotland. Too many for chips,
// so a dropdown grouped by country.
function MoreLeagues({ leagues, value, onChange }) {
  const byCountry = {}
  for (const lg of leagues) (byCountry[lg.country] ||= []).push(lg)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor="more-league" className="text-sm text-ink-soft">League</label>
      <select
        id="more-league"
        className="input w-auto max-w-full"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">All {leagues.length} leagues</option>
        {Object.entries(byCountry).map(([country, lgs]) => (
          <optgroup key={country} label={country}>
            {lgs.map((lg) => (
              <option key={lg.id} value={lg.id}>{lg.name}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}

export default function Fixtures({ results = false }) {
  const [tier, setTier] = useState('main')
  const [league, setLeague] = useState(null)
  const [days, setDays] = useState(7)
  const leagues = useApi(() => api.leagues(), [])
  const fixtures = useApi(
    () => api.fixtures({ when: results ? 'results' : 'upcoming', league_id: league, tier: league ? 'all' : tier, days }),
    [results, league, tier, days],
  )
  const inTier = (leagues.data || []).filter((lg) => lg.supplementary === (tier === 'more'))
  const switchTier = (t) => {
    setTier(t)
    setLeague(null)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="text-4xl">{results ? 'Results' : 'Fixtures'}</h1>
        <div className="ml-auto inline-flex rounded-md bg-ink/5 p-0.5" role="group" aria-label="Date range">
          {RANGES.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-sm font-semibold ${days === d ? 'bg-white shadow-sm' : 'text-ink-soft'}`}
            >
              {d} days
            </button>
          ))}
        </div>
      </div>
      <div className="inline-flex rounded-md bg-ink/5 p-0.5" role="group" aria-label="Which leagues">
        {TIERS.map(([t, label]) => (
          <button
            key={t}
            type="button"
            aria-pressed={tier === t}
            onClick={() => switchTier(t)}
            className={`px-3 py-1 rounded text-sm font-semibold ${tier === t ? 'bg-white shadow-sm' : 'text-ink-soft'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {leagues.data &&
        (tier === 'main' ? (
          <LeagueFilter leagues={inTier} value={league} onChange={setLeague} />
        ) : (
          <MoreLeagues leagues={inTier} value={league} onChange={setLeague} />
        ))}
      {fixtures.loading ? (
        <Loading />
      ) : fixtures.error ? (
        <ErrorNote error={fixtures.error} />
      ) : fixtures.data.length ? (
        <FixtureList fixtures={fixtures.data} results={results} />
      ) : (
        <Empty title={results ? 'No results in this range' : 'No fixtures in this range'}>
          Try a longer range or another league. Fixtures appear once they've been synced from the admin page.
        </Empty>
      )}
    </div>
  )
}
