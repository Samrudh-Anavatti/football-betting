import { useState } from 'react'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { fullDate } from '../../lib/membership.js'
import { Empty, ErrorNote, Loading, SectionHead } from '../ui.jsx'

const amount = (minor, currency) =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency: currency || 'GBP' }).format(minor / 100)

function statusText(m) {
  if (!m.member) return m.status === 'canceled' || m.paid_until ? 'Ended' : 'Never paid'
  if (m.status === 'past_due') return 'Payment failed'
  if (m.cancelling || m.status === 'canceled') return 'Cancelled, access to end of month'
  return 'Active'
}

// Who the members are and where the money comes from. VAT on digital services is owed in the customer's country,
// so each payment keeps the billing address country Whop collected at checkout.
export default function MembersTab() {
  const { data, loading, error } = useApi(() => api.members(), [])
  const [csvError, setCsvError] = useState(null)
  if (loading && !data) return <Loading rows={4} />
  if (error) return <ErrorNote error={error} />
  const download = async () => {
    setCsvError(null)
    try {
      const url = URL.createObjectURL(await api.paymentsCsv())
      Object.assign(document.createElement('a'), { href: url, download: 'payments.csv' }).click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setCsvError(err)
    }
  }
  return (
    <div className="space-y-8">
      {!data.open && (
        <p className="panel p-4 text-sm">
          Membership is closed: Whop isn't connected yet (WHOP_API_KEY, WHOP_WEBHOOK_SECRET and WHOP_PLAN_ID in the
          App Service settings).
        </p>
      )}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <div className="panel px-4 py-3">
          <p className="text-sm text-ink-soft">Accounts</p>
          <p className="num text-3xl font-semibold">{data.signups.length}</p>
        </div>
        <div className="panel px-4 py-3">
          <p className="text-sm text-ink-soft">Joined in the last 7 days</p>
          <p className="num text-3xl font-semibold">{data.signups_week}</p>
        </div>
        <div className="panel px-4 py-3">
          <p className="text-sm text-ink-soft">Paying members now</p>
          <p className="num text-3xl font-semibold">{data.active}</p>
        </div>
      </div>

      <section>
        <SectionHead title="Sign-ups" count={data.signups.length || null} />
        {data.signups.length ? (
          <ol className="panel divide-y divide-ink/5 text-sm">
            {data.signups.map((u) => (
              <li key={u.id} className="px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="font-semibold min-w-0 truncate flex-1 select-all">{u.email}</span>
                {u.member && <span className="text-pitch font-semibold">Paying</span>}
                <span className="num text-ink-soft">
                  {u.created_at ? new Date(u.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'date not recorded'}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <Empty title="No sign-ups yet" />
        )}
        <p className="mt-2 text-sm text-ink-soft">Sign-up asks only for an email and a password, so the email and the time are all we hold.</p>
      </section>

      <section>
        <SectionHead title="Payments by country, last 12 months">
          <button type="button" className="btn-ghost text-sm" onClick={download}>All payments (CSV)</button>
        </SectionHead>
        <ErrorNote error={csvError} />
        {data.by_country.length ? (
          <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-ink-soft text-left">
              <tr>
                <th className="px-4 py-2 font-normal">Country</th>
                <th className="px-4 py-2 font-normal text-right">Payments</th>
                <th className="px-4 py-2 font-normal text-right">Taken</th>
                <th className="px-4 py-2 font-normal text-right">Tax in it</th>
                <th className="px-4 py-2 font-normal text-right" title="Card issued in another country than the billing address">
                  Card elsewhere
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/5 num">
              {data.by_country.map((r) => (
                <tr key={`${r.country}-${r.currency}`}>
                  <td className="px-4 py-2">{r.country || 'Unknown'}</td>
                  <td className="px-4 py-2 text-right">{r.payments}</td>
                  <td className="px-4 py-2 text-right">{amount(r.amount, r.currency)}</td>
                  <td className="px-4 py-2 text-right">{amount(r.tax, r.currency)}</td>
                  <td className="px-4 py-2 text-right">{r.card_elsewhere || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        ) : (
          <Empty title="No payments yet" />
        )}
      </section>

      <section>
        <SectionHead title="Paying members" count={data.members.length || null} />
        {data.members.length ? (
          <ol className="panel divide-y divide-ink/5 text-sm">
            {data.members.map((m) => (
              <li key={m.id} className="px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="font-semibold min-w-0 truncate flex-1">{m.email}</span>
                <span className="text-ink-soft">{statusText(m)}</span>
                <span className="num text-ink-soft">
                  {m.member_since ? `since ${fullDate(m.member_since)}` : ''}
                  {m.paid_until ? `, paid to ${fullDate(m.paid_until)}` : ''}
                </span>
                <span className="num w-12 text-right" title="Billing country">{m.billing_country || '–'}</span>
              </li>
            ))}
          </ol>
        ) : (
          <Empty title="No members yet" />
        )}
      </section>
    </div>
  )
}
