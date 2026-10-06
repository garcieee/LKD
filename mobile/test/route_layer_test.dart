import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/layers/route_layer.dart';

Map<String, dynamic> leg(String kind, List<List<double>> line) => {
  'kind': kind,
  'duration_s': 100,
  'distance_m': 100,
  'label': kind,
  'geometry': line,
};

void main() {
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
