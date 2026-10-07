// The notice on the map page: when the city changes a ticket the person sent, a banner names it and says what
// happened; a tap opens that ticket's card (or the list, for several). It stays out of the way of the menu and the
// camera. The map is a blank box and the notification tray a fake (test_support.dart, ticket_fixtures.dart).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/report/report_screen.dart';
import 'package:lakad/features/tickets/ticket_notifier.dart';
import 'package:lakad/map/map_view.dart';
import 'package:lakad/state/my_tickets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'test_support.dart';
import 'ticket_fixtures.dart';

void main() {
  setUpAll(loadRoboto);
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    Plugins(); // the stand-ins for the camera, GPS and map plugins
  });

  // What the city says right now, which the phone's next ask gets.
  late List<Report> served;

  // The tickets this phone sent in this run (so a change to them is a notice), and a server that answers [served].
  Future<MyTickets> mineWith(List<Report> sent) async {
    served = sent;
    final mine = MyTickets((_) async => served);
    for (final t in sent) {
      await mine.add(t);
    }
    return mine;
  }

  Future<void> openMap(WidgetTester tester, MyTickets mine, {TicketNotifier? notifier}) async {
    await tester.pumpWidget(
      MaterialApp(theme: testTheme(), home: MapView(mapboxToken: 'pk.test', myTickets: mine, notifier: notifier)),
    );
    await tester.pump(const Duration(milliseconds: 100)); // it asks the server at once
    await tester.pump(const Duration(milliseconds: 750)); // and the banner slides in
  }

  // The Report button, and the camera screen once its route has come in.
  Future<void> openCamera(WidgetTester tester) async {
    await tester.tap(find.byTooltip('Report'));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(ReportScreen), findsOneWidget, reason: 'the camera screen is up');
  }

  // Back from the camera: [sent] is the ticket it filed, if any.
  Future<void> closeCamera(WidgetTester tester, [Report? sent]) async {
    tester.state<NavigatorState>(find.byType(Navigator)).pop(sent);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 750));
  }

  testWidgets('a ticket the city changed shows a banner naming it, and a tap opens its card', (tester) async {
    final mine = await mineWith([ticket('3f2a9c01aa')]);
    served = [ticket('3f2a9c01aa', status: 'verified', updated: 20)];
    await openMap(tester, mine);

    expect(find.text('LKD-3F2A9C: Confirmed by the city'), findsOneWidget);
    expect(find.text('View'), findsOneWidget);
    expect(find.byTooltip('Menu: my tickets, 1 with news'), findsOneWidget, reason: 'the red dot stays until they look');

    await tester.tap(find.text('LKD-3F2A9C: Confirmed by the city'));
    await tester.pumpAndSettle();
    expect(find.text('Confirmed by the city.'), findsOneWidget, reason: "the ticket's card, in plain words");
    expect(find.text('LKD-3F2A9C'), findsOneWidget);
    expect(mine.news, 0, reason: 'they read it: the dot goes');
    await leave(tester);
  });

  testWidgets('the View button opens the card too, and the banner goes after a few seconds', (tester) async {
    final mine = await mineWith([ticket('3f2a9c01aa')]);
    served = [ticket('3f2a9c01aa', status: 'rejected', updated: 20, more: {'rejected_note': 'A duplicate.'})];
    await openMap(tester, mine);
    expect(find.text('LKD-3F2A9C: Not accepted · note from the city'), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(SnackBar), findsNothing, reason: 'it must not stay on the map for good, with its button');
    await leave(tester);

    await mine.refresh();
    served = [ticket('3f2a9c01aa', status: 'open', updated: 30, more: {'rejected_note': 'A duplicate.'})];
    await openMap(tester, mine);
    await tester.tap(find.text('View'));
    await tester.pumpAndSettle();
    expect(find.text('Received. Waiting for the city to review it.'), findsOneWidget);
    await leave(tester);
  });

  testWidgets('several tickets changed at once are one banner with a count, and it opens the list', (tester) async {
    final mine = await mineWith([ticket('a'), ticket('b', created: 5)]);
    served = [ticket('a', status: 'verified', updated: 20), ticket('b', created: 5, status: 'fixed', updated: 21)];
    await openMap(tester, mine);

    expect(find.text('2 of your tickets were updated'), findsOneWidget);
    expect(find.byType(SnackBar), findsOneWidget);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.text('My tickets'), findsOneWidget);
    expect(find.text('NEW'), findsNWidgets(2));
    await leave(tester);
  });

  testWidgets('nothing changed, nothing said; and what the phone kept from the last run is not announced on opening', (tester) async {
    final earlier = await mineWith([ticket('a')]); // the last run
    served = [ticket('a', status: 'verified', updated: 20)]; // the city answered while the app was closed
    final mine = MyTickets((_) async => served); // the app opens again
    await openMap(tester, mine);
    expect(find.byType(SnackBar), findsNothing);
    expect(find.byTooltip('Menu: my tickets, 1 with news'), findsOneWidget, reason: 'the dot says it');
    earlier.dispose();
    await leave(tester);
  });

  testWidgets('with the menu open there is no banner: the list shows what changed', (tester) async {
    final mine = await mineWith([ticket('a')]);
    await openMap(tester, mine);
    served = [ticket('a', status: 'verified', updated: 20)];
    await tester.tap(find.byTooltip('Menu: my tickets'));
    await tester.pumpAndSettle(); // opening the menu asks the server
    expect(find.text('NEW'), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);

    await tester.tapAt(const Offset(780, 300)); // close the menu
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsNothing, reason: 'they have looked: the change is not announced after the fact');
    await leave(tester);
  });

  testWidgets('over the camera the news waits, and shows when they are back', (tester) async {
    final mine = await mineWith([ticket('3f2a9c01aa')]);
    await openMap(tester, mine);
    await openCamera(tester);

    served = [ticket('3f2a9c01aa', status: 'assigned', updated: 20, more: {'handler': 'Ana Reyes'})];
    await mine.refresh();
    await tester.pump(const Duration(milliseconds: 750));
    expect(find.byType(SnackBar), findsNothing);

    await closeCamera(tester); // back without sending anything
    expect(find.text('LKD-3F2A9C: Assigned to Ana Reyes'), findsOneWidget);
    await leave(tester);
  });

  testWidgets('news they looked at while the camera was up is not announced when they are back', (tester) async {
    final mine = await mineWith([ticket('a')]);
    await openMap(tester, mine);
    await openCamera(tester);
    served = [ticket('a', status: 'verified', updated: 20)];
    await mine.refresh();
    await mine.markSeen(); // however it came about: they have seen it
    await closeCamera(tester);
    expect(find.byType(SnackBar), findsNothing);
    await leave(tester);
  });

  testWidgets('sending a ticket asks to show notifications once; sending nothing asks nothing', (tester) async {
    final mine = await mineWith(const []);
    final tray = FakeNotifier();
    await openMap(tester, mine, notifier: tray);
    await openCamera(tester);
    await closeCamera(tester); // closed the camera without sending
    expect(tray.asked, 0, reason: 'not before the person has a ticket');

    for (var n = 0; n < 2; n++) {
      await openCamera(tester);
      await closeCamera(tester, ticket('sent$n', created: n));
    }
    expect(mine.tickets, hasLength(2));
    expect(tray.asked, 1, reason: 'once, ever: with the first ticket');
    await leave(tester);
  });

  testWidgets('tapping a notification opens that ticket, or the list for several', (tester) async {
    final mine = await mineWith([ticket('3f2a9c01aa')]);
    final tray = FakeNotifier();
    await openMap(tester, mine, notifier: tray);
    expect(tray.tap, isNotNull);

    tray.tap!('3f2a9c01aa');
    await tester.pumpAndSettle();
    expect(find.text('LKD-3F2A9C'), findsOneWidget);
    expect(find.text('Received. Waiting for the city to review it.'), findsOneWidget);
    tester.state<NavigatorState>(find.byType(Navigator)).pop(); // close the card
    await tester.pumpAndSettle();

    tray.tap!('');
    await tester.pumpAndSettle();
    expect(find.text('My tickets'), findsOneWidget);
    await leave(tester);
  });

  testWidgets('sent to the background the page stops banners and posts a notification instead; back, it takes it down', (tester) async {
    final mine = await mineWith([ticket('3f2a9c01aa')]);
    final tray = FakeNotifier();
    await openMap(tester, mine, notifier: tray);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump();

    served = [ticket('3f2a9c01aa', status: 'verified', updated: 20)];
    await tester.pump(const Duration(minutes: 2, seconds: 1));
    await tester.pump();
    expect(tray.shown, [(title: 'LKD-3F2A9C', body: 'Confirmed by the city', payload: '3f2a9c01aa')]);
    expect(find.byType(SnackBar), findsNothing);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(tray.cleared, 1);
    await leave(tester);
  });

  testWidgets('the banner fits small phones and large text, with a long handler name', (tester) async {
    late MyTickets mine;
    Widget page() {
      served = [
        ticket('3f2a9c01aa', status: 'assigned', updated: 20, more: {'handler': 'Liza Mendoza · Drainage and Flood Control'}),
      ];
      mine = MyTickets((_) async => served);
      return MapView(mapboxToken: 'pk.test', myTickets: mine);
    }

    await fitsEveryPhone(
      tester,
      page,
      after: (tester) async {
        await mine.add(ticket('3f2a9c01aa'));
        await mine.refresh();
        await tester.pump(const Duration(milliseconds: 800));
        expect(find.textContaining('Assigned to Liza Mendoza'), findsOneWidget);
      },
    );
    await leave(tester);
  });
}
