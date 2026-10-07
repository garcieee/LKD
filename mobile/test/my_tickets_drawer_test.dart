// The menu: what each status says in plain words, the notes the city left, the list at small phone sizes and large
// text, and the burger button on the map page.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/tickets/my_tickets_drawer.dart';
import 'package:lakad/features/tickets/ticket_text.dart';
import 'package:lakad/map/map_view.dart';
import 'package:lakad/state/my_tickets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'test_support.dart';

Report ticket(
  String id, {
  String status = 'open',
  String category = 'pothole',
  int created = 0,
  int? updated,
  Map<String, dynamic> more = const {},
}) {
  String at(int min) => DateTime.utc(2026, 10, 7, 7, min).toIso8601String();
  return Report.fromJson({
    'id': id,
    'category': category,
    'lat': 14.5547,
    'lng': 121.0244,
    'heading': null,
    'note': '',
    'photo_url': category == 'sos' ? '' : '/photos/$id.jpg',
    'status': status,
    'created_at': at(created),
    'updated_at': at(updated ?? created),
    ...more,
  });
}

void main() {
  setUpAll(loadRoboto);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('what a ticket says', () {
    test('each status in plain words, with the handler when there is one', () {
      expect(ticketMessage(ticket('a')), 'Received. Waiting for the city to review it.');
      expect(ticketMessage(ticket('a', status: 'verified')), 'Confirmed by the city.');
      expect(ticketMessage(ticket('a', status: 'assigned')), 'Assigned to a handler.');
      expect(ticketMessage(ticket('a', status: 'assigned', more: {'handler': 'Ana Reyes'})), 'Assigned to Ana Reyes.');
      expect(ticketMessage(ticket('a', status: 'fixed')), 'Resolved.');
      expect(ticketMessage(ticket('a', status: 'fixed', more: {'handler': 'Ana Reyes'})), 'Resolved. Handled by Ana Reyes.');
      expect(ticketMessage(ticket('a', status: 'rejected')), 'Not accepted.');
    });

    test('the reason for a rejection shows only while it is rejected', () {
      final more = {'rejected_note': 'A duplicate of an earlier report.'};
      expect(ticketNotes(ticket('a', status: 'rejected', more: more)).single.text, 'A duplicate of an earlier report.');
      expect(ticketNotes(ticket('a', status: 'rejected', more: more)).single.bad, isTrue);
      expect(ticketNotes(ticket('a', status: 'open', more: more)), isEmpty, reason: 'reopened: the old reason is gone');
    });

    test('the note left on confirming is kept for every later status, and the note on the fix shows once fixed', () {
      final more = {'verified_note': 'A crew has been told.', 'resolved_note': 'Filled and sealed.'};
      expect(ticketNotes(ticket('a', status: 'verified', more: more)).map((n) => n.text), ['A crew has been told.']);
      expect(ticketNotes(ticket('a', status: 'assigned', more: more)).map((n) => n.text), ['A crew has been told.']);
      expect(ticketNotes(ticket('a', status: 'fixed', more: more)).map((n) => n.text), [
        'A crew has been told.',
        'Filled and sealed.',
      ]);
      expect(ticketNotes(ticket('a', status: 'open', more: more)), isEmpty);
    });

    test('empty or spaces-only notes are not shown', () {
      expect(ticketNotes(ticket('a', status: 'fixed', more: {'verified_note': '  ', 'resolved_note': ''})), isEmpty);
    });
  });

  group('the list', () {
    Future<MyTickets> mineWith(List<Report> tickets, {FetchMine? fetch}) async {
      final mine = MyTickets(fetch ?? (_) async => tickets);
      for (final t in tickets) {
        await mine.add(t);
      }
      return mine;
    }

    Widget drawerPage(MyTickets mine, {void Function(Report)? onOpen}) => Scaffold(
      drawer: MyTicketsDrawer(mine: mine, onOpen: onOpen ?? (_) {}),
      body: const SizedBox(),
    );

    Future<void> openDrawer(WidgetTester tester) async {
      tester.state<ScaffoldState>(find.byType(Scaffold)).openDrawer();
      await tester.pumpAndSettle();
    }

    testWidgets('says so when nothing has been sent yet', (tester) async {
      final mine = MyTickets((_) async => const []);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine)));
      await openDrawer(tester);
      expect(find.text('My tickets'), findsOneWidget);
      expect(find.text('No tickets yet'), findsOneWidget);
    });

    testWidgets('shows each ticket with its ID, status, plain-words line and the notes', (tester) async {
      final mine = await mineWith([
        ticket('3f2a9c01aa', status: 'rejected', created: 5, more: {'rejected_note': 'A duplicate of an earlier report.'}),
        ticket('b7e1ffaa00', status: 'fixed', category: 'open_manhole', created: 1, more: {
          'handler': 'Ana Reyes · Public Works',
          'verified_note': 'A crew has been told.',
          'resolved_note': 'Filled and sealed.',
        }),
      ]);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine)));
      await openDrawer(tester);

      expect(find.text('LKD-3F2A9C'), findsOneWidget);
      expect(find.text('Pothole'), findsOneWidget);
      expect(find.text('Rejected'), findsOneWidget);
      expect(find.text('Not accepted.'), findsOneWidget);
      expect(find.text('WHY IT WAS NOT ACCEPTED'), findsOneWidget);
      expect(find.text('A duplicate of an earlier report.'), findsOneWidget);

      expect(find.text('LKD-B7E1FF'), findsOneWidget);
      expect(find.text('Resolved. Handled by Ana Reyes · Public Works.'), findsOneWidget);
      expect(find.text('A crew has been told.'), findsOneWidget);
      expect(find.text('Filled and sealed.'), findsOneWidget);
    });

    testWidgets('marks a ticket with news, and the mark goes once they have looked', (tester) async {
      final mine = MyTickets((_) async => [ticket('a', status: 'verified', updated: 30)]);
      await mine.add(ticket('a'));
      await mine.refresh();
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine)));
      await openDrawer(tester);
      expect(find.text('NEW'), findsOneWidget);
      await mine.markSeen();
      await tester.pump();
      expect(find.text('NEW'), findsNothing);
    });

    testWidgets('a tap on a ticket opens it', (tester) async {
      final mine = await mineWith([ticket('abc123def')]);
      Report? opened;
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine, onOpen: (t) => opened = t)));
      await openDrawer(tester);
      await tester.tap(find.text('Pothole'));
      expect(opened?.id, 'abc123def');
    });

    testWidgets('pulling down asks the server again', (tester) async {
      var asked = 0;
      final mine = await mineWith([ticket('a')], fetch: (_) async {
        asked++;
        return [ticket('a', status: 'verified', updated: 20)];
      });
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine)));
      await openDrawer(tester);
      await tester.fling(find.text('Pothole'), const Offset(0, 300), 1000);
      await tester.pumpAndSettle();
      expect(asked, 1);
      expect(find.text('Confirmed by the city.'), findsOneWidget);
    });

    testWidgets('says when it could not update, and still shows what it knew', (tester) async {
      final mine = MyTickets((_) async => throw const ApiException("Can't reach the server."));
      await mine.add(ticket('a', status: 'verified'));
      await mine.refresh();
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: drawerPage(mine)));
      await openDrawer(tester);
      expect(find.textContaining("Couldn't update: Can't reach the server."), findsOneWidget);
      expect(find.text('Confirmed by the city.'), findsOneWidget);
    });

    testWidgets('fits small phones and large text with long notes, an SOS and a long handler', (tester) async {
      final long = 'A long note from the city that has to wrap onto several lines. ' * 4;
      final mine = await mineWith([
        ticket('aaaaaa1', status: 'rejected', category: 'blocked_tactile_paving', created: 9, more: {'rejected_note': long}),
        ticket('bbbbbb2', status: 'fixed', category: 'sos', created: 8, more: {
          'handler': 'Liza Mendoza · Drainage and Flood Control',
          'verified_note': long,
          'resolved_note': long,
        }),
        ticket('cccccc3', status: 'open', category: 'missing_ramp', created: 7),
      ]);
      await mine.refresh();
      await fitsEveryPhone(tester, () => drawerPage(mine), after: openDrawer);
    });
  });

  group('the burger button on the map page', () {
    setUp(Plugins.new); // the stand-ins for the camera, GPS and map plugins

    testWidgets('opens the menu with the tickets this phone filed', (tester) async {
      final mine = MyTickets((_) async => const []);
      await mine.add(ticket('abc123def', status: 'verified'));
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: MapView(mapboxToken: 'pk.test', myTickets: mine)));
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byTooltip('Menu: my tickets'));
      await tester.pumpAndSettle();
      expect(find.text('My tickets'), findsOneWidget);
      expect(find.text('LKD-ABC123'), findsOneWidget);
      expect(find.text('Confirmed by the city.'), findsOneWidget);
      await leave(tester);
    });

    testWidgets('wears a dot, and says how many, while a ticket has news', (tester) async {
      final mine = MyTickets((_) async => [ticket('a', status: 'rejected', updated: 30, more: {'rejected_note': 'Duplicate.'})]);
      await mine.add(ticket('a'));
      await mine.refresh();
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: MapView(mapboxToken: 'pk.test', myTickets: mine)));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byTooltip('Menu: my tickets, 1 with news'), findsOneWidget);
      expect(tester.widget<Badge>(find.byType(Badge)).isLabelVisible, isTrue);

      await tester.tap(find.byTooltip('Menu: my tickets, 1 with news'));
      await tester.pumpAndSettle();
      expect(find.text('NEW'), findsOneWidget, reason: 'while the menu is open it shows which one');
      await tester.tapAt(const Offset(780, 300)); // the scrim: close the menu
      await tester.pumpAndSettle();
      expect(mine.news, 0, reason: 'closing it means they looked');
      expect(find.byTooltip('Menu: my tickets'), findsOneWidget);
      await leave(tester);
    });

    testWidgets('an edge swipe pans the map instead of opening the menu', (tester) async {
      final mine = MyTickets((_) async => const []);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: MapView(mapboxToken: 'pk.test', myTickets: mine)));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.dragFrom(const Offset(2, 300), const Offset(200, 0));
      await tester.pumpAndSettle();
      expect(find.text('My tickets'), findsNothing);
      await leave(tester);
    });
  });
}
