import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to FastAPI
// (API_PROXY=https://api.football-predictions.org to browse live data).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY || 'http://localhost:8000', changeOrigin: true },
    },
  },
})
