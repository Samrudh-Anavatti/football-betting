import JoinCard from './JoinCard.jsx'

// A whole page that needs a free account: its title, what it is, and the way in.
export default function SignUpWall({ heading, title, children }) {
  return (
    <section className="space-y-6">
      <h1 className="text-4xl sm:text-5xl leading-none">{heading}</h1>
      <JoinCard title={title} className="max-w-xl">{children}</JoinCard>
    </section>
  )
}
