function formatDate(d) {
  return d
    ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Unknown'
}

export default function FireList({ fires, onSelect }) {
  // Show the largest fires first — those are what you want to monitor.
  const sorted = [...fires].sort((a, b) => b.acres - a.acres).slice(0, 100)

  if (sorted.length === 0) {
    return <div className="fire-item">No fires match the current filters.</div>
  }

  return (
    <div className="fire-list">
      {sorted.map((f) => (
        <div key={f.id} className="fire-item" onClick={() => onSelect(f)}>
          <div className="name">{f.name}</div>
          <div className="meta">
            {f.acres.toLocaleString()} ac &middot; {f.county} &middot;{' '}
            {formatDate(f.discovered)} &middot; {f.cause}
          </div>
        </div>
      ))}
    </div>
  )
}
