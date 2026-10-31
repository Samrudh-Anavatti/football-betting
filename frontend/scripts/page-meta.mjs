// After `vite build`: give each fixed page its own HTML file (dist/history.html is served at /history) with its
// title, description and canonical link already in place, so crawlers and link previews see them without the app.
// Match pages get theirs from functions/match/[id].js.
import { readFileSync, writeFileSync } from 'node:fs'
import { PAGES, canonical } from '../src/lib/seo.js'

const dist = new URL('../dist/', import.meta.url)
const template = readFileSync(new URL('index.html', dist), 'utf8')

const escape = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

for (const [path, { title, description, noindex }] of Object.entries(PAGES)) {
  const html = template
    .replace(/<title>.*?<\/title>/, `<title>${escape(title)}</title>`)
    .replace(/<meta name="description" content=".*?" \/>/, `<meta name="description" content="${escape(description)}" />`)
    .replace(
      '</head>',
      `  <link rel="canonical" href="${canonical(path)}" />\n${noindex ? '    <meta name="robots" content="noindex" />\n' : ''}  </head>`,
    )
  writeFileSync(new URL(path === '/' ? 'index.html' : `${path.slice(1)}.html`, dist), html)
}
console.log(`page-meta: wrote ${Object.keys(PAGES).length} pages`)
