import { openCookieSettings } from '../lib/analytics.js'

const H = ({ children }) => <h2 className="text-xl mt-8 mb-2">{children}</h2>

export default function Privacy() {
  return (
    <article className="max-w-prose text-[15px] leading-relaxed text-ink/85">
      <h1 className="text-3xl sm:text-4xl leading-tight text-ink">Privacy</h1>
      <p className="mt-3">
        Football Predictions AI publishes football picks and match data. You don't need an account to use it. If you
        make one, we keep your email address and password. If you become a member, our payment provider handles your
        card; we never see it. This page explains what we collect and why.
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

      <H>Accounts</H>
      <p>
        An account holds your email address, a scrambled copy of your password (we can't read it), and when the
        account was made. We use your email only to sign you in and to send a password-reset link when you ask for
        one; we don't send marketing or share it with anyone. Reset emails are sent through Microsoft Azure.
      </p>
      <p className="mt-3">
        Signing in stores a login token in your browser so you stay signed in; it's removed when you sign out. You can
        delete your account at any time from the account page, which removes your email address straight away. To stop
        password guessing, our server briefly remembers the IP address of sign-in and reset attempts, in memory only,
        for up to an hour.
      </p>

      <H>Membership payments</H>
      <p>
        Payments are taken by <strong>Stripe</strong>, which collects your card details and billing address on its own
        secure page; we never see or store your card number. Stripe tells us your billing address country, the country
        your card was issued in, and when and how much you paid. We keep these with your account, and keep payment
        records for six years after a payment because tax law requires it (VAT on online services depends on where you
        live); if you delete your account, those records stay without your email address. Stripe keeps its own records
        as described in its privacy policy at stripe.com/privacy.
      </p>

      <H>Contact</H>
      <p>
        Questions about your data, or a request to see or delete it: email{' '}
        <a href="mailto:samrudh.anavatti@gmail.com" className="link">
          samrudh.anavatti@gmail.com
        </a>
        .
      </p>

      <H>Betting</H>
      <p>
        Our picks are opinions, not financial advice. You must be 18 or over to bet. Bet only with money you can
        afford to lose; free, confidential support is available at BeGambleAware.org.
      </p>
    </article>
  )
}
