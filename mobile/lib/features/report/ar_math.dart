// Geometry for the report camera's AR overlay. Plain Dart, so test/ar_math_test.dart runs without a
// device. Angles are degrees clockwise from north, distances metres.
import 'dart:math' as math;

import '../../config/makati.dart';

// ponytail: an assumed horizontal field of view for a phone's main camera. It differs per phone, and
// the full-screen preview crops some of it away, so a chip can sit a little off its hazard. Tune it
// on a device: stand ~50 m from a filed report and turn until the chip covers it. Upgrade: work it
// out from the lens focal length and sensor size (Camera2 characteristics, via a platform channel).
const fovDeg = 60.0;

/// How far around the camera to show reports that are already filed.
const nearbyM = 150.0;

/// How far past the city edge the server still takes a report (MARGIN in server/app/routers/reports.py).
const cityMarginDeg = 0.004;

const _earthM = 6371008.8; // mean Earth radius

double _rad(double deg) => deg * math.pi / 180;

/// Great-circle distance (haversine).
double distanceM(double lat1, double lng1, double lat2, double lng2) {
  final dLat = math.sin(_rad(lat2 - lat1) / 2);
  final dLng = math.sin(_rad(lng2 - lng1) / 2);
  final a = dLat * dLat + math.cos(_rad(lat1)) * math.cos(_rad(lat2)) * dLng * dLng;
  return 2 * _earthM * math.asin(math.min(1, math.sqrt(a)));
}

/// Initial bearing from the first point to the second, 0..360.
double bearingDeg(double lat1, double lng1, double lat2, double lng2) {
  final p1 = _rad(lat1), p2 = _rad(lat2), dLng = _rad(lng2 - lng1);
  final y = math.sin(dLng) * math.cos(p2);
  final x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dLng);
  return (math.atan2(y, x) * 180 / math.pi) % 360;
}

/// Where [bearing] is seen from a camera facing [heading]: -180..180, negative to the left.
double relativeDeg(double bearing, double heading) => (bearing - heading + 540) % 360 - 180;

/// Screen x of something [rel] degrees off the camera axis, or null when it is out of view.
/// A pinhole camera puts it at tan(rel), so equal angles spread out towards the edges.
double? screenX(double rel, double width, {double fov = fovDeg}) {
  if (rel.abs() > fov / 2) return null;
  return width / 2 * (1 + math.tan(_rad(rel)) / math.tan(_rad(fov / 2)));
}

/// Whether the server takes a report from here. Written so NaN is outside, as on the server.
bool inMakati(double lat, double lng) =>
    Makati.south - cityMarginDeg <= lat &&
    lat <= Makati.north + cityMarginDeg &&
    Makati.west - cityMarginDeg <= lng &&
    lng <= Makati.east + cityMarginDeg;

/// Compass heading of the back camera, 0..360 from magnetic north, from an accelerometer reading
/// (gravity, which reads as pointing up) and a magnetometer reading, both in device axes. The camera
/// looks along -z, so the phone may be upright, tilted or in landscape. Null when it points within
/// ~10° of straight up or down, where there is no heading, or when the field reads as nothing.
double? cameraHeading(double ax, double ay, double az, double mx, double my, double mz) {
  // East = field × up, north = up × east, as in Android's SensorManager.getRotationMatrix.
  final ex = my * az - mz * ay, ey = mz * ax - mx * az, ez = mx * ay - my * ax;
  final up = math.sqrt(ax * ax + ay * ay + az * az);
  final east = math.sqrt(ex * ex + ey * ey + ez * ez);
  if (up == 0 || east < 1e-6 * up || az.abs() > up * math.cos(_rad(10))) return null;
  final northZ = ax * ey - ay * ex; // z of up × east: |up||east| times that of the unit north
  // The camera axis (0, 0, -1) against east and north, both scaled by |up||east|.
  return (math.atan2(-ez * up, -northZ) * 180 / math.pi) % 360;
}

/// "NE" for 42.
String compassPoint(double deg) =>
    const ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][(deg % 360 + 22.5) ~/ 45 % 8];
