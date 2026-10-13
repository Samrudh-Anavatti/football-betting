import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base` is set at build time for GitHub Pages project sites (e.g. /TT-App/).
// Locally it defaults to '/', and the dev server proxies /api to FastAPI
// (API_PROXY=https://football-betting-api-sa.azurewebsites.net to browse live data).
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY || 'http://localhost:8000', changeOrigin: true },
    },
  },
})
