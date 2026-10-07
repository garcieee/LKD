import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/search/place_search.dart';
import 'package:lakad/features/search/search_bar.dart';
import 'package:lakad/state/recent_places.dart';
import 'package:lakad/state/trip_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

Place place(String label) => Place.fromJson({'label': label, 'lat': 14.5547, 'lng': 121.0244});

void main() {
  late TripState trip;
  late PlaceSearch search;

  Future<void> mount(WidgetTester tester, SearchFn fn) async {
    trip = TripState((from, to, mode) async => throw UnimplementedError('no route fetch without a start'));
    search = PlaceSearch(fn, delay: const Duration(milliseconds: 10));
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: PlaceSearchBar(search: search, trip: trip))),
    );
  }

  testWidgets('typing lists places, picking one sets the destination and hides the list', (tester) async {
    await mount(tester, (text, near) async => [place('Ayala Triangle Gardens'), place('Ayala Museum')]);
    await tester.enterText(find.byType(TextField), 'Ayala');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump();
    expect(find.text('Ayala Museum'), findsOneWidget);

    await tester.tap(find.text('Ayala Museum'));
    await tester.pump();
    expect(trip.destination!.label, 'Ayala Museum');
    expect(find.byType(ListTile), findsNothing, reason: 'the list closes once a place is picked');
    expect(find.widgetWithText(TextField, 'Ayala Museum'), findsOneWidget);
  });

  testWidgets('clear empties the field and the destination', (tester) async {
    await mount(tester, (text, near) async => [place('Ayala Museum')]);
    await tester.enterText(find.byType(TextField), 'Ayala');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump();
    await tester.tap(find.text('Ayala Museum'));
    await tester.pump();

    await tester.tap(find.byTooltip('Clear'));
    await tester.pump();
    expect(trip.destination, isNull);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
    expect(find.byTooltip('Clear'), findsNothing);
  });

  testWidgets('says so when nothing matches, and shows a search error', (tester) async {
    await mount(tester, (text, near) async => text == 'zzz' ? throw const ApiException('Place search is busy.') : []);
    await tester.enterText(find.byType(TextField), 'Nowhere');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump();
    expect(find.text('No places found in Makati.'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'zzz');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump();
    expect(find.text('Place search is busy.'), findsOneWidget);
  });

  testWidgets('a destination set from elsewhere (a transit hub) shows in the field, and clearing it empties it', (tester) async {
    await mount(tester, (text, near) async => []);
    trip.setDestination(const Place(label: 'Washington Terminal', lat: 14.55856, lng: 121.01033));
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, 'Washington Terminal');
    expect(find.byTooltip('Clear'), findsOneWidget);
    expect(find.byType(ListTile), findsNothing, reason: 'no suggestions for a chosen place');

    trip.clear();
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
  });

  testWidgets('a picked place is remembered and listed under the empty field', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final recents = RecentPlaces();
    trip = TripState((from, to, mode) async => throw UnimplementedError('no route fetch without a start'));
    search = PlaceSearch((text, near) async => [place('Ayala Museum')], delay: const Duration(milliseconds: 10));
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: PlaceSearchBar(search: search, trip: trip, recents: recents))),
    );
    expect(find.text('Recent'), findsNothing);

    await tester.enterText(find.byType(TextField), 'Ayala');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump();
    await tester.tap(find.text('Ayala Museum'));
    await tester.pump();
    await tester.tap(find.byTooltip('Clear'));
    await tester.pump();
    expect(find.text('Recent'), findsOneWidget);
    expect(find.text('Ayala Museum'), findsOneWidget);

    final reloaded = RecentPlaces();
    await tester.runAsync(reloaded.load);
    expect(reloaded.places.map((p) => p.label), ['Ayala Museum'], reason: 'kept between launches');
  });
}
