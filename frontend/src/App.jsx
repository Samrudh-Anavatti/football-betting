import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell.jsx'
import Home from './pages/Home.jsx'
import Fixtures from './pages/Fixtures.jsx'
import Match from './pages/Match.jsx'
import Admin from './pages/Admin.jsx'

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/fixtures" element={<Fixtures />} />
        <Route path="/results" element={<Fixtures results />} />
        <Route path="/match/:id" element={<Match />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}
