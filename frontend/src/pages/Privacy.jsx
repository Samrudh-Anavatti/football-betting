import { openCookieSettings } from '../lib/analytics.js'

const H = ({ children }) => <h2 className="text-xl mt-8 mb-2">{children}</h2>

export default function Privacy() {
  return (
    <article className="max-w-prose text-[15px] leading-relaxed text-ink/85">
      <h1 className="text-3xl sm:text-4xl leading-tight text-ink">Privacy</h1>
      <p className="mt-3">
        Football Predictions AI publishes football picks and match data. You don't need an account to use it, and we
        don't ask for your name, email or payment details. This page explains the little we do collect.
      </p>

      <H>Analytics</H>
      <p>
        <strong>Cloudflare Web Analytics</strong> counts visits to every page. It sets no cookies and doesn't
        identify you: we see totals such as page views, the site that referred you, country and browser type.
      </p>
      <p className="mt-3">
        <strong>Google Analytics</strong> helps us see which pages people use and how they move around the site. It
        sets cookies (<code>_ga</code> and <code>_ga_MDK0G2HH7M</code>, kept for up to two years) only if you choose
        Accept. It records the pages you view, roughly where you are (country and city), your device and browser, and
        how you arrived. Google doesn't store your IP address in Analytics. We don't use it for advertising and don't
        share the data with anyone else. If you choose Reject, no Google Analytics cookies are set; Google may still
        receive a basic, cookie-free signal that a page was viewed, with no identifier attached.
      </p>
      <p className="mt-3">
        <button type="button" className="link font-semibold" onClick={openCookieSettings}>
          Change your cookie settings
        </button>
      </p>

      <H>Signing in</H>
      <p>
        Only our team signs in. Signing in stores a login token in your browser so you stay signed in; it's removed
        when you sign out.
      </p>

      <H>Betting</H>
      <p>
        Our picks are opinions, not financial advice. You must be 18 or over to bet. Bet only with money you can
        afford to lose; free, confidential support is available at BeGambleAware.org.
      </p>
    </article>
  )
}
