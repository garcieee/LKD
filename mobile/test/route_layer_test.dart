import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/layers/route_layer.dart';
import 'package:lakad/state/trip_progress.dart';

Map<String, dynamic> leg(String kind, List<List<double>> line) => {
  'kind': kind,
  'duration_s': 100,
  'distance_m': 100,
  'label': kind,
  'geometry': line,
};

void main() {
  tripTests();
  test('a commute is one feature per leg, in order, and only the walking legs are thin', () {
    final option = CommuteOption.fromJson({
      'id': 'city_bus:a:b',
      'total_s': 300,
      'walk_s': 200,
      'tags': <String>[],
      'legs': [
        leg('walk', [
          [121.0, 14.5],
          [121.1, 14.6],
        ]),
        leg('city_bus', [
          [121.1, 14.6],
          [121.2, 14.7],
        ]),
        leg('walk', [
          [121.2, 14.7],
          [121.3, 14.8],
        ]),
      ],
    });
    final geo = commuteGeoJson(option);
    expect(geo['type'], 'FeatureCollection');
    final features = (geo['features'] as List).cast<Map<String, Object>>();
    expect([for (final f in features) (f['properties'] as Map)['kind']], ['walk', 'city_bus', 'walk']);
    expect([for (final f in features) (f['properties'] as Map)['thin']], [true, false, true]);
    expect((features[1]['geometry'] as Map)['coordinates'], [
      [121.1, 14.6],
      [121.2, 14.7],
    ]);
  });

  test('a walking route stays a single line with no thin flag, so it draws thick as before', () {
    final route = WalkRoute.fromJson({
      'mode': 'walkable',
      'distance_m': 480,
      'duration_s': 345,
      'geometry': [
        [121.0244, 14.5547],
        [121.021, 14.553],
      ],
      'hazard_ids': <String>[],
      'avoids_hazards': true,
    });
    final geo = walkGeoJson(route);
    expect(geo['type'], 'Feature');
    expect((geo['properties'] as Map).containsKey('thin'), isFalse);
    expect((geo['geometry'] as Map)['type'], 'LineString');
  });
}

// Legs up the 121.0 meridian, each [kind, from latitude, to latitude].
List<CommuteLeg> _trip(List<(String, double, double)> legs) => [
  for (final (kind, from, to) in legs)
    CommuteLeg.fromJson({
      'kind': kind,
      'duration_s': 100,
      'distance_m': 100,
      'label': kind,
      'geometry': [
        [121.0, from],
        [121.0, to],
      ],
    }),
];

void tripTests() {
  test('a trip in progress draws from the user on: the leg they are on is trimmed, the ones before it are gone', () {
    final legs = _trip([('walk', 14.5000, 14.5010), ('city_bus', 14.5010, 14.5100), ('walk', 14.5100, 14.5110)]);
    final ride = tripProgress(legs, 1, 14.5050, 121.0)!;
    final features = (tripGeoJson(legs, ride)['features'] as List).cast<Map<String, Object>>();
    expect([for (final f in features) (f['properties'] as Map)['kind']], ['city_bus', 'walk']);
    final coords = (features[0]['geometry'] as Map)['coordinates'] as List;
    expect(coords.length, 2);
    expect((coords.first as List)[1], closeTo(14.5050, 1e-6), reason: 'it starts at the user');
    expect(coords.last, [121.0, 14.5100]);
    expect((features[1]['geometry'] as Map)['coordinates'], legs[2].line, reason: 'later legs are whole');
    expect([for (final f in features) (f['properties'] as Map)['thin']], [false, true]);
  });

  test('before the first fix the whole trip is drawn, and a walk-only trip is one thick line', () {
    final legs = _trip([('walk', 14.5000, 14.5010)]);
    final features = (tripGeoJson(legs, null)['features'] as List).cast<Map<String, Object>>();
    expect(features.length, 1);
    expect((features.single['geometry'] as Map)['coordinates'], legs.single.line);
    expect((features.single['properties'] as Map)['thin'], isFalse, reason: 'the whole trip is the walk');
  });
}
