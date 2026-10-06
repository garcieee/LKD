import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/config/makati.dart';
import 'package:lakad/features/report/ar_math.dart';

// Ayala Avenue, inside Makati.
const lat = 14.5547, lng = 121.0244;
// 0.001° of latitude: 2πR/360000 with R = 6371008.8 m.
const milliDegree = 111.195;

typedef Vec = (double, double, double); // world axes: east, north, up

double dot(Vec a, Vec b) => a.$1 * b.$1 + a.$2 * b.$2 + a.$3 * b.$3;
Vec cross(Vec a, Vec b) => (a.$2 * b.$3 - a.$3 * b.$2, a.$3 * b.$1 - a.$1 * b.$3, a.$1 * b.$2 - a.$2 * b.$1);
Vec neg(Vec a) => (-a.$1, -a.$2, -a.$3);

// What the phone's accelerometer and magnetometer read when its camera faces [heading], [down]
// degrees below the horizon (0 is upright), in portrait or landscape.
double? headingFromSensors(double heading, {double down = 0, bool landscape = false}) {
  final h = heading * math.pi / 180, d = down * math.pi / 180;
  final camera = (math.sin(h) * math.cos(d), math.cos(h) * math.cos(d), -math.sin(d));
  final Vec right = (math.cos(h), -math.sin(h), 0);
  final z = neg(camera); // device axes as world vectors
  var x = right, y = cross(z, right);
  if (landscape) (x, y) = (y, neg(x)); // turned a quarter about the camera axis
  const Vec up = (0, 0, 9.81); // gravity reads as up
  final field = (0.0, 40 * math.cos(0.3), -40 * math.sin(0.3)); // µT, north and dipping down
  return cameraHeading(dot(up, x), dot(up, y), dot(up, z), dot(field, x), dot(field, y), dot(field, z));
}

// Within a millionth of a degree of [h], across the 0/360 seam too.
Matcher facing(double h) => predicate<double?>(
  (v) => v != null && v >= 0 && v < 360 && relativeDeg(v, h).abs() < 1e-6,
  'a heading of $h°',
);

