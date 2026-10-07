import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/navigate/nav_bar.dart';
import 'package:lakad/state/trip_state.dart';

const here = (lat: 14.5000, lng: 121.0);
final place = Place.fromJson({'label': 'Dian, Makati', 'lat': 14.5100, 'lng': 121.0});

Map<String, dynamic> leg(String kind, String label, double from, double to, num secs) => {
  'kind': kind,
  'duration_s': secs,
  'distance_m': (to - from) * 111320,
  'label': label,
  'geometry': [
    [121.0, from],
    [121.0, to],
  ],
};

// Walk 14.5000 to 14.5020, ride to 14.5100: 223 m and 891 m up the 121.0 meridian.
final option = CommuteOption.fromJson({
  'id': 'a',
  'total_s': 1000,
  'walk_s': 200,
  'tags': <String>[],
  'legs': [
    leg('walk', 'Walk to Ayala Terminal', 14.5000, 14.5020, 200),
    leg('city_bus', 'Ayala Terminal to Dian', 14.5020, 14.5100, 800),
  ],
});

WalkRoute walk(String mode) => WalkRoute.fromJson({
  'mode': mode,
  'distance_m': 480,
  'duration_s': 345,
  'geometry': [
    [121.0, 14.5000],
    [121.0, 14.5100],
  ],
  'hazard_ids': <String>[],
  'avoids_hazards': true,
});

Future<TripState> started() async {
  final trip = TripState((from, to, mode) async => walk(mode), (from, to, mode) async => [option]);
  trip.setDestination(place, from: here);
  await Future<void>.delayed(Duration.zero);
  await trip.toCommute();
  trip.start();
  return trip;
}

Future<void> show(WidgetTester tester, TripState trip) => tester.pumpWidget(
  MaterialApp(
    home: Scaffold(
      body: Column(
        children: [
          NavBanner(trip: trip),
          NavPanel(trip: trip, now: () => DateTime(2026, 10, 6, 21, 0)),
        ],
      ),
    ),
  ),
);

