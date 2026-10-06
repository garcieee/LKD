import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/transfer_walk/route_card.dart';
import 'package:lakad/state/trip_state.dart';

WalkRoute route(String mode, {double m = 480, double s = 345, List<String> hazards = const [], bool avoids = true}) =>
    WalkRoute.fromJson({
      'mode': mode,
      'distance_m': m,
      'duration_s': s,
      'geometry': [
        [121.0244, 14.5547],
        [121.021, 14.553],
      ],
      'hazard_ids': hazards,
      'avoids_hazards': avoids,
    });

const here = (lat: 14.5547, lng: 121.0244);
final greenbelt = Place.fromJson({'label': 'Greenbelt, Makati', 'lat': 14.553, 'lng': 121.021});

void main() {
  group('labels', () {
    test('distanceLabel: metres under a kilometre, then km to one decimal', () {
      expect(distanceLabel(480.4), '480 m');
      expect(distanceLabel(999.4), '999 m');
      expect(distanceLabel(1000), '1.0 km');
      expect(distanceLabel(1234), '1.2 km');
    });

    test('durationLabel: rounds to the minute, never under one, hours past an hour', () {
      expect(durationLabel(10), '1 min');
      expect(durationLabel(345), '6 min');
      expect(durationLabel(3540), '59 min');
      expect(durationLabel(3600), '1 h');
      expect(durationLabel(3900), '1 h 5 min');
    });

    test('hazardLabel: says what the route passes, and owns up when it could not steer around', () {
      expect(hazardLabel(route('walkable')), 'Steers clear of reported hazards');
      expect(hazardLabel(route('fastest', avoids: false)), 'No reported hazards on this route');
      expect(hazardLabel(route('fastest', hazards: ['a'], avoids: false)), 'Passes 1 reported hazard');
      expect(hazardLabel(route('walkable', hazards: ['a', 'b'])), 'Passes 2 reported hazards');
      expect(hazardLabel(route('accessible', hazards: ['a'], avoids: false)), 'Passes 1 reported hazard (no way around)');
    });
  });

  group('RouteCard', () {
    Future<TripState> mount(WidgetTester tester, RouteFn fetch, {bool withStart = true}) async {
      final trip = TripState(fetch);
      trip.setDestination(greenbelt, from: withStart ? here : null);
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: RouteCard(trip: trip))));
      return trip;
    }

    testWidgets('shows each mode with its time, and the chosen mode in full; tapping switches', (tester) async {
      await mount(tester, (from, to, mode) async => switch (mode) {
        'fastest' => route(mode, m: 400, s: 300, hazards: ['a', 'b'], avoids: false),
        'walkable' => route(mode, m: 520, s: 400),
        _ => route(mode, m: 560, s: 480),
      });
      await tester.pump();
      expect(find.text('Greenbelt, Makati'), findsOneWidget);
      expect(find.text('5 min'), findsOneWidget);
      expect(find.text('7 min'), findsOneWidget);
      expect(find.text('8 min'), findsOneWidget);
      expect(find.text('520 m · 7 min'), findsOneWidget, reason: 'Walkable is chosen first');
      expect(find.text('Steers clear of reported hazards'), findsOneWidget);

      await tester.tap(find.text('Fastest'));
      await tester.pump();
      expect(find.text('400 m · 5 min'), findsOneWidget);
      expect(find.text('Passes 2 reported hazards'), findsOneWidget);
    });

    testWidgets('waiting, loading and failing each say so', (tester) async {
      final wait = Completer<WalkRoute>();
      final trip = await mount(tester, (from, to, mode) => mode == 'walkable' ? wait.future : Future.value(route(mode)), withStart: false);
      expect(find.text('Waiting for your location…'), findsOneWidget);

      unawaited(trip.plan(here));
      await tester.pump();
      expect(find.text('Finding the route…'), findsOneWidget);
      expect(find.text('…'), findsOneWidget, reason: 'Walkable has no time yet');

      wait.completeError(const ApiException('No walking route found between those points.'));
      await tester.pump();
      await tester.pump();
      expect(find.text('No walking route found between those points.'), findsOneWidget);
      expect(find.text('–'), findsOneWidget);
    });
  });
}
