import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/commute/commute_list.dart';
import 'package:lakad/features/transfer_walk/route_card.dart';
import 'package:lakad/state/trip_state.dart';

const here = (lat: 14.5547, lng: 121.0244);
final greenbelt = Place.fromJson({'label': 'Greenbelt, Makati', 'lat': 14.553, 'lng': 121.021});

Map<String, dynamic> leg(String kind, num s) => {
  'kind': kind,
  'duration_s': s,
  'distance_m': 300,
  'label': kind,
  'geometry': [
    [121.0244, 14.5547],
    [121.021, 14.553],
  ],
};

CommuteOption option(String id, {required num total, required num walk, List<String> tags = const []}) =>
    CommuteOption.fromJson({
      'id': id,
      'total_s': total,
      'walk_s': walk,
      'tags': tags,
      'legs': [leg('walk', walk / 2), leg('city_bus', total - walk), leg('walk', walk / 2)],
    });

WalkRoute walk(String mode) => WalkRoute.fromJson({
  'mode': mode,
  'distance_m': 480,
  'duration_s': 345,
  'geometry': [
    [121.0244, 14.5547],
    [121.021, 14.553],
  ],
  'hazard_ids': <String>[],
  'avoids_hazards': true,
});

TripState tripWith(List<CommuteOption> options) =>
    TripState((from, to, mode) async => walk(mode), (from, to, mode) async => options);

Future<void> show(WidgetTester tester, Widget child) => tester.pumpWidget(
  MaterialApp(
    home: Scaffold(body: SingleChildScrollView(child: child)),
  ),
);