void main() {
  test('legTitle names the ride by its kind and keeps a walk as the server wrote it', () {
    expect(legTitle(option.legs[0]), 'Walk to Ayala Terminal');
    expect(legTitle(option.legs[1]), 'City bus: Ayala Terminal to Dian');
  });

  testWidgets('before the first fix it says it is finding the position, and End works', (tester) async {
    final trip = (await tester.runAsync(started))!;
    await show(tester, trip);
    expect(find.text('Finding your position…'), findsOneWidget);
    expect(find.text('Trip to Dian, Makati'), findsOneWidget);
    await tester.tap(find.text('End trip'));
    expect(trip.started, isFalse);
    trip.dispose();
  });

  testWidgets('on a leg: its name, distance left, time left and arrival, and what comes next', (tester) async {
    final trip = (await tester.runAsync(started))!;
    trip.update(14.5010, 121.0);
    await show(tester, trip);
    expect(find.text('Walk to Ayala Terminal'), findsOneWidget);
    expect(find.text('111 m left on this leg'), findsOneWidget);
    // Half of the 200 s walk is left, plus the 800 s ride: 900 s is 15 min, so 9:15 PM from 9:00 PM.
    expect(find.text('9:15 PM'), findsOneWidget);
    expect(find.text('15 min'), findsOneWidget);
    expect(find.text('1.0 km'), findsOneWidget);
    expect(find.text('Then: City bus: Ayala Terminal to Dian'), findsOneWidget);
    expect(find.byIcon(Icons.directions_walk), findsOneWidget);
    trip.dispose();
  });

  testWidgets('the next leg shows its own icon, and the last leg has nothing after it', (tester) async {
    final trip = (await tester.runAsync(started))!;
    trip.update(14.5020, 121.0);
    await show(tester, trip);
    expect(find.text('City bus: Ayala Terminal to Dian'), findsOneWidget);
    expect(find.byIcon(Icons.directions_bus), findsOneWidget);
    expect(find.textContaining('Then:'), findsNothing);
    trip.dispose();
  });

  testWidgets('far from the path it says so instead of what comes next', (tester) async {
    final trip = (await tester.runAsync(started))!;
    trip.update(14.5010, 121.002);
    await show(tester, trip);
    expect(find.textContaining('Off route: '), findsOneWidget);
    expect(find.textContaining('Then:'), findsNothing);
    trip.dispose();
  });

  group('turn by turn', () {
    // A walk up the meridian with a turn half way, then the ride; the bar speaks the turns the server sent.
    Map<String, dynamic> stepLeg() => {
      ...leg('walk', 'Walk to Ayala Terminal', 14.5000, 14.5020, 200),
      'geometry': [
        [121.0, 14.5000],
        [121.0, 14.5010],
        [121.0, 14.5020],
      ],
      'steps': [
        {'type': 11, 'text': 'Head north on Ayala Avenue', 'name': 'Ayala Avenue', 'distance_m': 111.3, 'at': 0},
        {'type': 5, 'text': 'Bear right onto Paseo de Roxas', 'name': 'Paseo de Roxas', 'distance_m': 111.3, 'at': 1},
        {'type': 10, 'text': 'Arrive at your destination', 'name': '', 'distance_m': 0, 'at': 2},
      ],
    };

    Future<TripState> withTurns() async {
      final o = CommuteOption.fromJson({
        'id': 'a',
        'total_s': 1000,
        'walk_s': 200,
        'tags': <String>[],
        'legs': [stepLeg(), leg('city_bus', 'Ayala Terminal to Dian', 14.5020, 14.5100, 800)],
      });
      final trip = TripState((from, to, mode) async => walk(mode), (from, to, mode) async => [o]);
      trip.setDestination(place, from: here);
      await Future<void>.delayed(Duration.zero);
      await trip.toCommute();
      trip.start();
      return trip;
    }

    testWidgets('the next turn with its distance and the street the user is on', (tester) async {
      final trip = (await tester.runAsync(withTurns))!;
      trip.update(14.5004, 121.0);
      await show(tester, trip);
      expect(find.text('Bear right onto Paseo de Roxas'), findsOneWidget);
      expect(find.text('In 67 m · on Ayala Avenue'), findsOneWidget);
      expect(find.byIcon(Icons.turn_slight_right), findsOneWidget);
      expect(find.textContaining('left on this leg'), findsNothing);
      trip.update(14.5013, 121.0);
      await tester.pump();
      expect(find.text('In 78 m · on Paseo de Roxas'), findsOneWidget, reason: 'only the leg end is left of the turns');
      expect(find.text('Walk to Ayala Terminal'), findsOneWidget, reason: 'a leg end is not "your destination"');
      expect(find.byIcon(Icons.flag), findsOneWidget);
      trip.dispose();
    });

    testWidgets('a ride has no turns: it falls back to the leg', (tester) async {
      final trip = (await tester.runAsync(withTurns))!;
      trip.update(14.5020, 121.0);
      await show(tester, trip);
      expect(find.text('City bus: Ayala Terminal to Dian'), findsOneWidget);
      expect(find.textContaining('left on this leg'), findsOneWidget);
      trip.dispose();
    });

    testWidgets('off the path it says it is finding a new way while the reroute is on its way', (tester) async {
      final pending = Completer<WalkRoute>();
      final trip = TripState((from, to, mode) => from.lat == here.lat ? Future.value(walk(mode)) : pending.future, (
        from,
        to,
        mode,
      ) async {
        return [option];
      });
      trip.setDestination(place, from: here);
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await trip.toCommute();
      trip.start();
      for (var i = 0; i < 3; i++) {
        trip.update(14.5010, 121.002);
      }
      await show(tester, trip);
      expect(find.text('Off route · finding a new way…'), findsOneWidget);
      expect(find.textContaining('Off route: '), findsNothing);
      trip.dispose();
    });

    test('every turn code has a glyph, and the unknown ones go straight', () {
      for (var t = 0; t <= 13; t++) {
        expect(turnIcon(t), isA<IconData>());
      }
      expect(turnIcon(0), Icons.turn_left);
      expect(turnIcon(1), Icons.turn_right);
      expect(turnIcon(99), Icons.straight);
    });
  });

  testWidgets('arriving says so, and Done ends the trip', (tester) async {
    final trip = (await tester.runAsync(started))!;
    trip.update(14.5100, 121.0);
    await show(tester, trip);
    expect(find.text("You've arrived"), findsOneWidget);
    expect(find.text('Dian, Makati'), findsOneWidget);
    await tester.tap(find.text('Done'));
    expect(trip.started, isFalse);
    trip.dispose();
  });

  testWidgets('the bar follows the trip as fixes come in', (tester) async {
    final trip = (await tester.runAsync(started))!;
    trip.update(14.5000, 121.0);
    await show(tester, trip);
    expect(find.text('223 m left on this leg'), findsOneWidget);
    trip.update(14.5010, 121.0);
    await tester.pump();
    expect(find.text('111 m left on this leg'), findsOneWidget);
    trip.dispose();
  });
}
