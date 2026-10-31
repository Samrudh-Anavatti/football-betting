import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './lib/auth.jsx'
import './index.css'

// Links from before the move to Cloudflare Pages (2026-10-31) used hash URLs (/#/match/123): move them to the real path.
if (location.hash.startsWith('#/')) history.replaceState(null, '', location.hash.slice(1))

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
