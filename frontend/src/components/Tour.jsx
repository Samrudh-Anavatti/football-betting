import { Component, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation } from 'react-router-dom'
import { FACE, PORTRAIT, stepsFor, tourKey } from '../lib/tour.js'

// Mr Predictions' welcome. The page dims, one part of it stays lit, and he points at it from a card with a short
// line. A click anywhere (or Enter) moves to the next stop; Escape or Skip ends it. Once per page per visit
// (sessionStorage), and `?tour=1` brings it back for a look. Nothing animates, so three quick clicks clear it.

const SEEN = 'tour:'
const seen = (key) => {
  try {
    return sessionStorage.getItem(SEEN + key) === '1'
  } catch {
    return false
  }
}
const markSeen = (key) => {
  try {
    sessionStorage.setItem(SEEN + key, '1')
  } catch {
    /* private mode: it'll show again next page load */
  }
}

const find = (target) => document.querySelector(`[data-tour="${target}"]`)
const PAD = 8 // the lit area reaches this far past the element
const CARD_W = 352
const GAP = 28

// Where the card goes: beside the lit area when there's room, else under or over it; on phones along the bottom.
function place(rect, vw, vh, phone) {
  if (phone) return { kind: 'bottom' }
  if (rect.height > vh * 0.55) return { kind: 'corner' } // the lit area fills the screen: sit in the corner
  if (rect.right + GAP + CARD_W <= vw - 16) return { kind: 'right', left: rect.right + GAP, top: Math.max(16, Math.min(rect.top, vh - 300)) }
  if (rect.left - GAP - CARD_W >= 16) return { kind: 'left', left: rect.left - GAP - CARD_W, top: Math.max(16, Math.min(rect.top, vh - 300)) }
  if (rect.bottom + GAP + 240 <= vh) return { kind: 'below', left: Math.min(Math.max(16, rect.left), vw - CARD_W - 16), top: rect.bottom + GAP }
  return { kind: 'above', left: Math.min(Math.max(16, rect.left), vw - CARD_W - 16), top: Math.max(16, rect.top - GAP - 240) }
}