void main() {
  group('cameraHeading', () {
    test('is where the upright camera faces', () {
      for (final h in <double>[0, 42, 90, 180, 270, 359.5]) {
        expect(headingFromSensors(h), facing(h));
      }
    });

    test('holds when tilted at the ground or the sky, and in landscape', () {
      expect(headingFromSensors(120, down: 60), facing(120)); // a pothole ahead
      expect(headingFromSensors(300, down: -45), facing(300)); // a streetlight
      expect(headingFromSensors(75, landscape: true), facing(75));
    });

    test('has none when the camera points straight down, or without a field', () {
      expect(headingFromSensors(10, down: 90), isNull); // flat on a table
      expect(headingFromSensors(10, down: 85), isNull);
      expect(headingFromSensors(10, down: 75), facing(10));
      expect(cameraHeading(0, 9.81, 0, 0, 0, 0), isNull);
    });

    test('has none when the camera points straight up, or before the first gravity reading', () {
      expect(headingFromSensors(10, down: -90), isNull); // at the sky
      expect(headingFromSensors(10, down: -85), isNull);
      expect(headingFromSensors(10, down: -75), facing(10));
      expect(cameraHeading(0, 0, 0, 0, 40, -20), isNull); // the magnetometer can fire first
    });
  });

  group('distanceM', () {
    test('is zero to the same point', () => expect(distanceM(lat, lng, lat, lng), 0));

    test('0.001° north is ~111 m', () {
      expect(distanceM(lat, lng, lat + 0.001, lng), closeTo(milliDegree, 0.01));
    });

    test('0.001° east shrinks with the cosine of the latitude', () {
      expect(distanceM(lat, lng, lat, lng + 0.001), closeTo(107.63, 0.05)); // 111.195 × cos 14.5547°
    });
  });

  group('bearingDeg', () {
    test('points the four ways', () {
      expect(bearingDeg(lat, lng, lat + 0.001, lng), closeTo(0, 1e-9));
      expect(bearingDeg(lat, lng, lat, lng + 0.001), closeTo(90, 0.01));
      expect(bearingDeg(lat, lng, lat - 0.001, lng), closeTo(180, 1e-9));
      expect(bearingDeg(lat, lng, lat, lng - 0.001), closeTo(270, 0.01));
    });

    test('just west of north is near 360, not negative', () {
      final b = bearingDeg(lat, lng, lat + 0.001, lng - 0.00001);
      expect(b, greaterThan(359));
      expect(b, lessThan(360));
    });
  });

  group('relativeDeg', () {
    test('wraps around 0/360', () {
      expect(relativeDeg(10, 350), 20); // north-east of a camera facing north-west of north
      expect(relativeDeg(350, 10), -20);
      expect(relativeDeg(0, 359), 1);
      expect(relativeDeg(359, 0), -1);
    });

    test('stays in -180..180', () {
      expect(relativeDeg(90, 90), 0);
      expect(relativeDeg(180, 0), -180);
      expect(relativeDeg(0, -90), 90); // a heading that was not normalised
      for (var b = 0.0; b < 360; b += 7.5) {
        for (var h = 0.0; h < 360; h += 11.25) {
          expect(relativeDeg(b, h), inInclusiveRange(-180, 180));
        }
      }
    });
  });

  group('screenX', () {
    const width = 400.0;

    test('puts the camera axis in the middle and the view edges at the screen edges', () {
      expect(screenX(0, width), width / 2);
      expect(screenX(-fovDeg / 2, width), closeTo(0, 1e-9));
      expect(screenX(fovDeg / 2, width), closeTo(width, 1e-9));
    });

    test('follows the pinhole tangent, not a straight line', () {
      // tan 15° / tan 30° = 0.4641: 73.2% across, where a linear map would say 75%.
      expect(screenX(15, width), closeTo(width * (1 + 0.4641) / 2, 0.05));
      expect(screenX(-15, width), closeTo(width * (1 - 0.4641) / 2, 0.05));
    });

    test('is null outside the field of view', () {
      expect(screenX(fovDeg / 2 + 0.1, width), isNull);
      expect(screenX(-fovDeg / 2 - 0.1, width), isNull);
      expect(screenX(-90, width), isNull);
      expect(screenX(180, width), isNull);
      expect(screenX(40, width, fov: 90), isNotNull);
    });

    test('chains with the geometry: a report due east, camera facing east', () {
      final rel = relativeDeg(bearingDeg(lat, lng, lat, lng + 0.001), 90);
      expect(screenX(rel, width), closeTo(width / 2, 1));
    });

    test('chains across north: a report just east of it, camera just west of it, sits right of centre', () {
      final bearing = bearingDeg(lat, lng, lat + 0.001, lng + 0.0001); // ~5.5°
      final x = screenX(relativeDeg(bearing, 355), width)!;
      expect(x, greaterThan(width / 2));
      expect(x, lessThan(width * 0.75));
    });
  });

  group('inMakati', () {
    test('takes the city and the margin around it', () {
      expect(inMakati(lat, lng), isTrue);
      expect(inMakati(Makati.south - 0.003, lng), isTrue);
      expect(inMakati(lat, Makati.east + 0.0039), isTrue);
    });

    test('rejects past the margin, and NaN', () {
      expect(inMakati(Makati.south - 0.005, lng), isFalse);
      expect(inMakati(14.6500, 121.0300), isFalse); // Quezon City
      expect(inMakati(lat, Makati.west - 0.0041), isFalse);
      expect(inMakati(double.nan, lng), isFalse);
      expect(inMakati(lat, double.nan), isFalse);
    });

    test('takes a point exactly on the margin line, on every side, and not a hair past it', () {
      const m = cityMarginDeg, hair = 1e-9;
      for (final (la, ln, outLa, outLn) in [
        (Makati.south - m, lng, -hair, 0.0),
        (Makati.north + m, lng, hair, 0.0),
        (lat, Makati.west - m, 0.0, -hair),
        (lat, Makati.east + m, 0.0, hair),
      ]) {
        expect(inMakati(la, ln), isTrue, reason: '$la, $ln');
        expect(inMakati(la + outLa, ln + outLn), isFalse, reason: 'past $la, $ln');
      }
    });
  });

  test('compassPoint names eight directions and wraps', () {
    expect(compassPoint(0), 'N');
    expect(compassPoint(42), 'NE');
    expect(compassPoint(90), 'E');
    expect(compassPoint(200), 'S');
    expect(compassPoint(292), 'W');
    expect(compassPoint(337.4), 'NW');
    expect(compassPoint(359), 'N');
    expect(compassPoint(-10), 'N');
  });
}
