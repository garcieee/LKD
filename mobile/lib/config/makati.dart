// THE PIN. Makati is set here and nowhere else. The map opens framed on the whole
// city, can't leave it, and "Reset to Makati" returns to that view.
// Mirrors dashboard/src/config/makati.ts: change both together.
class Makati {
  static const double lat = 14.5546; // middle of the city extent (Ayala / CBD)
  static const double lng = 121.0244;
  static const double zoom = 12.1; // fallback only: the city across a ~390px phone
  static const double minZoom = 11;
  static const double maxZoom = 19;

  // City extent: OSM boundary of Makati (relation 103716) via Nominatim, rounded outwards (~11 m).
  static const double south = 14.5296;
  static const double west = 120.9987;
  static const double north = 14.5796;
  static const double east = 121.0501;

  // Room (degrees, ~0.45 km) the camera gets beyond the city on every side.
  // The dashboard's mapbox-gl zooms in until the screen fits inside maxBounds, so bounds hugging
  // the city can't show all of it on a screen of another shape. It grows south/west/north/east
  // plus this margin along the short axis to the screen's aspect ratio (Mercator space): see
  // lockBounds() in the dashboard file. Native camera bounds may constrain only the camera
  // centre instead: check on a device.
  static const double lockMargin = 0.004;
}
