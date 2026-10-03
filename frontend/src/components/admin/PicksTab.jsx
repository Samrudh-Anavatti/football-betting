import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { odds, pct, pickLabel, shortDate, signed } from '../../lib/format.js'
import { Empty, ErrorNote, Loading } from '../ui.jsx'

const STATUS_STYLE = { won: 'text-pitch', lost: 'text-red', void: 'text-ink-soft', pending: 'text-ink-soft' }

function Stat({ label, value, hint }) {
  return (
    <div className="panel px-4 py-3" title={hint}>
      <p className="text-sm text-ink-soft">{label}</p>
      <p className="num text-3xl font-semibold">{value}</p>
    </div>
  )
}

export default function PicksTab() {
  const { data, loading, error, reload } = useApi(() => api.adminTips(), [])
  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  const { tips, record } = data

  const act = (fn) => async () => {
    try {
      await fn()
      reload()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Picks" value={`${record.tips}`} />
        <Stat label="Won / lost" value={`${record.won}–${record.lost}`} />
        <Stat label="Profit (units)" value={signed(record.profit_units)} />
        <Stat label="Return on stake" value={pct(record.roi)} />
        <Stat label="Strike rate" value={pct(record.strike_rate, 0)} />
        <Stat
          label="Beat the closing price by"
          value={record.clv == null ? '–' : pct(record.clv)}
          hint={`Average across ${record.clv_samples} picks with a price pull after the pick was made. Consistently positive = genuine edge.`}
        />
      </div>
      <p className="text-sm text-ink-soft">
        To add a pick, open a match and click a price on its odds board. Picks lock at kick-off and settle automatically
        when fixtures and results are next synced. Use the menu below for anything that needs settling by hand.
      </p>
      {tips.length === 0 ? (
        <Empty title="No picks yet">Open an upcoming match from Fixtures to make the first one.</Empty>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-soft">
              <tr>
                <th className="px-4 py-2 font-medium">Match</th>
                <th className="py-2 font-medium">Pick</th>
                <th className="py-2 font-medium text-right">Odds</th>
                <th className="py-2 font-medium text-right">Stake</th>
                <th className="py-2 font-medium px-3">Result</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/5">
              {tips.map((t) => (
                <tr key={t.id}>
                  <td className="px-4 py-2">
                    <Link to={`/match/${t.fixture.id}`} className="font-medium hover:underline">
                      {t.fixture.home.name} v {t.fixture.away.name}
                    </Link>
                    <div className="text-ink-faint">
                      {shortDate(t.fixture.kickoff)}, by {t.author}
                      {!t.published && ', hidden'}
                    </div>
                  </td>
                  <td className="py-2 pr-3">{pickLabel(t, t.fixture)}</td>
                  <td className="py-2 text-right num text-base">{odds(t.odds)}</td>
                  <td className="py-2 text-right num text-base">{t.stake_units}u</td>
                  <td className={`py-2 px-3 capitalize font-semibold ${STATUS_STYLE[t.status]}`}>
                    {t.status}
                    {t.profit_units != null && t.status !== 'void' && ` ${signed(t.profit_units)}u`}
                  </td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    {!t.locked ? (
                      <button type="button" className="text-red font-semibold" onClick={act(() => confirm('Delete this pick?') && api.deleteTip(t.id))}>
                        Delete
                      </button>
                    ) : (
                      <select
                        className="input py-1 w-auto"
                        value={t.status}
                        aria-label="Settle by hand"
                        onChange={(e) => act(() => api.settleTip(t.id, e.target.value))()}
                      >
                        <option value="pending">Pending</option>
                        <option value="won">Won</option>
                        <option value="lost">Lost</option>
                        <option value="void">Void</option>
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
