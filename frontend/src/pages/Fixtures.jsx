import { useState } from 'react'
import FixtureList from '../components/FixtureList.jsx'
import LeagueFilter from '../components/LeagueFilter.jsx'
import { Empty, ErrorNote, Loading } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'

const RANGES = [3, 7, 14]

export default function Fixtures({ results = false }) {
  const [league, setLeague] = useState(null)
  const [days, setDays] = useState(7)
  const leagues = useApi(() => api.leagues(), [])
  const fixtures = useApi(
    () => api.fixtures({ when: results ? 'results' : 'upcoming', league_id: league, days }),
    [results, league, days],
  )

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
      {leagues.data && <LeagueFilter leagues={leagues.data} value={league} onChange={setLeague} />}
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
