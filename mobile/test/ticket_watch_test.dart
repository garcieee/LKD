// The clock behind the notices: when the phone asks about the tickets, when it stops, who is told what, and that it
// asks for notification permission only once. Time is the test's: `pump` moves it.
import 'dart:ui' show AppLifecycleState;

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/state/my_tickets.dart';
import 'package:lakad/state/ticket_watch.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ticket_fixtures.dart';

const _s = Duration(seconds: 1);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  late List<Report> served;
  Object? failing;
  var asked = 0; // calls to the server
  late MyTickets mine;
  late TicketWatch watch;
  late List<List<String>> onScreen; // the ticket ids each banner was about

  // A phone with the app open and [kept] tickets from earlier runs.
  Future<void> open(WidgetTester tester, {List<Report> kept = const [], FakeNotifier? notifier}) async {
    served = kept;
    failing = null;
    asked = 0;
    onScreen = [];
    SharedPreferences.setMockInitialValues({});
    final earlier = MyTickets((_) async => const []);
    for (final t in kept) {
      await earlier.add(t);
    }
    mine = MyTickets((_) async {
      asked++;
      if (failing != null) throw failing!;
      return served;
    });
    watch = TicketWatch(mine, notifier: notifier, onNews: (u) => onScreen.add([for (final x in u) x.now.id]));
    await watch.start();
  }

  Future<void> wait(WidgetTester tester, Duration d) async {
    await tester.pump(d);
    await tester.pump(); // the ask that fired settles
  }

  testWidgets('with no ticket it never asks; the first one sent starts the clock', (tester) async {
    await open(tester);
    await wait(tester, const Duration(minutes: 10));
    expect(asked, 0);
    await mine.add(ticket('a'));
    await wait(tester, _s * 29);
    expect(asked, 0);
    await wait(tester, _s * 2);
    expect(asked, 1);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('with the app open it asks at once, then every 30 seconds', (tester) async {
    await open(tester, kept: [ticket('a')]);
    expect(asked, 1, reason: 'on start: the baseline and the menu dot');
    await wait(tester, _s * 31);
    expect(asked, 2);
    await wait(tester, _s * 30);
    expect(asked, 3);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('an offline phone backs off: twice the wait each time, five minutes at most, and 30 seconds once it works', (tester) async {
    await open(tester, kept: [ticket('a')]); // asked at 0 s, and it worked
    var now = 0; // seconds since then
    Future<void> at(int seconds, int asks, String why) async {
      await wait(tester, _s * (seconds - now));
      now = seconds;
      expect(asked, asks, reason: '$why (at $seconds s)');
    }

    failing = const ApiException("Can't reach the server.");
    await at(29, 1, 'every 30 seconds');
    await at(31, 2, 'asked at 30: it failed');
    await at(89, 2, 'so it waits a minute');
    await at(91, 3, 'asked at 90: failed');
    await at(209, 3, 'then two minutes');
    await at(211, 4, 'asked at 210: failed');
    await at(449, 4, 'then four');
    await at(451, 5, 'asked at 450: failed');
    await at(749, 5, 'then five minutes, which is the most');
    await at(751, 6, 'asked at 750: failed');
    await at(1049, 6, 'five minutes again');
    failing = null;
    await at(1051, 7, 'asked at 1050: it worked');
    await at(1079, 7, 'and it is back to 30 seconds');
    await at(1081, 8, 'asked at 1080');
    expect(onScreen, isEmpty, reason: 'offline is silent');
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('the first answer is a baseline; a later change reaches the screen once, however long it waits', (tester) async {
    await open(tester, kept: [ticket('a')]);
    served = [ticket('a', status: 'verified', updated: 20)];
    await wait(tester, _s * 31);
    expect(onScreen, [
      ['a'],
    ]);
    await wait(tester, const Duration(minutes: 5));
    expect(onScreen, hasLength(1));
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('the app on the screen shows a banner and sends no notification', (tester) async {
    final tray = FakeNotifier();
    await open(tester, kept: [ticket('a')], notifier: tray);
    served = [ticket('a', status: 'verified', updated: 20)];
    await wait(tester, _s * 31);
    expect(onScreen, hasLength(1));
    expect(tray.shown, isEmpty);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('the notification shade or a permission dialog (inactive) is not leaving the app', (tester) async {
    await open(tester, kept: [ticket('a')]);
    await watch.lifecycle(AppLifecycleState.inactive);
    await wait(tester, _s * 31);
    expect(asked, 2);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('away without notifications it asks no more; back on the screen it asks at once and shows what it finds', (tester) async {
    await open(tester, kept: [ticket('a')]);
    await watch.lifecycle(AppLifecycleState.paused);
    await wait(tester, const Duration(minutes: 30));
    expect(asked, 1);
    served = [ticket('a', status: 'verified', updated: 20)];
    await watch.lifecycle(AppLifecycleState.resumed);
    await wait(tester, Duration.zero);
    expect(asked, 2, reason: 'at once, not after the wait');
    expect(onScreen, [
      ['a'],
    ]);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('away with notifications allowed it asks every 2 minutes, and a change is a notification, not a banner', (tester) async {
    final tray = FakeNotifier();
    await open(tester, kept: [ticket('3f2a9c01aa')], notifier: tray);
    await watch.lifecycle(AppLifecycleState.hidden);
    served = [ticket('3f2a9c01aa', status: 'verified', updated: 20)];
    await wait(tester, _s * 119);
    expect(asked, 1);
    await wait(tester, _s * 2);
    expect(asked, 2);
    expect(tray.shown, [(title: 'LKD-3F2A9C', body: 'Confirmed by the city', payload: '3f2a9c01aa')]);
    expect(onScreen, isEmpty);
    await wait(tester, const Duration(minutes: 5));
    expect(tray.shown, hasLength(1), reason: 'not again');
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('several tickets changed while away are one notification that opens the list', (tester) async {
    final tray = FakeNotifier();
    await open(tester, kept: [ticket('a'), ticket('b', created: 5)], notifier: tray);
    await watch.lifecycle(AppLifecycleState.paused);
    served = [ticket('a', status: 'verified', updated: 20), ticket('b', created: 5, status: 'fixed', updated: 21)];
    await wait(tester, _s * 121);
    expect(tray.shown, [(title: 'My tickets', body: '2 of your tickets were updated', payload: '')]);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('coming back takes the notifications down and asks at once', (tester) async {
    final tray = FakeNotifier();
    await open(tester, kept: [ticket('a')], notifier: tray);
    await watch.lifecycle(AppLifecycleState.paused);
    await watch.lifecycle(AppLifecycleState.resumed);
    await wait(tester, Duration.zero);
    expect(tray.cleared, 1);
    expect(asked, 2);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('away and not allowed to show notifications (turned off in Settings): no asking at all', (tester) async {
    final tray = FakeNotifier(permitted: false);
    await open(tester, kept: [ticket('a')], notifier: tray);
    await watch.lifecycle(AppLifecycleState.paused);
    await wait(tester, const Duration(minutes: 30));
    expect(asked, 1);
    expect(tray.shown, isEmpty);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('allowing notifications in Settings while away is noticed the next time the app leaves', (tester) async {
    final tray = FakeNotifier(permitted: false);
    await open(tester, kept: [ticket('a')], notifier: tray);
    await watch.lifecycle(AppLifecycleState.paused);
    await watch.lifecycle(AppLifecycleState.resumed);
    tray.permitted = true;
    await watch.lifecycle(AppLifecycleState.paused);
    await wait(tester, _s * 121);
    expect(asked, 3);
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('it asks the phone for notification permission once, ever', (tester) async {
    final tray = FakeNotifier();
    await open(tester, notifier: tray);
    await watch.askOnce();
    await watch.askOnce();
    expect(tray.asked, 1);
    final later = TicketWatch(mine, notifier: tray, onNews: (_) {}); // the app opened again
    await later.askOnce();
    expect(tray.asked, 1, reason: 'Android asks a person once or twice at most: asking again is no use');
    await TicketWatch(mine, onNews: (_) {}).askOnce(); // no tray: nothing to ask, nothing thrown
    watch.dispose(); // the test's clock must be empty when it ends
  });

  testWidgets('a watch that is disposed stops asking', (tester) async {
    await open(tester, kept: [ticket('a')]);
    watch.dispose();
    await wait(tester, const Duration(minutes: 10));
    expect(asked, 1);
    watch.dispose(); // the test's clock must be empty when it ends
  });
}
