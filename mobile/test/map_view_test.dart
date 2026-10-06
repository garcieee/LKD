// The map page, whole: its chips and cards at small phone sizes and large text, how they sit when the keyboard opens,
// and that the screen stays on for a trip. The map itself is a blank box (test_support.dart), so no Mapbox token or
// phone is needed.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/navigate/compass_chip.dart';
import 'package:lakad/features/search/search_bar.dart';
import 'package:lakad/map/map_view.dart';
import 'package:lakad/state/trip_state.dart';

import 'test_support.dart';

void main() {
  setUpAll(loadRoboto);

  late Plugins plugins;
  setUp(() => plugins = Plugins());

  Widget page() => const MapView(mapboxToken: 'pk.test');

  // The page's own trip, which is how a test reaches it.
  TripState tripOf(WidgetTester tester) => tester.widget<PlaceSearchBar>(find.byType(PlaceSearchBar)).trip;

  // A destination with its walks and rides, as if the server had answered (the page's own calls get a 400 in tests).
  Future<TripState> planTrip(WidgetTester tester) async {
    final trip = tripOf(tester);
    trip.setDestination(destination, from: here);
    await tester.pump(const Duration(milliseconds: 100));
    for (final mode in routeModes.keys) {
      trip.routes[mode] = walkRoute(mode, hazards: ['a'], avoids: false);
    }
    trip.errors.clear();
    trip.setMode('fastest'); // any change tells the page
    trip.setMode('walkable');
    trip.commute = [
      commuteOption('a', total: 2100, walk: 360, earliest: true),
      commuteOption('b', total: 2700, walk: 600, kind: 'mrt3'),
      commuteOption('c', total: 3000, walk: 900, kind: 'uv_express'),
    ];
    trip.commuteMode = trip.mode;
    await tester.pump(const Duration(milliseconds: 100));
    return trip;
  }

  testWidgets('the page fits at each stage of a trip, on small phones and at large text', (tester) async {
    await fitsEveryPhone(
      tester,
      page,
      after: (tester) async {
        plugins.geo.emit(fixAt(14.5547, 121.0244));
        await tester.pump(const Duration(milliseconds: 100)); // the traffic panel
        final trip = await planTrip(tester); // the walking card
        await trip.toCommute();
        await tester.pump(const Duration(milliseconds: 100)); // the ride options
        trip.start();
        plugins.geo.emit(fixAt(14.5545, 121.0240));
        await tester.pump(const Duration(milliseconds: 100)); // the nav bar
      },
    );
    await leave(tester);
  });

  testWidgets('the page fits the chips that ask for the location', (tester) async {
    for (final (serviceOn, permission) in [
      (false, LocationPermission.whileInUse),
      (true, LocationPermission.denied),
      (true, LocationPermission.deniedForever),
    ]) {
      plugins.geo.serviceOn = serviceOn;
      plugins.geo.permission = permission;
      await fitsEveryPhone(tester, page);
    }
    await leave(tester);
  });

  testWidgets('with the keyboard up the chips make way for the search suggestions', (tester) async {
    tester.view.physicalSize = phones.last;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: testTheme(), home: page()));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Report'), findsOneWidget);

    tester.view.viewInsets = const FakeViewPadding(bottom: 300);
    await tester.pump();
    expect(find.text('Report'), findsNothing, reason: 'lifted by the keyboard, it would cover the suggestions');
    expect(find.byType(PlaceSearchBar), findsOneWidget);
    expect(find.byType(CompassChip), findsOneWidget, reason: 'the compass sits at the top, clear of the keyboard');

    tester.view.resetViewInsets();
    await tester.pump();
    expect(find.text('Report'), findsOneWidget);
    await leave(tester);
  });

  testWidgets('on a short phone the ride options scroll, so Start trip can still be pressed', (tester) async {
    tester.view.physicalSize = phones.first;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: testTheme(), home: page()));
    await tester.pump(const Duration(milliseconds: 100));
    plugins.geo.emit(fixAt(14.5547, 121.0244));
    final trip = await planTrip(tester);
    await trip.toCommute();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.ensureVisible(find.text('Start trip'));
    await tester.pump();
    await tester.tap(find.text('Start trip'));
    expect(trip.started, isTrue);
    await leave(tester);
  });

  testWidgets('the screen stays on from Start until the trip ends, or the user arrives', (tester) async {
    tester.view.physicalSize = phones.last;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: testTheme(), home: page()));
    await tester.pump(const Duration(milliseconds: 100));
    final trip = await planTrip(tester);
    await trip.toCommute();
    expect(plugins.wakelock.calls, isEmpty);

    trip.start();
    await tester.pump();
    expect(plugins.wakelock.on, isTrue);
    trip.end();
    await tester.pump();
    expect(plugins.wakelock.on, isFalse);

    trip.start();
    await tester.pump();
    expect(plugins.wakelock.on, isTrue);
    for (var leg = 0; leg < 3; leg++) {
      plugins.geo.emit(fixAt(14.553, 121.021)); // at the destination: one more leg done per fix
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(trip.progress?.arrived, isTrue);
    expect(plugins.wakelock.on, isFalse, reason: 'arrived: nothing left to watch');
    await leave(tester);
  });
}
