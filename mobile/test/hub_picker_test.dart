import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/transfer_walk/hub_picker.dart';

Hub hub(String name, double lat, double lng, {bool terminal = true, int err = 60}) => Hub.fromJson({
  'id': name.toLowerCase().replaceAll(' ', '-'),
  'name': name,
  'kind': terminal ? 'terminal' : 'stop',
  'modes': ['jeepney'],
  'lat': lat,
  'lng': lng,
  'error_m': err,
});

final hubs = [
  hub('Washington Terminal', 14.55856, 121.01033),
  hub('One Ayala', 14.55048, 121.02817),
  hub('Landmark Terminal', 14.55253, 121.02334),
  hub('Dian', 14.55555, 121.00264, terminal: false),
];
const ayala = (lat: 14.5547, lng: 121.0244);

void main() {
  group('nearestHubs', () {
    test('sorts terminals by distance from the user and leaves bus stops out by default', () {
      final rows = nearestHubs(hubs, ayala);
      expect(rows.map((r) => r.hub.name), ['Landmark Terminal', 'One Ayala', 'Washington Terminal']);
      expect(rows.first.metres, closeTo(268, 5));
      expect(rows.map((r) => r.metres!), orderedEquals(rows.map((r) => r.metres!).toList()..sort()));
    });

    test('includes stops on request, and caps the list', () {
      expect(nearestHubs(hubs, ayala, withStops: true).length, 4);
      expect(nearestHubs(hubs, ayala, limit: 2).length, 2);
    });

    test('without a position it is alphabetical and has no distances', () {
      final rows = nearestHubs(hubs, null);
      expect(rows.map((r) => r.hub.name), ['Landmark Terminal', 'One Ayala', 'Washington Terminal']);
      expect(rows.every((r) => r.metres == null), isTrue);
    });
  });

  testWidgets('the hub card names the hub, its distance and its doubt, and Walk here hands it back', (tester) async {
    Hub? walked;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showHubSheet(context, hubs[0], from: ayala, onWalk: (h) => walked = h),
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Washington Terminal'), findsOneWidget);
    expect(find.text('Terminal · Jeepney'), findsOneWidget);
    expect(find.textContaining('from you'), findsOneWidget);
    expect(find.text('Position estimated from the study map, about ±60 m.'), findsOneWidget);

    await tester.tap(find.text('Walk here'));
    await tester.pumpAndSettle();
    expect(walked!.name, 'Washington Terminal');
    expect(find.text('Walk here'), findsNothing, reason: 'the card closes');
  });

  testWidgets('the nearby list says when there is no location, and opens a hub on tap', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showNearbyHubs(context, hubs, onWalk: (_) {}),
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Location is off, so these are listed by name.'), findsOneWidget);
    expect(find.text('Dian'), findsNothing, reason: 'a bus stop is not a terminal');

    await tester.tap(find.text('One Ayala'));
    await tester.pumpAndSettle();
    expect(find.text('Walk here'), findsOneWidget);
  });
}
