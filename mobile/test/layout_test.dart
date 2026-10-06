// The map page's cards and sheets, and the SOS overlay, at a small and a common phone size and at 1x, 1.5x and 2x
// text: none may overflow (test_support.dart has the sizes). The page as a whole is in map_view_test.dart, the report
// screen in report_screen_test.dart.
//
// ponytail: the ride options are 35 to 50 minutes. Hour-long ones (a "1 h 5 min" next to "21 min walk") still overflow
// the option's top line on a 320 px phone at 2x text. Upgrade: let that line wrap.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/navigate/compass_chip.dart';
import 'package:lakad/features/navigate/nav_bar.dart';
import 'package:lakad/features/report/category_picker.dart';
import 'package:lakad/features/report/sos_overlay.dart';
import 'package:lakad/features/search/place_search.dart';
import 'package:lakad/features/search/search_bar.dart';
import 'package:lakad/features/transfer_walk/hub_picker.dart';
import 'package:lakad/features/transfer_walk/mode_toggle.dart';
import 'package:lakad/features/transfer_walk/route_card.dart';
import 'package:lakad/layers/hubs_layer.dart';
import 'package:lakad/map/pin_chip.dart';
import 'package:lakad/state/layers_state.dart';
import 'package:lakad/state/trip_state.dart';
import 'package:lakad/widgets/layer_sheet.dart';

import 'test_support.dart';

Hub hub(
  String name, {
  String kind = 'terminal',
  List<String> modes = const ['jeepney', 'uv_express', 'city_bus', 'p2p_bus'],
}) => Hub.fromJson({
  'id': name,
  'name': name,
  'kind': kind,
  'modes': modes,
  'lat': 14.5547,
  'lng': 121.0244,
  'error_m': 120,
});

// Where the map page puts a card: along the bottom, 14 px in from the sides, up to 420 wide.
Widget onTheMap(Widget card) => Scaffold(
  body: Align(
    alignment: Alignment.bottomCenter,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 54),
      child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 420), child: card),
    ),
  ),
);

