import { Navigate, useSearchParams } from 'react-router-dom'
import AccountsTab from '../components/admin/AccountsTab.jsx'
import AiLabTab from '../components/admin/AiLabTab.jsx'
import AiTab from '../components/admin/AiTab.jsx'
import BundlesTab from '../components/admin/BundlesTab.jsx'
import DataTab from '../components/admin/DataTab.jsx'
import MembersTab from '../components/admin/MembersTab.jsx'
import PicksTab from '../components/admin/PicksTab.jsx'
import { Loading } from '../components/ui.jsx'
import { useAuth } from '../lib/auth.jsx'

const TABS = [
  { key: 'data', label: 'Data', el: DataTab },
  { key: 'picks', label: 'Picks', el: PicksTab },
  { key: 'bundles', label: 'Bundles', el: BundlesTab },
  { key: 'ai', label: 'AI', el: AiTab },
  { key: 'lab', label: 'AI Lab', el: AiLabTab },
  { key: 'accounts', label: 'Accounts', el: AccountsTab },
  { key: 'members', label: 'Members', el: MembersTab },
]

export default function Admin() {
  const { user, checking, logout } = useAuth()
  const [params, setParams] = useSearchParams()
  if (checking) return <Loading />
  if (!user) return <Navigate to="/login?next=/admin" replace />
  if (!user.is_admin) return <Navigate to="/account" replace />

  const active = TABS.find((t) => t.key === params.get('tab')) || TABS[0]
  const Tab = active.el
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-4xl sm:text-5xl leading-none">Admin</h1>
        <nav className="segmented" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-current={t.key === active.key ? 'page' : undefined}
              onClick={() => setParams({ tab: t.key })}
              className={`segment px-4 ${t.key === active.key ? 'segment-on' : ''}`}
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
