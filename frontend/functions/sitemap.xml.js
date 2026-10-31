// The sitemap search engines read: the fixed pages plus every match from the last 30 days and the next 14,
// each at its own address (/match/<teams>-<id>). Built from GET /sitemap and cached for an hour.
import { API_URL, PAGES, canonical, matchPath } from '../src/lib/seo.js'

export async function onRequest() {
  let matches = []
  try {
    const res = await fetch(`${API_URL}/sitemap`, {
      cf: { cacheTtlByStatus: { '200-299': 3600, '400-599': 0 }, cacheEverything: true },
      signal: AbortSignal.timeout(5000),
    })
    if (res.ok) matches = await res.json()
  } catch {
    // API down: the sitemap still lists the fixed pages.
  }
  const pages = Object.keys(PAGES).filter((path) => !PAGES[path].noindex)
  const xml =
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    [...pages, ...matches.map(matchPath)].map((path) => `  <url><loc>${canonical(path)}</loc></url>`).join('\n') +
    '\n</urlset>\n'
  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': 'public, max-age=3600' },
  })
}
