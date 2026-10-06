import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/state/trip_progress.dart';

// A trip straight up a meridian: walk 14.5000 to 14.5020, ride to 14.5100, walk to 14.5110.
const lng = 121.0;
const mPerDeg = 111320.0;
double m(double lat0, double lat1) => (lat1 - lat0).abs() * mPerDeg;

CommuteLeg leg(String kind, double from, double to, double seconds) => CommuteLeg.fromJson({
  'kind': kind,
  'duration_s': seconds,
  'distance_m': m(from, to),
  'label': kind,
  'geometry': [
    [lng, from],
    [lng, to],
  ],
});

final legs = [
  leg('walk', 14.5000, 14.5020, 200),
  leg('city_bus', 14.5020, 14.5100, 900),
  leg('walk', 14.5100, 14.5110, 100),
];
final total = legs.fold<double>(0, (sum, l) => sum + l.distanceM);

/// Degrees of longitude for [metres] east at [lat].
double east(double metres, double lat) => metres / (mPerDeg * math.cos(lat * math.pi / 180));

Matcher near(num v, [num tol = 1.0]) => closeTo(v, tol);

void main() {
  test('at the start: first leg, the whole trip ahead, on the line', () {
    final p = tripProgress(legs, 0, 14.5000, lng)!;
    expect(p.leg, 0);
    expect(p.legLeftM, near(m(14.5000, 14.5020)));
    expect(p.leftM, near(total));
    expect(p.leftS, near(1200));
    expect(p.offM, near(0));
    expect(p.arrived, isFalse);
    expect(p.offRoute, isFalse);
  });

  test('part way along a leg, the distance and time left shrink pro rata', () {
    final p = tripProgress(legs, 0, 14.5010, lng)!;
    expect(p.leg, 0);
    expect(p.legLeftM, near(m(14.5010, 14.5020)));
    expect(p.leftM, near(total - m(14.5000, 14.5010)));
    expect(p.leftS, near(1100), reason: 'half of the first 200 s is gone');
  });

  test('how far off the line is the distance to it, and past 30 m it is off route', () {
    final a = tripProgress(legs, 0, 14.5010, lng + east(20, 14.5010))!;
    expect(a.offM, near(20));
    expect(a.leg, 0);
    expect(a.offRoute, isFalse);
    final b = tripProgress(legs, 0, 14.5010, lng + east(60, 14.5010))!;
    expect(b.offM, near(60));
    expect(b.offRoute, isTrue);
  });

  test('a ride is never off route: its line is a straight guess, not where the vehicle goes', () {
    final p = tripProgress(legs, 1, 14.5060, lng + east(150, 14.5060))!;
    expect(p.leg, 1);
    expect(p.offM, near(150));
    expect(p.offRoute, isFalse);
    expect(p.walking, isFalse);
  });

  test('a leg ends 25 m from its end: the next one takes over', () {
    final before = tripProgress(legs, 0, 14.5020 - 40 / mPerDeg, lng)!;
    expect(before.leg, 0, reason: '40 m short of the hub');
    final almost = tripProgress(legs, 0, 14.5020 - 10 / mPerDeg, lng)!;
    expect(almost.leg, 1, reason: '10 m short is close enough');
    expect(almost.legLeftM, near(legs[1].distanceM, 12), reason: 'and the ride lies ahead in full');
    final at = tripProgress(legs, 0, 14.5020, lng)!;
    expect(at.leg, 1);
  });

  test('on the ride the legs after it still count', () {
    final p = tripProgress(legs, 1, 14.5060, lng)!;
    expect(p.leg, 1);
    expect(p.legLeftM, near(m(14.5060, 14.5100)));
    expect(p.leftM, near(m(14.5060, 14.5100) + legs[2].distanceM));
    expect(p.leftS, near(900 * (m(14.5060, 14.5100) / legs[1].distanceM) + 100));
  });

  test('the trip never goes backwards: a fix back on an earlier leg stays on the current one', () {
    final p = tripProgress(legs, 1, 14.5005, lng)!;
    expect(p.leg, 1, reason: 'leg 0 is not even considered once the user is past it');
    expect(p.offM, greaterThan(100), reason: 'so they read as far off the ride line');
  });

  test('the next leg is taken as soon as the fix is nearer to it than to this one', () {
    // Past the hub and off to the side: leg 1 (the ride) is the nearer line.
    final p = tripProgress(legs, 0, 14.5030, lng + east(5, 14.5030))!;
    expect(p.leg, 1);
  });

  test('arrived: on the last leg within 25 m of its end', () {
    expect(tripProgress(legs, 2, 14.5110 - 100 / mPerDeg, lng)!.arrived, isFalse);
    final p = tripProgress(legs, 2, 14.5110 - 10 / mPerDeg, lng)!;
    expect(p.arrived, isTrue);
    expect(p.leg, 2);
    expect(p.leftM, lessThan(arriveM));
    final past = tripProgress(legs, 2, 14.5115, lng)!;
    expect(past.arrived, isTrue, reason: 'a fix just past the end still counts');
  });

  test('a one-leg trip, and no legs at all', () {
    final one = [legs.first];
    final p = tripProgress(one, 0, 14.5000, lng)!;
    expect(p.leg, 0);
    expect(p.leftM, near(one.single.distanceM));
    expect(tripProgress(one, 0, 14.5020, lng)!.arrived, isTrue);
    expect(tripProgress(const [], 0, 14.5, lng), isNull);
  });

  test('the line ahead starts at the user and is trimmed as they move', () {
    final start = tripProgress(legs, 0, 14.5000, lng)!;
    expect(start.alongM, near(0));
    expect(start.ahead, [
      [lng, near(14.5000, 1e-6)],
      [lng, 14.5020],
    ]);
    final p = tripProgress(legs, 0, 14.5010, lng + east(5, 14.5010))!;
    expect(p.alongM, near(111.32));
    expect(p.ahead.first[0], closeTo(lng, 1e-9), reason: 'snapped onto the line, not where the GPS says');
    expect(p.ahead.first[1], closeTo(14.5010, 1e-6));
    expect(p.ahead.last, [lng, 14.5020]);
    expect(p.ahead.length, 2);
  });

  test('a line with a bend keeps the points still ahead and drops those behind', () {
    final bent = CommuteLeg.fromJson({
      'kind': 'walk',
      'duration_s': 100,
      'distance_m': 200,
      'label': 'Walk',
      'geometry': [
        [lng, 14.5000],
        [lng, 14.5010],
        [lng + 0.001, 14.5010],
      ],
    });
    final before = tripProgress([bent], 0, 14.5004, lng)!;
    expect(before.ahead.length, 3, reason: 'user, the corner, the end');
    final after = tripProgress([bent], 0, 14.5010, lng + 0.0004)!;
    expect(after.ahead.length, 2, reason: 'the corner is behind: user and the end');
    expect(after.ahead.last, [lng + 0.001, 14.5010]);
  });

  // 14.5000 north to the corner at 14.5010, then east to lng + 0.001.
  final turns = CommuteLeg.fromJson({
    'kind': 'walk',
    'duration_s': 150,
    'distance_m': 200,
    'label': 'Walk to Ayala Terminal',
    'geometry': [
      [lng, 14.5000],
      [lng, 14.5010],
      [lng + 0.001, 14.5010],
    ],
    'steps': [
      {'type': 11, 'text': 'Head north on Ayala Avenue', 'name': 'Ayala Avenue', 'distance_m': 111.3, 'at': 0},
      {'type': 1, 'text': 'Turn right onto Paseo de Roxas', 'name': 'Paseo de Roxas', 'distance_m': 107.9, 'at': 1},
      {'type': 10, 'text': 'Arrive at your destination', 'name': '', 'distance_m': 0, 'at': 2},
    ],
  });

  test('the next turn, how far away it is, and the street the user is on', () {
    final a = tripProgress([turns], 0, 14.5000, lng)!;
    expect(a.street, 'Ayala Avenue', reason: 'the depart step is where they stand');
    expect(a.turn!.text, 'Turn right onto Paseo de Roxas');
    expect(a.turnInM, near(111.3));

    final b = tripProgress([turns], 0, 14.5006, lng)!;
    expect(b.turnInM, near(111.3 - 66.8));
    expect(b.street, 'Ayala Avenue');

    final c = tripProgress([turns], 0, 14.5010, lng + 0.0004)!;
    expect(c.street, 'Paseo de Roxas', reason: 'round the corner');
    expect(c.turn!.type, 10, reason: 'only the arrival is left');
    expect(c.turnInM, near(0.0006 * mPerDeg * math.cos(14.501 * math.pi / 180)));
  });

  test('a leg with no steps has no turn and no street', () {
    final p = tripProgress(legs, 0, 14.5005, lng)!;
    expect(p.turn, isNull);
    expect(p.turnInM, isNull);
    expect(p.street, '');
  });

  test('a stale leg index is held inside the trip', () {
    expect(tripProgress(legs, 9, 14.5105, lng)!.leg, 2);
    expect(tripProgress(legs, -3, 14.5000, lng)!.leg, 0);
  });
}
