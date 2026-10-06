import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/state/trip_state.dart';

const here = (lat: 14.5547, lng: 121.0244);
Place place(String label) => Place.fromJson({'label': label, 'lat': 14.553, 'lng': 121.021});
WalkRoute route(String mode, {double m = 480}) => WalkRoute.fromJson({
  'mode': mode,
  'distance_m': m,
  'duration_s': 300,
  'geometry': [
    [121.0244, 14.5547],
    [121.021, 14.553],
  ],
  'hazard_ids': <String>[],
  'avoids_hazards': mode != 'fastest',
});

void main() {
  test('picking a place with a start fetches all three modes, each showing as it lands', () async {
    final pending = {for (final m in routeModes.keys) m: Completer<WalkRoute>()};
    final asked = <String>[];
    final trip = TripState((from, to, mode) {
      asked.add(mode);
      expect(from, here);
      expect(to, (lat: 14.553, lng: 121.021));
      return pending[mode]!.future;
    });
    trip.setDestination(place('Greenbelt'), from: here);
    expect(asked, ['fastest', 'walkable', 'accessible']);
    expect(trip.loading, isTrue);
    expect(trip.route, isNull);

    pending['walkable']!.complete(route('walkable', m: 520));
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 520, reason: 'the shown mode (walkable) is there before the others');
    expect(trip.loading, isTrue);

    pending['fastest']!.complete(route('fastest'));
    pending['accessible']!.complete(route('accessible'));
    await Future<void>.delayed(Duration.zero);
    expect(trip.loading, isFalse);
    expect(trip.routes.keys, containsAll(routeModes.keys));
    trip.dispose();
  });

  test('one mode failing keeps its message and leaves the others', () async {
    final trip = TripState((from, to, mode) async {
      if (mode == 'accessible') throw const ApiException('No walking route found between those points.');
      return route(mode);
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.routes.keys, unorderedEquals(['fastest', 'walkable']));
    expect(trip.loading, isFalse);
    trip.setMode('accessible');
    expect(trip.route, isNull);
    expect(trip.error, 'No walking route found between those points.');
    trip.setMode('walkable');
    expect(trip.error, isNull);
    trip.dispose();
  });

  test('without a start nothing is fetched until plan() gets one', () async {
    final asked = <String>[];
    final trip = TripState((from, to, mode) async {
      asked.add(mode);
      return route(mode);
    });
    trip.setDestination(place('Greenbelt'));
    expect(asked, isEmpty);
    expect(trip.planned, isFalse);
    await trip.plan(here);
    expect(asked.length, 3);
    expect(trip.planned, isTrue);
    await trip.plan(here);
    expect(asked.length, 3, reason: 'asked once per destination');
    trip.dispose();
  });

  test('a new destination drops answers still coming for the old one', () async {
    final slow = Completer<WalkRoute>();
    var first = true;
    final trip = TripState((from, to, mode) {
      if (first && mode == 'walkable') return slow.future;
      return Future.value(route(mode, m: first ? 1 : 2));
    });
    trip.setDestination(place('Old'), from: here);
    first = false;
    trip.setDestination(place('New'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 2);
    slow.complete(route('walkable', m: 1));
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 2, reason: 'the old walkable answer arrived late and is ignored');
    trip.dispose();
  });

  test('clear forgets the destination and its routes; unknown modes are ignored', () async {
    final trip = TripState((from, to, mode) async => route(mode));
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    trip.setMode('teleport');
    expect(trip.mode, 'walkable');
    trip.clear();
    expect(trip.destination, isNull);
    expect(trip.routes, isEmpty);
    expect(trip.loading, isFalse);
    expect(trip.planned, isFalse);
    trip.dispose();
  });
}
