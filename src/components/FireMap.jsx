import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'

// Color + radius scale based on acres burned.
function fireStyle(acres) {
  if (acres >= 1000) return { color: '#b71c1c', radius: 12 }
  if (acres >= 100) return { color: '#e53935', radius: 9 }
  if (acres >= 10) return { color: '#fb8c00', radius: 7 }
  if (acres >= 1) return { color: '#fdd835', radius: 5 }
  return { color: '#9ccc65', radius: 4 }
}

function formatDate(d) {
  return d ? d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : 'Unknown'
}

// Pans/zooms the map when a fire is selected from the list.
function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], 11, { duration: 0.8 })
  }, [target, map])
  return null
}

export default function FireMap({ fires, selected }) {
  // Render at most a sane number of markers for performance.
  const MAX_MARKERS = 4000
  const shown = fires.length > MAX_MARKERS ? fires.slice(0, MAX_MARKERS) : fires

  return (
    <MapContainer center={[47.4, -120.5]} zoom={7} className="map" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      <FlyTo target={selected} />
      {shown.map((f) => {
        const s = fireStyle(f.acres)
        return (
          <CircleMarker
            key={f.id}
            center={[f.lat, f.lon]}
            radius={s.radius}
            pathOptions={{ color: s.color, fillColor: s.color, fillOpacity: 0.6, weight: 1 }}
          >
            <Popup>
              <b>{f.name}</b>
              <br />
              {f.county} County &middot; {f.region}
              <br />
              {f.acres.toLocaleString()} acres
              <br />
              Cause: {f.cause}
              <br />
              Discovered: {formatDate(f.discovered)}
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
