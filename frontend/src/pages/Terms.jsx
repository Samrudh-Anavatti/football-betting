import { Link } from 'react-router-dom'
import { BUSINESS } from '../lib/business.js'

// A plain-English draft for the business to review before membership opens; not legal advice.
const H = ({ children }) => <h2 className="text-xl mt-8 mb-2">{children}</h2>

function Operator() {
  if (!BUSINESS.name) return <>the business behind it (its details will appear here before membership opens)</>
  return (
    <>
      <strong>{BUSINESS.name}</strong>
      {BUSINESS.number && <>, a company registered in England and Wales (number {BUSINESS.number})</>}
      {BUSINESS.address && <>, of {BUSINESS.address}</>}
      {BUSINESS.vat && <>, VAT number {BUSINESS.vat}</>}
    </>
  )
}

export default function Terms() {
  return (
    <article className="max-w-prose text-[15px] leading-relaxed text-ink/85">
      <h1 className="text-3xl sm:text-4xl leading-tight text-ink">Terms</h1>
      <p className="mt-3">
        These terms cover using Football Predictions AI and paying for membership. The site is run by <Operator />
        ("we", "us"). By making an account or joining, you agree to them.
      </p>

      <H>What we offer</H>
      <p>
        Our picks, odds, statistics and AI match analysis are free to read. Members also get our staking plan (see{' '}
        <Link to="/membership" className="link">membership</Link>). Everything on the site is our opinion and general
        information. It isn't financial advice, and we don't take bets or hold money for anyone.
      </p>

      <H>No guarantees</H>
      <p>
        Football is unpredictable. Picks lose, staking plans have losing runs, and you can lose money following us. Past
        results don't mean future ones. Decide your own stakes and bet only what you can afford to lose. Prices on the
        site come from bookmakers through a data provider and can be out of date, so check them before you bet.
      </p>

      <H>Who can use it</H>
      <p>
        You must be 18 or over, and you're responsible for making sure betting is legal where you live. Keep your
        password to yourself; a membership is for one person. We may close an account that's used to copy or resell our
        content, shared, or used to attack the site. If we close a paid account for any other reason, we refund the rest
        of the month.
      </p>

      <H>Membership and payment</H>
      <p>
        Membership is a monthly subscription at the price shown when you join, taken by our payment provider, Stripe.
        It renews automatically each month on the day you joined until you cancel. Prices include any VAT we have to
        charge. If we change the price, we'll email you at least 30 days before it applies to you, and you can cancel
        before then.
      </p>

      <H>Cancelling</H>
      <p>
        Cancel any time from your <Link to="/account" className="link">account page</Link>. You keep access until the
        end of the month you've paid for and won't be charged again. We don't refund part-months, except as set out in
        these terms or where the law says we must.
      </p>
      <p className="mt-3">
        <strong>Your 14-day right to cancel.</strong> If you're a consumer in the UK or the EU, you normally have 14
        days to cancel an online purchase for a full refund. Membership gives you access straight away, so when you
        join we ask you to agree to it starting at once and to confirm you understand that you lose this right once it
        starts. If you didn't agree to that, you can cancel within 14 days of joining for a full refund.
      </p>

      <H>If a payment fails</H>
      <p>
        Stripe will try again over the following days and email you so you can update your card. You keep access for 3
        days after the end of your paid month while that happens. If no payment goes through, membership ends.
      </p>

      <H>Refunds and chargebacks</H>
      <p>
        If something has gone wrong, contact us first and we'll put it right; a refund ends the membership it's for. If
        a payment is disputed with your bank, the membership ends while the dispute is open.
      </p>

      <H>Our responsibility to you</H>
      <p>
        We provide the site with reasonable care and skill. We aren't responsible for bets you place, or for losses that
        come from them, or for the site being unavailable for a while. Nothing in these terms limits your legal rights
        as a consumer, or our liability where the law doesn't allow it to be limited. If we let you down, our liability
        is limited to what you've paid us in the last 12 months.
      </p>

      <H>Changes</H>
      <p>
        We may update these terms. If a change matters to members, we'll email you before it applies; carrying on after
        that means you accept it, and you can cancel if you don't.
      </p>

      <H>Law</H>
      <p>
        These terms are governed by the law of England and Wales. If you live elsewhere in the UK or in the EU, you keep
        the protections of your own country's consumer law and can bring a claim there.
      </p>

      <H>Contact</H>
      <p>
        Questions, refunds or complaints:{' '}
        <a href={`mailto:${BUSINESS.email}`} className="link">
          {BUSINESS.email}
        </a>
        . Free, confidential support with gambling is available at BeGambleAware.org.
      </p>
    </article>
  )
}
