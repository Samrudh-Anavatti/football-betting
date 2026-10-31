import { useEffect } from 'react'
import { canonical } from '../lib/seo.js'

function tag(selector, create) {
  let el = document.head.querySelector(selector)
  if (!el) {
    el = create()
    document.head.appendChild(el)
  }
  return el
}

// Keeps the title, description and canonical link in step with the page as people move around the app.
// The first load already has them in its HTML (the build for fixed pages, the function for matches).
export default function usePageMeta(meta, path) {
  const { title, description, noindex } = meta || {}
  useEffect(() => {
    if (!title) return
    document.title = title
    tag('meta[name="description"]', () => Object.assign(document.createElement('meta'), { name: 'description' }))
      .content = description
    tag('link[rel="canonical"]', () => Object.assign(document.createElement('link'), { rel: 'canonical' }))
      .href = canonical(path)
    const robots = document.head.querySelector('meta[name="robots"]')
    if (noindex && !robots) document.head.appendChild(Object.assign(document.createElement('meta'), { name: 'robots', content: 'noindex' }))
    if (!noindex && robots) robots.remove()
  }, [title, description, noindex, path])
}
