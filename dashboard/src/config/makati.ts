// THE PIN. Makati is set here and nowhere else. Every map opens framed on the whole
// city, can't leave it, and "Reset to Makati" returns to that view.
// Order is [lng, lat] (Mapbox order). Mirrored in mobile/lib/config/makati.dart.
export type LngLat = [number, number];

export const MAKATI = {
  center: [121.0244, 14.5546] as LngLat, // middle of the city extent (Ayala / CBD)
  zoom: 12.1, // fallback only: the city across a ~390px phone. The dashboard fits bounds instead.
  minZoom: 11,
  maxZoom: 19,
  // City extent: OSM boundary of Makati (relation 103716) via Nominatim, rounded outwards (~11 m).
  bounds: [
    [120.9987, 14.5296], // south-west
    [121.0501, 14.5796], // north-east
  ] as [LngLat, LngLat],
  // Room (degrees, ~0.45 km) the camera gets beyond the city on every side.
  lockMargin: 0.004,
};

// Mercator plane in degrees: same unit on both axes, so a box's aspect ratio matches the screen's.
const mercY = (lat: number) => (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const mercLat = (y: number) => (360 / Math.PI) * Math.atan(Math.exp((y * Math.PI) / 180)) - 90;

// The camera lock (mapbox maxBounds) for a viewport of width x height px, and also the home view.
// Why not fixed bounds: mapbox zooms in until the viewport fits inside maxBounds in BOTH directions.
// The city is about square, so bounds hugging it never let a wide desktop or a tall phone see all of
// it, and one fixed margin big enough for both (about 10 x 14 km) lets you drag 4 km off the city on
// one of them. So the bounds follow the viewport: the city plus lockMargin, grown only along the short
// axis to the screen's aspect ratio. At the lowest zoom the screen IS the bounds, so nothing drags.
// Recompute on resize.
export function lockBounds(width: number, height: number): [LngLat, LngLat] {
  const [[w, s], [e, n]] = MAKATI.bounds;
  const m = MAKATI.lockMargin;
  let [x0, x1, y0, y1] = [w - m, e + m, mercY(s - m), mercY(n + m)];
  const aspect = width > 0 && height > 0 ? width / height : 4 / 3; // mapbox's 400x300 fallback
  if ((x1 - x0) / (y1 - y0) < aspect) {
    const d = ((y1 - y0) * aspect - (x1 - x0)) / 2;
    [x0, x1] = [x0 - d, x1 + d];
  } else {
    const d = ((x1 - x0) / aspect - (y1 - y0)) / 2;
    [y0, y1] = [y0 - d, y1 + d];
  }
  return [
    [x0, mercLat(y0)],
    [x1, mercLat(y1)],
  ];
}
