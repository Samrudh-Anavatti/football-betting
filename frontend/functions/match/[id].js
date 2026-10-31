// Cloudflare Pages Function for /match/<teams>-<id>: serves the app's HTML with this match's title, description and
// canonical link written in, so search engines and link previews see them. The app takes over in the browser.
// Any other address for the match (the old /match/<id>, misspelt teams) gets a permanent redirect to its own one.
import { API_URL, canonical, matchIdFrom, matchMeta, matchPath } from '../../src/lib/seo.js'

export async function onRequestGet({ request, params, env }) {
  const page = await env.ASSETS.fetch(new URL('/', request.url))
  const url = new URL(request.url)
  const id = matchIdFrom(String(params.id))
  if (!id) return page

  let data = null
  let status = 200
  try {
    // Cached at Cloudflare for 10 minutes (a 404 for one); a slow API never holds the page up for more than 2 s.
    const res = await fetch(`${API_URL}/matches/${id}/meta`, {
      cf: { cacheTtlByStatus: { '200-299': 600, 404: 60, '500-599': 0 }, cacheEverything: true },
      signal: AbortSignal.timeout(2000),
    })
    if (res.status === 404) status = 404
    else if (res.ok) data = await res.json()
  } catch {
    // API down or slow: the page still works, it just carries the site's default title.
  }

  const path = data ? matchPath(data.fixture) : url.pathname
  if (data && url.pathname !== path) return Response.redirect(new URL(path + url.search, url), 301)

  const rewriter = new HTMLRewriter().on('link[rel="canonical"]', {
    element: (el) => el.setAttribute('href', canonical(path)),
  })
  if (data) {
    const meta = matchMeta(data.fixture, data.tips)
    rewriter
      .on('title', { element: (el) => el.setInnerContent(meta.title) })
      .on('meta[name="description"]', { element: (el) => el.setAttribute('content', meta.description) })
  }
  if (status === 404) {
    rewriter.on('head', { element: (el) => el.append('<meta name="robots" content="noindex" />', { html: true }) })
  }
  return rewriter.transform(new Response(page.body, { status, headers: page.headers }))
}