// A page with a button that opens a bottom sheet, and the tap that does.
Widget opens(void Function(BuildContext) show) => Scaffold(
  body: Builder(
    builder: (context) => Center(
      child: TextButton(onPressed: () => show(context), child: const Text('open')),
    ),
  ),
);
Future<void> tapOpen(WidgetTester tester) async {
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<TripState> tripWith(WidgetTester tester, {List<CommuteOption> options = const []}) async {
  final trip = TripState(
    (from, to, mode) async => walkRoute(mode, hazards: ['a', 'b', 'c'], avoids: false),
    (from, to, mode) async => options,
  );
  trip.setDestination(destination, from: here);
  await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  return trip;
}

void main() {
  setUpAll(loadRoboto);

  testWidgets('the route card compares the walks, then lists the rides', (tester) async {
    final trip = await tripWith(
      tester,
      options: [
        commuteOption('a', total: 2100, walk: 360, earliest: true),
        commuteOption('b', total: 2700, walk: 600, kind: 'mrt3'),
        commuteOption('c', total: 3000, walk: 900, kind: 'uv_express'),
      ],
    );
    await fitsEveryPhone(tester, () => onTheMap(RouteCard(trip: trip)));
    await tester.runAsync(trip.toCommute);
    await fitsEveryPhone(tester, () => onTheMap(RouteCard(trip: trip)));
    trip.dispose();
  });

  testWidgets('the route card fits a failed route and its long message', (tester) async {
    final trip = TripState(
      (from, to, mode) async =>
          throw const ApiException('No walking route found between those points. Try a closer place.'),
    );
    trip.setDestination(destination, from: here);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await fitsEveryPhone(tester, () => onTheMap(RouteCard(trip: trip)));
    trip.dispose();
  });

  testWidgets('the nav bar fits each stage of a trip', (tester) async {
    final trip = await tripWith(tester, options: [commuteOption('a', total: 2100, walk: 360)]);
    await tester.runAsync(trip.toCommute);
    trip.start();
    Widget bar() => onTheMap(NavBar(trip: trip));
    await fitsEveryPhone(tester, bar); // before the first fix
    trip.update(14.5540, 121.0230); // on the ride
    await fitsEveryPhone(tester, bar);
    trip.update(14.5600, 121.0300); // far from the line
    await fitsEveryPhone(tester, bar);
    trip.update(14.553, 121.021); // there
    await fitsEveryPhone(tester, bar);
    trip.dispose();
  });

  testWidgets('the mode toggle and the compass chip fit', (tester) async {
    final trip = await tripWith(tester);
    await fitsEveryPhone(
      tester,
      () => Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(14),
          child: ModeToggle(trip: trip),
        ),
      ),
    );
    final bearing = ValueNotifier(315.0), following = ValueNotifier(true);
    await fitsEveryPhone(
      tester,
      () => Scaffold(
        body: Align(
          alignment: Alignment.bottomRight,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: CompassChip(bearing: bearing, following: following),
          ),
        ),
      ),
    );
    trip.dispose();
  });

  testWidgets('the search field fits five long suggestions, and an error', (tester) async {
    final trip = TripState((from, to, mode) async => throw UnimplementedError());
    Future<void> typeIn(WidgetTester tester) async {
      await tester.enterText(find.byType(TextField), 'Green');
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump();
    }

    Widget field(PlaceSearch search) => Scaffold(
      body: SafeArea(
        minimum: const EdgeInsets.all(14),
        child: Align(
          alignment: Alignment.topCenter,
          child: PlaceSearchBar(search: search, trip: trip),
        ),
      ),
    );
    final found = PlaceSearch(
      (text, near) async => [
        for (var i = 0; i < 5; i++) Place(label: '${destination.label} $i', lat: 14.55, lng: 121.02),
      ],
      delay: const Duration(milliseconds: 10),
    );
    await fitsEveryPhone(tester, () => field(found), after: typeIn);
    final broken = PlaceSearch(
      (text, near) async =>
          throw const ApiException('Place search is unavailable. Try again in a minute, or check the connection.'),
      delay: const Duration(milliseconds: 10),
    );
    await fitsEveryPhone(tester, () => field(broken), after: typeIn);
    found.dispose();
    broken.dispose();
  });

  testWidgets('a hub card and the list of hubs near you fit, and Walk here can be reached', (tester) async {
    final station = hub('Taft Avenue Station (MRT-3)', kind: 'station', modes: ['mrt3', 'city_bus', 'jeepney']);
    final hubs = [
      station,
      hub(terminal),
      hub(farTerminal),
      hub('Ayala Avenue-Paseo de Roxas'),
      hub('San Lorenzo Place Terminal'),
    ];
    await fitsEveryPhone(
      tester,
      () => opens((c) => showHubSheet(c, station, from: here, onWalk: (_) {})),
      after: tapOpen,
    );
    await fitsEveryPhone(
      tester,
      () => opens((c) => showNearbyHubs(c, hubs, from: here, onWalk: (_) {})),
      after: tapOpen,
    );

    // Largest text on a small phone: the card is taller than the sheet, and still scrolls to its button.
    tester.view.physicalSize = phones.first;
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearAllTestValues);
    Hub? walked;
    await tester.pumpWidget(const SizedBox()); // drop the last page, sheet and all
    await tester.pumpWidget(
      MaterialApp(
        theme: testTheme(),
        home: opens((c) => showHubSheet(c, station, from: here, onWalk: (h) => walked = h)),
      ),
    );
    await tapOpen(tester);
    await tester.ensureVisible(find.text('Walk here'));
    await tester.pump();
    await tester.tap(find.text('Walk here'));
    expect(walked, station);
  });

  testWidgets('a report pin card fits a long note', (tester) async {
    final report = Report.fromJson({
      'id': 'x',
      'category': 'blocked_tactile_paving',
      'lat': 14.55,
      'lng': 121.02,
      'heading': 10,
      'note': 'A very long note about the paving. ' * 20,
      'photo_url': '/photos/x.jpg',
      'status': 'assigned',
      'created_at': '2026-10-06T07:31:05+00:00',
    });
    await fitsEveryPhone(tester, () => opens((c) => showReportSheet(c, report)), after: tapOpen);
  });

  testWidgets('the traffic panel fits, with the transit legend', (tester) async {
    final layers = LayersState();
    await fitsEveryPhone(
      tester,
      () => onTheMap(LayerSheet(layers: layers, legend: [for (final e in hubIcons.values) e])),
    );
  });

  testWidgets('the category picker fits with a PWD barrier chosen', (tester) async {
    await fitsEveryPhone(
      tester,
      () => Scaffold(
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: CategoryPicker(value: 'blocked_tactile_paving', onChanged: (_) {}),
        ),
      ),
    );
  });

  testWidgets('the SOS banner, guide and shutter fit while recording and on the cancel target', (tester) async {
    final slide = ValueNotifier(0.0);
    final recorded = ValueNotifier(const Duration(seconds: 12));
    Widget overlay() => Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        minimum: const EdgeInsets.all(14),
        child: Stack(
          children: [
            // The report screen's top column leaves room for its close button.
            Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 52),
                child: SosBanner(cancel: slide, recorded: recorded),
              ),
            ),
            Align(
              alignment: Alignment.bottomCenter,
              child: SizedBox(
                width: 240,
                height: sosGuideHeight,
                child: Stack(
                  alignment: Alignment.bottomCenter,
                  children: [
                    Positioned.fill(child: SosGuide(cancel: slide, reduceMotion: true)),
                    SosShutter(
                      enabled: true,
                      busy: false,
                      armed: true,
                      cancelling: slide.value >= 1,
                      onTap: () {},
                      onSosStart: () {},
                      onSosMove: (_) {},
                      onSosEnd: (_) {},
                      onSosAbort: () {},
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
    await fitsEveryPhone(tester, overlay);
    slide.value = 1;
    await fitsEveryPhone(tester, overlay);
  });
}
