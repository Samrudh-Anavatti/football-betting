import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Shell from './components/Shell.jsx'
import Home from './pages/Home.jsx'
import Fixtures from './pages/Fixtures.jsx'
import Match from './pages/Match.jsx'
import History from './pages/History.jsx'
import Privacy from './pages/Privacy.jsx'
import Membership from './pages/Membership.jsx'
import Terms from './pages/Terms.jsx'
import Friends from './pages/Friends.jsx'
import Staking from './pages/Staking.jsx'
import ConsentBanner from './components/ConsentBanner.jsx'
import Tour from './components/Tour.jsx'
import Admin from './pages/Admin.jsx'
import Account from './pages/Account.jsx'
import AiLab from './pages/AiLab.jsx'
import { Forgot, Login, Reset, Signup } from './pages/Auth.jsx'
import usePageMeta from './hooks/usePageMeta.js'
import { PAGES } from './lib/seo.js'

// Fixed pages' titles; a match page sets its own once the match has loaded.
function StaticMeta() {
  const { pathname } = useLocation()
  usePageMeta(PAGES[pathname], pathname)
  return null
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/fixtures" element={<Fixtures />} />
        <Route path="/results" element={<Fixtures results />} />
        <Route path="/history" element={<History />} />
        <Route path="/staking" element={<Staking />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/membership" element={<Membership />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/friends" element={<Friends />} />
        <Route path="/match/:slug" element={<Match />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot" element={<Forgot />} />
        <Route path="/reset" element={<Reset />} />
        <Route path="/account" element={<Account />} />
        <Route path="/ai-lab" element={<AiLab />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <StaticMeta />
      <ConsentBanner />
      <Tour />
    </Shell>
  )
}
