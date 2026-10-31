// Google Analytics 4 behind a consent banner, using Google's Consent Mode v2. Until a
// visitor accepts, analytics_storage is "denied": GA sets no cookies and only sends
// cookieless pings, which Google uses to estimate totals. Ads features are always off.
// Live site only, so local development doesn't land in the reports.
const GA_ID = 'G-MDK0G2HH7M'
const KEY = 'analytics-consent' // 'granted' | 'denied'; missing = not asked yet
const enabled = import.meta.env.PROD

window.dataLayer = window.dataLayer || []
function gtag() {
  // gtag.js expects the arguments object itself, not an array.
  window.dataLayer.push(arguments) // eslint-disable-line prefer-rest-params
}

export function storedConsent() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

let started = false
export function startAnalytics() {
  if (!enabled || started) return
  started = true
  gtag('consent', 'default', {
    analytics_storage: storedConsent() === 'granted' ? 'granted' : 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
  })
  gtag('js', new Date())
  // Page views are sent by trackPage on every route change, with the real path.
  gtag('config', GA_ID, { send_page_view: false })
  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`
  document.head.appendChild(s)
}

export function setConsent(value) {
  try {
    localStorage.setItem(KEY, value)
  } catch {
    // Private mode etc.: the choice holds for this visit only.
  }
  gtag('consent', 'update', { analytics_storage: value })
  if (value === 'denied') clearGaCookies()
}

// Withdrawing consent removes the cookies GA set while it was allowed.
function clearGaCookies() {
  const host = location.hostname
  for (const c of document.cookie.split(';')) {
    const name = c.split('=')[0].trim()
    if (name === '_ga' || name.startsWith('_ga_')) {
      for (const domain of ['', `; domain=${host}`, `; domain=.${host.replace(/^www\./, '')}`]) {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain}`
      }
    }
  }
}

// Sent by hand on every route change: GA's own page view only fires on full page loads.
export function trackPage(path) {
  if (!enabled) return
  gtag('event', 'page_view', { page_location: location.origin + path, page_title: document.title })
}

export const OPEN_SETTINGS = 'open-cookie-settings'
export const openCookieSettings = () => window.dispatchEvent(new Event(OPEN_SETTINGS))
