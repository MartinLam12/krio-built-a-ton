export default function Filters({
  years,
  year,
  onYear,
  counties,
  county,
  onCounty,
  causes,
  cause,
  onCause,
}) {
  return (
    <div className="filters">
      <label htmlFor="year">Year</label>
      <select id="year" value={year} onChange={(e) => onYear(e.target.value)}>
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>

      <label htmlFor="county">County</label>
      <select id="county" value={county} onChange={(e) => onCounty(e.target.value)}>
        <option value="all">All counties</option>
        {counties.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <label htmlFor="cause">Cause</label>
      <select id="cause" value={cause} onChange={(e) => onCause(e.target.value)}>
        <option value="all">All causes</option>
        {causes.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </div>
  )
}
