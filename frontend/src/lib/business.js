// Who sells the membership: shown on the terms and privacy pages. Fill in from Ivo's company details before
// membership opens (HANDOFF.md, "Membership"). Until `name` is set, the pages say the details are coming.
export const BUSINESS = {
  name: null, // registered company name, e.g. "Example Ltd"
  number: null, // Companies House number
  address: null, // registered office, one line
  vat: null, // VAT number, once registered
  email: 'samrudh.anavatti@gmail.com', // contact for terms, refunds and data requests
}

// Price in a currency's minor units (pence) as text: 399 GBP -> "£3.99".
export function formatPrice(price) {
  if (!price) return null
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency: price.currency.toUpperCase() }).format(price.amount / 100)
}
