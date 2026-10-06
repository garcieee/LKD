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
      body: NavBar(trip: trip, now: () => DateTime(2026, 10, 6, 21, 0)),
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
    expect(find.text('15 min left · arrive at 9:15 PM'), findsOneWidget);
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
