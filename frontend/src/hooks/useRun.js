import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'

// Start a sync (a POST that returns a SyncRun) and poll it every 2s until it finishes.
export function useRun(onDone) {
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef(null)
  const done = useRef(onDone)
  done.current = onDone

  const poll = useCallback((r) => {
    setRun(r)
    if (r.status !== 'running') {
      done.current?.(r)
      return
    }
    timer.current = setTimeout(async () => {
      try {
        poll(await api.syncRun(r.id))
      } catch (e) {
        setError(e)
      }
    }, 2000)
  }, [])

  const start = useCallback(
    async (fn) => {
      setError(null)
      try {
        poll(await fn())
      } catch (e) {
        setError(e)
      }
    },
    [poll],
  )

  useEffect(() => () => clearTimeout(timer.current), [])
  return { run, error, start, busy: run?.status === 'running', resume: poll }
}
