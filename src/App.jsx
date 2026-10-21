import { useEffect, useMemo, useState } from 'react'
import {
  fetchFires,
  getAvailableYears,
  whereForYear,
} from './api/wildfires.js'
import FireMap from './components/FireMap.jsx'
import StatsPanel from './components/StatsPanel.jsx'
import Filters from './components/Filters.jsx'
import FireList from './components/FireList.jsx'

export default function App() {
  const [years, setYears] = useState([])
  const [year, setYear] = useState(null)

  const [allFires, setAllFires] = useState([]) // all fires for the selected year
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)

  const [county, setCounty] = useState('all')
  const [cause, setCause] = useState('all')
  const [selected, setSelected] = useState(null)

  // Load the list of available years once on mount, default to the newest.
  useEffect(() => {
    let cancelled = false
    getAvailableYears()
      .then((ys) => {
        if (cancelled) return
        setYears(ys)
        setYear(String(ys[0]))
      })
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  // Fetch all fires whenever the selected year changes.
  useEffect(() => {
    if (!year) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setProgress(null)
    setCounty('all')
    setCause('all')
    setSelected(null)

    fetchFires({
      where: whereForYear(year),
      onProgress: (loaded, total) =>
        !cancelled && setProgress({ loaded, total }),
    })
      .then((fires) => {
        if (cancelled) return
        setAllFires(fires)
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [year])

  // Distinct counties/causes for the loaded year, for the filter dropdowns.
  const counties = useMemo(
    () => [...new Set(allFires.map((f) => f.county))].sort(),
    [allFires],
  )
  const causes = useMemo(
    () => [...new Set(allFires.map((f) => f.cause))].sort(),
    [allFires],
  )

  // Apply county + cause filters in memory (fast, no refetch).
  const filtered = useMemo(() => {
    return allFires.filter(
      (f) =>
        (county === 'all' || f.county === county) &&
        (cause === 'all' || f.cause === cause),
    )
  }, [allFires, county, cause])

  return (
    <div className="app">
      <header className="header">
        <span className="flame">🔥</span>
        <h1>Washington Wildfire Monitor</h1>
        <span className="sub">DNR Fire Statistics 2008–present</span>
      </header>

      <div className="layout">
        <aside className="sidebar">
          {error && <div className="error-banner">⚠️ {error}</div>}

          <Filters
            years={years}
            year={year ?? ''}
            onYear={setYear}
            counties={counties}
            county={county}
            onCounty={setCounty}
            causes={causes}
            cause={cause}
            onCause={setCause}
          />

          <StatsPanel fires={filtered} />

          <div>
            <div className="section-title">Largest fires</div>
            <FireList fires={filtered} onSelect={setSelected} />
          </div>

          <div className="legend">
            <div className="section-title">Marker size = acres</div>
            <div className="row">
              <span className="dot" style={{ width: 24, height: 24, background: '#b71c1c' }} />
              1,000+ acres
            </div>
            <div className="row">
              <span className="dot" style={{ width: 18, height: 18, background: '#e53935' }} />
              100–999 acres
            </div>
            <div className="row">
              <span className="dot" style={{ width: 14, height: 14, background: '#fb8c00' }} />
              10–99 acres
            </div>
            <div className="row">
              <span className="dot" style={{ width: 10, height: 10, background: '#fdd835' }} />
              1–9 acres
            </div>
            <div className="row">
              <span className="dot" style={{ width: 8, height: 8, background: '#9ccc65' }} />
              &lt; 1 acre
            </div>
          </div>
        </aside>

        <div className="map-wrap">
          {loading && (
            <div className="loading-overlay">
              <div className="spinner" />
              <div>
                Loading {year} fires
                {progress
                  ? ` — ${progress.loaded.toLocaleString()} / ${progress.total.toLocaleString()}`
                  : '…'}
              </div>
            </div>
          )}
          <FireMap fires={filtered} selected={selected} />
        </div>
      </div>
    </div>
  )
}
