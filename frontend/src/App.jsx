import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Shell from './components/Shell.jsx'
import Home from './pages/Home.jsx'
import Fixtures from './pages/Fixtures.jsx'
import Match from './pages/Match.jsx'
import History from './pages/History.jsx'
import Privacy from './pages/Privacy.jsx'
import Friends from './pages/Friends.jsx'
import ConsentBanner from './components/ConsentBanner.jsx'
import Admin from './pages/Admin.jsx'
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
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/friends" element={<Friends />} />
        <Route path="/match/:id" element={<Match />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <StaticMeta />
      <ConsentBanner />
    </Shell>
  )
}
