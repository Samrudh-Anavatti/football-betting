import { useCallback, useEffect, useState } from 'react'

// Small data-fetching hook: runs `fn` on mount / when deps change,
// tracking loading + error, and exposes `reload()` for manual refresh.
export function useApi(fn, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const memoFn = useCallback(fn, deps) // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await memoFn())
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [memoFn])

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      setError(null)
      // Retry once on a likely-transient failure. Free-tier cold starts and
      // redeploys make the first request after idle fail (502/503/reset); a
      // short retry lets it self-heal instead of surfacing an error.
      for (let attempt = 0; attempt < 2 && alive; attempt++) {
        try {
          const result = await memoFn()
          if (alive) {
            setData(result)
            setError(null)
          }
          break
        } catch (e) {
          const transient = !e.status || e.status >= 500
          if (attempt === 0 && transient) {
            await new Promise((r) => setTimeout(r, 1200))
            continue
          }
          if (alive) setError(e)
        }
      }
      if (alive) setLoading(false)
    })()
    return () => {
      alive = false
    }
  }, [memoFn])

  return { data, loading, error, reload, setData }
}
