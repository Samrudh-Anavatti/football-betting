// Sites we recommend, linked from the footer. They link back to us; add a friend with one entry here.
const FRIENDS = [
  {
    name: 'MaTips',
    url: 'https://matips.net/',
    blurb:
      "Free daily predictions for the result and over/under 2.5 goals, worked out from each team's scoring record " +
      'with a Poisson model.',
  },
]

export default function Friends() {
  return (
    <article className="max-w-prose">
      <h1 className="text-3xl sm:text-4xl leading-tight">Football Friends</h1>
      <p className="mt-3 text-[15px] leading-relaxed text-ink/85">
        A short list of football sites run by people we know and rate. They're independent of us, so their tips are
        their own.
      </p>
      <ul className="mt-6 space-y-3">
        {FRIENDS.map((f) => (
          <li key={f.url}>
            <a
              href={f.url}
              target="_blank"
              rel="noopener"
              className="panel group block p-5 transition hover:shadow-lift"
            >
              <span className="flex items-baseline gap-3">
                <span className="font-display text-xl font-extrabold">{f.name}</span>
                <span className="text-sm text-ink-faint">{new URL(f.url).hostname}</span>
              </span>
              <span className="mt-1.5 block text-[15px] leading-relaxed text-ink/85">{f.blurb}</span>
              <span className="mt-3 inline-block text-sm link group-hover:decoration-ink">
                Open site <span aria-hidden>↗</span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </article>
  )
}
