// Data layer for the WA DNR wildfire feature service.
// Source: DNR Fire Statistics 2008-Present (geo.wa.gov dataset
// dabefcb8f03549b49bee7564d4c3c4b5). Served from the public DNR ArcGIS
// MapServer, layer 2. Query API docs:
// https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/

const LAYER_URL =
  'https://gis.dnr.wa.gov/site3/rest/services/Public_Wildfire/WADNR_PUBLIC_WD_WildFire_Data/MapServer/2'

// Fields we care about for the dashboard.
const OUT_FIELDS = [
  'OBJECTID',
  'INCIDENT_NM',
  'COUNTY_LABEL_NM',
  'REGION_NAME',
  'ACRES_BURNED',
  'DSCVR_DT',
  'FIREGCAUSE_LABEL_NM',
  'FIRESCAUSE_LABEL_NM',
  'LAT_COORD',
  'LON_COORD',
].join(',')

// ArcGIS caps a single response at ~2000 records, so we paginate.
const PAGE_SIZE = 2000

function buildQueryUrl(params) {
  const url = new URL(`${LAYER_URL}/query`)
  const defaults = {
    f: 'json',
    outFields: OUT_FIELDS,
    returnGeometry: 'false',
    outSR: '4326',
  }
  Object.entries({ ...defaults, ...params }).forEach(([k, v]) =>
    url.searchParams.set(k, v),
  )
  return url.toString()
}

async function fetchJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`)
  const data = await res.json()
  if (data.error) {
    throw new Error(data.error.message || 'ArcGIS query error')
  }
  return data
}

/**
 * Normalize a raw ArcGIS feature into a flat fire record.
 */
function toFireRecord(feature) {
  const a = feature.attributes
  return {
    id: a.OBJECTID,
    name: a.INCIDENT_NM || 'Unnamed',
    county: a.COUNTY_LABEL_NM || 'Unknown',
    region: a.REGION_NAME || 'Unknown',
    acres: typeof a.ACRES_BURNED === 'number' ? a.ACRES_BURNED : 0,
    discovered: a.DSCVR_DT ? new Date(a.DSCVR_DT) : null,
    year: a.DSCVR_DT ? new Date(a.DSCVR_DT).getFullYear() : null,
    cause: a.FIREGCAUSE_LABEL_NM || 'Unknown',
    specificCause: a.FIRESCAUSE_LABEL_NM || null,
    lat: a.LAT_COORD,
    lon: a.LON_COORD,
  }
}

/**
 * Return the total number of records matching a where clause.
 */
export async function getFireCount(where = '1=1') {
  const url = buildQueryUrl({ where, returnCountOnly: 'true' })
  const data = await fetchJson(url)
  return data.count ?? 0
}

/**
 * Return the list of distinct years that have data, newest first.
 */
export async function getAvailableYears() {
  const url = buildQueryUrl({
    where: 'DSCVR_DT IS NOT NULL',
    outFields: 'DSCVR_DT',
    returnDistinctValues: 'false',
    orderByFields: 'DSCVR_DT DESC',
    resultRecordCount: '1',
  })
  const data = await fetchJson(url)
  const newest = data.features?.[0]?.attributes?.DSCVR_DT
  const maxYear = newest ? new Date(newest).getFullYear() : new Date().getFullYear()
  // Dataset covers 2008-present.
  const years = []
  for (let y = maxYear; y >= 2008; y--) years.push(y)
  return years
}

/**
 * Fetch all fire records matching a where clause, paginating through the
 * service. Returns an array of normalized records with valid coordinates.
 *
 * @param {object} opts
 * @param {string} opts.where  ArcGIS SQL where clause.
 * @param {(loaded:number,total:number)=>void} [opts.onProgress]
 */
export async function fetchFires({ where = '1=1', onProgress } = {}) {
  const total = await getFireCount(where)
  const records = []
  let offset = 0

  while (offset < total) {
    const url = buildQueryUrl({
      where,
      resultOffset: String(offset),
      resultRecordCount: String(PAGE_SIZE),
      orderByFields: 'DSCVR_DT DESC',
    })
    const data = await fetchJson(url)
    const features = data.features || []
    for (const f of features) {
      const rec = toFireRecord(f)
      if (Number.isFinite(rec.lat) && Number.isFinite(rec.lon)) {
        records.push(rec)
      }
    }
    offset += PAGE_SIZE
    if (onProgress) onProgress(Math.min(offset, total), total)
    if (features.length === 0) break // safety: no more data
  }

  return records
}

/**
 * Build a where clause for a given year. The service stores DSCVR_DT as an
 * epoch timestamp; filtering by a date range is the most portable approach.
 */
export function whereForYear(year) {
  if (!year || year === 'all') return '1=1'
  // ArcGIS date literals: TIMESTAMP 'YYYY-MM-DD HH:MM:SS'
  return `DSCVR_DT >= TIMESTAMP '${year}-01-01 00:00:00' AND DSCVR_DT <= TIMESTAMP '${year}-12-31 23:59:59'`
}