void main() {
  test('arrivalLabel is a 12-hour clock with AM and PM', () {
    expect(arrivalLabel(DateTime(2026, 10, 6, 22, 33)), '10:33 PM');
    expect(arrivalLabel(DateTime(2026, 10, 6, 0, 5)), '12:05 AM');
    expect(arrivalLabel(DateTime(2026, 10, 6, 12, 0)), '12:00 PM');
  });

  testWidgets('each option shows minutes, arrival, walking, its legs, and the earliest badge', (tester) async {
    final trip = tripWith([
      option('a', total: 2100, walk: 360, tags: ['earliest']),
      option('b', total: 3000, walk: 600),
    ]);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.runAsync(trip.toCommute);
    await show(tester, CommuteList(trip: trip, now: () => DateTime(2026, 10, 6, 21, 58)));

    expect(find.text('2 suggested routes'), findsOneWidget);
    expect(find.text('35 min'), findsOneWidget);
    expect(find.text('Arrive at 10:33 PM'), findsOneWidget);
    expect(find.text('6 min walk'), findsOneWidget);
    expect(find.text('50 min'), findsOneWidget);
    expect(find.text('Arrive at 10:48 PM'), findsOneWidget);
    expect(find.text('City bus'), findsNWidgets(2), reason: 'the ride leg is named in each strip');
    expect(find.byIcon(Icons.directions_walk), findsNWidgets(4), reason: 'two walks per option');
    expect(find.text('Earliest arrival'), findsOneWidget, reason: 'only the tagged option has it');
    expect(find.text('Ride times are estimates.'), findsOneWidget);
    trip.dispose();
  });

  testWidgets('tapping an option selects it', (tester) async {
    final trip = tripWith([option('a', total: 2100, walk: 360), option('b', total: 3000, walk: 600)]);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.runAsync(trip.toCommute);
    await show(tester, CommuteList(trip: trip));
    expect(trip.selected, 0);
    await tester.tap(find.text('50 min'));
    expect(trip.selected, 1);
    trip.dispose();
  });

  testWidgets('no options says why: still looking, nothing found, or the server\'s message', (tester) async {
    final empty = tripWith([]);
    await show(tester, CommuteList(trip: empty));
    expect(find.text('Waiting for your location…'), findsOneWidget);
    empty.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.runAsync(empty.toCommute);
    await tester.pump();
    expect(find.text('No ride found near both ends of this trip.'), findsOneWidget);

    final failing = TripState(
      (from, to, mode) async => walk(mode),
      (from, to, mode) async => throw const ApiException('Routing is busy. Try again in a minute.'),
    );
    failing.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.runAsync(failing.toCommute);
    await show(tester, CommuteList(trip: failing));
    expect(find.text('Routing is busy. Try again in a minute.'), findsOneWidget);
    empty.dispose();
    failing.dispose();
  });

  testWidgets('the card compares the walks first; Next brings the rides, and the back chip names the mode', (tester) async {
    final trip = tripWith([option('a', total: 2100, walk: 360, tags: ['earliest'])]);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await show(tester, RouteCard(trip: trip));
    expect(find.text('Fastest'), findsOneWidget, reason: 'the walking comparison comes first');
    expect(find.text('Walkable'), findsOneWidget);
    expect(find.text('Accessible'), findsOneWidget);
    expect(find.text('480 m · 6 min'), findsOneWidget);
    expect(find.textContaining('suggested route'), findsNothing);

    await tester.tap(find.text('Accessible'));
    await tester.pump();
    await tester.tap(find.text('Next: trip options'));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    expect(trip.step, TripStep.commute);
    expect(find.text('1 suggested route'), findsOneWidget);
    expect(find.text('Walking: Accessible'), findsOneWidget);
    expect(find.text('Fastest'), findsNothing);
    expect(find.text('Next: trip options'), findsNothing);

    await tester.tap(find.text('Walking: Accessible'));
    await tester.pump();
    expect(find.text('Fastest'), findsOneWidget);
    expect(find.text('1 suggested route'), findsNothing);
    trip.dispose();
  });

  testWidgets('Next waits for a walking route', (tester) async {
    final trip = tripWith([]);
    trip.setDestination(greenbelt);
    await show(tester, RouteCard(trip: trip));
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    trip.dispose();
  });

  testWidgets('without a commute source the card is the walking card, with no Next', (tester) async {
    final trip = TripState((from, to, mode) async => walk(mode));
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await show(tester, RouteCard(trip: trip));
    expect(find.text('Next: trip options'), findsNothing);
    expect(find.text('Fastest'), findsOneWidget);
    trip.dispose();
  });

  testWidgets('Start trip begins the trip with the chosen option', (tester) async {
    final trip = tripWith([option('a', total: 2100, walk: 360, tags: ['earliest'])]);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await show(tester, RouteCard(trip: trip));
    expect(find.text('Start trip'), findsNothing, reason: 'not on the commute step yet');
    await tester.tap(find.text('Next: trip options'));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    expect(find.text('Start trip'), findsOneWidget);
    await tester.tap(find.text('Start trip'));
    await tester.pump();
    expect(trip.started, isTrue, reason: 'the map view swaps this card for the nav bar');
    trip.dispose();
  });

  testWidgets('not commuting: Start walking on the walking step starts a walk all the way', (tester) async {
    final trip = tripWith([option('a', total: 2100, walk: 360)]);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await show(tester, RouteCard(trip: trip));
    await tester.tap(find.text('Start walking'));
    await tester.pump();
    expect(trip.started, isTrue);
    expect(trip.step, TripStep.walk);
    expect(trip.activeLegs.single.isWalk, isTrue);
    trip.dispose();
  });

  testWidgets('with no ride the button says Start walking, and it waits while the options load', (tester) async {
    final pending = Completer<List<CommuteOption>>();
    final trip = TripState((from, to, mode) async => walk(mode), (from, to, mode) => pending.future);
    trip.setDestination(greenbelt, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await show(tester, RouteCard(trip: trip));
    await tester.tap(find.text('Next: trip options'));
    await tester.pump();
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull, reason: 'still loading');

    pending.complete([]);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    expect(find.text('No ride found near both ends of this trip.'), findsOneWidget);
    expect(find.text('Start walking'), findsOneWidget);
    await tester.tap(find.text('Start walking'));
    await tester.pump();
    expect(trip.started, isTrue);
    trip.dispose();
  });
}
