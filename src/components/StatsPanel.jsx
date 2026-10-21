function topBy(fires, key) {
  const counts = {}
  for (const f of fires) {
    const v = f[key] || 'Unknown'
    counts[v] = (counts[v] || 0) + 1
  }
  let best = null
  let bestN = -1
  for (const [k, n] of Object.entries(counts)) {
    if (n > bestN) {
      best = k
      bestN = n
    }
  }
  return best ? `${best} (${bestN})` : '—'
}

export default function StatsPanel({ fires }) {
  const total = fires.length
  const totalAcres = fires.reduce((sum, f) => sum + f.acres, 0)
  const biggest = fires.reduce(
    (max, f) => (f.acres > (max?.acres ?? -1) ? f : max),
    null,
  )
  const topCause = topBy(fires, 'cause')

  return (
    <div className="stats">
      <div className="stat">
        <div className="value">{total.toLocaleString()}</div>
        <div className="label">Fires</div>
      </div>
      <div className="stat">
        <div className="value">
          {Math.round(totalAcres).toLocaleString()}
        </div>
        <div className="label">Acres burned</div>
      </div>
      <div className="stat wide">
        <div className="value">
          {biggest ? `${biggest.name} — ${biggest.acres.toLocaleString()} ac` : '—'}
        </div>
        <div className="label">Largest fire</div>
      </div>
      <div className="stat wide">
        <div className="value">{topCause}</div>
        <div className="label">Most common cause</div>
      </div>
    </div>
  )
}