function Step({ step, index, count, onNext, onEnd }) {
  const [rect, setRect] = useState(null)
  const [card, setCard] = useState(null)
  const cardRef = useRef(null)
  const nextRef = useRef(null)
  const phone = typeof window !== 'undefined' && window.innerWidth < 768

  // Bring the element into view, then follow it: scrolls, resizes, and the page growing as its data lands
  // (no event fires for that, so the page's size is watched and there's a slow re-measure as a backstop).
  useLayoutEffect(() => {
    const el = find(step.target)
    if (!el) return undefined
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.55
    el.scrollIntoView({ block: phone || tall ? 'start' : 'center', behavior: 'instant' })
    if (phone || tall) window.scrollBy(0, -12)
    const measure = () => {
      const r = el.getBoundingClientRect()
      setRect((old) => {
        const next = { left: r.left - PAD, top: r.top - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD, right: r.right + PAD, bottom: r.bottom + PAD }
        return old && Object.keys(next).every((k) => old[k] === next[k]) ? old : next
      })
    }
    measure()
    window.addEventListener('scroll', measure, true)
    window.addEventListener('resize', measure)
    const grow = new ResizeObserver(measure)
    grow.observe(document.body)
    const backstop = setInterval(measure, 300)
    return () => {
      window.removeEventListener('scroll', measure, true)
      window.removeEventListener('resize', measure)
      grow.disconnect()
      clearInterval(backstop)
    }
  }, [step.target, phone])

  // The card's own box, for the arrow; only stored when it has actually moved, or this would loop.
  useLayoutEffect(() => {
    const r = cardRef.current?.getBoundingClientRect()
    if (!r) return
    if (card && card.left === r.left && card.top === r.top && card.width === r.width && card.height === r.height) return
    setCard({ left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height })
  })

  useEffect(() => {
    nextRef.current?.focus({ preventScroll: true })
  }, [step.target])

  if (!rect) return null
  const vw = window.innerWidth
  const vh = window.innerHeight
  const pos = place(rect, vw, vh, phone)
  const style =
    pos.kind === 'bottom' ? { left: 12, right: 12, bottom: 12 }
    : pos.kind === 'corner' ? { right: 24, bottom: 24, width: CARD_W }
    : { left: pos.left, top: pos.top, width: CARD_W }

  // The arrow: from the card's nearest edge to the lit area's nearest edge, with a little bend.
  let arrow = null
  if (card) {
    const cx = Math.max(rect.left, Math.min(card.left + card.width / 2, rect.right))
    const cy = Math.max(rect.top, Math.min(card.top + card.height / 2, rect.bottom))
    const from = {
      x: Math.max(card.left, Math.min(cx, card.right)),
      y: Math.max(card.top, Math.min(cy, card.bottom)),
    }
    const to = { x: cx, y: cy }
    const dx = to.x - from.x
    const dy = to.y - from.y
    if (Math.hypot(dx, dy) > 24) {
      const mx = (from.x + to.x) / 2 - dy * 0.2
      const my = (from.y + to.y) / 2 + dx * 0.2
      arrow = `M${from.x} ${from.y} Q${mx} ${my} ${to.x} ${to.y}`
    }
  }

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="A quick welcome" onClick={onNext}>
      {/* The lit area: its shadow is what dims everything else. */}
      <div
        aria-hidden
        className="pointer-events-none fixed rounded-xl ring-2 ring-amber"
        style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height, boxShadow: '0 0 0 200vmax rgba(10, 22, 40, 0.72)' }}
      />
      {arrow && (
        <svg aria-hidden className="pointer-events-none fixed inset-0 h-full w-full" width={vw} height={vh}>
          <defs>
            <marker id="tour-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
              <path d="M0 0 L8 4 L0 8 z" fill="#F2B705" />
            </marker>
          </defs>
          <path d={arrow} fill="none" stroke="#F2B705" strokeWidth="3" strokeLinecap="round" markerEnd="url(#tour-arrowhead)" />
        </svg>
      )}
      <div ref={cardRef} className="fixed" style={style}>
        <div className="flex items-end gap-3">
          {!phone && (
            <img src={step.image || PORTRAIT} alt="" width="120" height="160" className="h-40 w-[7.5rem] shrink-0 rounded-xl object-cover object-top ring-2 ring-amber shadow-slip" />
          )}
          <div className="panel shadow-lift min-w-0 flex-1 p-4 sm:p-5">
            <div className="flex items-start gap-3">
              {phone && <img src={step.image || FACE} alt="" width="56" height="56" className="h-14 w-14 shrink-0 rounded-full object-cover ring-2 ring-amber" />}
              <div className="min-w-0">
                <p className="font-display text-xs font-bold uppercase tracking-wider text-amber-dark">Mr Predictions</p>
                <p className="mt-1 text-[15px] leading-snug">{step.text}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <button ref={nextRef} type="button" className="btn-primary py-1.5 text-sm" onClick={onNext}>
                {index + 1 < count ? 'Next' : 'Got it'}
              </button>
              {count > 1 && (
                <span className="num text-xs text-ink-soft">
                  {index + 1} of {count}
                </span>
              )}
              {index + 1 < count && (
                <button
                  type="button"
                  className="ml-auto text-sm text-ink-soft underline underline-offset-4 hover:text-ink"
                  onClick={(e) => {
                    e.stopPropagation()
                    onEnd()
                  }}
                >
                  Skip
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// A bug in the welcome must never take the site down with it: it just doesn't show.
class Quiet extends Component {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

export default function Tour() {
  return (
    <Quiet>
      <TourInner />
    </Quiet>
  )
}

function TourInner() {
  const { pathname, search } = useLocation()
  const [run, setRun] = useState(null) // { key, steps, i }

  useEffect(() => {
    const key = tourKey(pathname)
    const steps = stepsFor(pathname)
    const force = new URLSearchParams(search).get('tour') === '1'
    setRun(null)
    if (!steps.length || (seen(key) && !force)) return undefined
    // The page's data lands after the route does: wait for the first stop to exist (up to 5 s, then start with
    // whatever stops there are, or none).
    let tries = 0
    let timer
    const start = () => {
      tries += 1
      if (find(steps[0].target) || (tries >= 50 && steps.some((s) => find(s.target)))) setRun({ key, steps, i: 0 })
      else if (tries < 50) timer = setTimeout(start, 100)
    }
    start()
    return () => clearTimeout(timer)
  }, [pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!run) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') end()
      else if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowRight') {
        e.preventDefault()
        next()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // A stop whose anchor has disappeared since it was chosen is passed over.
  useEffect(() => {
    if (run && !find(run.steps[run.i].target)) next()
  })

  if (!run) return null
  const end = () => {
    markSeen(run.key)
    setRun(null)
  }
  // Stops whose anchor isn't on the page (no open picks, say) are passed over.
  const next = () => {
    let i = run.i + 1
    while (i < run.steps.length && !find(run.steps[i].target)) i += 1
    if (i >= run.steps.length) end()
    else setRun({ ...run, i })
  }
  const live = run.steps.filter((s) => find(s.target))
  const step = run.steps[run.i]
  if (!find(step.target)) return null // the stop has gone (data re-rendered): the effect below moves on
  return createPortal(
    <Step step={step} index={live.indexOf(step)} count={live.length} onNext={next} onEnd={end} />,
    document.body,
  )
}
