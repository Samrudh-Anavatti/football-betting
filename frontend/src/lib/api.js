// Thin API client. In dev, VITE_API_URL is unset and calls hit /api/v1
// (proxied to FastAPI). In prod it's the deployed backend base URL.
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'
const TOKEN_KEY = 'fb.token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(t) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode: stay signed in for this tab only */
  }
}

async function request(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join('; ') : j.detail || detail
    } catch {
      /* non-JSON error */
    }
    const err = new Error(detail)
    err.status = res.status
    if (res.status === 401 && token) setToken(null)
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

function qs(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') continue
    for (const x of Array.isArray(v) ? v : [v]) sp.append(k, x)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // public
  leagues: () => request('/leagues'),
  fixtures: (params = {}) => request(`/fixtures${qs(params)}`),
  match: (id) => request(`/matches/${id}`),
  tips: (status = 'open') => request(`/tips${qs({ status })}`),
  record: () => request('/record'),

  // auth
  login: (username, password) => request('/auth/login', { method: 'POST', body: { username, password } }),
  me: () => request('/auth/me'),

  // integrations
  integrations: () => request('/admin/integrations'),
  checkQuota: (provider) => request(`/admin/integrations/${provider}/check`, { method: 'POST' }),
  syncRuns: (limit = 30) => request(`/admin/sync-runs${qs({ limit })}`),
  syncRun: (id) => request(`/admin/sync-runs/${id}`),
  syncFixtures: (body) => request('/admin/sync/fixtures', { method: 'POST', body }),
  syncOdds: (body) => request('/admin/sync/odds', { method: 'POST', body }),
  refreshContext: (id) => request(`/admin/matches/${id}/context`, { method: 'POST' }),
  refreshMatchOdds: (id, body) => request(`/admin/matches/${id}/odds`, { method: 'POST', body }),
  syncMarkets: (body) => request('/admin/sync/markets', { method: 'POST', body }),
  refreshMatchMarkets: (id) => request(`/admin/matches/${id}/markets`, { method: 'POST' }),
  refreshLineups: (id) => request(`/admin/matches/${id}/lineups`, { method: 'POST' }),

  // AI
  matchAi: (id) => request(`/admin/matches/${id}/ai`),
  analyse: (id) => request(`/admin/matches/${id}/ai`, { method: 'POST' }),
  chatAi: (threadId, text) => request(`/admin/ai/threads/${threadId}/messages`, { method: 'POST', body: { text } }),
  aiSummary: () => request('/admin/ai/summary'),

  // tips + accounts
  adminTips: (source = 'ivo') => request(`/admin/tips${qs({ source })}`),
  createTip: (body) => request('/admin/tips', { method: 'POST', body }),
  deleteTip: (id) => request(`/admin/tips/${id}`, { method: 'DELETE' }),
  settleTip: (id, status) => request(`/admin/tips/${id}/settle`, { method: 'POST', body: { status } }),
  accounts: () => request('/admin/accounts'),
  createBet: (body) => request('/admin/bets', { method: 'POST', body }),
  deleteBet: (id) => request(`/admin/bets/${id}`, { method: 'DELETE' }),
  setBankroll: (starting_bankroll) => request('/admin/accounts/me', { method: 'PUT', body: { starting_bankroll } }),
}
